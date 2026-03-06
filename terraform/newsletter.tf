# ============================================================================
# Weekly Tech Newsletter (Epic 15)
# ============================================================================
# Cloud Scheduler -> HTTP Cloud Function -> ADK Agent + Gemini Flash -> Firestore

# Service Account
resource "google_service_account" "newsletter_sa" {
  account_id   = "newsletter-sa"
  display_name = "Service Account for Newsletter Cloud Function"
  description  = "Service account for weekly tech newsletter generation"
}

# Firestore access (read kb_items, write newsletter_drafts, config)
resource "google_project_iam_member" "newsletter_sa_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.newsletter_sa.email}"
}

# Secret Manager access (readwise-api-key, newsletter-agent-engine-id)
resource "google_project_iam_member" "newsletter_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.newsletter_sa.email}"
}

# Vertex AI access (Gemini Flash + Agent Engine)
resource "google_project_iam_member" "newsletter_sa_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.newsletter_sa.email}"
}

# GCS access (write to kx-hub-content/newsletter/)
resource "google_storage_bucket_iam_member" "newsletter_sa_content_writer" {
  bucket = google_storage_bucket.summary_images.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.newsletter_sa.email}"
}

# Archive the build directory
data "archive_file" "newsletter_source" {
  type        = "zip"
  source_dir  = "../src/newsletter/build"
  output_path = "/tmp/newsletter_source.zip"
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
resource "google_storage_bucket_object" "newsletter_source_zip" {
  name   = "newsletter_source.zip#${data.archive_file.newsletter_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.newsletter_source.output_path
}

# Cloud Function (2nd gen) - HTTP triggered
resource "google_cloudfunctions2_function" "newsletter" {
  name     = "newsletter-generator"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "generate_newsletter_cf"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.newsletter_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count             = 1
    timeout_seconds                = 540
    available_memory               = "512Mi"
    service_account_email          = google_service_account.newsletter_sa.email
    all_traffic_on_latest_revision = true
    environment_variables = {
      GCP_PROJECT = var.project_id
    }
    secret_environment_variables {
      key        = "NEWSLETTER_AGENT_ENGINE_ID"
      project_id = var.project_id
      secret     = google_secret_manager_secret.newsletter_agent_engine_id.secret_id
      version    = "latest"
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.newsletter_sa_firestore,
    google_project_iam_member.newsletter_sa_secret_accessor,
    google_project_iam_member.newsletter_sa_aiplatform,
    google_storage_bucket_iam_member.newsletter_sa_function_source_viewer,
    google_secret_manager_secret.newsletter_agent_engine_id,
  ]
}

# Grant newsletter SA read access to function source bucket
resource "google_storage_bucket_iam_member" "newsletter_sa_function_source_viewer" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.newsletter_sa.email}"
}

# Allow Cloud Scheduler to invoke the function
resource "google_cloud_run_service_iam_member" "newsletter_scheduler_invoker" {
  location = google_cloudfunctions2_function.newsletter.location
  service  = google_cloudfunctions2_function.newsletter.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.newsletter_sa.email}"
}

# Secret: agent engine ID (populated by deploy_agent.py)
resource "google_secret_manager_secret" "newsletter_agent_engine_id" {
  secret_id = "newsletter-agent-engine-id"
  replication {
    auto {}
  }
}

# Placeholder initial version so CF can reference 'latest' before deploy_agent.py runs.
# The curation_agent.py gracefully degrades when value is "NOT_SET".
resource "google_secret_manager_secret_version" "newsletter_agent_engine_id_placeholder" {
  secret      = google_secret_manager_secret.newsletter_agent_engine_id.id
  secret_data = "NOT_SET"

  lifecycle {
    ignore_changes = [secret_data]  # don't overwrite after deploy_agent.py sets the real value
  }
}

# Cloud Scheduler job - weekly newsletter generation
# Saturday 08:00 UTC = 09:00 CET / 10:00 CEST
resource "google_cloud_scheduler_job" "newsletter_weekly" {
  name             = "newsletter-weekly"
  description      = "Weekly tech newsletter generation (Saturday morning)"
  schedule         = "0 8 * * 6"
  time_zone        = "UTC"
  region           = "europe-west3"
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.newsletter.service_config[0].uri

    body = base64encode(jsonencode({
      days  = 7
      limit = 50
    }))

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.newsletter_sa.email
    }
  }

  depends_on = [
    google_project_service.cloudscheduler_api,
    google_cloudfunctions2_function.newsletter
  ]
}

# ============================================================================
# Outputs
# ============================================================================

output "newsletter_function_url" {
  value       = google_cloudfunctions2_function.newsletter.service_config[0].uri
  description = "URL for the newsletter Cloud Function"
}

output "newsletter_sa_email" {
  value       = google_service_account.newsletter_sa.email
  description = "Service account email for newsletter function"
}
