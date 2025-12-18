# Monitoring and Alerting for MCP Remote Server
#
# This configuration sets up:
# - Log-based metrics for auth failures
# - Alert policies for 5xx errors
# - Notification channels

# Log-based metric for authentication failures
resource "google_logging_metric" "auth_failures" {
  project = var.project_id
  name    = "mcp_server_auth_failures"

  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.service_name}"
    jsonPayload.message=~"(Missing or invalid Authorization header|Invalid token attempt)"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "client_ip"
      value_type  = "STRING"
      description = "IP address of the client"
    }
  }

  label_extractors = {
    "client_ip" = "EXTRACT(jsonPayload.client_host)"
  }

  depends_on = [google_project_service.required_apis]
}

# Log-based metric for 5xx errors
resource "google_logging_metric" "server_errors" {
  project = var.project_id
  name    = "mcp_server_5xx_errors"

  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.service_name}"
    httpRequest.status>=500
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "status_code"
      value_type  = "STRING"
      description = "HTTP status code"
    }
  }

  label_extractors = {
    "status_code" = "EXTRACT(httpRequest.status)"
  }

  depends_on = [google_project_service.required_apis]
}

# Notification channel (email)
variable "alert_email" {
  description = "Email address for alerts"
  type        = string
  default     = ""
}

resource "google_monitoring_notification_channel" "email" {
  count = var.alert_email != "" ? 1 : 0

  project      = var.project_id
  display_name = "MCP Server Alerts Email"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.required_apis]
}

# Alert policy for sustained 5xx errors
resource "google_monitoring_alert_policy" "high_5xx_rate" {
  project      = var.project_id
  display_name = "MCP Server - High 5xx Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "5xx errors > 5/min for 5 minutes"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${var.service_name}\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.server_errors.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email[0].id] : []

  alert_strategy {
    auto_close = "86400s" # 24 hours
  }

  documentation {
    content = <<-EOT
      MCP Server is experiencing a high rate of 5xx errors.

      This could indicate:
      - Application crashes or bugs
      - Resource exhaustion (memory/CPU)
      - Dependency failures (Firestore, Vertex AI, Tavily API)

      Actions:
      1. Check Cloud Run logs for error details
      2. Review recent deployments
      3. Check service quotas and limits
      4. Verify external API connectivity

      Service: ${var.service_name}
      Region: ${var.region}
    EOT
  }

  depends_on = [google_logging_metric.server_errors]
}

# Alert policy for authentication failures
resource "google_monitoring_alert_policy" "high_auth_failure_rate" {
  project      = var.project_id
  display_name = "MCP Server - High Authentication Failure Rate"
  combiner     = "OR"

  conditions {
    display_name = "Auth failures > 10/min for 5 minutes"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${var.service_name}\" AND metric.type = \"logging.googleapis.com/user/${google_logging_metric.auth_failures.name}\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email[0].id] : []

  alert_strategy {
    auto_close = "86400s" # 24 hours
  }

  documentation {
    content = <<-EOT
      MCP Server is experiencing a high rate of authentication failures.

      This could indicate:
      - Brute force attack attempt
      - Misconfigured client
      - Token rotation issue

      Actions:
      1. Review Cloud Run logs for source IPs
      2. Consider implementing IP-based rate limiting if needed
      3. Verify client configuration
      4. Check if auth token was recently rotated

      Service: ${var.service_name}
      Region: ${var.region}
    EOT
  }

  depends_on = [google_logging_metric.auth_failures]
}

# Dashboard (optional, for visibility)
resource "google_monitoring_dashboard" "mcp_server" {
  project        = var.project_id
  dashboard_json = jsonencode({
    displayName = "MCP Server Monitoring"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "Request Rate"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${var.service_name}\" metric.type=\"run.googleapis.com/request_count\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_RATE"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "5xx Error Rate"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${var.service_name}\" metric.type=\"logging.googleapis.com/user/${google_logging_metric.server_errors.name}\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_RATE"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Request Latency (P95)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${var.service_name}\" metric.type=\"run.googleapis.com/request_latencies\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_DELTA"
                      crossSeriesReducer = "REDUCE_PERCENTILE_95"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Auth Failures"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${var.service_name}\" metric.type=\"logging.googleapis.com/user/${google_logging_metric.auth_failures.name}\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_RATE"
                    }
                  }
                }
              }]
            }
          }
        }
      ]
    }
  })

  depends_on = [
    google_logging_metric.auth_failures,
    google_logging_metric.server_errors
  ]
}
