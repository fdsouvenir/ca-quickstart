#!/bin/bash
#
# Deploy PMIX PDF Pipeline, Daily Report, and Weather Pipeline to Google Cloud
#
# This script deploys the complete pipeline:
# PMIX Pipeline (Phases 1-8):
#   1. Creates GCS bucket
#   2. Creates BigQuery import log table
#   3. Bootstraps import log with existing data
#   4. Creates service account with permissions
#   5-7. Deploys Cloud Functions (sync-drive-to-gcs, process-pmix)
#   8. Creates Cloud Scheduler job for PMIX sync
#
# Daily Report (Phases 9-12):
#   9. Creates email report tables
#   10. Grants Secret Manager access
#   11. Deploys send-daily-report function
#   12. Creates Cloud Scheduler job for 7 AM CT daily report
#
# Weather Pipeline (Phases 13-15):
#   13. Creates weather tables (weather_forecast, weather_import_log, training views)
#   14. Deploys fetch-openmeteo-weather function
#   15. Creates Cloud Scheduler job for 5:45 AM CT weather fetch
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

# Note: --allow-unauthenticated because this is called by external webhook
# Security is handled via API key validation in the function code
gcloud functions deploy sync-drive-to-gcs \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$PROJECT_ROOT/cloud_functions/sync_drive_to_gcs" \
    --entry-point=sync_drive_to_gcs \
    --trigger-http \
    --allow-unauthenticated \
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
# Phase 9: Create Email Report Tables
# ============================================
echo -e "${YELLOW}Phase 9: Creating email report tables...${NC}"

bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/create_email_recipients.sql"
echo "Created email_recipients table"

bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/create_email_report_log.sql"
echo "Created email_report_log table"

# ============================================
# Phase 10: Grant Secret Manager Access
# ============================================
echo -e "${YELLOW}Phase 10: Granting Secret Manager access...${NC}"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

echo "Granted Secret Manager access"

# ============================================
# Phase 11: Deploy send-daily-report Function
# ============================================
echo -e "${YELLOW}Phase 11: Deploying send-daily-report function...${NC}"

# Note: --allow-unauthenticated because this is called by process-pmix function
# Duplicate email prevention is handled via email_report_log table
gcloud functions deploy send-daily-report \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$PROJECT_ROOT/cloud_functions/send_daily_report" \
    --entry-point=send_daily_report \
    --trigger-http \
    --allow-unauthenticated \
    --service-account=$SA_EMAIL \
    --memory=256MB \
    --timeout=120s \
    --set-env-vars="PROJECT_ID=$PROJECT_ID" \
    --project=$PROJECT_ID

echo "Deployed send-daily-report"

# ============================================
# Phase 12: Create Daily Report Scheduler Job
# ============================================
echo -e "${YELLOW}Phase 12: Creating daily report scheduler job...${NC}"

# Get function URL
REPORT_URL=$(gcloud functions describe send-daily-report \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format='value(serviceConfig.uri)')

# Delete existing job if exists
gcloud scheduler jobs delete daily-analytics-report \
    --location=$REGION \
    --project=$PROJECT_ID \
    --quiet 2>/dev/null || true

# Create scheduler job (7 AM CT = 13:00 UTC)
gcloud scheduler jobs create http daily-analytics-report \
    --location=$REGION \
    --schedule="0 13 * * *" \
    --time-zone="UTC" \
    --uri="$REPORT_URL" \
    --http-method=POST \
    --oidc-service-account-email=$SA_EMAIL \
    --project=$PROJECT_ID

echo "Created daily report scheduler job: 7 AM CT daily"

# ============================================
# Phase 13: Create Weather Tables
# ============================================
echo -e "${YELLOW}Phase 13: Creating weather tables...${NC}"

# Update local_weather schema (add new columns)
bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/update_local_weather_schema.sql" 2>/dev/null || echo "Schema already up to date or table doesn't exist yet"

# Create weather_forecast table
bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/create_weather_forecast_table.sql"
echo "Created weather_forecast table"

# Create weather_import_log table
bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/create_weather_import_log.sql"
echo "Created weather_import_log table"

# Create weather training views
bq query --nouse_legacy_sql --project_id=$PROJECT_ID < "$PROJECT_ROOT/schema/create_weather_training_views.sql"
echo "Created weather training views"

# ============================================
# Phase 14: Deploy fetch-openmeteo-weather Function
# ============================================
echo -e "${YELLOW}Phase 14: Deploying fetch-openmeteo-weather function...${NC}"

gcloud functions deploy fetch-openmeteo-weather \
    --gen2 \
    --runtime=python311 \
    --region=$REGION \
    --source="$PROJECT_ROOT/cloud_functions/fetch_openmeteo_weather" \
    --entry-point=main \
    --trigger-http \
    --no-allow-unauthenticated \
    --service-account=$SA_EMAIL \
    --memory=256MB \
    --timeout=120s \
    --set-env-vars="PROJECT_ID=$PROJECT_ID" \
    --project=$PROJECT_ID

echo "Deployed fetch-openmeteo-weather"

# ============================================
# Phase 15: Create Weather Fetch Scheduler Job
# ============================================
echo -e "${YELLOW}Phase 15: Creating weather fetch scheduler job...${NC}"

# Get function URL
WEATHER_URL=$(gcloud functions describe fetch-openmeteo-weather \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format='value(serviceConfig.uri)')

# Delete existing job if exists
gcloud scheduler jobs delete weather-daily-fetch \
    --location=$REGION \
    --project=$PROJECT_ID \
    --quiet 2>/dev/null || true

# Create scheduler job (5:45 AM CT = 11:45 UTC - 15 min before ML refresh)
gcloud scheduler jobs create http weather-daily-fetch \
    --location=$REGION \
    --schedule="45 11 * * *" \
    --time-zone="UTC" \
    --uri="$WEATHER_URL" \
    --http-method=POST \
    --oidc-service-account-email=$SA_EMAIL \
    --project=$PROJECT_ID

echo "Created weather fetch scheduler job: 5:45 AM CT daily"

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
echo "2. Set up SendGrid API key in Secret Manager:"
echo "   echo -n 'SG.your-api-key' | gcloud secrets create sendgrid-api-key --data-file=- --project=$PROJECT_ID"
echo ""
echo "3. Add email recipients:"
echo "   bq query --nouse_legacy_sql 'INSERT INTO \`$PROJECT_ID.insights.email_recipients\` (email, name, active) VALUES (\"you@example.com\", \"Your Name\", TRUE)'"
echo ""
echo "4. Backfill weather data from Open-Meteo:"
echo "   python scripts/backfill_openmeteo_weather.py --dry-run   # Preview"
echo "   python scripts/backfill_openmeteo_weather.py             # Execute"
echo ""
echo "5. Retrain BQML model with weather regressors:"
echo "   bq query --nouse_legacy_sql < schema/create_bqml_model.sql"
echo ""
echo "6. Test the weather fetch manually:"
echo "   curl \$(gcloud functions describe fetch-openmeteo-weather --region=$REGION --format='value(serviceConfig.uri)')"
echo ""
echo "7. Test the daily report manually:"
echo "   gcloud functions call send-daily-report --region=$REGION --project=$PROJECT_ID"
echo ""
echo "8. Monitor logs:"
echo "   gcloud logging read 'resource.labels.function_name=\"fetch-openmeteo-weather\"' --limit=10 --project=$PROJECT_ID"
echo "   gcloud logging read 'resource.labels.function_name=\"send-daily-report\"' --limit=10 --project=$PROJECT_ID"
echo ""
echo "9. Check weather import log:"
echo "   bq query --nouse_legacy_sql 'SELECT * FROM \`$PROJECT_ID.insights.weather_import_log\` ORDER BY processed_at DESC LIMIT 10'"
