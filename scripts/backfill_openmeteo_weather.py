#!/usr/bin/env python3
"""
Backfill historical weather data from Open-Meteo.
Replaces all NOAA GSOD data with Open-Meteo data for consistency.

Usage:
    python scripts/backfill_openmeteo_weather.py --dry-run
    python scripts/backfill_openmeteo_weather.py
    python scripts/backfill_openmeteo_weather.py --start-date 2024-01-01 --end-date 2025-12-31

This script:
1. Fetches historical weather from Open-Meteo Archive API
2. Transforms to BigQuery schema
3. Truncates existing local_weather table
4. Inserts all new records
5. Logs the operation to weather_import_log
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add cloud_functions to path so we can reuse the transformer
sys.path.insert(0, str(Path(__file__).parent.parent / "cloud_functions" / "fetch_openmeteo_weather"))

from openmeteo_client import fetch_date_range
from weather_transformer import merge_historical_responses

from google.cloud import bigquery

PROJECT_ID = "fdsanalytics"
DATASET = "insights"
TABLE = "local_weather"
LOG_TABLE = "weather_import_log"


def get_date_range_from_sales(bq_client: bigquery.Client) -> tuple:
    """Get min/max dates from item_sales table."""
    query = """
    SELECT
        MIN(report_date) as min_date,
        MAX(report_date) as max_date
    FROM `fdsanalytics.restaurant_analytics.item_sales`
    """
    result = list(bq_client.query(query).result())
    if result:
        return result[0].min_date, result[0].max_date
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Backfill weather data from Open-Meteo")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't load to BigQuery")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    bq_client = bigquery.Client(project=PROJECT_ID)

    # Determine date range
    if args.start_date and args.end_date:
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date)
    else:
        # Get date range from sales data
        print("Determining date range from item_sales table...")
        min_date, max_date = get_date_range_from_sales(bq_client)
        if not min_date:
            print("ERROR: No sales data found")
            sys.exit(1)

        # Extend range slightly for context
        start_date = min_date - timedelta(days=7)
        end_date = min(max_date, date.today() - timedelta(days=1))  # Can't get today's archive data

    print(f"Date range: {start_date} to {end_date}")
    print(f"Days to fetch: {(end_date - start_date).days + 1}")

    # Fetch from Open-Meteo
    print("\nFetching weather data from Open-Meteo Archive API...")
    print("(This may take a moment for large date ranges)")

    try:
        responses = fetch_date_range(start_date, end_date)
        records = merge_historical_responses(responses)
    except Exception as e:
        print(f"ERROR: Failed to fetch weather data: {e}")
        sys.exit(1)

    print(f"Fetched {len(records)} weather records")

    if args.verbose:
        print("\nSample records:")
        for record in records[:3]:
            print(f"  {record['weather_date']}: {record['avg_temp_f']:.1f}°F, "
                  f"precip={record['precipitation_in']:.2f}in, "
                  f"condition={record['weather_condition']}")
        if len(records) > 3:
            print(f"  ... and {len(records) - 3} more")

    if args.dry_run:
        print("\n[DRY RUN] Would load to BigQuery:")
        print(f"  - Truncate {PROJECT_ID}.{DATASET}.{TABLE}")
        print(f"  - Insert {len(records)} records")
        print(f"  - Log to {PROJECT_ID}.{DATASET}.{LOG_TABLE}")
        return

    # Load to BigQuery
    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"

    print(f"\nDropping and recreating {table_ref}...")
    # Drop table to avoid streaming buffer issues
    drop_query = f"DROP TABLE IF EXISTS `{table_ref}`"
    bq_client.query(drop_query).result()

    # Recreate table with schema
    create_query = f"""
    CREATE TABLE `{table_ref}` (
        weather_date DATE NOT NULL,
        avg_temp_f FLOAT64,
        max_temp_f FLOAT64,
        min_temp_f FLOAT64,
        precipitation_in FLOAT64,
        had_rain BOOL,
        had_snow BOOL,
        visibility_miles FLOAT64,
        wind_speed_knots FLOAT64,
        wind_speed_mph FLOAT64,
        wind_gust_mph FLOAT64,
        weather_code INT64,
        weather_condition STRING,
        cloud_cover_pct INT64,
        humidity_pct INT64,
        uv_index FLOAT64
    )
    """
    bq_client.query(create_query).result()

    print(f"Inserting {len(records)} records...")
    errors = bq_client.insert_rows_json(table_ref, records)
    if errors:
        print(f"ERROR: BigQuery insert failed: {errors}")
        # Log failure
        log_row = {
            "fetch_date": str(date.today()),
            "fetch_type": "backfill",
            "status": "failed",
            "error_message": str(errors)[:1000]
        }
        bq_client.insert_rows_json(f"{PROJECT_ID}.{DATASET}.{LOG_TABLE}", [log_row])
        sys.exit(1)

    # Log success
    log_row = {
        "fetch_date": str(date.today()),
        "fetch_type": "backfill",
        "status": "success",
        "record_count": len(records),
        "date_range_start": str(start_date),
        "date_range_end": str(end_date)
    }
    bq_client.insert_rows_json(f"{PROJECT_ID}.{DATASET}.{LOG_TABLE}", [log_row])

    print(f"\nBackfill complete!")
    print(f"  Records loaded: {len(records)}")
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Table: {table_ref}")


if __name__ == "__main__":
    main()
