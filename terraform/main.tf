# Pub/Sub topic to trigger the daily ingest workflow
resource "google_pubsub_topic" "daily_trigger" {
  name = "daily-trigger"
}

# Cloud Scheduler job to publish to the daily-trigger topic every day at 2am
resource "google_cloud_scheduler_job" "daily_ingest_trigger" {
  name        = "daily-ingest-trigger-job"
  description = "Triggers the daily data ingest pipeline"
  schedule    = "0 2 * * *"
  time_zone   = "UTC"

  pubsub_target {
    topic_name = google_pubsub_topic.daily_trigger.id
    data       = base64encode("Go!")
  }
}

# Pub/Sub topic for the ingest function to publish to upon completion
resource "google_pubsub_topic" "daily_ingest" {
  name = "daily-ingest"
}

# Cloud Storage bucket to store raw ingested JSON data
resource "google_storage_bucket" "raw_json" {
  name          = "${var.project_id}-raw-json"
  location      = var.region
  force_destroy = true // Note: Set to false in production

  uniform_bucket_level_access = true
}

# IAM Service Account for the Ingest Cloud Function
resource "google_service_account" "ingest_function_sa" {
  account_id   = "ingest-function-sa"
  display_name = "Service Account for Ingest Cloud Function"
}

# Permissions for the Service Account
resource "google_project_iam_member" "ingest_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.ingest_function_sa.email}"
}

resource "google_project_iam_member" "ingest_sa_storage_creator" {
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.ingest_function_sa.email}"
}

resource "google_project_iam_member" "ingest_sa_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.ingest_function_sa.email}"
}

# Archive the source code for the Cloud Function
data "archive_file" "ingest_source" {
  type        = "zip"
  source_dir  = "../src/ingest"
  output_path = "/tmp/ingest_source.zip"
}

# Cloud Storage bucket to store the function's source code
resource "google_storage_bucket" "function_source" {
  name          = "${var.project_id}-function-source"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}

# Upload the zipped source code to the bucket
resource "google_storage_bucket_object" "ingest_source_zip" {
  name   = "ingest_source.zip#${data.archive_file.ingest_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.ingest_source.output_path
}

# Cloud Function (2nd gen) for data ingestion
resource "google_cloudfunctions2_function" "ingest_function" {
  name     = "ingest-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "handler"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.ingest_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count = 1
    service_account_email = google_service_account.ingest_function_sa.email
    all_traffic_on_latest_revision = true
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.daily_trigger.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }
}
