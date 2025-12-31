#!/bin/bash
#
# Deploy PMIX PDF Pipeline to Google Cloud
#
# This script deploys the complete pipeline:
# 1. Creates GCS bucket
# 2. Creates BigQuery import log table
# 3. Bootstraps import log with existing data
# 4. Creates service account with permissions
# 5. Deploys Cloud Functions
# 6. Creates Cloud Scheduler job
#
# Prerequisites:
# - gcloud CLI authenticated
# - Project set to fdsanalytics
#
# Usage:
#   ./deploy/deploy_cloud_functions.sh
#
# After deployment, share the Drive folder with:
#   pmix-processor@fdsanalytics.iam.gserviceaccount.com

set -e  # Exit on error

# Configuration
PROJECT_ID="fdsanalytics"
REGION="us-central1"
BUCKET_NAME="fdsanalytics-pmix-uploads"
SERVICE_ACCOUNT="pmix-processor"
DRIVE_FOLDER_ID="1MPXgywD-TvvsB1bFVDQ3CocujcF8ucia"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PMIX Pipeline Deployment ===${NC}"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ============================================
# Phase 1: Enable APIs
# ============================================
echo -e "${YELLOW}Phase 1: Enabling APIs...${NC}"

gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    eventarc.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    storage.googleapis.com \
    bigquery.googleapis.com \
    drive.googleapis.com \
    logging.googleapis.com \
    --project=$PROJECT_ID

echo "APIs enabled"

# ============================================
# Phase 2: Create GCS Bucket
# ============================================
echo -e "${YELLOW}Phase 2: Creating GCS bucket...${NC}"

if gsutil ls -b gs://$BUCKET_NAME 2>/dev/null; then
    echo "Bucket already exists: gs://$BUCKET_NAME"
else
    gsutil mb -p $PROJECT_ID -l $REGION gs://$BUCKET_NAME
    echo "Created bucket: gs://$BUCKET_NAME"
fi

# Create incoming folder
echo "placeholder" | gsutil cp - gs://$BUCKET_NAME/incoming/.keep
echo "Created incoming/ folder"

# ============================================
# Phase 3: Create Import Log Table
# ============================================
echo -e "${YELLOW}Phase 3: Creating import log table...${NC}"

bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/create_import_log.sql"
echo "Created import log table"

# ============================================
# Phase 4: Bootstrap Import Log
# ============================================
echo -e "${YELLOW}Phase 4: Bootstrapping import log with existing data...${NC}"

# Check if import log is empty
EXISTING_COUNT=$(bq query --nouse_legacy_sql --format=csv --project_id=$PROJECT_ID \
    "SELECT COUNT(*) FROM \`$PROJECT_ID.insights.pmix_import_log\`" 2>/dev/null | tail -1)

if [ "$EXISTING_COUNT" == "0" ]; then
    bq query --nouse_legacy_sql --project_id=$PROJECT_ID "
        INSERT INTO \`$PROJECT_ID.insights.pmix_import_log\` (file_name, report_date, status, record_count, total_sales)
        SELECT
            CONCAT('pmix-senso-', CAST(report_date AS STRING), '.pdf') AS file_name,
            report_date,
            'success' AS status,
            COUNT(*) AS record_count,
            SUM(net_sales) AS total_sales
        FROM \`$PROJECT_ID.restaurant_analytics.item_sales\`
        WHERE location = 'senso-sushi'
        GROUP BY report_date;
    "
    echo "Bootstrapped import log with existing data"
else
    echo "Import log already has $EXISTING_COUNT records, skipping bootstrap"
fi

# ============================================
# Phase 5: Create Service Account
# ============================================
echo -e "${YELLOW}Phase 5: Creating service account...${NC}"

SA_EMAIL="$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID 2>/dev/null; then
    echo "Service account already exists: $SA_EMAIL"
else
    gcloud iam service-accounts create $SERVICE_ACCOUNT \
        --display-name="PMIX PDF Processor" \
        --project=$PROJECT_ID
    echo "Created service account: $SA_EMAIL"
fi

# Grant BigQuery permissions
echo "Granting BigQuery permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/bigquery.dataEditor" \
    --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/bigquery.jobUser" \
    --quiet

# Grant Storage permissions
echo "Granting Storage permissions..."
gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://$BUCKET_NAME

# Grant Logging permissions
echo "Granting Logging permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/logging.logWriter" \
    --quiet

# Grant Eventarc permissions
echo "Granting Eventarc permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/eventarc.eventReceiver" \
    --quiet

# Grant Cloud Run invoker for scheduler
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/run.invoker" \
    --quiet

echo "Permissions granted"

# ============================================
# Phase 6: Deploy sync-drive-to-gcs Function
# ============================================
echo -e "${YELLOW}Phase 6: Deploying sync-drive-to-gcs function...${NC}"

gcloud functions deploy sync-drive-to-gcs \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$PROJECT_ROOT/cloud_functions/sync_drive_to_gcs" \
    --entry-point=sync_drive_to_gcs \
    --trigger-http \
    --no-allow-unauthenticated \
    --service-account=$SA_EMAIL \
    --memory=256MB \
    --timeout=300s \
    --set-env-vars="DRIVE_FOLDER_ID=$DRIVE_FOLDER_ID,BUCKET_NAME=$BUCKET_NAME,PROJECT_ID=$PROJECT_ID" \
    --project=$PROJECT_ID

echo "Deployed sync-drive-to-gcs"

# ============================================
# Phase 7: Deploy process-pmix Function
# ============================================
echo -e "${YELLOW}Phase 7: Deploying process-pmix function...${NC}"

# Get the GCS service agent for Eventarc
GCS_SA="service-$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')@gs-project-accounts.iam.gserviceaccount.com"

# Grant pubsub.publisher to GCS service account for Eventarc
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$GCS_SA" \
    --role="roles/pubsub.publisher" \
    --quiet

gcloud functions deploy process-pmix \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$PROJECT_ROOT/cloud_functions/process_pmix" \
    --entry-point=process_pmix \
    --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
    --trigger-event-filters="bucket=$BUCKET_NAME" \
    --trigger-location=$REGION \
    --service-account=$SA_EMAIL \
    --memory=512MB \
    --timeout=300s \
    --set-env-vars="PROJECT_ID=$PROJECT_ID,BUCKET_NAME=$BUCKET_NAME" \
    --project=$PROJECT_ID

echo "Deployed process-pmix"

# ============================================
# Phase 8: Create Cloud Scheduler Job
# ============================================
echo -e "${YELLOW}Phase 8: Creating Cloud Scheduler job...${NC}"

# Get function URL
SYNC_URL=$(gcloud functions describe sync-drive-to-gcs \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format='value(serviceConfig.uri)')

# Delete existing job if exists
gcloud scheduler jobs delete sync-pmix-from-drive \
    --location=$REGION \
    --project=$PROJECT_ID \
    --quiet 2>/dev/null || true

# Create scheduler job (every 15 minutes)
gcloud scheduler jobs create http sync-pmix-from-drive \
    --location=$REGION \
    --schedule="*/15 * * * *" \
    --uri="$SYNC_URL" \
    --http-method=POST \
    --oidc-service-account-email=$SA_EMAIL \
    --project=$PROJECT_ID

echo "Created scheduler job: every 15 minutes"

# ============================================
# Complete
# ============================================
echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Share the Google Drive folder with the service account:"
echo "   ${YELLOW}$SA_EMAIL${NC}"
echo "   (Grant Viewer access)"
echo ""
echo "2. Test the sync manually:"
echo "   gcloud functions call sync-drive-to-gcs --region=$REGION --project=$PROJECT_ID"
echo ""
echo "3. Monitor logs:"
echo "   gcloud logging read 'resource.type=\"cloud_function\" AND resource.labels.function_name=\"process-pmix\"' --limit=20 --project=$PROJECT_ID"
echo ""
echo "4. Check import log:"
echo "   bq query --nouse_legacy_sql 'SELECT * FROM \`$PROJECT_ID.insights.pmix_import_log\` ORDER BY processed_at DESC LIMIT 10'"
