"""
Test Mini-Batch K-Means as an incremental clustering alternative.

Compare:
1. UMAP + HDBSCAN (current)
2. Mini-Batch K-Means in 768D (truly incremental, no model persistence)

Goal: Assess if simpler approach can work for our use case.
"""

import logging
import time
import numpy as np
from typing import Dict, Any
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import (
    silhouette_score,
    adjusted_rand_score,
)
import umap
from sklearn.cluster import HDBSCAN

from google.cloud import firestore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_embeddings_from_firestore(db: firestore.Client) -> tuple[np.ndarray, list]:
    """Load all chunk embeddings from Firestore."""
    logger.info("Loading embeddings from Firestore...")

    chunks_ref = db.collection('kb_items')
    docs = list(chunks_ref.stream())

    embeddings = []
    chunk_ids = []

    for doc in docs:
        data = doc.to_dict()
        if 'embedding' in data and data['embedding']:
            embeddings.append(data['embedding'])
            chunk_ids.append(doc.id)

    embeddings_array = np.array(embeddings)
    logger.info(f"Loaded {len(embeddings_array)} embeddings")

    return embeddings_array, chunk_ids


def cluster_with_umap_hdbscan(embeddings: np.ndarray) -> Dict[str, Any]:
    """Baseline: UMAP + HDBSCAN."""
    logger.info("\n" + "="*80)
    logger.info("APPROACH 1: UMAP + HDBSCAN (Current)")
    logger.info("="*80)

    start_time = time.time()

    umap_model = umap.UMAP(
        n_components=5,
        n_neighbors=15,
        metric='cosine',
        random_state=42,
        min_dist=0.0
    )
    embeddings_reduced = umap_model.fit_transform(embeddings)

    clusterer = HDBSCAN(
        metric='euclidean',
        min_cluster_size=10,
        min_samples=2,
        cluster_selection_epsilon=0.1
    )
    labels = clusterer.fit_predict(embeddings_reduced)

    total_time = time.time() - start_time

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = np.sum(labels == -1)

    mask = labels != -1
    silhouette = None
    if n_clusters >= 2 and np.sum(mask) > 0:
        try:
            silhouette = silhouette_score(embeddings[mask], labels[mask], metric='cosine')
        except Exception:
            pass

    cluster_sizes = [np.sum(labels == i) for i in set(labels) if i != -1]

    logger.info(f"\nResults:")
    logger.info(f"   Clusters: {n_clusters}")
    logger.info(f"   Noise points: {n_noise}")
    logger.info(f"   Silhouette: {silhouette:.4f}" if silhouette else "   Silhouette: N/A")
    logger.info(f"   Cluster sizes: min={min(cluster_sizes)}, max={max(cluster_sizes)}, "
                f"mean={np.mean(cluster_sizes):.1f}")
    logger.info(f"   Time: {total_time:.2f}s")
    logger.info(f"   Model persistence: ~2.7 MB UMAP model")

    return {
        'method': 'UMAP+HDBSCAN',
        'labels': labels,
        'n_clusters': n_clusters,
        'n_noise': n_noise,
        'silhouette_score': silhouette,
        'time': total_time,
        'cluster_sizes': cluster_sizes
    }


def cluster_with_minibatch_kmeans(embeddings: np.ndarray, n_clusters: int = None) -> Dict[str, Any]:
    """Alternative: Mini-Batch K-Means in 768D."""
    logger.info("\n" + "="*80)
    logger.info("APPROACH 2: Mini-Batch K-Means in 768D (Truly Incremental)")
    logger.info("="*80)

    start_time = time.time()

    # Auto-calculate k if not provided
    if n_clusters is None:
        n_clusters = int(np.sqrt(embeddings.shape[0]))
        logger.info(f"Auto-calculated n_clusters: {n_clusters}")

    # Normalize embeddings for better clustering with cosine similarity
    from sklearn.preprocessing import normalize
    normalized_embeddings = normalize(embeddings, norm='l2')

    clusterer = MiniBatchKMeans(
        n_clusters=n_clusters,
        batch_size=100,
        random_state=42,
        n_init=10
    )
    labels = clusterer.fit_predict(normalized_embeddings)

    total_time = time.time() - start_time

    # No noise points in K-Means (all points assigned)
    n_noise = 0
    unique_labels = set(labels)

    silhouette = None
    if len(unique_labels) >= 2:
        try:
            silhouette = silhouette_score(embeddings, labels, metric='cosine')
        except Exception:
            pass

    cluster_sizes = [np.sum(labels == i) for i in unique_labels]

    # Calculate centroid storage size
    centroid_size_kb = (n_clusters * embeddings.shape[1] * 4) / 1024  # 4 bytes per float32

    logger.info(f"\nResults:")
    logger.info(f"   Clusters: {n_clusters}")
    logger.info(f"   Noise points: {n_noise} (K-Means assigns all points)")
    logger.info(f"   Silhouette: {silhouette:.4f}" if silhouette else "   Silhouette: N/A")
    logger.info(f"   Cluster sizes: min={min(cluster_sizes)}, max={max(cluster_sizes)}, "
                f"mean={np.mean(cluster_sizes):.1f}")
    logger.info(f"   Time: {total_time:.2f}s")
    logger.info(f"   Model persistence: {centroid_size_kb:.1f} KB (centroids only)")
    logger.info(f"   Incremental updates: YES (partial_fit)")

    return {
        'method': 'MiniBatch K-Means',
        'labels': labels,
        'n_clusters': n_clusters,
        'n_noise': n_noise,
        'silhouette_score': silhouette,
        'time': total_time,
        'cluster_sizes': cluster_sizes,
        'centroid_size_kb': centroid_size_kb,
        'clusterer': clusterer
    }


def simulate_incremental_update(
    clusterer: MiniBatchKMeans,
    all_embeddings: np.ndarray,
    new_chunk_ids: list,
    split_idx: int = 800
) -> Dict[str, Any]:
    """Simulate adding new chunks incrementally."""
    logger.info("\n" + "="*80)
    logger.info("SIMULATING INCREMENTAL UPDATE (10 new chunks)")
    logger.info("="*80)

    from sklearn.preprocessing import normalize

    # Split: initial 800, delta 35
    initial_embeddings = all_embeddings[:split_idx]
    delta_embeddings = all_embeddings[split_idx:]

    logger.info(f"Initial: {len(initial_embeddings)} chunks")
    logger.info(f"Delta: {len(delta_embeddings)} new chunks")

    # Fit on initial
    start_time = time.time()
    normalized_initial = normalize(initial_embeddings, norm='l2')
    clusterer.fit(normalized_initial)
    initial_time = time.time() - start_time

    logger.info(f"Initial clustering: {initial_time:.2f}s")

    # Incremental update with new chunks
    start_time = time.time()
    normalized_delta = normalize(delta_embeddings, norm='l2')

    # Partial fit (updates centroids)
    clusterer.partial_fit(normalized_delta)

    # Predict (assign to clusters)
    delta_labels = clusterer.predict(normalized_delta)

    delta_time = time.time() - start_time

    logger.info(f"Delta processing: {delta_time:.3f}s for {len(delta_embeddings)} chunks")
    logger.info(f"  partial_fit time: ~{delta_time/2:.3f}s")
    logger.info(f"  predict time: ~{delta_time/2:.3f}s")

    # Log assignments
    from collections import Counter
    assignment_counts = Counter(delta_labels)
    logger.info(f"\nDelta chunk assignments:")
    for cluster_id, count in sorted(assignment_counts.items()):
        logger.info(f"  Cluster {cluster_id}: {count} chunks")

    return {
        'initial_time': initial_time,
        'delta_time': delta_time,
        'delta_labels': delta_labels
    }


def compare_results(umap_result: Dict[str, Any], kmeans_result: Dict[str, Any]):
    """Compare UMAP vs Mini-Batch K-Means."""
    logger.info("\n" + "="*80)
    logger.info("COMPARISON ANALYSIS")
    logger.info("="*80)

    # Cluster agreement
    ari = adjusted_rand_score(umap_result['labels'], kmeans_result['labels'])

    logger.info(f"\n1. CLUSTER AGREEMENT:")
    logger.info(f"   Adjusted Rand Index (ARI): {ari:.4f}")
    logger.info(f"   (Note: Different algorithms, so low ARI expected)")

    logger.info(f"\n2. CLUSTER COUNTS:")
    logger.info(f"   UMAP+HDBSCAN: {umap_result['n_clusters']} clusters (density-based, auto)")
    logger.info(f"   Mini-Batch K-Means: {kmeans_result['n_clusters']} clusters (pre-specified)")

    logger.info(f"\n3. NOISE DETECTION:")
    logger.info(f"   UMAP+HDBSCAN: {umap_result['n_noise']} noise points ✅")
    logger.info(f"   Mini-Batch K-Means: {kmeans_result['n_noise']} noise points (all assigned)")

    logger.info(f"\n4. QUALITY METRICS:")
    if umap_result['silhouette_score'] and kmeans_result['silhouette_score']:
        logger.info(f"   UMAP silhouette: {umap_result['silhouette_score']:.4f}")
        logger.info(f"   K-Means silhouette: {kmeans_result['silhouette_score']:.4f}")
        diff = kmeans_result['silhouette_score'] - umap_result['silhouette_score']
        logger.info(f"   Difference: {diff:+.4f}")

    logger.info(f"\n5. PERFORMANCE:")
    logger.info(f"   UMAP time: {umap_result['time']:.2f}s")
    logger.info(f"   K-Means time: {kmeans_result['time']:.2f}s")
    speedup = umap_result['time'] / kmeans_result['time']
    logger.info(f"   Speedup: {speedup:.1f}x faster")

    logger.info(f"\n6. MODEL PERSISTENCE:")
    logger.info(f"   UMAP: ~2700 KB (UMAP model)")
    logger.info(f"   K-Means: ~{kmeans_result['centroid_size_kb']:.1f} KB (centroids only)")
    storage_reduction = 2700 / kmeans_result['centroid_size_kb']
    logger.info(f"   Storage reduction: {storage_reduction:.1f}x smaller")

    logger.info(f"\n7. INCREMENTAL UPDATES:")
    logger.info(f"   UMAP: Approximate (nearest neighbor heuristic)")
    logger.info(f"   K-Means: True incremental (partial_fit)")

    # Decision
    logger.info("\n" + "="*80)
    logger.info("DECISION FRAMEWORK")
    logger.info("="*80)

    logger.info("\n✅ Choose Mini-Batch K-Means IF:")
    logger.info("   - Noise detection not critical")
    logger.info("   - Can pre-specify cluster count (~28-40 clusters)")
    logger.info("   - Want true incremental updates")
    logger.info("   - Want minimal storage footprint")
    logger.info("   - Prefer simple, maintainable code")

    logger.info("\n✅ Keep UMAP + HDBSCAN IF:")
    logger.info("   - Noise detection is important (outlier chunks)")
    logger.info("   - Want automatic cluster count determination")
    logger.info("   - Want density-based clustering (varying cluster shapes)")
    logger.info("   - Accept model persistence complexity")
    logger.info("   - Want best clustering quality")

    logger.info("\n" + "="*80)


def main():
    """Run comparison."""
    db = firestore.Client(project='kx-hub', database='(default)')
    embeddings, chunk_ids = load_embeddings_from_firestore(db)

    logger.info(f"\nTesting with {len(embeddings)} chunks, {embeddings.shape[1]}D embeddings")

    # Baseline: UMAP + HDBSCAN
    umap_result = cluster_with_umap_hdbscan(embeddings)

    # Alternative: Mini-Batch K-Means
    # Use same number of clusters as UMAP found for fair comparison
    kmeans_result = cluster_with_minibatch_kmeans(
        embeddings,
        n_clusters=umap_result['n_clusters']
    )

    # Compare
    compare_results(umap_result, kmeans_result)

    # Simulate incremental update
    simulate_incremental_update(
        kmeans_result['clusterer'],
        embeddings,
        chunk_ids,
        split_idx=800
    )


if __name__ == '__main__':
    main()
