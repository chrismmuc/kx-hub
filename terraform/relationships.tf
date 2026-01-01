# ============================================================================
# Story 4.5: Incremental Relationship Extraction - Cloud Function
# ============================================================================
#
# Deploys relationship extraction as a Cloud Function integrated into the
# daily batch pipeline workflow (after knowledge cards step).
#
# Pipeline flow: ingest → normalize → embed → knowledge_cards → relationships
#

# IAM Service Account for Relationships Cloud Function
resource "google_service_account" "relationships_function_sa" {
  account_id   = "relationships-function-sa"
  display_name = "Service Account for Relationships Cloud Function"
}

# Grant relationships function access to Firestore (read/write kb_items, relationships)
resource "google_project_iam_member" "relationships_sa_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.relationships_function_sa.email}"
}

# Grant relationships function access to Vertex AI (for LLM calls)
resource "google_project_iam_member" "relationships_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.relationships_function_sa.email}"
}

# Grant relationships function logging permissions
resource "google_project_iam_member" "relationships_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.relationships_function_sa.email}"
}

# Grant access to Secret Manager for API keys (Anthropic)
resource "google_project_iam_member" "relationships_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.relationships_function_sa.email}"
}

# Archive the source code for the Relationships Cloud Function
data "archive_file" "relationships_source" {
  type        = "zip"
  source_dir  = "../functions/relationships"
  output_path = "/tmp/relationships_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store"
  ]
}

# Upload the relationships function source code
resource "google_storage_bucket_object" "relationships_source_zip" {
  name   = "relationships_source.zip#${data.archive_file.relationships_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.relationships_source.output_path
}

# Cloud Function (2nd gen) for relationship extraction
resource "google_cloudfunctions2_function" "relationships_function" {
  name     = "relationships-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "extract_relationships"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.relationships_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "1Gi"
    timeout_seconds       = 540  # 9 minutes for LLM calls
    service_account_email = google_service_account.relationships_function_sa.email

    environment_variables = {
      GCP_PROJECT          = var.project_id
      GCP_REGION           = var.region
      FIRESTORE_COLLECTION = "kb_items"
      SIMILARITY_THRESHOLD = "0.80"
      CONFIDENCE_THRESHOLD = "0.8"
      MAX_SIMILAR_CHUNKS   = "10"
    }
  }

  depends_on = [
    google_project_iam_member.relationships_sa_datastore_user,
    google_project_iam_member.relationships_sa_aiplatform_user,
    google_project_iam_member.relationships_sa_log_writer,
    google_project_iam_member.relationships_sa_secret_accessor
  ]
}

# Grant Cloud Workflows permission to invoke relationships function
resource "google_cloudfunctions2_function_iam_member" "relationships_invoker" {
  project        = google_cloudfunctions2_function.relationships_function.project
  location       = google_cloudfunctions2_function.relationships_function.location
  cloud_function = google_cloudfunctions2_function.relationships_function.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.workflow_sa.email}"
}

# Output the function URL
output "relationships_function_url" {
  value       = google_cloudfunctions2_function.relationships_function.service_config[0].uri
  description = "URL of the relationships Cloud Function"
}
