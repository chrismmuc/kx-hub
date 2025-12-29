"""
Extended PoC: Test Random Projection with different dimensions.

Compare UMAP (5D) vs Random Projection at multiple dimensions:
- 5D (same as UMAP)
- 10D, 15D, 20D, 30D, 45D (JL lemma)

Goal: Find optimal dimension for Random Projection that matches UMAP quality.
"""

import logging
import time
import numpy as np
from typing import Dict, Any, List
from sklearn.random_projection import GaussianRandomProjection
from sklearn.cluster import HDBSCAN
from sklearn.metrics import (
    silhouette_score,
    adjusted_rand_score,
    adjusted_mutual_info_score
)
import umap

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


def cluster_with_umap(embeddings: np.ndarray, n_components: int = 5) -> Dict[str, Any]:
    """Cluster using UMAP + HDBSCAN."""
    start_time = time.time()

    umap_model = umap.UMAP(
        n_components=n_components,
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

    return {
        'method': 'UMAP',
        'n_components': n_components,
        'labels': labels,
        'n_clusters': n_clusters,
        'n_noise': n_noise,
        'silhouette_score': silhouette,
        'time': total_time
    }


def cluster_with_random_projection(embeddings: np.ndarray, n_components: int) -> Dict[str, Any]:
    """Cluster using Random Projection + HDBSCAN."""
    start_time = time.time()

    projector = GaussianRandomProjection(
        n_components=n_components,
        random_state=42
    )
    embeddings_reduced = projector.fit_transform(embeddings)

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

    return {
        'method': 'RandomProj',
        'n_components': n_components,
        'labels': labels,
        'n_clusters': n_clusters,
        'n_noise': n_noise,
        'silhouette_score': silhouette,
        'time': total_time
    }


def compare_to_baseline(baseline: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Compare result against UMAP baseline."""
    ari = adjusted_rand_score(baseline['labels'], result['labels'])
    ami = adjusted_mutual_info_score(baseline['labels'], result['labels'])

    same = np.sum(baseline['labels'] == result['labels'])
    total = len(baseline['labels'])
    agreement_rate = same / total * 100

    silh_diff = None
    silh_pct = None
    if baseline['silhouette_score'] and result['silhouette_score']:
        silh_diff = result['silhouette_score'] - baseline['silhouette_score']
        silh_pct = abs(silh_diff) / baseline['silhouette_score'] * 100

    return {
        'ari': ari,
        'ami': ami,
        'agreement_rate': agreement_rate,
        'silh_diff': silh_diff,
        'silh_pct': silh_pct
    }


def main():
    """Run dimension comparison analysis."""
    db = firestore.Client(project='kx-hub', database='(default)')
    embeddings, chunk_ids = load_embeddings_from_firestore(db)

    logger.info(f"\nTesting with {len(embeddings)} chunks, {embeddings.shape[1]}D embeddings")
    logger.info("="*80)

    # Baseline: UMAP 5D
    logger.info("\n📊 BASELINE: UMAP (5D)")
    umap_result = cluster_with_umap(embeddings, n_components=5)
    logger.info(f"   Clusters: {umap_result['n_clusters']}, "
                f"Noise: {umap_result['n_noise']}, "
                f"Silhouette: {umap_result['silhouette_score']:.4f}, "
                f"Time: {umap_result['time']:.2f}s")

    # Test Random Projection at different dimensions
    dimensions = [5, 10, 15, 20, 30, 45]
    results = []

    logger.info("\n📊 RANDOM PROJECTION TESTS:")
    for n_comp in dimensions:
        logger.info(f"\n   Testing {n_comp}D...")
        rp_result = cluster_with_random_projection(embeddings, n_components=n_comp)
        comparison = compare_to_baseline(umap_result, rp_result)

        logger.info(f"      Clusters: {rp_result['n_clusters']}, "
                    f"Noise: {rp_result['n_noise']}, "
                    f"Silhouette: {rp_result['silhouette_score']:.4f}")
        logger.info(f"      Agreement: {comparison['agreement_rate']:.1f}%, "
                    f"ARI: {comparison['ari']:.4f}, "
                    f"Time: {rp_result['time']:.2f}s")

        results.append({
            'result': rp_result,
            'comparison': comparison
        })

    # Summary table
    logger.info("\n" + "="*80)
    logger.info("SUMMARY TABLE")
    logger.info("="*80)
    logger.info(f"{'Method':<15} {'Dim':<5} {'Clusters':<10} {'Noise':<7} "
                f"{'Silh':<8} {'Agreement':<12} {'ARI':<8} {'Time':<8}")
    logger.info("-"*80)

    # UMAP baseline
    logger.info(f"{'UMAP (baseline)':<15} {'5':<5} "
                f"{umap_result['n_clusters']:<10} "
                f"{umap_result['n_noise']:<7} "
                f"{umap_result['silhouette_score']:.4f}   "
                f"{'100.0%':<12} "
                f"{'1.0000':<8} "
                f"{umap_result['time']:.2f}s")

    # Random Projection results
    for i, dim in enumerate(dimensions):
        r = results[i]['result']
        c = results[i]['comparison']
        logger.info(f"{'Random Proj':<15} {dim:<5} "
                    f"{r['n_clusters']:<10} "
                    f"{r['n_noise']:<7} "
                    f"{r['silhouette_score']:.4f}   "
                    f"{c['agreement_rate']:>5.1f}%      "
                    f"{c['ari']:.4f}   "
                    f"{r['time']:.2f}s")

    # Find best Random Projection configuration
    logger.info("\n" + "="*80)
    logger.info("BEST RANDOM PROJECTION CONFIGURATION")
    logger.info("="*80)

    best_idx = max(range(len(results)), key=lambda i: results[i]['comparison']['ari'])
    best_result = results[best_idx]['result']
    best_comparison = results[best_idx]['comparison']

    logger.info(f"\nBest: {best_result['n_components']}D Random Projection")
    logger.info(f"   ARI: {best_comparison['ari']:.4f}")
    logger.info(f"   Agreement: {best_comparison['agreement_rate']:.1f}%")
    logger.info(f"   Clusters: {best_result['n_clusters']} (UMAP: {umap_result['n_clusters']})")
    logger.info(f"   Silhouette: {best_result['silhouette_score']:.4f} "
                f"(UMAP: {umap_result['silhouette_score']:.4f})")

    # Final assessment
    logger.info("\n" + "="*80)
    logger.info("FINAL ASSESSMENT")
    logger.info("="*80)

    if best_comparison['agreement_rate'] >= 80 and best_comparison['ari'] >= 0.7:
        logger.info("✅ Random Projection meets quality criteria!")
        logger.info(f"   Recommended: {best_result['n_components']}D")
    elif best_comparison['agreement_rate'] >= 60 and best_comparison['ari'] >= 0.5:
        logger.info("⚠️  Random Projection shows moderate agreement")
        logger.info("   Consider as alternative if model persistence is critical concern")
    else:
        logger.info("❌ Random Projection does not meet quality criteria")
        logger.info("   RECOMMENDATION: Keep UMAP approach")
        logger.info("\n   Key issues:")
        logger.info(f"      - Low cluster agreement: {best_comparison['agreement_rate']:.1f}% (need 80%)")
        logger.info(f"      - Low ARI: {best_comparison['ari']:.4f} (need 0.7)")
        logger.info(f"      - Large noise difference: {abs(best_result['n_noise'] - umap_result['n_noise'])} points")

    logger.info("="*80)


if __name__ == '__main__':
    main()
