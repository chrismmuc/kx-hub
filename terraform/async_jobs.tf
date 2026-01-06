# ============================================================================
# Async Jobs Infrastructure (Epic 7)
# ============================================================================
# Cloud Tasks queue for async MCP job execution.
# Jobs are enqueued when `recommendations()` is called without a job_id,
# and executed by calling the /jobs/run endpoint on the MCP server.

# Enable Cloud Tasks API
resource "google_project_service" "cloudtasks_api" {
  service            = "cloudtasks.googleapis.com"
  disable_on_destroy = false
}

# Cloud Tasks queue for async jobs
# Note: Cloud Tasks not available in europe-west4, using europe-west1
resource "google_cloud_tasks_queue" "async_jobs" {
  name     = "async-jobs"
  location = "europe-west1"

  rate_limits {
    max_concurrent_dispatches = 2    # Limit parallel jobs
    max_dispatches_per_second = 1    # Rate limit
  }

  retry_config {
    max_attempts       = 3           # Retry failed jobs up to 3 times
    max_retry_duration = "3600s"     # Give up after 1 hour
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_doublings      = 4
  }

  # Cleanup tasks after 14 days
  stackdriver_logging_config {
    sampling_ratio = 1.0
  }

  depends_on = [google_project_service.cloudtasks_api]
}

# Service account for Cloud Tasks to invoke Cloud Run
resource "google_service_account" "cloud_tasks_sa" {
  account_id   = "cloud-tasks-invoker"
  display_name = "Cloud Tasks Job Invoker"
  description  = "Service account for Cloud Tasks to invoke MCP server job endpoint"
}

# Grant Cloud Tasks SA permission to invoke Cloud Run services
resource "google_project_iam_member" "cloud_tasks_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.cloud_tasks_sa.email}"
}

# Grant Cloud Tasks SA permission to create tokens (needed for OIDC auth)
resource "google_project_iam_member" "cloud_tasks_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.cloud_tasks_sa.email}"
}

# Grant MCP server SA permission to enqueue Cloud Tasks
resource "google_project_iam_member" "mcp_sa_cloudtasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.mcp_server_sa.email}"
}

# Output the queue name for use in MCP server config
output "async_jobs_queue_name" {
  value       = google_cloud_tasks_queue.async_jobs.name
  description = "Cloud Tasks queue name for async jobs"
}

output "cloud_tasks_sa_email" {
  value       = google_service_account.cloud_tasks_sa.email
  description = "Service account email for Cloud Tasks invocations"
}
