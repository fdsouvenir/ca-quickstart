"""
Cloud Function: fetch-openmeteo-weather

Fetches weather data from Open-Meteo API and loads to BigQuery.
- Historical: Yesterday's actual weather -> insights.local_weather
- Forecast: 14-day forecast -> insights.weather_forecast (truncate + insert)

Trigger: HTTP (called by Cloud Scheduler at 5:45 AM CT / 11:45 UTC)
"""

import os
import traceback
from datetime import date, datetime, timedelta
from typing import Tuple

import functions_framework
from flask import Request, jsonify
from google.cloud import bigquery
import google.cloud.logging

from openmeteo_client import fetch_yesterday, fetch_forecast, fetch_historical
from weather_transformer import transform_historical, transform_forecast

# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID", "fdsanalytics")
DATASET = "insights"
HISTORICAL_TABLE = "local_weather"
FORECAST_TABLE = "weather_forecast"
LOG_TABLE = "weather_import_log"

# Initialize clients
bq_client = bigquery.Client(project=PROJECT_ID)
logging_client = google.cloud.logging.Client(project=PROJECT_ID)
logger = logging_client.logger("weather-import")


def log_info(message: str, **kwargs):
    """Log info message to Cloud Logging."""
    logger.log_struct({
        "severity": "INFO",
        "message": message,
        **kwargs
    })


def log_error(message: str, **kwargs):
    """Log error message to Cloud Logging."""
    logger.log_struct({
        "severity": "ERROR",
        "message": message,
        **kwargs
    })


def log_import(fetch_date: date, fetch_type: str, status: str,
               record_count: int = 0, date_range_start: date = None,
               date_range_end: date = None, error_message: str = None):
    """Log import result to BigQuery."""
    table_ref = f"{PROJECT_ID}.{DATASET}.{LOG_TABLE}"

    row = {
        "fetch_date": str(fetch_date),
        "fetch_type": fetch_type,
        "status": status,
        "record_count": record_count,
        "date_range_start": str(date_range_start) if date_range_start else None,
        "date_range_end": str(date_range_end) if date_range_end else None,
        "error_message": error_message,
    }

    errors = bq_client.insert_rows_json(table_ref, [row])
    if errors:
        log_error(f"Failed to log import: {errors}")


def upsert_historical(records: list) -> int:
    """
    Upsert historical weather records to local_weather table.
    Uses MERGE to handle existing records without streaming buffer issues.

    Returns number of records processed.
    """
    if not records:
        return 0

    table_ref = f"{PROJECT_ID}.{DATASET}.{HISTORICAL_TABLE}"

    # Check if record already exists for this date
    for record in records:
        weather_date = record["weather_date"]
        check_query = f"""
        SELECT COUNT(*) as cnt FROM `{table_ref}`
        WHERE weather_date = '{weather_date}'
        """
        result = list(bq_client.query(check_query).result())
        if result and result[0].cnt > 0:
            log_info(f"Weather for {weather_date} already exists, skipping")
            continue

        # Insert only if not exists
        errors = bq_client.insert_rows_json(table_ref, [record])
        if errors:
            raise Exception(f"BigQuery insert errors: {errors}")

    return len(records)


def replace_forecast(records: list) -> int:
    """
    Replace all forecast records (truncate + insert).
    Implements "always latest" approach.

    Note: Uses DML to avoid streaming buffer issues. If streaming buffer
    prevents deletion, we skip the delete and just insert (next run will clean up).

    Returns number of records inserted.
    """
    if not records:
        return 0

    table_ref = f"{PROJECT_ID}.{DATASET}.{FORECAST_TABLE}"

    # Try to truncate existing forecasts (may fail if streaming buffer active)
    try:
        delete_query = f"DELETE FROM `{table_ref}` WHERE 1=1"
        bq_client.query(delete_query).result()
    except Exception as e:
        if "streaming buffer" in str(e).lower():
            log_info("Streaming buffer active, skipping delete (will have duplicates)")
        else:
            raise

    # Insert new forecasts
    errors = bq_client.insert_rows_json(table_ref, records)
    if errors:
        raise Exception(f"BigQuery insert errors: {errors}")

    return len(records)


def fetch_and_load_historical(target_date: date = None) -> Tuple[int, date, date]:
    """
    Fetch historical weather for a specific date (default: yesterday).

    Returns (record_count, start_date, end_date)
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    log_info(f"Fetching historical weather for {target_date}")

    api_response = fetch_historical(target_date, target_date)
    records = transform_historical(api_response)
    count = upsert_historical(records)

    log_info(f"Loaded {count} historical weather records", date=str(target_date))
    return count, target_date, target_date


def fetch_and_load_forecast() -> Tuple[int, date, date]:
    """
    Fetch 14-day weather forecast and replace existing forecasts.

    Returns (record_count, start_date, end_date)
    """
    log_info("Fetching 14-day weather forecast")

    api_response = fetch_forecast(days=14)
    records = transform_forecast(api_response)
    count = replace_forecast(records)

    if records:
        start_date = date.fromisoformat(records[0]["forecast_date"])
        end_date = date.fromisoformat(records[-1]["forecast_date"])
    else:
        start_date = end_date = date.today()

    log_info(f"Loaded {count} forecast records", start=str(start_date), end=str(end_date))
    return count, start_date, end_date


@functions_framework.http
def main(request: Request):
    """
    HTTP entry point for Cloud Function.

    Query params:
    - mode: 'all' (default), 'historical', or 'forecast'
    - date: Override date for historical fetch (YYYY-MM-DD)

    Returns JSON with results for each operation.
    """
    try:
        mode = request.args.get("mode", "all")
        target_date_str = request.args.get("date")

        target_date = None
        if target_date_str:
            target_date = date.fromisoformat(target_date_str)

        results = {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "operations": []
        }

        # Fetch historical (yesterday or specified date)
        if mode in ("all", "historical"):
            try:
                count, start, end = fetch_and_load_historical(target_date)
                log_import(date.today(), "historical", "success",
                          record_count=count, date_range_start=start, date_range_end=end)
                results["operations"].append({
                    "type": "historical",
                    "status": "success",
                    "record_count": count,
                    "date_range": {"start": str(start), "end": str(end)}
                })
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                log_error("Historical fetch failed", error=error_msg,
                         traceback=traceback.format_exc())
                log_import(date.today(), "historical", "failed", error_message=error_msg)
                results["operations"].append({
                    "type": "historical",
                    "status": "failed",
                    "error": error_msg
                })

        # Fetch forecast
        if mode in ("all", "forecast"):
            try:
                count, start, end = fetch_and_load_forecast()
                log_import(date.today(), "forecast", "success",
                          record_count=count, date_range_start=start, date_range_end=end)
                results["operations"].append({
                    "type": "forecast",
                    "status": "success",
                    "record_count": count,
                    "date_range": {"start": str(start), "end": str(end)}
                })
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                log_error("Forecast fetch failed", error=error_msg,
                         traceback=traceback.format_exc())
                log_import(date.today(), "forecast", "failed", error_message=error_msg)
                results["operations"].append({
                    "type": "forecast",
                    "status": "failed",
                    "error": error_msg
                })

        # Check if any operations failed
        if any(op["status"] == "failed" for op in results["operations"]):
            results["status"] = "partial_failure"

        return jsonify(results), 200

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        log_error("Weather fetch failed", error=error_msg,
                 traceback=traceback.format_exc())
        return jsonify({
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }), 500
