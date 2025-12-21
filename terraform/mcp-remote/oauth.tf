# OAuth 2.1 + Dynamic Client Registration Infrastructure for Claude Mobile/Web
#
# This configuration provisions:
# - JWT RSA key pair for access token signing
# - Secret Manager storage for OAuth secrets
# - Firestore indexes for OAuth clients and tokens
# - Environment variables for OAuth server
#
# Enable OAuth by setting OAUTH_ENABLED=true environment variable

# ==================== Variables ====================

variable "oauth_enabled" {
  description = "Enable OAuth 2.1 authentication for Claude Mobile/Web"
  type        = bool
  default     = false
}

variable "oauth_user_email" {
  description = "Authorized user email for single-user OAuth"
  type        = string
  default     = ""
}

variable "oauth_user_password_hash" {
  description = "Bcrypt hash of authorized user password"
  type        = string
  default     = ""
  sensitive   = true
}

variable "oauth_issuer_override" {
  description = "OAuth Issuer URL override (e.g., https://kx-hub-mcp-remote-xxx.run.app). If not set, the server will derive it from the request. Set this after first deployment to ensure consistent HTTPS issuer."
  type        = string
  default     = ""
}

# ==================== JWT RSA Key Pair Generation ====================

# Generate RSA private key for JWT signing
resource "tls_private_key" "oauth_jwt" {
  count       = var.oauth_enabled ? 1 : 0
  algorithm   = "RSA"
  rsa_bits    = 2048
}

# Store JWT private key in Secret Manager
resource "google_secret_manager_secret" "oauth_jwt_private_key" {
  count     = var.oauth_enabled ? 1 : 0
  project   = var.project_id
  secret_id = "oauth-jwt-private-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "oauth_jwt_private_key" {
  count       = var.oauth_enabled ? 1 : 0
  secret      = google_secret_manager_secret.oauth_jwt_private_key[0].id
  secret_data = tls_private_key.oauth_jwt[0].private_key_pem
}

# Store JWT public key in Secret Manager (for validation)
resource "google_secret_manager_secret" "oauth_jwt_public_key" {
  count     = var.oauth_enabled ? 1 : 0
  project   = var.project_id
  secret_id = "oauth-jwt-public-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "oauth_jwt_public_key" {
  count       = var.oauth_enabled ? 1 : 0
  secret      = google_secret_manager_secret.oauth_jwt_public_key[0].id
  secret_data = tls_private_key.oauth_jwt[0].public_key_pem
}

# ==================== Secret Manager IAM ====================

# Grant service account access to OAuth JWT keys
resource "google_secret_manager_secret_iam_member" "oauth_jwt_private_key_access" {
  count     = var.oauth_enabled ? 1 : 0
  secret_id = google_secret_manager_secret.oauth_jwt_private_key[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp_server.email}"
}

resource "google_secret_manager_secret_iam_member" "oauth_jwt_public_key_access" {
  count     = var.oauth_enabled ? 1 : 0
  secret_id = google_secret_manager_secret.oauth_jwt_public_key[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp_server.email}"
}

# ==================== Firestore OAuth Indexes ====================

# Single-field indexes are automatically created by Firestore
# No composite indexes needed for oauth_clients or oauth_tokens collections

# ==================== Outputs ====================

output "oauth_enabled" {
  description = "OAuth 2.1 authentication enabled status"
  value       = var.oauth_enabled
}

output "oauth_issuer" {
  description = "OAuth token issuer URL (service URL)"
  value       = var.oauth_enabled ? google_cloud_run_v2_service.mcp_server.uri : null
}

output "oauth_user_email" {
  description = "Authorized OAuth user email"
  value       = var.oauth_enabled ? var.oauth_user_email : null
}

output "oauth_setup_instructions" {
  description = "Instructions for OAuth setup in Claude.ai Web"
  value       = var.oauth_enabled ? format(<<-EOT
    ===================================
    OAuth 2.1 Setup Complete!
    ===================================

    To add kx-hub to Claude.ai Web/Mobile:

    1. Open Claude.ai Settings > Connectors
    2. Click "Add custom connector"
    3. Enter:
       - Name: kx-hub
       - Remote MCP Server URL: %s
    4. Leave OAuth Client ID and Secret EMPTY
       (Dynamic Client Registration will auto-configure)
    5. Click "Add"
    6. Claude will redirect to authorization page
    7. Enter password to authorize
    8. Done! kx-hub is now accessible on all devices

    Authorization URL: %s/authorize
    Token URL: %s/token
    DCR URL: %s/register

    ===================================
  EOT
  , google_cloud_run_v2_service.mcp_server.uri, google_cloud_run_v2_service.mcp_server.uri, google_cloud_run_v2_service.mcp_server.uri, google_cloud_run_v2_service.mcp_server.uri) : null
}
