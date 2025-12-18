#!/usr/bin/env python3
"""
Parse a single PMIX PDF file and output item records as NDJSON.

This parser uses a hybrid approach to handle two PDF formats:
- Old format (Dec 2024 - Mar 2025): Table extraction with clean columns
- New format (Apr 2025+): Word position extraction for multi-line items

Usage:
    python scripts/parse_pmix_pdf.py pmix/pmix-senso-2025-06-14.pdf
    python scripts/parse_pmix_pdf.py pmix/pmix-senso-2025-06-14.pdf --output /tmp/items.json
    python scripts/parse_pmix_pdf.py pmix/pmix-senso-2025-06-14.pdf -v
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber


def parse_currency(value: str) -> float:
    """Parse currency string like '$ 1,234.56' or '$1,234.56' to float."""
    if not value:
        return 0.0
    # Remove $ and spaces, then parse
    cleaned = value.replace('$', '').replace(',', '').replace(' ', '').strip()
    if not cleaned:
        return 0.0
    return float(cleaned)


def parse_quantity(value: str) -> int:
    """Parse quantity string like '7.00' or '7' to int."""
    if not value:
        return 0
    cleaned = value.strip()
    if not cleaned:
        return 0
    return int(float(cleaned))


def extract_date_from_filename(pdf_path: str) -> str:
    """Extract date from filename like 'pmix-senso-2025-06-14.pdf' -> '2025-06-14'."""
    filename = Path(pdf_path).stem
    match = re.search(r'(\d{4}-\d{2}-\d{2})$', filename)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract date from filename: {filename}")


def find_data_table(pdf) -> list | None:
    """
    Find the main data table in the PDF (old format only).

    Returns the combined table rows from all pages, or None if no data table found.
    """
    all_rows = []

    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if len(table) > 10:
                # Check if this looks like a data table
                # Should have rows with category/item structure
                for row in table:
                    if row and len(row) >= 8:
                        # Check for data-like content
                        if row[0] and (row[0].startswith('(') or
                                      row[2] and re.match(r'[\d.]+', str(row[2]))):
                            all_rows.extend(table)
                            break
                break  # Only one data table per page

    return all_rows if all_rows else None


def parse_from_table(table_rows: list, report_date: str, verbose: bool = False) -> tuple[list[dict], float | None]:
    """
    Parse records from table extraction (old format).

    Table columns: [category, item_name, qty, net_sales, avg_price, discount, pct_net, pct_cat]
    Note: Old format has no Refunds column - net_sales is column index 3
    """
    records = []
    current_primary_category = None
    grand_total_from_pdf = None

    for row in table_rows:
        if not row or len(row) < 8:
            continue

        cell0 = str(row[0] or '').strip()
        cell1 = str(row[1] or '').strip() if row[1] else ''

        # Skip header rows and extract embedded category
        if 'Menu Group' in cell0 or 'Category' in cell0:
            # Check for embedded primary category in header row
            # Format: "Category Item\n(Beer)" or "Category\n(Food)"
            if '\n' in cell0:
                for part in cell0.split('\n'):
                    part = part.strip()
                    if part.startswith('(') and part.endswith(')'):
                        current_primary_category = part
                        if verbose:
                            print(f"    Primary category (from header): {current_primary_category}", file=sys.stderr)
                        break
            continue

        # Check for category headers embedded in cell0
        # Format: "(Category)\nsubcategory item..." or just "(Category)"
        if '\n' in cell0 and cell0.startswith('('):
            # Split embedded header
            parts = cell0.split('\n', 1)
            header_part = parts[0].strip()
            if header_part.startswith('(') and header_part.endswith(')'):
                current_primary_category = header_part
                if verbose:
                    print(f"    Primary category (embedded): {current_primary_category}", file=sys.stderr)
            continue

        # Primary category header row - starts and ends with parentheses
        if cell0.startswith('(') and cell0.endswith(')'):
            current_primary_category = cell0
            if verbose:
                print(f"    Primary category: {current_primary_category}", file=sys.stderr)
            continue

        # Grand Total row
        if 'Grand Total' in cell0:
            # Old format: net_sales is at index 3
            grand_total_from_pdf = parse_currency(str(row[3]) if row[3] else '0')
            if verbose:
                print(f"    Grand Total: ${grand_total_from_pdf:.2f}", file=sys.stderr)
            continue

        # Skip if no quantity data
        qty_str = str(row[2]) if row[2] else ''
        if not qty_str or not re.match(r'[\d.]+', qty_str):
            continue

        # Check for 100% category sales (last column) - indicates category subtotal
        pct_cat = str(row[7]).strip() if len(row) > 7 and row[7] else ''
        is_category_subtotal = pct_cat == '100.00%'

        # Skip category subtotal rows (100% category sales AND no item name)
        # This catches category headers like "Gift Card" that aren't parenthesized
        if is_category_subtotal and not cell1:
            if verbose:
                print(f"    Skipping subtotal (no item): {cell0}", file=sys.stderr)
            continue

        # Regular item row
        category = cell0  # Menu group
        item_name = cell1  # Item name

        # Old format columns: [category, item, qty, net_sales, avg_price, discount, pct_net, pct_cat]
        qty = parse_quantity(qty_str)
        net_sales = parse_currency(str(row[3]) if row[3] else '0')
        discount = parse_currency(str(row[5]) if len(row) > 5 and row[5] else '0')

        record = {
            "customer_id": "senso-sushi",
            "report_date": report_date,
            "primary_category": current_primary_category,
            "category": category,
            "item_name": item_name,
            "quantity_sold": qty,
            "net_sales": round(net_sales, 2),
            "discount": round(discount, 2)
        }
        records.append(record)

    return records, grand_total_from_pdf


def parse_from_words(pdf, report_date: str, verbose: bool = False) -> tuple[list[dict], float | None]:
    """
    Parse records using word position extraction (new format).

    Column boundaries (x positions):
    - Category (menu group): x < 85 (narrowed from 100 to exclude wrapped item names)
    - Item name: 85 <= x < 185 (widened to include wrapped text starting at ~89)
    - Quantity: 185 <= x < 220
    - Refunds, Net Sales, etc: x >= 220
    """
    records = []
    current_primary_category = None
    grand_total_from_pdf = None

    for page_num, page in enumerate(pdf.pages, 1):
        words = page.extract_words()

        # Group words by y position
        rows_by_y = defaultdict(list)
        for w in words:
            rows_by_y[w['top']].append(w)

        # Find data rows (have numeric qty in x range 185-220)
        data_rows = []
        for y, row_words in sorted(rows_by_y.items()):
            has_qty = any(
                w['text'].isdigit() and 185 <= w['x0'] < 220
                for w in row_words
            )
            if has_qty:
                data_rows.append((y, row_words))

        if verbose:
            print(f"  Page {page_num}: {len(data_rows)} data rows", file=sys.stderr)

        # Process each data row
        for y, row_words in data_rows:
            # Get category text (x < 85, including nearby y positions ±10)
            category_words = []
            for other_y, other_words in rows_by_y.items():
                if abs(other_y - y) <= 10:
                    for w in other_words:
                        if w['x0'] < 85:
                            category_words.append((other_y, w['x0'], w['text']))
            category_words.sort()  # Sort by y then x
            category_text = ' '.join(w[2] for w in category_words).strip()

            # Get item name (x 85-185, including nearby y positions ±15)
            item_words = []
            for other_y, other_words in rows_by_y.items():
                if abs(other_y - y) <= 15:
                    for w in other_words:
                        if 85 <= w['x0'] < 185:
                            item_words.append((other_y, w['x0'], w['text']))
            item_words.sort()  # Sort by y then x
            item_name = ' '.join(w[2] for w in item_words).strip()

            # Get numeric values from this row
            qty_words = [w['text'] for w in row_words if 185 <= w['x0'] < 220 and w['text'].isdigit()]
            qty = int(qty_words[0]) if qty_words else 0

            # Get currency values (x >= 220)
            currency_words = []
            for w in sorted(row_words, key=lambda w: w['x0']):
                if w['x0'] >= 220 and w['text'].startswith('$'):
                    currency_words.append(w['text'])

            # New format: [Refunds, Net Sales, Avg Price, Discount]
            refunds = parse_currency(currency_words[0]) if len(currency_words) > 0 else 0.0
            net_sales = parse_currency(currency_words[1]) if len(currency_words) > 1 else 0.0
            avg_price = parse_currency(currency_words[2]) if len(currency_words) > 2 else 0.0
            discount = parse_currency(currency_words[3]) if len(currency_words) > 3 else 0.0

            # Check for 100% category sales (indicates category header or subtotal)
            pct_words = [w['text'] for w in row_words if w['text'] == '100.00' and w['x0'] > 500]
            is_category_header = len(pct_words) > 0

            # Primary category header detection (starts with parentheses)
            if category_text.startswith('(') and category_text.endswith(')'):
                current_primary_category = category_text
                if verbose:
                    print(f"    Primary category: {current_primary_category}", file=sys.stderr)
                continue

            # Grand Total detection
            if 'Grand' in category_text and 'Total' in category_text:
                grand_total_from_pdf = net_sales
                if verbose:
                    print(f"    Grand Total: ${grand_total_from_pdf:.2f}", file=sys.stderr)
                continue

            # Skip category subtotal rows (100% category sales AND no item name)
            # A row is a subtotal if it has 100% category sales but no actual item
            # (items that are 100% of their category still have item names)
            if is_category_header and not category_text.startswith('(') and not item_name:
                if verbose:
                    print(f"    Skipping subtotal: {category_text}", file=sys.stderr)
                continue

            # Skip rows with no category (probably continuation lines)
            if not category_text:
                continue

            # Regular item row
            record = {
                "customer_id": "senso-sushi",
                "report_date": report_date,
                "primary_category": current_primary_category,
                "category": category_text,
                "item_name": item_name,
                "quantity_sold": qty,
                "net_sales": round(net_sales, 2),
                "discount": round(discount, 2)
            }
            records.append(record)

    return records, grand_total_from_pdf


def parse_pmix_pdf(pdf_path: str, verbose: bool = False) -> tuple[list[dict], float | None]:
    """
    Parse a PMIX PDF and return item records.

    Uses hybrid approach:
    - Try table extraction first (works for old format Dec 2024 - Mar 2025)
    - Fall back to word position extraction (works for new format Apr 2025+)

    Returns:
        tuple of (records list, grand_total from PDF or None)
    """
    try:
        report_date = extract_date_from_filename(pdf_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return [], None

    if verbose:
        print(f"Parsing: {pdf_path}", file=sys.stderr)
        print(f"Report date: {report_date}", file=sys.stderr)

    with pdfplumber.open(pdf_path) as pdf:
        # Try table extraction first (old format)
        table_rows = find_data_table(pdf)

        if table_rows:
            if verbose:
                print(f"  Using table extraction (old format)", file=sys.stderr)
            return parse_from_table(table_rows, report_date, verbose)
        else:
            if verbose:
                print(f"  Using word position extraction (new format)", file=sys.stderr)
            return parse_from_words(pdf, report_date, verbose)


def validate_totals(records: list[dict], grand_total_from_pdf: float | None, verbose: bool = False) -> bool:
    """Validate that calculated total matches PDF grand total."""
    if grand_total_from_pdf is None:
        print("Warning: No Grand Total found in PDF", file=sys.stderr)
        return True

    calculated_total = sum(r["net_sales"] for r in records)
    calculated_qty = sum(r["quantity_sold"] for r in records)

    if verbose:
        print(f"Calculated: {calculated_qty} items, ${calculated_total:.2f}", file=sys.stderr)
        print(f"PDF Total: ${grand_total_from_pdf:.2f}", file=sys.stderr)

    # Allow small floating point differences
    if abs(calculated_total - grand_total_from_pdf) > 1.00:
        print(f"Warning: Total mismatch! Calculated ${calculated_total:.2f}, PDF shows ${grand_total_from_pdf:.2f}", file=sys.stderr)
        return False

    return True


def output_ndjson(records: list[dict], output_path: str | None = None):
    """Output records as newline-delimited JSON."""
    if output_path:
        with open(output_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        print(f"Wrote {len(records)} records to {output_path}", file=sys.stderr)
    else:
        for record in records:
            print(json.dumps(record))


def main():
    parser = argparse.ArgumentParser(
        description="Parse a PMIX PDF file and output item records as NDJSON"
    )
    parser.add_argument("pdf_path", help="Path to the PMIX PDF file")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not Path(args.pdf_path).exists():
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    records, grand_total = parse_pmix_pdf(args.pdf_path, verbose=args.verbose)

    if not records:
        print("No records found in PDF", file=sys.stderr)
        sys.exit(1)

    validate_totals(records, grand_total, verbose=args.verbose)
    output_ndjson(records, args.output)

    if args.verbose:
        print(f"Total records: {len(records)}", file=sys.stderr)


if __name__ == "__main__":
    main()
