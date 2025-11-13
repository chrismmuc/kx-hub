"""
Proof of Concept: Compare UMAP vs Random Projection for clustering.

This script compares clustering quality and performance between:
1. UMAP + HDBSCAN (current approach)
2. Random Projection + HDBSCAN (alternative)

Goal: Determine if Random Projection can replace UMAP to eliminate model persistence.
"""

import logging
import sys
import time
import numpy as np
from typing import Dict, Any
from sklearn.random_projection import GaussianRandomProjection
from sklearn.cluster import HDBSCAN
from sklearn.metrics import (
    silhouette_score,
    adjusted_rand_score,
    adjusted_mutual_info_score
)
import umap

# Add project root to path
sys.path.insert(0, '/Users/christian/dev/kx-hub')

from src.clustering.clusterer import SemanticClusterer
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
    logger.info(f"Loaded {len(embeddings_array)} embeddings with shape {embeddings_array.shape}")

    return embeddings_array, chunk_ids


def cluster_with_umap_hdbscan(
    embeddings: np.ndarray,
    n_components: int = 5,
    min_cluster_size: int = 10,
    random_state: int = 42
) -> Dict[str, Any]:
    """Cluster using UMAP + HDBSCAN (current approach)."""
    logger.info("\n" + "="*60)
    logger.info("APPROACH 1: UMAP + HDBSCAN (Current)")
    logger.info("="*60)

    start_time = time.time()

    # UMAP dimensionality reduction
    logger.info(f"Applying UMAP: {embeddings.shape[1]}D → {n_components}D...")
    umap_start = time.time()
    umap_model = umap.UMAP(
        n_components=n_components,
        n_neighbors=15,
        metric='cosine',
        random_state=random_state,
        min_dist=0.0
    )
    embeddings_reduced = umap_model.fit_transform(embeddings)
    umap_time = time.time() - umap_start
    logger.info(f"UMAP complete in {umap_time:.2f}s")

    # HDBSCAN clustering
    logger.info("Running HDBSCAN...")
    hdbscan_start = time.time()
    clusterer = HDBSCAN(
        metric='euclidean',
        min_cluster_size=min_cluster_size,
        min_samples=2,
        cluster_selection_epsilon=0.1
    )
    labels = clusterer.fit_predict(embeddings_reduced)
    hdbscan_time = time.time() - hdbscan_start
    logger.info(f"HDBSCAN complete in {hdbscan_time:.2f}s")

    total_time = time.time() - start_time

    # Compute statistics
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = np.sum(labels == -1)

    # Silhouette score (exclude noise)
    mask = labels != -1
    silhouette = None
    if n_clusters >= 2 and np.sum(mask) > 0:
        try:
            silhouette = silhouette_score(
                embeddings[mask],
                labels[mask],
                metric='cosine'
            )
        except Exception as e:
            logger.warning(f"Failed to compute silhouette: {e}")

    # Cluster size statistics
    cluster_sizes = [np.sum(labels == i) for i in set(labels) if i != -1]

    results = {
        'labels': labels,
        'embeddings_reduced': embeddings_reduced,
        'n_clusters': n_clusters,
        'n_noise': n_noise,
        'silhouette_score': silhouette,
        'min_cluster_size': min(cluster_sizes) if cluster_sizes else 0,
        'max_cluster_size': max(cluster_sizes) if cluster_sizes else 0,
        'mean_cluster_size': np.mean(cluster_sizes) if cluster_sizes else 0,
        'total_time': total_time,
        'umap_time': umap_time,
        'hdbscan_time': hdbscan_time,
        'model': umap_model,
        'clusterer': clusterer
    }

    logger.info(f"\nResults:")
    logger.info(f"  Clusters: {n_clusters}")
    logger.info(f"  Noise points: {n_noise}")
    logger.info(f"  Silhouette score: {silhouette:.4f}" if silhouette else "  Silhouette score: N/A")
    logger.info(f"  Cluster sizes: min={results['min_cluster_size']}, "
                f"max={results['max_cluster_size']}, mean={results['mean_cluster_size']:.1f}")
    logger.info(f"  Total time: {total_time:.2f}s")

    return results


def cluster_with_random_projection_hdbscan(
    embeddings: np.ndarray,
    n_components: int = None,
    min_cluster_size: int = 10,
    random_state: int = 42
) -> Dict[str, Any]:
    """Cluster using Random Projection + HDBSCAN (alternative)."""
    logger.info("\n" + "="*60)
    logger.info("APPROACH 2: Random Projection + HDBSCAN (Alternative)")
    logger.info("="*60)

    start_time = time.time()

    # Calculate target dimension using Johnson-Lindenstrauss lemma
    n_samples = embeddings.shape[0]
    if n_components is None:
        n_components = int(np.log(n_samples) ** 2)
        logger.info(f"Auto-calculated n_components from JL lemma: {n_components}")

    # Random Projection dimensionality reduction
    logger.info(f"Applying Random Projection: {embeddings.shape[1]}D → {n_components}D...")
    rp_start = time.time()
    projector = GaussianRandomProjection(
        n_components=n_components,
        random_state=random_state
    )
    embeddings_reduced = projector.fit_transform(embeddings)
    rp_time = time.time() - rp_start
    logger.info(f"Random Projection complete in {rp_time:.2f}s")

    # HDBSCAN clustering
    logger.info("Running HDBSCAN...")
    hdbscan_start = time.time()
    clusterer = HDBSCAN(
        metric='euclidean',
        min_cluster_size=min_cluster_size,
        min_samples=2,
        cluster_selection_epsilon=0.1
    )
    labels = clusterer.fit_predict(embeddings_reduced)
    hdbscan_time = time.time() - hdbscan_start
    logger.info(f"HDBSCAN complete in {hdbscan_time:.2f}s")

    total_time = time.time() - start_time

    # Compute statistics
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = np.sum(labels == -1)

    # Silhouette score (exclude noise)
    mask = labels != -1
    silhouette = None
    if n_clusters >= 2 and np.sum(mask) > 0:
        try:
            silhouette = silhouette_score(
                embeddings[mask],
                labels[mask],
                metric='cosine'
            )
        except Exception as e:
            logger.warning(f"Failed to compute silhouette: {e}")

    # Cluster size statistics
    cluster_sizes = [np.sum(labels == i) for i in set(labels) if i != -1]

    results = {
        'labels': labels,
        'embeddings_reduced': embeddings_reduced,
        'n_clusters': n_clusters,
        'n_noise': n_noise,
        'silhouette_score': silhouette,
        'min_cluster_size': min(cluster_sizes) if cluster_sizes else 0,
        'max_cluster_size': max(cluster_sizes) if cluster_sizes else 0,
        'mean_cluster_size': np.mean(cluster_sizes) if cluster_sizes else 0,
        'total_time': total_time,
        'rp_time': rp_time,
        'hdbscan_time': hdbscan_time,
        'projector': projector,
        'clusterer': clusterer,
        'n_components': n_components
    }

    logger.info(f"\nResults:")
    logger.info(f"  Clusters: {n_clusters}")
    logger.info(f"  Noise points: {n_noise}")
    logger.info(f"  Silhouette score: {silhouette:.4f}" if silhouette else "  Silhouette score: N/A")
    logger.info(f"  Cluster sizes: min={results['min_cluster_size']}, "
                f"max={results['max_cluster_size']}, mean={results['mean_cluster_size']:.1f}")
    logger.info(f"  Total time: {total_time:.2f}s")

    return results


def compare_results(umap_results: Dict[str, Any], rp_results: Dict[str, Any]):
    """Compare clustering results between approaches."""
    logger.info("\n" + "="*60)
    logger.info("COMPARISON ANALYSIS")
    logger.info("="*60)

    # Cluster agreement (Adjusted Rand Index)
    ari = adjusted_rand_score(umap_results['labels'], rp_results['labels'])
    ami = adjusted_mutual_info_score(umap_results['labels'], rp_results['labels'])

    # Calculate percentage of chunks assigned to same cluster
    same_cluster = np.sum(umap_results['labels'] == rp_results['labels'])
    total = len(umap_results['labels'])
    agreement_rate = same_cluster / total * 100

    logger.info(f"\n1. CLUSTER AGREEMENT:")
    logger.info(f"   Adjusted Rand Index (ARI): {ari:.4f}")
    logger.info(f"   Adjusted Mutual Info (AMI): {ami:.4f}")
    logger.info(f"   Direct agreement rate: {agreement_rate:.1f}% ({same_cluster}/{total})")

    logger.info(f"\n2. CLUSTER COUNTS:")
    logger.info(f"   UMAP:       {umap_results['n_clusters']} clusters, {umap_results['n_noise']} noise")
    logger.info(f"   Random Proj: {rp_results['n_clusters']} clusters, {rp_results['n_noise']} noise")
    logger.info(f"   Difference: {abs(umap_results['n_clusters'] - rp_results['n_clusters'])} clusters")

    logger.info(f"\n3. QUALITY METRICS:")
    if umap_results['silhouette_score'] and rp_results['silhouette_score']:
        silh_diff = abs(umap_results['silhouette_score'] - rp_results['silhouette_score'])
        silh_pct = silh_diff / umap_results['silhouette_score'] * 100
        logger.info(f"   UMAP silhouette:       {umap_results['silhouette_score']:.4f}")
        logger.info(f"   Random Proj silhouette: {rp_results['silhouette_score']:.4f}")
        logger.info(f"   Difference: {silh_diff:.4f} ({silh_pct:.1f}%)")

    logger.info(f"\n4. PERFORMANCE:")
    speedup = umap_results['total_time'] / rp_results['total_time']
    logger.info(f"   UMAP total time:        {umap_results['total_time']:.2f}s")
    logger.info(f"   Random Proj total time: {rp_results['total_time']:.2f}s")
    logger.info(f"   Speedup: {speedup:.2f}x {'faster' if speedup > 1 else 'slower'}")

    logger.info(f"\n5. MODEL PERSISTENCE:")
    logger.info(f"   UMAP: ~2.7 MB model file required")
    logger.info(f"   Random Proj: 0 bytes (deterministic with seed) ✅")

    logger.info(f"\n6. DELTA PROCESSING:")
    logger.info(f"   UMAP: Load model (~0.2s first time) + transform")
    logger.info(f"   Random Proj: Regenerate projector (deterministic) + transform")

    # Decision criteria
    logger.info("\n" + "="*60)
    logger.info("DECISION CRITERIA EVALUATION")
    logger.info("="*60)

    criteria_met = []
    criteria_failed = []

    # Criterion 1: Cluster agreement >80%
    if agreement_rate >= 80:
        criteria_met.append(f"✅ Cluster agreement {agreement_rate:.1f}% >= 80%")
    else:
        criteria_failed.append(f"❌ Cluster agreement {agreement_rate:.1f}% < 80%")

    # Criterion 2: ARI >0.7 (strong agreement)
    if ari >= 0.7:
        criteria_met.append(f"✅ ARI {ari:.4f} >= 0.7 (strong agreement)")
    else:
        criteria_failed.append(f"❌ ARI {ari:.4f} < 0.7")

    # Criterion 3: Silhouette within 10%
    if umap_results['silhouette_score'] and rp_results['silhouette_score']:
        if silh_pct <= 10:
            criteria_met.append(f"✅ Silhouette difference {silh_pct:.1f}% <= 10%")
        else:
            criteria_failed.append(f"❌ Silhouette difference {silh_pct:.1f}% > 10%")

    # Criterion 4: Similar noise detection
    noise_diff = abs(umap_results['n_noise'] - rp_results['n_noise'])
    noise_pct = noise_diff / umap_results['n_noise'] * 100 if umap_results['n_noise'] > 0 else 0
    if noise_pct <= 20:
        criteria_met.append(f"✅ Noise detection similar: {noise_diff} points difference ({noise_pct:.1f}%)")
    else:
        criteria_failed.append(f"❌ Noise detection differs: {noise_diff} points difference ({noise_pct:.1f}%)")

    logger.info("\nCriteria Met:")
    for c in criteria_met:
        logger.info(f"  {c}")

    if criteria_failed:
        logger.info("\nCriteria Failed:")
        for c in criteria_failed:
            logger.info(f"  {c}")

    # Final recommendation
    logger.info("\n" + "="*60)
    if len(criteria_met) >= 3:
        logger.info("✅ RECOMMENDATION: Random Projection is a viable alternative!")
        logger.info("   Benefits: Zero model persistence, simpler architecture")
        logger.info("   Trade-offs: Slightly different cluster assignments (but acceptable)")
    else:
        logger.info("❌ RECOMMENDATION: Keep UMAP approach")
        logger.info("   Random Projection does not meet quality criteria")
    logger.info("="*60)

    return {
        'ari': ari,
        'ami': ami,
        'agreement_rate': agreement_rate,
        'criteria_met': len(criteria_met),
        'criteria_failed': len(criteria_failed)
    }


def main():
    """Run comparison analysis."""
    # Initialize Firestore
    db = firestore.Client(project='kx-hub', database='(default)')

    # Load embeddings
    embeddings, chunk_ids = load_embeddings_from_firestore(db)

    logger.info(f"\nLoaded {len(embeddings)} chunks with {embeddings.shape[1]}D embeddings")

    # Run both approaches
    umap_results = cluster_with_umap_hdbscan(
        embeddings,
        n_components=5,
        min_cluster_size=10,
        random_state=42
    )

    rp_results = cluster_with_random_projection_hdbscan(
        embeddings,
        n_components=None,  # Auto-calculate from JL lemma
        min_cluster_size=10,
        random_state=42
    )

    # Compare results
    comparison = compare_results(umap_results, rp_results)

    # Save detailed results
    logger.info(f"\n💾 Saving detailed results to comparison_results.npz...")
    np.savez(
        'comparison_results.npz',
        umap_labels=umap_results['labels'],
        rp_labels=rp_results['labels'],
        umap_embeddings=umap_results['embeddings_reduced'],
        rp_embeddings=rp_results['embeddings_reduced'],
        chunk_ids=chunk_ids,
        comparison=comparison
    )
    logger.info("✅ Results saved!")


if __name__ == '__main__':
    main()
