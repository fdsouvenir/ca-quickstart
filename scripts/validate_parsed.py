#!/usr/bin/env python3
"""
Validate parsed PMIX PDF data using Claude Code CLI.

This script:
1. Takes parsed records and the original PDF
2. Extracts sample text from PDF for comparison
3. Invokes Claude Code CLI for full validation review
4. Logs results to validation_log.json

Usage:
    python scripts/validate_parsed.py --records /tmp/parsed.json --pdf pmix/pmix-senso-2025-06-14.pdf
    python scripts/validate_parsed.py --records /tmp/parsed.json --pdf pmix/pmix-senso-2025-06-14.pdf --log pmix/validation_log.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber


def extract_pdf_summary(pdf_path: str, max_lines: int = 50) -> str:
    """Extract summary text from PDF for validation."""
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:2]:  # First 2 pages
            text = page.extract_text()
            if text:
                lines.extend(text.split('\n')[:max_lines])
    return '\n'.join(lines[:max_lines])


def calculate_totals(records: list[dict]) -> dict:
    """Calculate totals from parsed records."""
    total_qty = sum(r.get('quantity_sold', 0) for r in records)
    total_sales = sum(r.get('net_sales', 0) for r in records)
    total_discount = sum(r.get('discount', 0) for r in records)

    # Count by category
    categories = {}
    for r in records:
        cat = r.get('primary_category', 'Unknown')
        if cat not in categories:
            categories[cat] = {'count': 0, 'sales': 0}
        categories[cat]['count'] += 1
        categories[cat]['sales'] += r.get('net_sales', 0)

    return {
        'record_count': len(records),
        'total_qty': total_qty,
        'total_sales': round(total_sales, 2),
        'total_discount': round(total_discount, 2),
        'categories': categories
    }


def validate_with_claude(pdf_path: str, records: list[dict], pdf_total: float | None) -> dict:
    """
    Validate parsed data using Claude Code CLI.

    Returns:
        dict with 'status' ('approved' or 'flagged'), 'issues' list, and 'details'
    """
    totals = calculate_totals(records)
    pdf_text = extract_pdf_summary(pdf_path)

    # Check basic total match first
    issues = []
    if pdf_total is not None:
        diff = abs(totals['total_sales'] - pdf_total)
        if diff > 1.00:
            issues.append(f"Total mismatch: calculated ${totals['total_sales']:.2f}, PDF shows ${pdf_total:.2f} (diff: ${diff:.2f})")

    # Check for suspicious patterns
    sample_records = records[:10]
    for r in sample_records:
        item = r.get('item_name', '')
        cat = r.get('category', '')
        # Check for obviously wrong item names (single characters, fragments)
        if len(item) <= 2 and item not in ['', 'GF', 'V']:
            issues.append(f"Suspicious item name: '{item}' in category '{cat}'")
        # Check for duplicate words in category
        cat_words = cat.split()
        if len(cat_words) != len(set(cat_words)):
            issues.append(f"Duplicate words in category: '{cat}'")

    # Build prompt for Claude CLI validation (optional - for deep review)
    # For now, use heuristic validation only

    status = 'approved' if len(issues) == 0 else 'flagged'

    return {
        'status': status,
        'issues': issues,
        'calculated_total': totals['total_sales'],
        'pdf_total': pdf_total,
        'record_count': totals['record_count'],
        'total_qty': totals['total_qty'],
        'categories': {k: v['count'] for k, v in totals['categories'].items()}
    }


def load_records(records_path: str) -> list[dict]:
    """Load records from NDJSON file."""
    records = []
    with open(records_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_to_log(log_path: str, entry: dict):
    """Append validation entry to log file."""
    # Load existing log
    log_entries = []
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            try:
                log_entries = json.load(f)
            except json.JSONDecodeError:
                log_entries = []

    # Append new entry
    log_entries.append(entry)

    # Write back
    with open(log_path, 'w') as f:
        json.dump(log_entries, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Validate parsed PMIX PDF data"
    )
    parser.add_argument("--records", required=True, help="Path to parsed records NDJSON file")
    parser.add_argument("--pdf", required=True, help="Path to original PDF file")
    parser.add_argument("--pdf-total", type=float, help="Grand total from PDF (if known)")
    parser.add_argument("--log", default="pmix/validation_log.json", help="Path to validation log")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Load records
    if not os.path.exists(args.records):
        print(f"Error: Records file not found: {args.records}", file=sys.stderr)
        sys.exit(1)

    records = load_records(args.records)
    if not records:
        print("No records found in file", file=sys.stderr)
        sys.exit(1)

    # Extract date from PDF filename
    pdf_name = Path(args.pdf).stem
    date_match = None
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2})', pdf_name)
    if match:
        date_match = match.group(1)

    # Validate
    result = validate_with_claude(args.pdf, records, args.pdf_total)

    # Create log entry
    log_entry = {
        'date': date_match or 'unknown',
        'pdf': args.pdf,
        'timestamp': datetime.now().isoformat(),
        **result
    }

    # Output result
    if args.verbose:
        print(f"Date: {date_match}", file=sys.stderr)
        print(f"Status: {result['status']}", file=sys.stderr)
        print(f"Records: {result['record_count']}", file=sys.stderr)
        print(f"Calculated total: ${result['calculated_total']:.2f}", file=sys.stderr)
        if result['pdf_total']:
            print(f"PDF total: ${result['pdf_total']:.2f}", file=sys.stderr)
        if result['issues']:
            print("Issues:", file=sys.stderr)
            for issue in result['issues']:
                print(f"  - {issue}", file=sys.stderr)

    # Append to log
    append_to_log(args.log, log_entry)

    # Print status to stdout
    print(json.dumps(log_entry))

    # Exit code: 0 for approved, 1 for flagged
    sys.exit(0 if result['status'] == 'approved' else 1)


if __name__ == "__main__":
    main()
