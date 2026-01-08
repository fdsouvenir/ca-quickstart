"""
Cloud Function: process-pmix

Processes PMIX PDFs when they land in Cloud Storage.
Triggered by GCS object finalized event.

Environment variables:
- PROJECT_ID: GCP project ID (default: fdsanalytics)
- BUCKET_NAME: GCS bucket name (default: fdsanalytics-pmix-uploads)
"""

import os
import re
import traceback
from datetime import datetime, date, timedelta

import functions_framework
import requests
from cloudevents.http import CloudEvent
from google.cloud import storage, bigquery
import google.cloud.logging

from pmix_parser import parse_pmix_pdf, validate_totals, extract_date_from_filename


# Configuration
PROJECT_ID = os.environ.get('PROJECT_ID', 'fdsanalytics')
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'fdsanalytics-pmix-uploads')

# PDF filename pattern
FILENAME_PATTERN = re.compile(r'^pmix-senso-(\d{4}-\d{2}-\d{2})\.pdf$')

# Initialize clients
storage_client = storage.Client(project=PROJECT_ID)
bq_client = bigquery.Client(project=PROJECT_ID)
logging_client = google.cloud.logging.Client(project=PROJECT_ID)
logger = logging_client.logger("pmix-import")


def log_info(message: str, **kwargs):
    """Log info-level structured event."""
    logger.log_struct({
        "severity": "INFO",
        "message": message,
        **kwargs
    })


def log_error(message: str, **kwargs):
    """Log error-level structured event."""
    logger.log_struct({
        "severity": "ERROR",
        "message": message,
        **kwargs
    })


def log_warning(message: str, **kwargs):
    """Log warning-level structured event."""
    logger.log_struct({
        "severity": "WARNING",
        "message": message,
        **kwargs
    })


def is_already_imported(report_date: str) -> bool:
    """Check if date already exists in import log."""
    query = f"""
        SELECT 1 FROM `{PROJECT_ID}.insights.pmix_import_log`
        WHERE report_date = '{report_date}'
        LIMIT 1
    """
    results = list(bq_client.query(query).result())
    return len(results) > 0


def log_import(file_name: str, report_date: str, status: str,
               record_count: int = None, total_sales: float = None,
               error_message: str = None):
    """Log import result to BigQuery."""
    row = {
        "file_name": file_name,
        "report_date": report_date,
        "processed_at": datetime.utcnow().isoformat(),
        "status": status,
        "record_count": record_count,
        "total_sales": total_sales,
        "error_message": error_message
    }

    table_ref = bq_client.dataset('insights').table('pmix_import_log')
    errors = bq_client.insert_rows_json(table_ref, [row])

    if errors:
        log_warning(f"Error writing to import log: {errors}", file_name=file_name)


def delete_existing_data(report_date: str):
    """Delete existing data for the date (idempotent reload)."""
    query = f"""
        DELETE FROM `{PROJECT_ID}.restaurant_analytics.item_sales`
        WHERE report_date = '{report_date}' AND location = 'senso-sushi'
    """
    bq_client.query(query).result()


def insert_records(records: list[dict]):
    """Insert records to BigQuery."""
    table_ref = bq_client.dataset('restaurant_analytics').table('item_sales')
    errors = bq_client.insert_rows_json(table_ref, records)

    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")


def delete_from_gcs(bucket_name: str, blob_name: str):
    """Delete file from GCS."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.delete()


def refresh_daily_summary():
    """Refresh ai.daily_summary table after import."""
    refresh_sql = """
    CREATE OR REPLACE TABLE `fdsanalytics.ai.daily_summary` AS
    SELECT
      report_date, location, location_name, region,
      SUM(quantity_sold) as total_quantity_sold,
      SUM(net_sales) as total_net_sales,
      SUM(discount) as total_discount,
      COUNT(DISTINCT item_name) as unique_items_sold,
      COUNT(*) as line_item_count,
      MAX(avg_temp_f) as avg_temp_f,
      MAX(max_temp_f) as max_temp_f,
      MAX(min_temp_f) as min_temp_f,
      MAX(precipitation_in) as precipitation_in,
      MAX(had_rain) as had_rain,
      MAX(had_snow) as had_snow,
      MAX(event_names) as event_names,
      MAX(event_types) as event_types,
      MAX(event_count) as event_count,
      MAX(has_local_event) as has_local_event,
      MAX(day_of_week) as day_of_week,
      MAX(day_name) as day_name,
      MAX(week_number) as week_number,
      MAX(month) as month,
      MAX(month_name) as month_name,
      MAX(year) as year,
      MAX(is_weekend) as is_weekend
    FROM `fdsanalytics.ai.restaurant_analytics`
    GROUP BY report_date, location, location_name, region
    """
    bq_client.query(refresh_sql).result()
    log_info("Refreshed ai.daily_summary")


def trigger_daily_report(report_date: str):
    """Trigger daily email report if imported date is yesterday."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if report_date != yesterday:
        print(f"Skipping email: {report_date} is not yesterday ({yesterday})")
        return

    # daily_summary already refreshed above, just trigger email
    # Trigger email function
    url = "https://us-central1-fdsanalytics.cloudfunctions.net/send-daily-report"
    try:
        response = requests.get(url, params={"test_date": report_date}, timeout=120)
        result = response.json()
        log_info(f"Email triggered: {result.get('status')}", report_date=report_date)
        print(f"Email triggered: {result.get('status')}")
    except Exception as e:
        log_error(f"Failed to trigger email: {e}", report_date=report_date)
        print(f"Failed to trigger email: {e}")


@functions_framework.cloud_event
def process_pmix(cloud_event: CloudEvent):
    """
    Cloud Function entry point.
    Triggered when a new file is uploaded to GCS.
    """
    data = cloud_event.data
    bucket_name = data["bucket"]
    blob_name = data["name"]
    file_name = os.path.basename(blob_name)

    print(f"Processing: gs://{bucket_name}/{blob_name}")

    # Only process files in incoming/
    if not blob_name.startswith("incoming/"):
        print(f"Skipping: not in incoming/ folder")
        return

    # Validate filename pattern
    match = FILENAME_PATTERN.match(file_name)
    if not match:
        log_warning(f"Invalid filename pattern: {file_name}", file_name=file_name)
        delete_from_gcs(bucket_name, blob_name)
        return

    report_date = match.group(1)

    # Check if already imported (idempotency)
    if is_already_imported(report_date):
        print(f"Already imported: {report_date}")
        delete_from_gcs(bucket_name, blob_name)
        return

    try:
        # Download PDF to /tmp
        tmp_path = f"/tmp/{file_name}"
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(tmp_path)
        print(f"Downloaded to: {tmp_path}")

        # Parse PDF
        records, grand_total = parse_pmix_pdf(tmp_path)

        if not records:
            raise ValueError("No records found in PDF")

        # Validate totals
        is_valid, validation_msg = validate_totals(records, grand_total)
        if not is_valid:
            raise ValueError(validation_msg)

        print(f"Parsed {len(records)} records, total: ${sum(r['net_sales'] for r in records):.2f}")

        # Delete existing data and insert new records
        delete_existing_data(report_date)
        insert_records(records)

        # Calculate totals for logging
        record_count = len(records)
        total_sales = sum(r['net_sales'] for r in records)

        # Log success
        log_import(file_name, report_date, 'success', record_count, total_sales)
        log_info(
            f"Imported {record_count} records for {report_date}",
            file_name=file_name,
            report_date=report_date,
            record_count=record_count,
            total_sales=total_sales
        )

        print(f"Success: {file_name} -> {record_count} records")

        # Always refresh daily_summary after successful import
        try:
            refresh_daily_summary()
        except Exception as e:
            log_error(f"Failed to refresh daily_summary: {e}")

        # Trigger daily email if this is yesterday's data
        trigger_daily_report(report_date)

    except Exception as e:
        # Log failure
        error_msg = f"{type(e).__name__}: {str(e)}"
        log_import(file_name, report_date, 'failed', error_message=error_msg)
        log_error(
            f"Failed to process {file_name}: {error_msg}",
            file_name=file_name,
            report_date=report_date,
            error=error_msg,
            traceback=traceback.format_exc()
        )

        print(f"Error: {file_name} - {error_msg}")

    finally:
        # Always delete from GCS (Drive is permanent store)
        try:
            delete_from_gcs(bucket_name, blob_name)
            print(f"Deleted from GCS: {blob_name}")
        except Exception as e:
            log_warning(f"Failed to delete from GCS: {e}", blob_name=blob_name)

        # Clean up temp file
        try:
            os.remove(tmp_path)
        except:
            pass
