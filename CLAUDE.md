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

### Datasets

| Dataset | Purpose |
|---------|---------|
| `restaurant_analytics` | Core fact and dimension tables |
| `insights` | Derived views, ML models, and event data |
| `ai` | LLM-facing views with pre-joined data |

### Core Tables

| Table | Description |
|-------|-------------|
| `restaurant_analytics.item_sales` | Denormalized fact table - one row per item per day (partitioned by date) |
| `restaurant_analytics.locations` | Dimension table mapping locations to regions |
| `insights.local_events` | Local events by region (replaces frankfort_events) |
| `insights.local_weather` | Daily weather from Joliet Regional Airport |
| `insights.sales_forecast_results` | BQML 14-day forecast (refreshed daily) |
| `insights.sales_anomaly_results` | BQML anomaly detection (refreshed daily) |

### Views

| View | Description |
|------|-------------|
| `ai.restaurant_analytics` | **Primary LLM view** - pre-joins sales, weather, events |
| `ai.restaurant_analytics_extended` | Extended view with anomaly data |
| `ai.sales_forecast` | 14-day sales forecast |
| `ai.data_quality` | Data coverage metadata for AI self-validation |
| `insights.expanded_events` | Expands recurring events to individual dates |
| `insights.daily_totals` | Materialized view - daily aggregations |
| `insights.category_daily` | Materialized view - category-level aggregations |

### BQML Model

| Model | Description |
|-------|-------------|
| `insights.sales_model` | ARIMA_PLUS model for forecasting and anomaly detection |

## Agent Configuration

When creating an agent in the app, use:

- **Project ID**: `fdsanalytics`
- **Dataset**: `ai`
- **Table**: `restaurant_analytics`

### Recommended System Instruction

```
You are a concise restaurant analytics assistant. Keep answers brief and scannable.

RESPONSE FORMAT:
- Lead with the key insight in 1-2 sentences
- Use bullet points for multiple items
- Round numbers to whole dollars
- Avoid technical jargon

DATA AVAILABLE (ai.restaurant_analytics view):
- Sales: report_date, item_name, category, primary_category, net_sales, quantity_sold, discount
- Location: location, location_name, region
- Weather: avg_temp_f, max_temp_f, min_temp_f, had_rain, had_snow, precipitation_in
- Events: event_names (comma-separated), event_types, event_count, has_local_event
- Time: day_of_week, day_name, week_number, month, month_name, is_weekend

EXAMPLE QUERIES:
- "Top sellers on rainy days" -> WHERE had_rain = TRUE ORDER BY net_sales DESC
- "Weekend vs weekday sales" -> GROUP BY is_weekend
- "Sales during festivals" -> WHERE has_local_event = TRUE
- "Best items in summer" -> WHERE month IN (6, 7, 8)
- "Sales during Country Market" -> WHERE event_names LIKE '%Country Market%'

FORECASTING (ai.sales_forecast view):
- forecast_date, predicted_sales, lower_bound, upper_bound, confidence_level
- "What are predicted sales for next week?" -> SELECT * FROM ai.sales_forecast

DATA COVERAGE (ai.data_quality view):
- earliest_date, latest_date, days_with_data, total_records, total_sales, missing_days
- Use this view to validate date ranges before answering questions

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
INSERT INTO `fdsanalytics.insights.local_events`
  (event_date, event_name, event_type, recurrence_type, end_date, region)
VALUES
  ('2026-07-04', 'Fourth of July Fireworks', 'patriotic', 'single', NULL, 'frankfort-il');
```

Recurrence types: `'single'` (one day), `'daily'` (every day in range), `'weekly'` (same weekday each week)

## Known Issues

1. **Weather data gaps**: Weather data only goes to Aug 2025; queries for later dates won't have weather context
2. **NOAA data loading**: Cannot create views directly referencing `bigquery-public-data` - must copy data to local table
3. **BQML anomaly detection**: May return NULL for anomaly_probability when data has gaps; improves with continuous data

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
- **Output table**: `fdsanalytics.restaurant_analytics.item_sales`
- **Validation log**: `pmix/validation_log.json`

### Parser Status (as of 2025-12-18)

- 200 days parsed and imported successfully
- 27,163 records, $1,535,454.82 total sales
- BQML model trained with 14-day forecasting

See `POC_IMPLEMENTATION_PLAN.md` for full architecture details.

## Useful Commands

```bash
# Check what's in BigQuery
bq ls fdsanalytics:ai
bq ls fdsanalytics:restaurant_analytics
bq ls fdsanalytics:insights

# Query the AI view (primary LLM view)
bq query --nouse_legacy_sql "SELECT * FROM ai.restaurant_analytics LIMIT 10"

# Check data quality
bq query --nouse_legacy_sql "SELECT * FROM ai.data_quality"

# Get sales forecast
bq query --nouse_legacy_sql "SELECT * FROM ai.sales_forecast"

# Check weather coverage
bq query --nouse_legacy_sql "SELECT MIN(weather_date), MAX(weather_date) FROM insights.local_weather"

# List events
bq query --nouse_legacy_sql "SELECT * FROM insights.local_events ORDER BY event_date"

# Check expanded events (recurring events expanded to individual dates)
bq query --nouse_legacy_sql "SELECT event_name, COUNT(*) FROM insights.expanded_events GROUP BY 1"

# Parse PMIX dry run
python scripts/import_pmix.py --pmix-dir pmix/ --dry-run

# Refresh ML results manually
bq query --nouse_legacy_sql < schema/refresh_ml_tables.sql
```
