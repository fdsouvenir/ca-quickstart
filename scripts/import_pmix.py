#!/usr/bin/env python3
"""
Bulk import PMIX PDFs to BigQuery.

This script:
1. Finds all PMIX PDF files in a directory
2. Parses each PDF using parse_pmix_pdf
3. Validates each parsed result (logs to validation_log.json)
4. Creates [CLOSED] placeholder rows for missing dates
5. Writes combined NDJSON file
6. Optionally loads to BigQuery (with delete of old data first)

Usage:
    # Dry run - parse all, show summary
    python scripts/import_pmix.py --pmix-dir pmix/ --dry-run

    # Full import
    python scripts/import_pmix.py --pmix-dir pmix/

    # Import specific date range
    python scripts/import_pmix.py --pmix-dir pmix/ --start-date 2025-06-01 --end-date 2025-06-30

    # Skip validation (faster)
    python scripts/import_pmix.py --pmix-dir pmix/ --skip-validation
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from glob import glob
from pathlib import Path

# Import the parser module
from parse_pmix_pdf import parse_pmix_pdf


def find_pdf_files(pmix_dir: str) -> dict[str, str]:
    """
    Find all PMIX PDF files and extract their dates.

    Returns:
        dict mapping date string (YYYY-MM-DD) to file path
    """
    pattern = os.path.join(pmix_dir, "pmix-senso-*.pdf")
    files = glob(pattern)

    date_pattern = re.compile(r'pmix-senso-(\d{4}-\d{2}-\d{2})\.pdf$')

    dates_to_files = {}
    for f in files:
        match = date_pattern.search(os.path.basename(f))
        if match:
            dates_to_files[match.group(1)] = f

    return dates_to_files


def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """Generate all dates between start and end (inclusive)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates


def create_closed_placeholder(date: str) -> dict:
    """Create a placeholder record for a closed/missing day."""
    return {
        "customer_id": "senso-sushi",
        "report_date": date,
        "primary_category": None,
        "category": None,
        "item_name": "[CLOSED]",
        "quantity_sold": 0,
        "net_sales": 0.0,
        "discount": 0.0
    }


def write_ndjson(records: list[dict], output_path: str):
    """Write records as newline-delimited JSON."""
    with open(output_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def validate_parsed(records: list[dict], grand_total: float | None, date: str, pdf_path: str,
                    log_path: str = "pmix/validation_log.json") -> dict:
    """
    Validate parsed records and log results.

    Returns dict with status ('approved' or 'flagged') and any issues.
    """
    issues = []

    # Calculate totals
    calculated_total = sum(r.get('net_sales', 0) for r in records)
    calculated_qty = sum(r.get('quantity_sold', 0) for r in records)

    # Check total match
    if grand_total is not None:
        diff = abs(calculated_total - grand_total)
        if diff > 1.00:
            issues.append(f"Total mismatch: calculated ${calculated_total:.2f}, PDF shows ${grand_total:.2f}")

    # Check for suspicious patterns in first 20 records
    for r in records[:20]:
        item = r.get('item_name', '')
        cat = r.get('category', '')

        # Single character item names (excluding known abbreviations)
        if len(item) <= 2 and item not in ['', 'GF', 'V', 'VG']:
            issues.append(f"Short item name: '{item}' in '{cat}'")

        # Duplicate words in category
        cat_words = cat.split()
        if len(cat_words) > 1 and len(cat_words) != len(set(cat_words)):
            issues.append(f"Duplicate words in category: '{cat}'")

    status = 'approved' if len(issues) == 0 else 'flagged'

    # Create log entry
    from collections import Counter
    cat_counts = Counter(r.get('primary_category', 'Unknown') for r in records)

    log_entry = {
        'date': date,
        'pdf': pdf_path,
        'timestamp': datetime.now().isoformat(),
        'status': status,
        'issues': issues[:10],  # Limit issues logged
        'calculated_total': round(calculated_total, 2),
        'pdf_total': grand_total,
        'record_count': len(records),
        'total_qty': calculated_qty,
        'categories': dict(cat_counts)
    }

    # Append to log file
    log_entries = []

    # Ensure directory exists
    log_dir = os.path.dirname(log_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                log_entries = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            log_entries = []

    log_entries.append(log_entry)

    with open(log_path, 'w') as f:
        json.dump(log_entries, f, indent=2)

    return log_entry


def run_bq_command(cmd: str, dry_run: bool = False) -> bool:
    """Run a bq command."""
    if dry_run:
        print(f"[DRY RUN] Would execute: {cmd}")
        return True

    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        return False

    if result.stdout:
        print(result.stdout)

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Bulk import PMIX PDFs to BigQuery"
    )
    parser.add_argument("--pmix-dir", required=True, help="Directory containing PMIX PDFs")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD), defaults to earliest PDF")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD), defaults to latest PDF")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't load to BigQuery")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--output", help="Output NDJSON file path (default: temp file)")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation step (faster)")
    parser.add_argument("--validation-log", default="pmix/validation_log.json", help="Validation log file path")

    args = parser.parse_args()

    # Find all PDF files
    print(f"Scanning {args.pmix_dir} for PMIX PDFs...")
    dates_to_files = find_pdf_files(args.pmix_dir)

    if not dates_to_files:
        print("No PMIX PDF files found!", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(dates_to_files)} PDF files")

    # Determine date range
    all_dates = sorted(dates_to_files.keys())
    start_date = args.start_date or all_dates[0]
    end_date = args.end_date or all_dates[-1]

    print(f"Date range: {start_date} to {end_date}")

    # Generate all expected dates
    expected_dates = generate_date_range(start_date, end_date)
    dates_with_pdfs = set(dates_to_files.keys())

    print(f"Expected dates: {len(expected_dates)}")
    print(f"Dates with PDFs: {len(dates_with_pdfs)}")
    print(f"Missing dates: {len(expected_dates) - len(dates_with_pdfs & set(expected_dates))}")

    # Clear validation log if it exists
    if not args.skip_validation and os.path.exists(args.validation_log):
        os.remove(args.validation_log)

    # Process all dates
    all_records = []
    total_qty = 0
    total_sales = 0.0
    parsed_count = 0
    closed_count = 0
    error_count = 0
    flagged_count = 0

    for date in expected_dates:
        if date in dates_with_pdfs:
            # Parse PDF
            pdf_path = dates_to_files[date]
            if args.verbose:
                print(f"Parsing: {pdf_path}")

            try:
                records, grand_total = parse_pmix_pdf(pdf_path, verbose=False)

                if records:
                    # Validate if not skipped
                    if not args.skip_validation:
                        validation = validate_parsed(records, grand_total, date, pdf_path, args.validation_log)
                        if validation['status'] == 'flagged':
                            flagged_count += 1
                            if args.verbose:
                                print(f"  {date}: FLAGGED - {validation['issues'][:2]}")

                    all_records.extend(records)
                    day_qty = sum(r["quantity_sold"] for r in records)
                    day_sales = sum(r["net_sales"] for r in records)
                    total_qty += day_qty
                    total_sales += day_sales
                    parsed_count += 1

                    if args.verbose:
                        print(f"  {date}: {len(records)} items, {day_qty} qty, ${day_sales:.2f}")
                else:
                    # PDF exists but no data - treat as closed
                    all_records.append(create_closed_placeholder(date))
                    closed_count += 1
                    if args.verbose:
                        print(f"  {date}: No data (closed)")
            except Exception as e:
                print(f"Error parsing {pdf_path}: {e}", file=sys.stderr)
                error_count += 1
                # Create placeholder for error case
                all_records.append(create_closed_placeholder(date))
        else:
            # No PDF - create closed placeholder
            all_records.append(create_closed_placeholder(date))
            closed_count += 1
            if args.verbose:
                print(f"  {date}: No PDF (closed)")

    # Summary
    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"Total records: {len(all_records)}")
    print(f"Days parsed: {parsed_count}")
    print(f"Days closed/missing: {closed_count}")
    print(f"Errors: {error_count}")
    if not args.skip_validation:
        print(f"Flagged for review: {flagged_count}")
    print(f"Total quantity: {total_qty}")
    print(f"Total sales: ${total_sales:,.2f}")
    if not args.skip_validation:
        print(f"Validation log: {args.validation_log}")

    if args.dry_run:
        print()
        print("[DRY RUN] No data loaded to BigQuery")

        # Optionally write output file
        if args.output:
            write_ndjson(all_records, args.output)
            print(f"Wrote {len(all_records)} records to {args.output}")

        return

    # Write NDJSON to temp file or specified output
    if args.output:
        output_path = args.output
    else:
        fd, output_path = tempfile.mkstemp(suffix='.json')
        os.close(fd)

    write_ndjson(all_records, output_path)
    print(f"Wrote {len(all_records)} records to {output_path}")

    # Delete existing data for date range
    delete_sql = f"""
        DELETE FROM `fdsanalytics.insights.top_items`
        WHERE report_date BETWEEN '{start_date}' AND '{end_date}'
        AND customer_id = 'senso-sushi'
    """

    print()
    print("Deleting existing data...")
    if not run_bq_command(f'bq query --nouse_legacy_sql "{delete_sql}"'):
        print("Failed to delete existing data", file=sys.stderr)
        sys.exit(1)

    # Load new data
    print()
    print("Loading new data...")
    load_cmd = f'bq load --source_format=NEWLINE_DELIMITED_JSON fdsanalytics:insights.top_items {output_path}'
    if not run_bq_command(load_cmd):
        print("Failed to load data", file=sys.stderr)
        sys.exit(1)

    # Clean up temp file
    if not args.output:
        os.remove(output_path)

    print()
    print("Import complete!")
    print(f"Loaded {len(all_records)} records for {start_date} to {end_date}")


if __name__ == "__main__":
    main()
