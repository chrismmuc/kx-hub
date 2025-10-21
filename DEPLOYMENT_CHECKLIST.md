# Pre-Deployment Checklist for Story 1.1 - Daily Ingest

## ✅ Critical Issues RESOLVED

### 1. Missing GCP_PROJECT Environment Variable
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:138`
- **Fix:** Added environment variable to Cloud Function service config

### 2. Missing Required GCP APIs
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:2-16`
- **Fix:** Added `google_project_service` resource with all required APIs

### 3. Insufficient Storage Permissions
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:68-72`
- **Fix:** Changed from project-level objectCreator to bucket-scoped objectAdmin

### 4. Cloud Scheduler Missing Location
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:31`
- **Fix:** Added `region = var.region` to Cloud Scheduler

### 5. Archive Including Python Cache
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:93-97`
- **Fix:** Added excludes for __pycache__, *.pyc, .DS_Store

### 6. Cloud Function Missing Dependencies
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:149-155`
- **Fix:** Added depends_on for API enablement and IAM bindings

### 7. Missing Eventarc Invoker Permission
- **Status:** ✅ FIXED
- **Location:** `terraform/main.tf:82-86`
- **Fix:** Added roles/run.invoker IAM binding

---

## 📋 Pre-Deployment Verification Steps

### Step 1: Verify GCP Prerequisites
```bash
# Check you're authenticated
gcloud auth list

# Verify project
gcloud config get-value project

# Confirm billing is enabled
gcloud billing projects describe $(gcloud config get-value project)
```

### Step 2: Create Required Secrets
The Cloud Function requires a Readwise API key in Secret Manager:

```bash
# Create the secret (replace YOUR_READWISE_API_KEY)
echo -n "YOUR_READWISE_API_KEY" | gcloud secrets create readwise-api-key \
  --data-file=- \
  --replication-policy="automatic"

# Verify it was created
gcloud secrets versions access latest --secret="readwise-api-key"
```

### Step 3: Review Terraform Variables
Create a `terraform.tfvars` file:

```hcl
project_id = "your-gcp-project-id"
region     = "europe-west4"  # Or your preferred region
```

### Step 4: Run Terraform Plan
```bash
cd terraform

# Initialize (if not already done)
terraform init

# Create execution plan
terraform plan -out=tfplan

# Review the plan carefully
# Expected resources: ~15 resources to create
```

### Step 5: Verify Source Code
```bash
# Run unit tests
cd ..
python3 -m unittest discover -s tests -p "test_*.py" -v

# Expected: 2 tests passing
```

---

## 🚨 Known Limitations & Future Work

### Not Implemented (By Design)
1. **Reader API Integration**
   - Story mentions Reader API but only Readwise is implemented
   - Acknowledged in story documentation

2. **State Tracking**
   - `get_last_run_timestamp()` is hardcoded to 24 hours
   - Real implementation would use Firestore/state file

### Recommended but Not Critical
3. **Monitoring & Alerting**
   - No Cloud Monitoring metrics
   - No alerting on failures
   - **Recommendation:** Add after initial deployment

4. **Terraform Remote State**
   - No backend configured for state file
   - **Recommendation:** Add GCS backend before team deployment

5. **Labels & Tags**
   - Resources not labeled
   - **Recommendation:** Add for cost tracking

6. **Test Coverage**
   - Only 2 basic tests
   - Missing: pagination, rate limiting, edge cases
   - **Recommendation:** Expand test suite

---

## 🚀 Deployment Commands

### Deploy Infrastructure
```bash
cd terraform

# Apply the plan
terraform apply tfplan

# Or apply directly
terraform apply
```

### Verify Deployment
```bash
# Check Cloud Function was deployed
gcloud functions list --gen2

# Check Cloud Scheduler job
gcloud scheduler jobs list --location=europe-west4

# Check Pub/Sub topics
gcloud pubsub topics list

# Check Storage buckets
gcloud storage buckets list | grep -E "(raw-json|function-source)"

# Check pipeline manifests
gcloud storage ls gs://$PROJECT_ID-pipeline/manifests | head -n 10

# Inspect Firestore pipeline state
gcloud firestore documents list --collection-ids=pipeline_items --limit=5 \
  --format="table(name,fields.normalize_status.stringValue,fields.embedding_status.stringValue,updateTime)"
```

### Test the Function Manually
```bash
# Trigger the Cloud Scheduler job manually
gcloud scheduler jobs run daily-ingest-trigger-job --location=europe-west4

# Check Cloud Function logs
gcloud functions logs read ingest-function --gen2 --region=europe-west4 --limit=50
```

---

## 📊 Expected Behavior

### On Successful Run
1. Cloud Scheduler triggers at 2am UTC daily
2. Pub/Sub message sent to `daily-trigger` topic
3. Cloud Function executes
4. Fetches books from Readwise API (last 24 hours)
5. Stores each book as JSON in `{project}-raw-json` bucket
6. Publishes completion message to `daily-ingest` topic
7. Returns "OK"

### File Output
- Bucket: `{project-id}-raw-json`
- File pattern: `readwise-book-{user_book_id}.json`
- Each file contains one book with nested highlights

---

## 🔍 Troubleshooting

### Common Issues

**Issue:** `Error 403: Permission denied`
- **Solution:** Verify IAM permissions and wait 60 seconds for propagation

**Issue:** `Secret not found`
- **Solution:** Create `readwise-api-key` secret in Secret Manager

**Issue:** `Rate limited by Readwise API`
- **Solution:** Function has retry logic, but check API quota

**Issue:** `Cloud Function timeout`
- **Solution:** Current timeout is 60s (default), may need increase for large datasets

---

## 📝 Post-Deployment Tasks

1. Monitor first scheduled run (2am UTC)
2. Verify books appear in Cloud Storage bucket
3. Check Cloud Function metrics in Cloud Console
4. Set up Cloud Monitoring alerts for failures
5. Document any production issues
6. Update story status to "Complete"

---

## 📚 Documentation References

- Story: `docs/stories/1.1.story.md`
- Source: `src/ingest/main.py`
- Tests: `tests/test_ingest.py`
- Terraform: `terraform/main.tf`
- Readwise API: https://readwise.io/api_doku
