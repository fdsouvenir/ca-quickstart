# Conversational Analytics Quickstart - Project Context

## Overview

This is a customized deployment of Google's [Conversational Analytics API Quickstart](https://github.com/looker-open-source/ca-api-quickstarts) for a restaurant in Frankfort, IL. The app enables natural language queries against BigQuery data.

## Tech Stack

- **Python 3.11+** with virtual environment (`venv/`)
- **Streamlit** - Web framework (runs on port 8501)
- **Google Cloud** - BigQuery, Gemini Data Analytics API
- **Project ID**: `fdsanalytics`

## Running the App

```bash
cd /home/souvy/ca_quickstart
source venv/bin/activate
streamlit run app.py
```

Access at: http://localhost:8501

## Project Structure

```
ca_quickstart/
├── app.py              # Main Streamlit entry point
├── state.py            # Session state management
├── app_pages/          # Multi-page app modules
├── utils/              # Helper utilities
├── .streamlit/
│   ├── config.toml     # Streamlit config
│   └── secrets.toml    # GCP project ID (fdsanalytics)
├── venv/               # Python virtual environment
└── requirements.txt    # Dependencies
```

## Custom BigQuery Resources

We created custom tables and views in `fdsanalytics` to enable richer analytics:

### Tables Created

| Table | Description |
|-------|-------------|
| `insights.frankfort_events` | 28 Frankfort IL special events for 2025 (festivals, markets, holidays) |
| `insights.local_weather` | Daily weather from Joliet Regional Airport (Jan 2024 - Aug 2025) |

### Views Created

| View | Description |
|------|-------------|
| `insights.unified_analytics` | Combined view joining restaurant data with weather and events |

### Unified Analytics View Schema

The `unified_analytics` view combines:
- `insights.top_items` - Item rankings (quantity_sold, net_sales, rank)
- `insights.category_trends` - Category performance (week_over_week_change, trend_direction)
- `insights.daily_forecast` - Sales predictions (predicted_sales, confidence_score)

With enrichments:
- **Weather**: avg_temp_f, max_temp_f, min_temp_f, precipitation_in, had_rain, had_snow
- **Events**: event_name, event_type, has_local_event

Key columns:
- `data_source` - Which table the row came from ('top_items', 'category_trends', 'daily_forecast')
- `report_date` - Date for joining with weather/events
- `customer_id` - Restaurant identifier ('senso-sushi')

## Agent Configuration

When creating an agent in the app, use:

- **Project ID**: `fdsanalytics`
- **Dataset**: `insights`
- **Table**: `unified_analytics`

### Recommended System Instruction

```
You are a concise restaurant analytics assistant. Keep answers brief and scannable.

RESPONSE FORMAT:
- Lead with the key insight in 1-2 sentences
- Use bullet points for multiple items
- Round numbers to whole dollars
- Avoid technical jargon

DATA AVAILABLE:
- top_items: Item sales rankings (quantity_sold, net_sales, rank)
- category_trends: Category performance (week_over_week_change, trend_direction)
- daily_forecast: Sales predictions (predicted_sales)
- Weather: avg_temp_f, had_rain, had_snow
- Events: event_name, event_type, has_local_event

EXAMPLE GOOD RESPONSE:
"Top seller on rainy days: Ramen ($2,450 avg sales)
- 34% higher than sunny days
- Best categories: Soups, Hot Drinks"

Keep it short. Users want insights, not explanations.
```

## Example Queries

With the unified view, users can ask:
- "What were our top items during Oktoberfest?"
- "How do sales compare on rainy vs sunny days?"
- "Which categories perform best during local festivals?"
- "Show me the correlation between temperature and beverage sales"

## GCP Setup Requirements

APIs enabled on `fdsanalytics`:
- `geminidataanalytics.googleapis.com` - Data Analytics API with Gemini
- `bigquery.googleapis.com` - BigQuery API
- `cloudaicompanion.googleapis.com` - Gemini for Google Cloud API

Authentication:
```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project fdsanalytics
```

## Weather Data Source

Weather data comes from NOAA GSOD (Global Surface Summary of Day):
- **Station**: Joliet Regional Airport (725345)
- **Location**: ~10 miles from Frankfort, IL
- **Coverage**: 2024-01-01 to 2025-08-25 (337 days)

To refresh weather data:
```bash
# Export from public dataset
bq query --nouse_legacy_sql --format=json --max_rows=1000 "
SELECT FORMAT_DATE('%Y-%m-%d', date) AS weather_date, temp AS avg_temp_f, ...
FROM \`bigquery-public-data.noaa_gsod.gsod2025\`
WHERE stn = '725345'" > /tmp/weather.json

# Convert and load
python3 -c "import json; ..." # Convert to NDJSON
bq load --source_format=NEWLINE_DELIMITED_JSON fdsanalytics:insights.local_weather /tmp/weather.json
```

## Events Data Source

Events scraped from: https://www.frankfortil.org/residents/special_events/index.php

To add new events:
```sql
INSERT INTO `fdsanalytics.insights.frankfort_events` VALUES
  ('2026-07-04', 'Fourth of July Fireworks', 'patriotic', FALSE, NULL);
```

## Known Issues

1. **Weather data gaps**: Weather data only goes to Aug 2025; queries for later dates won't have weather context
2. **Multi-event days**: Days with multiple events (e.g., Country Market + Fridays on the Green) create duplicate rows in the view
3. **NOAA data loading**: Cannot create views directly referencing `bigquery-public-data` - must copy data to local table

## PMIX PDF Parser (scripts/)

Parser and importer for PMIX (Product Mix) PDFs from SpotOn POS system. Parses daily sales reports and loads to BigQuery.

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/parse_pmix_pdf.py` | Parse single PDF → NDJSON output |
| `scripts/import_pmix.py` | Bulk import all PDFs to BigQuery |
| `scripts/validate_parsed.py` | Validate parsed data against PDF totals |

### Usage

```bash
# Parse single PDF
python scripts/parse_pmix_pdf.py pmix/pmix-senso-2025-06-14.pdf -v

# Dry run all PDFs (parse + validate, no BigQuery)
python scripts/import_pmix.py --pmix-dir pmix/ --dry-run

# Full import to BigQuery
python scripts/import_pmix.py --pmix-dir pmix/
```

### Key Details

- **PDF location**: `pmix/` directory
- **File pattern**: `pmix-senso-YYYY-MM-DD.pdf`
- **Date range**: 2024-12-15 to 2025-09-28 (213 PDFs)
- **Two PDF formats**: Old (Dec 2024 - Mar 2025) uses table extraction, New (Apr 2025+) uses word-position extraction
- **Output table**: `fdsanalytics.insights.top_items`
- **Validation log**: `pmix/validation_log.json`

### Parser Status (as of 2025-12-18)

- 200 days parsed successfully
- 0 errors, 0 flagged
- 27,251 records, $1,535,454.82 total sales
- Ready for BigQuery import

See `PMIX_PARSER_PLAN.md` for full implementation details.

## Useful Commands

```bash
# Check what's in BigQuery
bq ls fdsanalytics:insights

# Query the unified view
bq query --nouse_legacy_sql "SELECT * FROM fdsanalytics.insights.unified_analytics LIMIT 10"

# Check weather coverage
bq query --nouse_legacy_sql "SELECT MIN(weather_date), MAX(weather_date) FROM fdsanalytics.insights.local_weather"

# List events
bq query --nouse_legacy_sql "SELECT * FROM fdsanalytics.insights.frankfort_events ORDER BY event_date"

# Parse PMIX dry run
python scripts/import_pmix.py --pmix-dir pmix/ --dry-run
```
