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

- **Local**: http://localhost:8501
- **Production**: https://sensobot.streamlit.app/chat

## Project Structure

```
ca_quickstart/
├── app.py              # Main Streamlit entry point
├── state.py            # Session state management
├── app_pages/          # Multi-page app modules
├── utils/              # Helper utilities (chat.py with chart support)
├── scripts/
│   ├── parse_pmix_pdf.py   # PDF parser
│   ├── import_pmix.py      # Bulk import to BigQuery
│   ├── backfill_openmeteo_weather.py  # One-time weather backfill
│   └── test_agent.py       # CLI agent testing tool
├── cloud_functions/    # GCP Cloud Functions
│   ├── sync_drive_to_gcs/  # HTTP-triggered: syncs Drive → GCS
│   ├── process_pmix/       # GCS-triggered: parses PDF → BigQuery
│   ├── send_daily_report/  # HTTP-triggered: sends daily email report
│   └── fetch_openmeteo_weather/  # HTTP-triggered: fetches weather from Open-Meteo
├── deploy/
│   └── deploy_cloud_functions.sh  # Deployment script
├── schema/             # BigQuery DDL scripts
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
| `insights.local_weather` | Daily weather from Open-Meteo (historical actuals) |
| `insights.weather_forecast` | 14-day weather forecast from Open-Meteo (refreshed daily) |
| `insights.weather_import_log` | Tracks weather fetch operations (status, record counts) |
| `insights.sales_forecast_results` | BQML 14-day forecast (refreshed daily, uses weather regressors) |
| `insights.sales_anomaly_results` | BQML anomaly detection (refreshed daily) |
| `insights.primary_category_*_forecast_results` | Category-level forecasts (sales + quantity, refreshed daily) |
| `insights.*_anomaly_results` | Category-level anomaly detection (refreshed daily) |
| `insights.pmix_import_log` | Tracks automated PMIX PDF imports (status, record counts, errors) |
| `insights.email_recipients` | Email recipients for daily report (email, name, active) |
| `insights.email_report_log` | Tracks daily email sends (report_date, status, recipient_count) |

### Views

| View | Description |
|------|-------------|
| `ai.restaurant_analytics` | **Primary LLM view** - pre-joins sales, weather, events (item-level grain) |
| `ai.daily_summary` | **Day/location grain** - USE FOR weather correlations, daily trends, scatter plots |
| `ai.restaurant_analytics_extended` | Extended view with anomaly data |
| `ai.sales_forecast` | 14-day sales forecast |
| `ai.weather_forecast` | **14-day weather predictions** from Open-Meteo (refreshed daily at 5:45 AM CT) |
| `ai.primary_category_forecast` | **Category forecasts** - 14-day forecast by primary category (sales + quantity) |
| `ai.category_forecast` | **Fine category forecasts** - 14-day forecast by detailed category |
| `ai.category_anomalies` | **Category anomalies** - unusual patterns by category (sales + quantity) |
| `ai.category_forecast_quality` | Data quality metadata for category forecasts |
| `ai.data_quality` | Data coverage metadata for AI self-validation |
| `insights.expanded_events` | Expands recurring events to individual dates |
| `insights.daily_totals` | Materialized view - daily aggregations |
| `insights.category_daily` | Materialized view - category-level aggregations |
| `insights.daily_sales_with_weather` | Training view for BQML - daily sales with weather features |
| `insights.future_weather_regressors` | 14-day weather forecast formatted for ML.FORECAST |
| `insights.category_sales_with_weather` | Category-level training view (for future XREG models) |

### ai.daily_summary Columns

Pre-aggregated table to prevent weather column multiplication bugs. One row per day per location.

```
Grain: report_date, location, location_name, region
Sales: total_net_sales, total_quantity_sold, total_discount, unique_items_sold, line_item_count
Weather: avg_temp_f, max_temp_f, min_temp_f, precipitation_in, had_rain, had_snow
Events: event_names, event_types, event_count, has_local_event
Time: day_of_week, day_name, week_number, month, month_name, year, is_weekend
```

### BQML Models

| Model | Description |
|-------|-------------|
| `insights.sales_model` | **ARIMA_PLUS_XREG** with weather regressors (temp, precip, rain/snow, weekend) |
| `insights.primary_category_sales_model` | Multi-series ARIMA_PLUS for primary category sales (6 series) |
| `insights.primary_category_qty_model` | Multi-series ARIMA_PLUS for primary category quantity (6 series) |
| `insights.category_sales_model` | Multi-series ARIMA_PLUS for fine category sales (~20 series) |
| `insights.category_qty_model` | Multi-series ARIMA_PLUS for fine category quantity (~20 series) |

**Weather Regressors**: The sales_model uses external regressors from `insights.weather_forecast` for predictions:
- `avg_temp_f` - Average temperature
- `precipitation_in` - Precipitation amount
- `is_rainy` - Rain flag (1/0)
- `is_snowy` - Snow flag (1/0)
- `is_weekend` - Weekend flag (1/0)

Training view: `insights.daily_sales_with_weather`

### Scheduled Jobs

**Cloud Scheduler Jobs** (Cloud Functions):

| Job | Schedule | Function | Description |
|-----|----------|----------|-------------|
| `weather-daily-fetch` | 5:45 AM CT (11:45 UTC) | `fetch-openmeteo-weather` | Fetches yesterday's weather + 14-day forecast |
| `sync-pmix-from-drive` | Every 15 min | `sync-drive-to-gcs` | Syncs PMIX PDFs from Drive |
| `daily-analytics-report` | 7:00 AM CT (13:00 UTC) | `send-daily-report` | Sends daily email report |

**BigQuery Scheduled Queries** (service account: `bq-scheduled-queries@fdsanalytics.iam.gserviceaccount.com`):

| Query | Schedule | Description |
|-------|----------|-------------|
| Daily ML Tables Refresh | 6:00 AM CT (12:00 UTC) | Refreshes all forecast and anomaly tables (uses weather data) |
| Weekly Model Retraining | Sunday 2:00 AM CT (08:00 UTC) | Retrains all models (sales + category) to capture new data |

**Daily Refresh Order**:
1. 5:45 AM CT - Weather fetch (Open-Meteo → BigQuery)
2. 6:00 AM CT - ML refresh (uses fresh weather forecasts)
3. 7:00 AM CT - Daily email report

To check scheduled query status:
```bash
bq ls --transfer_config --transfer_location=us-central1 --project_id=fdsanalytics
```

To trigger a manual run:
```bash
bq mk --transfer_run --run_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)" 'projects/111874159771/locations/us-central1/transferConfigs/<config_id>'
```

## Agent Configuration

When creating an agent in the app, use:

- **Project ID**: `fdsanalytics`
- **Dataset**: `ai`
- **Table**: `restaurant_analytics`

### Recommended System Instruction

```
You are Senso Sushi's analytics assistant. Answer questions about sales, weather impacts, and local events. Use charts when they add clarity.

MANDATORY VIEW SELECTION:
- For ANY query involving weather (precipitation, temperature, rain, snow) or daily aggregations/correlations:
  → MUST use ai.daily_summary
- For item-level queries (top sellers, category breakdowns, specific menu items):
  → Use ai.restaurant_analytics

ai.daily_summary columns (day/location grain, 290 rows):
report_date, location, location_name, region, total_net_sales, total_quantity_sold,
total_discount, unique_items_sold, line_item_count, avg_temp_f, max_temp_f, min_temp_f,
precipitation_in, had_rain, had_snow, event_names, event_types, event_count,
has_local_event, day_of_week, day_name, week_number, month, month_name, year, is_weekend

ai.restaurant_analytics columns (item-level grain, 39K rows):
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
- ai.daily_summary: Day/location grain for weather correlations and daily trends (see columns above)
- ai.sales_forecast: 14-day sales predictions (forecast_date, predicted_sales, lower_bound, upper_bound)
- ai.weather_forecast: 14-day weather predictions (forecast_date, weather_condition, high_temp_f, low_temp_f, rain_likely, snow_likely)
- ai.data_quality: Data coverage info (earliest_date, latest_date, days_with_data, missing_days)

WEATHER FORECAST QUERIES:
- "Will it snow today?" → SELECT * FROM ai.weather_forecast WHERE forecast_date = CURRENT_DATE()
- "What's the weather tomorrow?" → SELECT * FROM ai.weather_forecast WHERE forecast_date = DATE_ADD(CURRENT_DATE(), INTERVAL 1 DAY)
- "Show me the 7-day forecast" → SELECT * FROM ai.weather_forecast LIMIT 7

CATEGORY-LEVEL FORECASTING:
- ai.primary_category_forecast: 14-day forecast by primary category (Beer, Food, Sushi, Liquor, Wine, N/A Beverages)
  Columns: forecast_date, primary_category, day_name, is_weekend, predicted_sales, sales_lower_bound,
           sales_upper_bound, predicted_quantity, quantity_lower_bound, quantity_upper_bound, confidence_level
- ai.category_forecast: 14-day forecast by detailed category (Classic Rolls, Bottle Beer, Signature Cocktails, etc.)
  Columns: forecast_date, category, primary_category, day_name, is_weekend, predicted_sales, predicted_quantity, bounds
- ai.category_forecast_quality: Shows which categories have enough data for reliable forecasting

CATEGORY FORECAST QUERY PATTERNS:
- "How many beers should I sell tomorrow?" → SELECT * FROM ai.primary_category_forecast WHERE primary_category LIKE '%Beer%' AND forecast_date = DATE_ADD(CURRENT_DATE(), INTERVAL 1 DAY)
- "Forecast sushi sales for next week" → SELECT * FROM ai.primary_category_forecast WHERE primary_category LIKE '%Sushi%' ORDER BY forecast_date
- "Predict Classic Rolls for Saturday" → SELECT * FROM ai.category_forecast WHERE category = 'Classic Rolls' AND day_name = 'Saturday'
- "Compare beer vs liquor forecast" → SELECT * FROM ai.primary_category_forecast WHERE primary_category IN ('(Beer)', '(Liquor)')

CATEGORY ANOMALY DETECTION:
- ai.category_anomalies: Unusual sales or quantity patterns by category (both primary and fine-grained)
  Columns: granularity ('primary_category' or 'category'), category_name, parent_category, report_date, day_name,
           metric_type ('sales' or 'quantity'), actual_value, predicted_value, is_anomaly, anomaly_type ('spike'/'drop'/'normal')

CATEGORY ANOMALY QUERY PATTERNS:
- "Any unusual sales days?" → SELECT * FROM ai.category_anomalies WHERE is_anomaly = TRUE ORDER BY report_date DESC LIMIT 10
- "Beer sales anomalies" → SELECT * FROM ai.category_anomalies WHERE category_name LIKE '%Beer%' AND is_anomaly = TRUE
- "Which categories spiked recently?" → SELECT * FROM ai.category_anomalies WHERE anomaly_type = 'spike' ORDER BY report_date DESC

NOTE: All forecasts refresh daily at 6 AM. Models retrain weekly (Sunday 2 AM) to incorporate new data.

DATA RANGE: December 2024 - December 2025 (290 days, ~39K records)

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

CHART BEST PRACTICES:
- Include descriptive axis titles with units (e.g., "Net Sales ($)", "Temperature (°F)")
- Sort bar charts by value (descending) unless time-based
- Limit bar charts to top 10-15 items for readability

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

Weather data comes from **Open-Meteo API** (free, no API key required):
- **Location**: Frankfort, IL (41.1958, -87.8487)
- **Historical**: `insights.local_weather` - 387 days (2024-12-08 to present)
- **Forecast**: `insights.weather_forecast` - 14-day predictions (refreshed daily)
- **Schedule**: Cloud Function `fetch-openmeteo-weather` runs at 5:45 AM CT (before ML refresh)
- **Weather-aware forecasting**: Sales model (ARIMA_PLUS_XREG) uses forecast weather as regressors

### Weather Tables

**insights.local_weather** (historical actuals):
```
weather_date, avg_temp_f, max_temp_f, min_temp_f, precipitation_in,
had_rain, had_snow, wind_speed_mph, wind_gust_mph, weather_code,
weather_condition, cloud_cover_pct, humidity_pct, uv_index
```

**insights.weather_forecast** (14-day forecast, refreshed daily):
```
forecast_date, updated_at, high_temp_f, low_temp_f, avg_temp_f,
precipitation_in, precipitation_probability_pct, rain_likely, snow_likely,
wind_speed_mph, wind_gust_mph, weather_code, weather_condition,
cloud_cover_pct, humidity_pct, uv_index
```

### Weather Commands

```bash
# Test weather fetch manually
curl $(gcloud functions describe fetch-openmeteo-weather --region=us-central1 --format='value(serviceConfig.uri)')

# Check weather import log
bq query --nouse_legacy_sql "SELECT * FROM insights.weather_import_log ORDER BY processed_at DESC LIMIT 10"

# Check forecast data
bq query --nouse_legacy_sql "SELECT * FROM insights.weather_forecast ORDER BY forecast_date"

# Backfill historical weather (one-time)
python scripts/backfill_openmeteo_weather.py --dry-run   # Preview
python scripts/backfill_openmeteo_weather.py             # Execute
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

1. **BQML anomaly detection**: Total sales anomalies use ML.DETECT_ANOMALIES; category-level anomalies use z-score (2.5σ threshold) because ML.DETECT_ANOMALIES returns NULL bounds for multi-series ARIMA models
2. **Scheduled query timezone**: BigQuery scheduled queries use UTC. Times are configured as 12:00 UTC (6 AM CT) and 08:00 UTC (2 AM CT)
3. **Weather forecast refresh**: Weather must be fetched before ML refresh. If weather fetch fails, forecasts will use stale regressor values
4. **Average ticket queries**: "Average ticket by category" queries may fail with SQL COUNT signature errors - the agent sometimes generates invalid `COUNT(date, item)` syntax instead of counting distinct transactions

## PMIX PDF Parser (scripts/)

Parser and importer for PMIX (Product Mix) PDFs from SpotOn POS system. Parses daily sales reports and loads to BigQuery.

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/parse_pmix_pdf.py` | Parse single PDF → NDJSON output |
| `scripts/import_pmix.py` | Bulk import all PDFs to BigQuery |
| `scripts/validate_parsed.py` | Validate parsed data against PDF totals |
| `scripts/backfill_openmeteo_weather.py` | One-time weather backfill from Open-Meteo |
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
- **Date range**: 2024-12-15 to 2025-12-30 (290 days imported)
- **Two PDF formats**: Old (Dec 2024 - Mar 2025) uses table extraction, New (Apr 2025+) uses word-position extraction
- **Output table**: `fdsanalytics.restaurant_analytics.item_sales`
- **Validation log**: `pmix/validation_log.json`

### Parser Status (as of 2025-12-31)

- 290 days parsed and imported successfully
- ~39,300 records, ~$2,091,000 total sales
- BQML model trained with 14-day forecasting

See `POC_IMPLEMENTATION_PLAN.md` for full architecture details.

## Automated PMIX Pipeline (Cloud Functions)

Automated pipeline that syncs PMIX PDFs from Google Drive to BigQuery.

### Architecture

```
Google Drive          Cloud Storage           Cloud Function          BigQuery
(Shared Folder)  →    (pmix-uploads)    →    (process-pmix)    →    item_sales
      ↑                     ↑                       ↓
External App          sync-drive-to-gcs      insights.pmix_import_log
(webhook call)        (HTTP trigger)
```

### Cloud Functions

| Function | Trigger | Auth | Purpose |
|----------|---------|------|---------|
| `sync-drive-to-gcs` | HTTP (webhook) | Public (API key in code) | Syncs new PDFs from Drive folder to GCS bucket |
| `process-pmix` | GCS event | N/A | Parses PDF, validates, loads to BigQuery |
| `send-daily-report` | HTTP | Public | Sends daily analytics email via SendGrid |
| `fetch-openmeteo-weather` | HTTP (scheduler) | OIDC | Fetches weather data from Open-Meteo API |

**Note**: `sync-drive-to-gcs` uses `supportsAllDrives=True` to access shared Drive folders.

### Triggering the Sync

The sync is triggered via HTTP webhook (not scheduled). Call from your external app after uploading a PDF to Drive:

```bash
curl -X POST https://sync-drive-to-gcs-nkiogckaga-uc.a.run.app \
  -H "X-API-Key: <api-key>"
```

API key stored in Secret Manager: `pmix-sync-api-key`

To retrieve the API key:
```bash
gcloud secrets versions access latest --secret=pmix-sync-api-key --project=fdsanalytics
```

### Configuration

- **Drive Folder ID**: `1MPXgywD-TvvsB1bFVDQ3CocujcF8ucia`
- **GCS Bucket**: `fdsanalytics-pmix-uploads`
- **Service Account**: `pmix-processor@fdsanalytics.iam.gserviceaccount.com`
- **Region**: `us-central1`

### Import Log

Track import status in BigQuery:
```sql
-- Recent imports
SELECT * FROM insights.pmix_import_log ORDER BY processed_at DESC LIMIT 10;

-- Failed imports
SELECT * FROM insights.pmix_import_log WHERE status = 'failed';
```

### Retry Failed Imports

1. Fix the issue (or wait for code fix)
2. Delete the failed record: `DELETE FROM insights.pmix_import_log WHERE report_date = '2025-XX-XX'`
3. Trigger sync again via webhook

### Monitoring

```bash
# View function logs
gcloud logging read 'resource.labels.function_name="process-pmix"' --limit=20 --project=fdsanalytics

# Check sync function logs
gcloud logging read 'resource.labels.function_name="sync-drive-to-gcs"' --limit=20 --project=fdsanalytics
```

### Deployment

To redeploy after code changes:
```bash
./deploy/deploy_cloud_functions.sh
```

**Note**: The deployment script uses `--allow-unauthenticated` for `sync-drive-to-gcs` and `send-daily-report`
(external webhook and inter-function calls). Security is handled via API key validation in code.

## Daily Email Report (Cloud Function)

Automated daily analytics email triggered after PMIX import completes.

### Trigger Flow

```
PMIX Import completes (yesterday's data)
       ↓
process-pmix refreshes ai.daily_summary
       ↓
process-pmix calls send-daily-report
       ↓
Email sent (duplicate check prevents re-sends)
       ↓
8:15 AM CT fallback (if not already sent)
```

### Report Contents

- **Yesterday's Performance**: Total sales, quantity, unique items + week-over-week comparison
- **7-Day Sales Trend**: Bar chart of recent daily sales
- **Top Categories**: Pie chart breakdown by primary category
- **Top 5 Items**: Best-selling menu items for the day
- **Anomaly Alerts**: Unusual sales/quantity spikes or drops (max 5, grouped by category)
- **5-Day Forecast**: Predicted sales with confidence ranges
- **Call-to-Action**: "Talk to Your Data" button linking to https://sensobot.streamlit.app/chat

### Configuration

- **Primary Trigger**: Automatic after PMIX import (if yesterday's data)
- **Fallback Scheduler**: Cloud Scheduler job `daily-analytics-report` at 14:15 UTC (8:15 AM CT)
- **Duplicate Prevention**: Checks `email_report_log` before sending
- **SendGrid API Key**: Secret Manager `sendgrid-api-key`
- **Sender**: analytics@fdsconsulting.com (domain verified)
- **Recipients**: Stored in `insights.email_recipients` table

### Managing Recipients

```bash
# Add recipient
bq query --nouse_legacy_sql "INSERT INTO insights.email_recipients (email, name, active) VALUES ('user@example.com', 'Name', TRUE)"

# Deactivate recipient
bq query --nouse_legacy_sql "UPDATE insights.email_recipients SET active = FALSE WHERE email = 'user@example.com'"

# List active recipients
bq query --nouse_legacy_sql "SELECT * FROM insights.email_recipients WHERE active = TRUE"
```

### Testing & Monitoring

**Test mode behavior** (when using `?test_date=`):
- Sends only to `fred@fdsconsulting.com` (not all recipients)
- Bypasses duplicate check (can re-run tests freely)

```bash
# Test the email function with specific date
curl "https://us-central1-fdsanalytics.cloudfunctions.net/send-daily-report?test_date=2026-01-04"

# Check email logs
bq query --nouse_legacy_sql "SELECT * FROM insights.email_report_log ORDER BY sent_at DESC LIMIT 10"

# View function logs
gcloud logging read 'resource.labels.function_name="send-daily-report"' --limit=10 --project=fdsanalytics
```

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

# Run stress test (original mode - new conversation every 10 questions)
python scripts/test_agent.py --agent SensoBot --stress-test

# Run grouped stress test (one conversation per category, tests follow-up context)
python scripts/test_agent.py --agent SensoBot --stress-test --grouped

# Run grouped stress test with file logging
python scripts/test_agent.py --agent SensoBot --stress-test --grouped --log

# Limit to first N questions
python scripts/test_agent.py --agent SensoBot --stress-test --grouped --log --limit 10
```

### Stress Test Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `--stress-test` | New conversation every 10 questions | Quick batch testing |
| `--stress-test --grouped` | One conversation per category + context switching test | Tests follow-up context within topics |
| `--stress-test --grouped --log` | Same + writes to `logs/stress_test_YYYYMMDD_HHMMSS.log` | Full test run with audit trail |

### Stress Test Questions

See `Stress Test Questions.md` for 121 sample queries organized by 20 categories:
- Basic queries, category analysis, time patterns
- Weather correlations, event impact, forecasting
- Weather forecast, category forecasting, anomaly detection
- Item-level analysis, comparisons, discount analysis
- Complex/multi-dimensional, visualization requests
- Edge cases, vague/ambiguous queries, data quality
- Natural language variations, context switching tests

### Test Results (2025-12-31)

- **121 questions** across 20 conversation groups
- **120/121 passed** (99.2% success rate)
- **Duration**: ~33 minutes
- **Failed**: "What's our average ticket by category?" (SQL COUNT signature error)
- **Verified**: Weather queries correctly use `ai.daily_summary`
- **Verified**: Category forecasting, anomaly detection, weather forecasts all working

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

# Category forecasts
bq query --nouse_legacy_sql "SELECT * FROM ai.primary_category_forecast WHERE primary_category LIKE '%Beer%' LIMIT 5"
bq query --nouse_legacy_sql "SELECT * FROM ai.category_anomalies WHERE is_anomaly = TRUE ORDER BY report_date DESC LIMIT 10"

# Check scheduled queries
bq ls --transfer_config --transfer_location=us-central1 --project_id=fdsanalytics

# View scheduled query run history
bq ls --transfer_run --transfer_location=us-central1 --max_results=5 'projects/111874159771/locations/us-central1/transferConfigs/<config_id>'

# Trigger PMIX sync (via webhook)
API_KEY=$(gcloud secrets versions access latest --secret=pmix-sync-api-key --project=fdsanalytics)
curl -X POST https://sync-drive-to-gcs-nkiogckaga-uc.a.run.app -H "X-API-Key: $API_KEY"

# Check PMIX import log
bq query --nouse_legacy_sql "SELECT * FROM insights.pmix_import_log ORDER BY processed_at DESC LIMIT 10"

# View Cloud Function logs
gcloud logging read 'resource.labels.function_name="process-pmix"' --limit=10 --project=fdsanalytics
gcloud logging read 'resource.labels.function_name="sync-drive-to-gcs"' --limit=10 --project=fdsanalytics

# List Cloud Functions
gcloud functions list --project=fdsanalytics --filter="name~pmix OR name~sync-drive OR name~daily-report OR name~weather"

# Daily Email Report (test mode: sends only to fred@fdsconsulting.com, bypasses duplicate check)
curl "https://us-central1-fdsanalytics.cloudfunctions.net/send-daily-report?test_date=2026-01-04"
bq query --nouse_legacy_sql "SELECT * FROM insights.email_report_log ORDER BY sent_at DESC LIMIT 5"
bq query --nouse_legacy_sql "SELECT * FROM insights.email_recipients WHERE active = TRUE"

# Weather Pipeline
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $(gcloud functions describe fetch-openmeteo-weather --region=us-central1 --format='value(serviceConfig.uri)')
bq query --nouse_legacy_sql "SELECT * FROM insights.weather_import_log ORDER BY processed_at DESC LIMIT 10"
bq query --nouse_legacy_sql "SELECT * FROM insights.weather_forecast ORDER BY forecast_date"
bq query --nouse_legacy_sql "SELECT weather_date, avg_temp_f, weather_condition FROM insights.local_weather ORDER BY weather_date DESC LIMIT 5"
python scripts/backfill_openmeteo_weather.py --dry-run

# Weather-aware sales forecast
bq query --nouse_legacy_sql "
SELECT f.forecast_date, ROUND(f.predicted_sales) as sales, w.weather_condition, ROUND(w.high_temp_f) as high_temp
FROM insights.sales_forecast_results f
LEFT JOIN insights.weather_forecast w ON f.forecast_date = w.forecast_date
ORDER BY f.forecast_date"

# Check Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-central1 --project=fdsanalytics
```
