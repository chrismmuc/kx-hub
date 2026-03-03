# ============================================================================
# Weekly Knowledge Summary (Epic 9)
# ============================================================================
# Cloud Scheduler → HTTP Cloud Function → Gemini 3.1 Pro → Readwise Reader
# Generates weekly narrative summary of KB activity every Sunday morning

# Cloud Scheduler job - weekly summary generation
# Sunday 06:00 UTC = 07:00 CET / 08:00 CEST
resource "google_cloud_scheduler_job" "weekly_summary" {
  name             = "weekly-summary"
  description      = "Weekly knowledge summary generation (Sunday morning)"
  schedule         = "0 6 * * 0"
  time_zone        = "UTC"
  region           = "europe-west3"
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.summary.service_config[0].uri

    body = base64encode(jsonencode({
      days  = 7
      limit = 100
    }))

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.summary_sa.email
    }
  }

  depends_on = [
    google_project_service.cloudscheduler_api,
    google_cloudfunctions2_function.summary
  ]
}

# ============================================================================
# Cloud Function Infrastructure
# ============================================================================

# Service Account
resource "google_service_account" "summary_sa" {
  account_id   = "summary-sa"
  display_name = "Service Account for Weekly Summary Cloud Function"
  description  = "Service account for weekly knowledge summary generation"
}

# Firestore access (read kb_items, sources, relationships, config)
resource "google_project_iam_member" "summary_sa_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.summary_sa.email}"
}

# Secret Manager access (readwise-api-key)
resource "google_project_iam_member" "summary_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.summary_sa.email}"
}

# Vertex AI access (Gemini 3.1 Pro)
resource "google_project_iam_member" "summary_sa_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.summary_sa.email}"
}

# Archive the build directory
data "archive_file" "summary_source" {
  type        = "zip"
  source_dir  = "../src/summary/build"
  output_path = "/tmp/summary_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store",
    ".pytest_cache",
    "**/.pytest_cache"
  ]
}

# Upload zipped source to function source bucket
resource "google_storage_bucket_object" "summary_source_zip" {
  name   = "summary_source.zip#${data.archive_file.summary_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.summary_source.output_path
}

# Cloud Function (2nd gen) - HTTP triggered
resource "google_cloudfunctions2_function" "summary" {
  name     = "weekly-summary"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "generate_summary"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.summary_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count             = 1
    timeout_seconds                = 540
    available_memory               = "512Mi"
    service_account_email          = google_service_account.summary_sa.email
    all_traffic_on_latest_revision = true
    environment_variables = {
      GCP_PROJECT = var.project_id
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.summary_sa_firestore,
    google_project_iam_member.summary_sa_secret_accessor,
    google_project_iam_member.summary_sa_aiplatform,
    google_storage_bucket_iam_member.summary_sa_function_source_viewer
  ]
}

# Grant summary SA read access to function source bucket
resource "google_storage_bucket_iam_member" "summary_sa_function_source_viewer" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.summary_sa.email}"
}

# Allow Cloud Scheduler to invoke the function
resource "google_cloud_run_service_iam_member" "summary_scheduler_invoker" {
  location = google_cloudfunctions2_function.summary.location
  service  = google_cloudfunctions2_function.summary.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.summary_sa.email}"
}

# ============================================================================
# Cover Image Storage (GCS)
# ============================================================================

# Public bucket for weekly summary cover images (1 image/week)
resource "google_storage_bucket" "summary_images" {
  name     = "kx-hub-summary-images"
  location = var.region

  uniform_bucket_level_access = true
}

# Public read access for Reader to fetch images
resource "google_storage_bucket_iam_member" "summary_images_public" {
  bucket = google_storage_bucket.summary_images.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Grant summary SA write access to upload images
resource "google_storage_bucket_iam_member" "summary_sa_images_writer" {
  bucket = google_storage_bucket.summary_images.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.summary_sa.email}"
}

# ============================================================================
# Outputs
# ============================================================================

output "summary_function_url" {
  value       = google_cloudfunctions2_function.summary.service_config[0].uri
  description = "URL for the weekly summary Cloud Function"
}

output "summary_sa_email" {
  value       = google_service_account.summary_sa.email
  description = "Service account email for summary function"
}
