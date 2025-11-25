# Firestore Vector Indexes
# Story 3.4: Cluster Relationship Discovery via Vector Search

# Vector index for cluster similarity search on centroid embeddings
# Enables efficient k-NN search for related clusters using Firestore find_nearest()
resource "google_firestore_index" "cluster_centroid_vector_index" {
  project    = var.project_id
  database   = "(default)"
  collection = "clusters"

  # Required: __name__ field must come BEFORE vector field
  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  # Vector field configuration (MUST be last in the index)
  fields {
    field_path = "centroid"
    vector_config {
      dimension = 768  # text-embedding-004 produces 768-dim embeddings
      flat {}          # Flat index type (only supported type currently)
    }
  }

  depends_on = [google_project_service.required_apis]
}

# Output the index name for verification
output "cluster_vector_index_name" {
  value       = google_firestore_index.cluster_centroid_vector_index.name
  description = "Name of the Firestore vector index for cluster centroids"
}

# Output the index ID
output "cluster_vector_index_id" {
  value       = google_firestore_index.cluster_centroid_vector_index.id
  description = "Full resource ID of the cluster vector index"
}
