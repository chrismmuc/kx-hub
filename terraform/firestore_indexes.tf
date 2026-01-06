# Firestore Indexes
# Note: Cluster index removed in Story 4.4 - clusters deprecated

# Epic 7: Async jobs composite index for recommendations_history
# Required for querying completed jobs by type, status, user, and date
resource "google_firestore_index" "async_jobs_history" {
  project    = var.project_id
  database   = "(default)"
  collection = "async_jobs"

  fields {
    field_path = "job_type"
    order      = "ASCENDING"
  }

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "user_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

# Epic 6: Article Ideas composite index for status filtering
# Required for list_ideas(status=...) queries
resource "google_firestore_index" "article_ideas_status" {
  project    = var.project_id
  database   = "(default)"
  collection = "article_ideas"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "suggested_at"
    order      = "DESCENDING"
  }
}
