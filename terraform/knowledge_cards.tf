# ============================================================================
# Story 2.1: Knowledge Card Generation - Cloud Function & Integration
# ============================================================================
#
# Deploys knowledge card generation as a Cloud Function and integrates it
# into the daily batch pipeline workflow (after embed step).
#
# Pipeline flow: ingest → normalize → embed → generate_knowledge_cards
#

# IAM Service Account for Knowledge Cards Cloud Function
resource "google_service_account" "knowledge_cards_function_sa" {
  account_id   = "knowledge-cards-function-sa"
  display_name = "Service Account for Knowledge Cards Cloud Function"
}

# Grant knowledge cards function access to Firestore (read/write kb_items)
resource "google_project_iam_member" "knowledge_cards_sa_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.knowledge_cards_function_sa.email}"
}

# Grant knowledge cards function access to Vertex AI (Gemini API)
resource "google_project_iam_member" "knowledge_cards_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.knowledge_cards_function_sa.email}"
}

# Grant knowledge cards function logging permissions
resource "google_project_iam_member" "knowledge_cards_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.knowledge_cards_function_sa.email}"
}

# Archive the source code for the Knowledge Cards Cloud Function
data "archive_file" "knowledge_cards_source" {
  type        = "zip"
  source_dir  = "../functions/knowledge_cards"
  output_path = "/tmp/knowledge_cards_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store"
  ]
}

# Upload the knowledge cards function source code
resource "google_storage_bucket_object" "knowledge_cards_source_zip" {
  name   = "knowledge_cards_source.zip#${data.archive_file.knowledge_cards_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.knowledge_cards_source.output_path
}

# Cloud Function (2nd gen) for knowledge card generation
resource "google_cloudfunctions2_function" "knowledge_cards_function" {
  name     = "knowledge-cards-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "generate_cards_handler"  # Entry point in cloud_function.py
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.knowledge_cards_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 3  # Allow parallel execution for faster processing
    timeout_seconds       = 3600  # 60 minutes for 818 chunks (~5 sec each = ~68 min)
    available_memory      = "1Gi"  # More memory for LLM API calls
    service_account_email = google_service_account.knowledge_cards_function_sa.email
    environment_variables = {
      GCP_PROJECT         = var.project_id
      GCP_REGION          = var.region
      FIRESTORE_COLLECTION = "kb_items"
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.knowledge_cards_sa_datastore_user,
    google_project_iam_member.knowledge_cards_sa_aiplatform_user,
    google_project_iam_member.knowledge_cards_sa_log_writer,
    google_firestore_database.kb_database
  ]
}

# Grant workflow service account permission to invoke the knowledge cards function
resource "google_cloud_run_service_iam_member" "knowledge_cards_function_workflow_invoker" {
  location = google_cloudfunctions2_function.knowledge_cards_function.location
  service  = google_cloudfunctions2_function.knowledge_cards_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.workflow_sa.email}"
}
