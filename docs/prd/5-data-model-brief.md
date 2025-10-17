# 5. Data Model (Brief)
**Firestore `kb_items`**: Document ID = item_id, fields: title, url, tags, authors, created_at, updated_at, cluster_id[], similar_ids[], scores[].
**Firestore `kb_clusters`**: Document ID = cluster_id, fields: label, members[], parent_cluster?, related_clusters[], label_version.
**Cloud Storage**: `/raw/*.json`, `/markdown/notes/{id}.md`, `/cards/{id}.md`, `/graphs/graph.json`.
