"""
Graph generation for knowledge base clustering.

Generates graph.json with nodes (chunks), edges (similarity links),
and cluster metadata for visualization and export.
"""

import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class GraphGenerator:
    """
    Generate graph.json from clustering results.

    Creates a graph representation with:
    - Nodes: Knowledge chunks with cluster assignments
    - Edges: Similarity relationships between chunks
    - Clusters: Metadata about each cluster
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        max_edges_per_node: int = 5
    ):
        """
        Initialize graph generator.

        Args:
            similarity_threshold: Minimum cosine similarity to create edge (default: 0.7)
            max_edges_per_node: Maximum edges per node to limit graph size (default: 5)
        """
        self.similarity_threshold = similarity_threshold
        self.max_edges_per_node = max_edges_per_node

    def generate(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray,
        cluster_labels: np.ndarray
    ) -> Dict[str, Any]:
        """
        Generate complete graph from chunks and clustering results.

        Args:
            chunks: List of chunk documents with metadata
            embeddings: Embedding vectors for chunks
            cluster_labels: Cluster assignments for each chunk

        Returns:
            Graph dictionary with nodes, edges, and clusters
        """
        if len(chunks) != len(embeddings) or len(chunks) != len(cluster_labels):
            raise ValueError(
                f"Length mismatch: {len(chunks)} chunks, {len(embeddings)} embeddings, "
                f"{len(cluster_labels)} labels"
            )

        logger.info(f"Generating graph for {len(chunks)} nodes...")

        # Generate nodes
        nodes = self._generate_nodes(chunks, cluster_labels)

        # Generate edges based on similarity
        edges = self._generate_edges(chunks, embeddings, cluster_labels)

        # Generate cluster metadata
        clusters = self._generate_cluster_metadata(chunks, cluster_labels)

        graph = {
            "nodes": nodes,
            "edges": edges,
            "clusters": clusters,
            "metadata": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_clusters": len(clusters),
                "similarity_threshold": self.similarity_threshold
            }
        }

        logger.info(
            f"Graph generated: {len(nodes)} nodes, {len(edges)} edges, "
            f"{len(clusters)} clusters"
        )

        return graph

    def _generate_nodes(
        self,
        chunks: List[Dict[str, Any]],
        cluster_labels: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Generate node list from chunks."""
        nodes = []

        for chunk, label in zip(chunks, cluster_labels):
            # Determine cluster ID
            if label == -1:
                cluster_id = "noise"
            else:
                cluster_id = f"cluster-{label}"

            node = {
                "id": chunk.get('id', 'unknown'),
                "cluster_id": cluster_id,
                "title": chunk.get('title', '')[:100],  # Truncate for graph
                "source": chunk.get('source', ''),
                "tags": chunk.get('tags', []),
            }

            # Optional: Add authors if present
            if 'authors' in chunk and chunk['authors']:
                node['authors'] = chunk['authors']

            nodes.append(node)

        return nodes

    def _generate_edges(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray,
        cluster_labels: np.ndarray
    ) -> List[Dict[str, Any]]:
        """
        Generate edges based on embedding similarity.

        Only creates edges for chunks above similarity threshold,
        and limits edges per node to prevent graph explosion.
        """
        edges = []

        # Compute similarity matrix
        logger.info("Computing similarity matrix for edges...")
        similarity_matrix = cosine_similarity(embeddings)

        # For each chunk, find top-k most similar chunks
        for i, chunk_i in enumerate(chunks):
            chunk_id_i = chunk_i.get('id', 'unknown')

            # Get similarity scores for this chunk with all others
            similarities = similarity_matrix[i]

            # Find indices of chunks above threshold (excluding self)
            similar_indices = np.where(
                (similarities >= self.similarity_threshold) & (np.arange(len(similarities)) != i)
            )[0]

            # Sort by similarity descending and take top-k
            similar_indices = similar_indices[np.argsort(-similarities[similar_indices])]
            similar_indices = similar_indices[:self.max_edges_per_node]

            # Create edges
            for j in similar_indices:
                chunk_id_j = chunks[j].get('id', 'unknown')
                weight = float(similarities[j])

                # Only add edge if not already added in reverse direction
                # (to avoid duplicate edges in undirected graph)
                if chunk_id_i < chunk_id_j:
                    edges.append({
                        "source": chunk_id_i,
                        "target": chunk_id_j,
                        "weight": weight
                    })

        return edges

    def _generate_cluster_metadata(
        self,
        chunks: List[Dict[str, Any]],
        cluster_labels: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Generate metadata for each cluster."""
        clusters = []

        # Group chunks by cluster
        unique_labels = set(cluster_labels)

        for label in unique_labels:
            if label == -1:
                # Skip noise cluster in metadata
                continue

            cluster_id = f"cluster-{label}"

            # Get all chunks in this cluster
            cluster_mask = cluster_labels == label
            cluster_size = int(np.sum(cluster_mask))

            # Get most common tags in cluster (for label suggestion)
            all_tags = []
            for chunk in np.array(chunks)[cluster_mask]:
                if 'tags' in chunk and chunk['tags']:
                    all_tags.extend(chunk['tags'])

            # Count tag occurrences
            tag_counts = {}
            for tag in all_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            # Get top 3 tags as label suggestion
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            suggested_label = ", ".join([tag for tag, count in top_tags]) if top_tags else f"Cluster {label}"

            cluster_meta = {
                "id": cluster_id,
                "label": suggested_label,
                "size": cluster_size,
                "top_tags": [tag for tag, count in top_tags]
            }

            clusters.append(cluster_meta)

        # Sort by size descending
        clusters.sort(key=lambda x: x['size'], reverse=True)

        return clusters

    def save_to_file(self, graph: Dict[str, Any], output_path: str):
        """
        Save graph to JSON file.

        Args:
            graph: Graph dictionary
            output_path: Path to output JSON file
        """
        logger.info(f"Saving graph to {output_path}...")

        with open(output_path, 'w') as f:
            json.dump(graph, f, indent=2)

        logger.info(f"Graph saved successfully to {output_path}")

    @staticmethod
    def save_to_storage(graph: Dict[str, Any], bucket_name: str, blob_name: str = 'graphs/graph.json'):
        """
        Save graph to Google Cloud Storage.

        Args:
            graph: Graph dictionary
            bucket_name: GCS bucket name
            blob_name: Blob path within bucket (default: 'graphs/graph.json')
        """
        from google.cloud import storage

        logger.info(f"Uploading graph to gs://{bucket_name}/{blob_name}...")

        # Convert graph to JSON string
        graph_json = json.dumps(graph, indent=2)

        # Upload to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        blob.upload_from_string(
            graph_json,
            content_type='application/json'
        )

        logger.info(f"Graph uploaded successfully to gs://{bucket_name}/{blob_name}")
