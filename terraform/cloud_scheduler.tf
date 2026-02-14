# ============================================================================
# Cloud Scheduler & Batch Recommendations (Epic 12)
# ============================================================================
# Weekly batch recommendations execution: Cloud Scheduler → Pub/Sub → Cloud Function
# Every Thursday at 22:00 UTC, automatically saves 0-3 recommendations to Readwise Reader

# Enable Cloud Scheduler API (if not already enabled in main.tf)
resource "google_project_service" "cloudscheduler_api" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

# Pub/Sub topic for batch recommendations trigger
resource "google_pubsub_topic" "batch_recommendations" {
  name = "batch-recommendations"

  depends_on = [google_project_service.required_apis]
}

# Cloud Scheduler job - weekly batch recommendations
# Story 12.1: Schedule batch recommendations for Thursday nights at 22:00 UTC
resource "google_cloud_scheduler_job" "batch_recommendations" {
  name             = "batch-recommendations"
  description      = "Weekly batch recommendations to Readwise Reader (Fri 04:00 UTC)"
  schedule         = "0 4 * * 5"  # Friday 04:00 UTC (cron format: minute hour day month day-of-week)
  time_zone        = "UTC"
  region           = "europe-west3"  # Cloud Scheduler only available in specific regions
  attempt_deadline = "600s"          # 10 minute deadline (Cloud Scheduler timeout, not Cloud Function timeout)

  pubsub_target {
    topic_name = google_pubsub_topic.batch_recommendations.id
    data       = base64encode(jsonencode({
      trigger    = "batch-recommendations"
      timestamp  = timestamp()
    }))
  }

  depends_on = [
    google_project_service.cloudscheduler_api,
    google_pubsub_topic.batch_recommendations
  ]
}

# ============================================================================
# Cloud Function Infrastructure for Batch Recommendations (Story 12.2)
# ============================================================================

# IAM Service Account for batch recommendations Cloud Function
resource "google_service_account" "batch_recommendations_sa" {
  account_id   = "batch-recommendations-sa"
  display_name = "Service Account for Batch Recommendations Cloud Function"
  description  = "Service account for weekly batch recommendations to Readwise"
}

# Grant service account permissions for Firestore (config + job tracking)
resource "google_project_iam_member" "batch_sa_firestore_admin" {
  project = var.project_id
  role    = "roles/datastore.user"  # Read/write to Firestore
  member  = "serviceAccount:${google_service_account.batch_recommendations_sa.email}"
}

# Grant service account permission to access Secret Manager (Readwise API key)
resource "google_project_iam_member" "batch_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.batch_recommendations_sa.email}"
}

# Grant service account permission to call MCP server on Cloud Run (for recommendations API)
resource "google_project_iam_member" "batch_sa_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.batch_recommendations_sa.email}"
}

# Archive the source code for the batch recommendations Cloud Function
data "archive_file" "batch_recommendations_source" {
  type        = "zip"
  source_dir  = "../src/batch_recommendations"
  output_path = "/tmp/batch_recommendations_source.zip"
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
resource "google_storage_bucket_object" "batch_recommendations_source_zip" {
  name   = "batch_recommendations_source.zip#${data.archive_file.batch_recommendations_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.batch_recommendations_source.output_path
}

# Cloud Function (2nd gen) for batch recommendations
# Story 12.2: Weekly batch recommendation execution with Reader integration
resource "google_cloudfunctions2_function" "batch_recommendations" {
  name     = "batch-recommendations"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "batch_recommendations"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.batch_recommendations_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count             = 1
    timeout_seconds                = 540  # 9 min timeout (max for event-triggered functions)
    service_account_email          = google_service_account.batch_recommendations_sa.email
    all_traffic_on_latest_revision = true
    environment_variables = {
      GCP_PROJECT = var.project_id
      # MCP_SERVER_URL will be passed via config/batch_recommendations Firestore doc
    }
  }

  # Trigger on Pub/Sub messages from Cloud Scheduler
  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = google_pubsub_topic.batch_recommendations.id
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.batch_recommendations_sa.email
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.batch_sa_firestore_admin,
    google_project_iam_member.batch_sa_secret_accessor,
    google_project_iam_member.batch_sa_run_invoker,
    google_storage_bucket_iam_member.batch_sa_function_source_viewer
  ]
}

# Grant batch SA read access to function source bucket
resource "google_storage_bucket_iam_member" "batch_sa_function_source_viewer" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.batch_recommendations_sa.email}"
}

# ============================================================================
# Security: Allow only Batch Function to invoke MCP Server /recommendations
# ============================================================================

# Get reference to MCP Server Cloud Run service
data "google_cloud_run_service" "mcp_server" {
  name     = "kx-hub-mcp"
  location = "europe-west1"  # MCP Server deployed in europe-west1
}

# Grant batch recommendations service account permission to invoke MCP server
resource "google_cloud_run_service_iam_member" "batch_sa_mcp_invoker" {
  service      = data.google_cloud_run_service.mcp_server.name
  location     = data.google_cloud_run_service.mcp_server.location
  role         = "roles/run.invoker"
  member       = "serviceAccount:${google_service_account.batch_recommendations_sa.email}"
}

# Output the batch recommendations Pub/Sub topic for reference
output "batch_recommendations_pubsub_topic" {
  value       = google_pubsub_topic.batch_recommendations.name
  description = "Pub/Sub topic for batch recommendations trigger"
}

output "batch_recommendations_sa_email" {
  value       = google_service_account.batch_recommendations_sa.email
  description = "Service account email for batch recommendations function"
}
