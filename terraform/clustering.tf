# ============================================================================
# Story 2.2: Semantic Clustering - Cloud Function & Integration
# ============================================================================
#
# Deploys clustering as a Cloud Function and integrates it into the daily
# batch pipeline workflow (after knowledge cards step).
#
# Pipeline flow: ingest → normalize → embed → knowledge_cards → clustering
#

# IAM Service Account for Clustering Cloud Function
resource "google_service_account" "clustering_function_sa" {
  account_id   = "clustering-function-sa"
  display_name = "Service Account for Clustering Cloud Function"
}

# Grant clustering function access to Firestore (read/write kb_items)
resource "google_project_iam_member" "clustering_sa_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.clustering_function_sa.email}"
}

# Grant clustering function access to Cloud Storage (write graph.json)
resource "google_project_iam_member" "clustering_sa_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.clustering_function_sa.email}"
}

# Grant clustering function logging permissions
resource "google_project_iam_member" "clustering_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.clustering_function_sa.email}"
}

# Archive the source code for the Clustering Cloud Function
data "archive_file" "clustering_source" {
  type        = "zip"
  source_dir  = "../functions/clustering"
  output_path = "/tmp/clustering_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store"
  ]
}

# Upload the clustering function source code
resource "google_storage_bucket_object" "clustering_source_zip" {
  name   = "clustering_source.zip#${data.archive_file.clustering_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.clustering_source.output_path
}

# Cloud Function (2nd gen) for clustering
resource "google_cloudfunctions2_function" "clustering_function" {
  name     = "clustering-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "cluster_new_chunks"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.clustering_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 300 # 5 minutes for delta processing
    service_account_email = google_service_account.clustering_function_sa.email

    environment_variables = {
      GCP_PROJECT          = var.project_id
      GCP_REGION           = var.region
      FIRESTORE_COLLECTION = "kb_items"
      GCS_BUCKET           = google_storage_bucket.pipeline.name
      UMAP_MODEL_PATH      = "models/umap_model.pkl"
      NUMBA_NUM_THREADS    = "1" # Fix Numba threading issues in serverless
    }
  }

  depends_on = [
    google_project_iam_member.clustering_sa_datastore_user,
    google_project_iam_member.clustering_sa_storage_object_admin,
    google_project_iam_member.clustering_sa_log_writer
  ]
}

# Grant Cloud Workflows permission to invoke clustering function
resource "google_cloudfunctions2_function_iam_member" "clustering_invoker" {
  project        = google_cloudfunctions2_function.clustering_function.project
  location       = google_cloudfunctions2_function.clustering_function.location
  cloud_function = google_cloudfunctions2_function.clustering_function.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.workflow_sa.email}"
}

# Output the function URL
output "clustering_function_url" {
  value       = google_cloudfunctions2_function.clustering_function.service_config[0].uri
  description = "URL of the clustering Cloud Function"
}
