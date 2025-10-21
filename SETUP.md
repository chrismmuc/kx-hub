# Setup Guide for Story 1.1 - Daily Ingest

## Quick Start

Your configuration is ready! Follow these steps to deploy:

### 1. Run the Secret Setup Script

This will create the Readwise API key in Google Secret Manager:

```bash
./setup-secrets.sh
```

The script will:
- Set your GCP project to `kx-hub`
- Enable Secret Manager API
- Create the `readwise-api-key` secret
- Verify the secret was created

### 2. Deploy Infrastructure

```bash
cd terraform
terraform plan
terraform apply
```

This will create:
- Cloud Function for data ingestion
- Cloud Scheduler (runs daily at 2am UTC)
- Pub/Sub topics (daily-trigger, daily-ingest)
- Cloud Storage buckets (raw-json, function-source)
- IAM service accounts and permissions

### 3. Test the Deployment

```bash
# Trigger the scheduler job manually
gcloud scheduler jobs run daily-ingest-trigger-job --location=europe-west4

# View Cloud Function logs
gcloud functions logs read ingest-function --gen2 --region=europe-west4 --limit=50
```

### 4. Verify Data Ingestion

```bash
# Check if data was stored in Cloud Storage
gcloud storage ls gs://kx-hub-raw-json/

# Download and inspect a file
gcloud storage cat gs://kx-hub-raw-json/readwise-book-[ID].json
```

## Configuration Files

- `terraform/terraform.tfvars` - Contains your project ID and region
- `setup-secrets.sh` - Script to create secrets (contains sensitive data)

⚠️ **These files are in .gitignore and will NOT be committed to git.**

## Troubleshooting

### "Permission denied" errors
Wait 60 seconds for IAM permissions to propagate, then try again.

### "Secret not found"
Run `./setup-secrets.sh` to create the required secret.

### "API not enabled"
The Terraform will enable all required APIs automatically. Wait for the API enablement to complete (1-2 minutes).

## Next Steps

See `DEPLOYMENT_CHECKLIST.md` for detailed deployment documentation.
