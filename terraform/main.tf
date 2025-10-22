# Enable required GCP APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com",
    "eventarc.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "workflows.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com"
  ])

  service            = each.value
  disable_on_destroy = false
}

# Pub/Sub topic to trigger the daily ingest workflow
resource "google_pubsub_topic" "daily_trigger" {
  name = "daily-trigger"

  depends_on = [google_project_service.required_apis]
}

# Cloud Scheduler job to publish to the daily-trigger topic every day at 2am
resource "google_cloud_scheduler_job" "daily_ingest_trigger" {
  name        = "daily-ingest-trigger-job"
  description = "Triggers the daily data ingest pipeline"
  schedule    = "0 2 * * *"
  time_zone   = "UTC"
  region      = "europe-west3" # Cloud Scheduler only supports specific regions

  pubsub_target {
    topic_name = google_pubsub_topic.daily_trigger.id
    data       = base64encode("Go!")
  }

  depends_on = [google_project_service.required_apis]
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

# Grant the service account admin access to the raw-json bucket
resource "google_storage_bucket_iam_member" "ingest_sa_raw_bucket_admin" {
  bucket = google_storage_bucket.raw_json.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingest_function_sa.email}"
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
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store"
  ]
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
    max_instance_count             = 1
    service_account_email          = google_service_account.ingest_function_sa.email
    all_traffic_on_latest_revision = true
    environment_variables = {
      GCP_PROJECT               = var.project_id
      PIPELINE_BUCKET           = google_storage_bucket.pipeline.name
      PIPELINE_MANIFEST_PREFIX  = "manifests"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.daily_trigger.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.ingest_sa_secret_accessor,
    google_storage_bucket_iam_member.ingest_sa_raw_bucket_admin,
    google_project_iam_member.ingest_sa_pubsub_publisher,
    google_storage_bucket_iam_member.ingest_sa_pipeline_bucket_admin
  ]
}

# ============================================================================
# Phase 2: Normalize Function & Cloud Workflow Resources (Story 1.2)
# ============================================================================

# Cloud Storage bucket for normalized Markdown files
resource "google_storage_bucket" "markdown_normalized" {
  name          = "${var.project_id}-markdown-normalized"
  location      = var.region
  force_destroy = true // Note: Set to false in production

  uniform_bucket_level_access = true
}

# Cloud Storage bucket for pipeline manifests and run artifacts
resource "google_storage_bucket" "pipeline" {
  name          = "${var.project_id}-pipeline"
  location      = var.region
  force_destroy = true // Note: tune lifecycle policies for production

  uniform_bucket_level_access = true
}

# Grant ingest function write access to pipeline bucket
resource "google_storage_bucket_iam_member" "ingest_sa_pipeline_bucket_admin" {
  bucket = google_storage_bucket.pipeline.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingest_function_sa.email}"
}

# Grant normalize function read access to pipeline bucket
resource "google_storage_bucket_iam_member" "normalize_sa_pipeline_bucket_viewer" {
  bucket = google_storage_bucket.pipeline.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.normalize_function_sa.email}"
}

# IAM Service Account for the Normalize Cloud Function
resource "google_service_account" "normalize_function_sa" {
  account_id   = "normalize-function-sa"
  display_name = "Service Account for Normalize Cloud Function"
}

# Grant normalize function read access to raw-json bucket
resource "google_storage_bucket_iam_member" "normalize_sa_raw_bucket_viewer" {
  bucket = google_storage_bucket.raw_json.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.normalize_function_sa.email}"
}

# Grant normalize function write access to markdown-normalized bucket
resource "google_storage_bucket_iam_member" "normalize_sa_markdown_bucket_creator" {
  bucket = google_storage_bucket.markdown_normalized.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.normalize_function_sa.email}"
}

# Grant logging permissions
resource "google_project_iam_member" "normalize_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.normalize_function_sa.email}"
}

# Grant run.invoker permission for workflow to invoke function
resource "google_project_iam_member" "normalize_sa_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.normalize_function_sa.email}"
}

# Archive the source code for the Normalize Cloud Function
data "archive_file" "normalize_source" {
  type        = "zip"
  source_dir  = "../src/normalize"
  output_path = "/tmp/normalize_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store"
  ]
}

# Upload the normalize function source code
resource "google_storage_bucket_object" "normalize_source_zip" {
  name   = "normalize_source.zip#${data.archive_file.normalize_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.normalize_source.output_path
}

# Cloud Function (2nd gen) for normalization (JSON → Markdown)
resource "google_cloudfunctions2_function" "normalize_function" {
  name     = "normalize-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "normalize"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.normalize_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    timeout_seconds       = 540 // 9 minutes for large batches
    service_account_email = google_service_account.normalize_function_sa.email
    environment_variables = {
      GCP_PROJECT              = var.project_id
      PIPELINE_BUCKET          = google_storage_bucket.pipeline.name
      PIPELINE_MANIFEST_PREFIX = "manifests"
      PIPELINE_COLLECTION      = "pipeline_items"
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_storage_bucket_iam_member.normalize_sa_raw_bucket_viewer,
    google_storage_bucket_iam_member.normalize_sa_markdown_bucket_creator,
    google_project_iam_member.normalize_sa_log_writer,
    google_project_iam_member.normalize_sa_run_invoker,
    google_storage_bucket_iam_member.normalize_sa_pipeline_bucket_viewer
  ]
}

# Service Account for Cloud Workflow
resource "google_service_account" "workflow_sa" {
  account_id   = "batch-pipeline-workflow-sa"
  display_name = "Service Account for Batch Pipeline Workflow"
}

# Grant workflow permission to invoke Cloud Functions
resource "google_project_iam_member" "workflow_sa_function_invoker" {
  project = var.project_id
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

# Grant workflow permission to write logs
resource "google_project_iam_member" "workflow_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

# Grant workflow service account permission to invoke workflows (needed for Eventarc trigger)
resource "google_project_iam_member" "workflow_sa_workflows_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.workflow_sa.email}"
}

# Cloud Workflow for batch processing pipeline
resource "google_workflows_workflow" "batch_pipeline" {
  name            = "batch-pipeline"
  region          = var.region
  description     = "Orchestrates the daily batch processing pipeline: normalize → embed → store"
  service_account = google_service_account.workflow_sa.id
  source_contents = file("${path.module}/workflows/batch-pipeline.yaml")

  depends_on = [
    google_project_service.required_apis,
    google_cloudfunctions2_function.normalize_function,
    google_project_iam_member.workflow_sa_function_invoker,
    google_project_iam_member.workflow_sa_log_writer,
    google_project_iam_member.workflow_sa_workflows_invoker
  ]
}

# Eventarc trigger to start workflow when daily-ingest Pub/Sub message is published
resource "google_eventarc_trigger" "workflow_trigger" {
  name     = "workflow-trigger-daily-ingest"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  destination {
    workflow = google_workflows_workflow.batch_pipeline.id
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.daily_ingest.id
    }
  }

  service_account = google_service_account.workflow_sa.email

  depends_on = [
    google_project_service.required_apis,
    google_workflows_workflow.batch_pipeline,
    google_project_iam_member.workflow_sa_workflows_invoker,
    google_project_iam_member.eventarc_sa_workflows_invoker
  ]
}

# Grant workflow service account permission to invoke the normalize function
resource "google_cloud_run_service_iam_member" "normalize_function_workflow_invoker" {
  location = google_cloudfunctions2_function.normalize_function.location
  service  = google_cloudfunctions2_function.normalize_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.workflow_sa.email}"
}

# Grant Eventarc service agent permission to invoke workflows
resource "google_project_iam_member" "eventarc_sa_workflows_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# Data source to get project number
data "google_project" "project" {
  project_id = var.project_id
}

# Allow Pub/Sub service agent to invoke ingest Cloud Run service (2nd gen function trigger)
resource "google_cloud_run_service_iam_member" "ingest_function_pubsub_invoker" {
  location = google_cloudfunctions2_function.ingest_function.location
  service  = google_cloudfunctions2_function.ingest_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_cloud_run_service_iam_member" "ingest_function_eventarc_invoker" {
  location = google_cloudfunctions2_function.ingest_function.location
  service  = google_cloudfunctions2_function.ingest_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-eventarc.iam.gserviceaccount.com"
}

# ============================================================================
# Phase 3: Embed Function & Vector Search + Firestore Resources (Story 1.3)
# ============================================================================

# Firestore database (Native mode)
resource "google_firestore_database" "kb_database" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.required_apis]
}

# Composite index to support pipeline_items queries by embedding status + content hash
resource "google_firestore_index" "pipeline_items_embedding_status_content_hash" {
  project    = var.project_id
  database   = "(default)"
  collection = "pipeline_items"
  query_scope = "COLLECTION"

  fields {
    field_path = "embedding_status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "content_hash"
    order      = "ASCENDING"
  }

  depends_on = [google_firestore_database.kb_database]
}

# Vertex AI Vector Search Index
resource "google_vertex_ai_index" "kb_vector_index" {
  display_name = "kb-vector-index"
  description  = "Vector search index for knowledge base embeddings"
  region       = var.region

  metadata {
    contents_delta_uri = "gs://${google_storage_bucket.vector_search_staging.name}/initial"
    config {
      dimensions                  = 768
      approximate_neighbors_count = 150
      distance_measure_type       = "COSINE_DISTANCE"
      feature_norm_type           = "UNIT_L2_NORM"
      algorithm_config {
        tree_ah_config {
          leaf_node_embedding_count    = 1000
          leaf_nodes_to_search_percent = 7
        }
      }
    }
  }

  depends_on = [google_project_service.required_apis]
}

# Cloud Storage bucket for Vector Search staging
resource "google_storage_bucket" "vector_search_staging" {
  name          = "${var.project_id}-vector-search-staging"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}

# Initial empty embedding file for Vector Search index creation
resource "google_storage_bucket_object" "initial_embeddings" {
  name   = "initial/embedding_seed.jsonl"
  bucket = google_storage_bucket.vector_search_staging.name
  source = "${path.module}/templates/embedding_seed.jsonl"
  content_type = "application/json"
}

# Vertex AI Index Endpoint
resource "google_vertex_ai_index_endpoint" "kb_index_endpoint" {
  display_name = "kb-index-endpoint"
  description  = "Endpoint for knowledge base vector search"
  region       = var.region

  depends_on = [google_project_service.required_apis]
}

# Deploy index to endpoint
resource "google_vertex_ai_index_endpoint_deployed_index" "kb_deployed_index" {
  index_endpoint        = google_vertex_ai_index_endpoint.kb_index_endpoint.id
  deployed_index_id     = "kb_deployed_index"
  display_name          = "KB Deployed Index"
  index                 = google_vertex_ai_index.kb_vector_index.id
  enable_access_logging = false

  automatic_resources {
    min_replica_count = 1
    max_replica_count = 2
  }

  depends_on = [
    google_vertex_ai_index.kb_vector_index,
    google_vertex_ai_index_endpoint.kb_index_endpoint
  ]
}

# IAM Service Account for the Embed Cloud Function
resource "google_service_account" "embed_function_sa" {
  account_id   = "embed-function-sa"
  display_name = "Service Account for Embed Cloud Function"
}

# Grant embed function read access to markdown-normalized bucket
resource "google_storage_bucket_iam_member" "embed_sa_markdown_bucket_viewer" {
  bucket = google_storage_bucket.markdown_normalized.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.embed_function_sa.email}"
}

# Grant embed function access to Vertex AI
resource "google_project_iam_member" "embed_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.embed_function_sa.email}"
}

# Grant embed function read access to pipeline bucket
resource "google_storage_bucket_iam_member" "embed_sa_pipeline_bucket_viewer" {
  bucket = google_storage_bucket.pipeline.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.embed_function_sa.email}"
}

# Grant embed function access to Firestore
resource "google_project_iam_member" "embed_sa_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.embed_function_sa.email}"
}

# Grant embed function logging permissions
resource "google_project_iam_member" "embed_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.embed_function_sa.email}"
}

# Archive the source code for the Embed Cloud Function
data "archive_file" "embed_source" {
  type        = "zip"
  source_dir  = "../src/embed"
  output_path = "/tmp/embed_source.zip"
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".DS_Store"
  ]
}

# Upload the embed function source code
resource "google_storage_bucket_object" "embed_source_zip" {
  name   = "embed_source.zip#${data.archive_file.embed_source.output_md5}"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.embed_source.output_path
}

# Cloud Function (2nd gen) for embedding and storage
resource "google_cloudfunctions2_function" "embed_function" {
  name     = "embed-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "embed"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.embed_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    timeout_seconds       = 540 // 9 minutes for large batches (271 files)
    available_memory      = "512Mi"
    service_account_email = google_service_account.embed_function_sa.email
    environment_variables = {
      GCP_PROJECT                     = var.project_id
      GCP_REGION                      = var.region
      VECTOR_SEARCH_INDEX_ENDPOINT    = google_vertex_ai_index_endpoint.kb_index_endpoint.name
      VECTOR_SEARCH_DEPLOYED_INDEX_ID = "kb_deployed_index"
      MARKDOWN_BUCKET                 = google_storage_bucket.markdown_normalized.name
      PIPELINE_BUCKET                 = google_storage_bucket.pipeline.name
      PIPELINE_COLLECTION             = "pipeline_items"
      PIPELINE_MANIFEST_PREFIX        = "manifests"
      EMBED_STALE_TIMEOUT_SECONDS     = "900" // 15 minutes
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_storage_bucket_iam_member.embed_sa_markdown_bucket_viewer,
    google_project_iam_member.embed_sa_aiplatform_user,
    google_project_iam_member.embed_sa_datastore_user,
    google_project_iam_member.embed_sa_log_writer,
    google_storage_bucket_iam_member.embed_sa_pipeline_bucket_viewer,
    google_vertex_ai_index_endpoint_deployed_index.kb_deployed_index,
    google_firestore_database.kb_database
  ]
}

# Grant workflow service account permission to invoke the embed function
resource "google_cloud_run_service_iam_member" "embed_function_workflow_invoker" {
  location = google_cloudfunctions2_function.embed_function.location
  service  = google_cloudfunctions2_function.embed_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.workflow_sa.email}"
}
