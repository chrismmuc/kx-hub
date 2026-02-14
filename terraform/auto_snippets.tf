# ============================================================================
# Auto-Snippets Nightly Trigger & Tag Management (Epic 13, Story 13.4)
# ============================================================================
# Nightly auto-ingest: Cloud Scheduler → Pub/Sub → Cloud Function
# Processes Reader articles tagged 'kx-auto-ingest' into KB snippets

# Pub/Sub topic for auto-snippets trigger
resource "google_pubsub_topic" "auto_snippets" {
  name = "auto-snippets"

  depends_on = [google_project_service.required_apis]
}

# Cloud Scheduler job - nightly auto-snippets at 02:00 UTC
resource "google_cloud_scheduler_job" "auto_snippets" {
  name             = "auto-snippets"
  description      = "Nightly auto-snippet ingestion from Reader (02:00 UTC)"
  schedule         = "0 2 * * *"
  time_zone        = "UTC"
  region           = "europe-west3"
  attempt_deadline = "600s"

  pubsub_target {
    topic_name = google_pubsub_topic.auto_snippets.id
    data       = base64encode(jsonencode({
      trigger   = "auto-snippets"
      timestamp = timestamp()
    }))
  }

  depends_on = [
    google_project_service.cloudscheduler_api,
    google_pubsub_topic.auto_snippets
  ]
}

# ============================================================================
# Cloud Function Infrastructure for Auto-Snippets
# ============================================================================

# IAM Service Account for auto-snippets Cloud Function
resource "google_service_account" "auto_snippets_sa" {
  account_id   = "auto-snippets-sa"
  display_name = "Service Account for Auto-Snippets Cloud Function"
  description  = "Service account for nightly auto-snippet ingestion from Reader"
}

# Grant service account permissions for Firestore (config + kb_items + batch_jobs)
resource "google_project_iam_member" "auto_snippets_sa_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.auto_snippets_sa.email}"
}

# Grant service account permission to access Secret Manager (readwise-api-key)
resource "google_project_iam_member" "auto_snippets_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.auto_snippets_sa.email}"
}

# Grant service account permission for Vertex AI embeddings
resource "google_project_iam_member" "auto_snippets_sa_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.auto_snippets_sa.email}"
}

# Archive the source code for the auto-snippets Cloud Function
data "archive_file" "auto_snippets_source" {
  type        = "zip"
  source_dir  = "../src/auto_snippets/build"
  output_path = "/tmp/auto_snippets_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store",
    ".pytest_cache",
    "**/.pytest_cache"
  ]
}

# Upload the zipped source code to the function source bucket
resource "google_storage_bucket_object" "auto_snippets_source_zip" {
  name   = "auto_snippets_source.zip#${data.archive_file.auto_snippets_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.auto_snippets_source.output_path
}

# Cloud Function (2nd gen) for auto-snippets
resource "google_cloudfunctions2_function" "auto_snippets" {
  name     = "auto-snippets"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "auto_snippets"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.auto_snippets_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count             = 1
    timeout_seconds                = 540
    available_memory               = "512Mi"
    service_account_email          = google_service_account.auto_snippets_sa.email
    all_traffic_on_latest_revision = true
    environment_variables = {
      GCP_PROJECT = var.project_id
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = google_pubsub_topic.auto_snippets.id
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.auto_snippets_sa.email
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.auto_snippets_sa_firestore,
    google_project_iam_member.auto_snippets_sa_secret_accessor,
    google_project_iam_member.auto_snippets_sa_aiplatform,
    google_storage_bucket_iam_member.auto_snippets_sa_function_source_viewer
  ]
}

# Grant auto-snippets SA read access to function source bucket
resource "google_storage_bucket_iam_member" "auto_snippets_sa_function_source_viewer" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.auto_snippets_sa.email}"
}

# ============================================================================
# Outputs
# ============================================================================

output "auto_snippets_pubsub_topic" {
  value       = google_pubsub_topic.auto_snippets.name
  description = "Pub/Sub topic for auto-snippets trigger"
}

output "auto_snippets_sa_email" {
  value       = google_service_account.auto_snippets_sa.email
  description = "Service account email for auto-snippets function"
}
