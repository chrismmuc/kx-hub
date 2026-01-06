# Firestore Indexes
# Note: Cluster index removed in Story 4.4 - clusters deprecated

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
