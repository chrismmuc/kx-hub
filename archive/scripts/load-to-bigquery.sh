#!/bin/bash
# Load Readwise data into BigQuery for SQL analysis

set -e

PROJECT_ID="kx-hub"
DATASET="readwise"
TABLE="books"
BUCKET="gs://${PROJECT_ID}-raw-json"

echo "Creating BigQuery dataset and table..."

# Create dataset
bq mk --dataset --location=EU ${PROJECT_ID}:${DATASET} 2>/dev/null || echo "Dataset already exists"

# Create table with schema
bq mk --table \
  --time_partitioning_field=updated \
  --description="Readwise books and highlights" \
  ${PROJECT_ID}:${DATASET}.${TABLE} \
  user_book_id:INTEGER,title:STRING,author:STRING,source:STRING,category:STRING,highlights:STRING,updated:TIMESTAMP

# Load data from GCS
echo "Loading data from ${BUCKET}..."
bq load \
  --source_format=NEWLINE_DELIMITED_JSON \
  --autodetect \
  ${PROJECT_ID}:${DATASET}.${TABLE} \
  "${BUCKET}/*.json"

echo "✓ Data loaded to BigQuery!"
echo ""
echo "Query your data:"
echo "  https://console.cloud.google.com/bigquery?project=${PROJECT_ID}"
echo ""
echo "Example queries:"
echo "  SELECT source, COUNT(*) as count FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\` GROUP BY source"
echo "  SELECT title, author FROM \`${PROJECT_ID}.${DATASET}.${TABLE}\` LIMIT 10"
