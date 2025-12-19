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
├── utils/              # Helper utilities (chat.py with chart support)
├── scripts/
│   ├── parse_pmix_pdf.py   # PDF parser
│   └── import_pmix.py      # Bulk import to BigQuery
├── schema/             # BigQuery DDL scripts (11 files)
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
You are Senso Sushi's analytics assistant. Answer questions about sales, weather impacts, and local events. Use charts when they add clarity.

DATA SCHEMA (ai.restaurant_analytics):
Sales: report_date, location, primary_category, category, item_name, quantity_sold, net_sales, discount
Weather: avg_temp_f, max_temp_f, min_temp_f, had_rain, had_snow, precipitation_in
Events: event_names, event_types, event_count, has_local_event
Time: day_of_week, day_name, week_number, month, month_name, year, is_weekend

PRODUCT HIERARCHY (important for category queries):
- item_name: Specific menu items (e.g., "Sapporo", "Dragon Roll", "Lychee Martini")
- category: Product categories, multi-word names (e.g., "Bottle Beer", "Classic Rolls", "Signature Cocktails")
- primary_category: Broad groupings in parentheses (e.g., "(Beer)", "(Sushi)", "(Liquor)", "(Wine)", "(Food)")

CATEGORY SEARCH RULES:
1. When user asks about a PRODUCT TYPE (beer, rolls, cocktails, beverages), search category or primary_category - NOT item_name
2. Use LIKE with wildcards, never exact match: WHERE LOWER(category) LIKE '%roll%'
3. For broad semantic terms (e.g., "beverages", "drinks", "food"), first discover what categories exist, then include all that semantically match
4. When unsure which categories match a query, first run: SELECT DISTINCT primary_category, category FROM ai.restaurant_analytics
5. primary_category values are wrapped in parentheses, so use LIKE '%beer%' not = 'Beer'

ADDITIONAL VIEWS:
- ai.sales_forecast: 14-day predictions (forecast_date, predicted_sales, lower_bound, upper_bound)
- ai.data_quality: Data coverage info (earliest_date, latest_date, days_with_data, missing_days)

DATA RANGE: December 2024 - September 2025 (200 days, ~27K records)

WHEN TO USE CHARTS:
- Bar charts: Comparing categories, top N items, day-of-week patterns
- Line charts: Trends over time, daily/weekly/monthly sales, forecasts
- Scatter plots: Correlations (temperature vs sales, etc.)

QUERY PATTERNS:
- Top sellers: ORDER BY net_sales DESC or ORDER BY quantity_sold DESC
- Weather correlation: WHERE had_rain = TRUE or GROUP BY had_rain
- Event impact: WHERE has_local_event = TRUE
- Time analysis: GROUP BY day_name, GROUP BY month_name, WHERE is_weekend = TRUE
- Forecasts: SELECT * FROM ai.sales_forecast

RESPONSE FORMAT:
- Lead with the key insight (1-2 sentences)
- Use charts for trends, comparisons, and distributions
- Use tables for detailed item lists
- Round dollars to whole numbers

Keep it concise. Prefer visuals over long text explanations.
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
| `scripts/test_agent.py` | CLI tool to test the agent without Streamlit UI |

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

## Agent Testing (scripts/test_agent.py)

CLI tool to test the Conversational Analytics agent without the Streamlit UI.

### Usage

```bash
# List available agents
python scripts/test_agent.py --list-agents

# Single query
python scripts/test_agent.py --agent SensoBot "What are our top sellers?"

# Interactive mode
python scripts/test_agent.py --agent SensoBot

# Run stress test (questions from Stress Test Questions.md)
python scripts/test_agent.py --agent SensoBot --stress-test

# Run first N stress test questions
python scripts/test_agent.py --agent SensoBot --stress-test --limit 10
```

### Stress Test Questions

See `Stress Test Questions.md` for 86 sample queries organized by category:
- Basic queries, category analysis, time patterns
- Weather correlations, event impact, forecasting
- Anomaly detection, item-level analysis, comparisons
- Edge cases, vague/ambiguous queries, data quality

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

# Test agent from CLI
python scripts/test_agent.py --agent SensoBot "What are top sellers?"
python scripts/test_agent.py --agent SensoBot --stress-test --limit 5
```
