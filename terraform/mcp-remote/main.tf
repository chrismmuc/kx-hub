# Terraform configuration for kx-hub Remote MCP Server
#
# This configuration deploys the MCP server to Google Cloud Run with:
# - Least-privilege service account
# - Bearer token authentication
# - Secrets management
# - Monitoring and alerting
#
# Security principles:
# - No public write access
# - Service account with minimal permissions
# - Secrets stored in Secret Manager
# - Authentication required on all requests

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region for Cloud Run deployment"
  type        = string
  default     = "us-central1"
}

variable "firestore_collection" {
  description = "Firestore collection name"
  type        = string
  default     = "kb_items"
}

variable "tavily_api_key" {
  description = "Tavily API key (will be stored in Secret Manager)"
  type        = string
  sensitive   = true
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "kx-hub-mcp-remote"
}

# Data sources
data "google_project" "project" {
  project_id = var.project_id
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "firestore.googleapis.com",
    "aiplatform.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

# Generate secure authentication token
resource "random_password" "mcp_auth_token" {
  length  = 48
  special = true
}

# Store MCP auth token in Secret Manager
resource "google_secret_manager_secret" "mcp_auth_token" {
  project   = var.project_id
  secret_id = "MCP_AUTH_TOKEN"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "mcp_auth_token" {
  secret      = google_secret_manager_secret.mcp_auth_token.id
  secret_data = random_password.mcp_auth_token.result
}

# Store Tavily API key in Secret Manager
resource "google_secret_manager_secret" "tavily_api_key" {
  project   = var.project_id
  secret_id = "TAVILY_API_KEY"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "tavily_api_key" {
  secret      = google_secret_manager_secret.tavily_api_key.id
  secret_data = var.tavily_api_key
}

# Create service account for MCP server
resource "google_service_account" "mcp_server" {
  project      = var.project_id
  account_id   = "mcp-server-remote"
  display_name = "MCP Server Remote Service Account"
  description  = "Least-privilege service account for remote MCP server on Cloud Run"
}

# Grant Firestore read permissions
resource "google_project_iam_member" "firestore_viewer" {
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Grant Secret Manager access
resource "google_secret_manager_secret_iam_member" "mcp_auth_token_access" {
  secret_id = google_secret_manager_secret.mcp_auth_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp_server.email}"
}

resource "google_secret_manager_secret_iam_member" "tavily_api_key_access" {
  secret_id = google_secret_manager_secret.tavily_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Grant Vertex AI access for embeddings and Gemini
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Deploy Cloud Run service
resource "google_cloud_run_v2_service" "mcp_server" {
  project  = var.project_id
  name     = var.service_name
  location = var.region

  template {
    service_account = google_service_account.mcp_server.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    timeout = "120s"

    containers {
      image = "gcr.io/${var.project_id}/${var.service_name}:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "TRANSPORT_MODE"
        value = "sse"
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      env {
        name  = "FIRESTORE_COLLECTION"
        value = var.firestore_collection
      }

      env {
        name = "MCP_AUTH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.mcp_auth_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "TAVILY_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.tavily_api_key.secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 8080
      }
    }

    max_instance_request_concurrency = 10
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.required_apis,
    google_secret_manager_secret_version.mcp_auth_token,
    google_secret_manager_secret_version.tavily_api_key
  ]
}

# Allow unauthenticated access (auth handled by Bearer token in app)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = google_cloud_run_v2_service.mcp_server.project
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Outputs
output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.mcp_server.uri
}

output "auth_token" {
  description = "MCP Authentication Token (keep secret!)"
  value       = random_password.mcp_auth_token.result
  sensitive   = true
}

output "service_account_email" {
  description = "Service account email"
  value       = google_service_account.mcp_server.email
}
