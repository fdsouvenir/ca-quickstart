# Restaurant Analytics with Conversational AI

A natural language analytics platform for restaurant data, powered by Google's Conversational Analytics API and BigQuery ML.

## Overview

This application enables restaurant owners to ask questions about their sales data in plain English and get instant insights with visualizations. Built on Google's Conversational Analytics API, it combines:

- **PMIX PDF parsing** - Extracts sales data from SpotOn POS daily reports
- **Denormalized BigQuery schema** - Optimized for LLM query generation
- **Weather & event enrichment** - Correlates sales with local conditions
- **BQML forecasting** - 14-day sales predictions using ARIMA_PLUS

### Example Questions

- "What were our top sellers last weekend?"
- "How do sales compare on rainy vs sunny days?"
- "Which items sell best during Country Market?"
- "What are predicted sales for next week?"

## Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud SDK (`gcloud` CLI)
- Access to `fdsanalytics` GCP project

### Setup

```bash
# Clone and enter directory
git clone https://github.com/fdsouvenir/ca-quickstart.git
cd ca-quickstart

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Authenticate with GCP
gcloud auth application-default login
gcloud auth application-default set-quota-project fdsanalytics
```

### Run the App

```bash
streamlit run app.py
```

Access at http://localhost:8501

## Architecture

### Data Flow

```
SpotOn POS → PMIX PDFs → Parser → BigQuery → Gemini API → User
                ↓
         [pmix/ folder]
                ↓
    scripts/parse_pmix_pdf.py
                ↓
    restaurant_analytics.item_sales
                ↓
    ai.restaurant_analytics (view)
                ↓
    Conversational Analytics Agent
```

### BigQuery Resources

| Resource | Type | Purpose |
|----------|------|---------|
| `restaurant_analytics.item_sales` | Table | Denormalized fact table (27K+ records) |
| `restaurant_analytics.locations` | Table | Location-to-region mapping |
| `insights.local_events` | Table | Frankfort IL community events |
| `insights.local_weather` | Table | Daily weather from NOAA |
| `insights.sales_model` | BQML Model | ARIMA_PLUS for forecasting |
| `ai.restaurant_analytics` | View | **Primary LLM view** - pre-joined data |
| `ai.sales_forecast` | View | 14-day predictions |
| `ai.data_quality` | View | Data coverage metadata |

### Schema Design

The `ai.restaurant_analytics` view pre-joins all data so the LLM generates simple queries:

```sql
-- Sales columns
report_date, location, primary_category, category, item_name,
quantity_sold, net_sales, discount

-- Weather columns
avg_temp_f, max_temp_f, min_temp_f, had_rain, had_snow

-- Event columns
event_names, event_types, event_count, has_local_event

-- Time intelligence
day_of_week, day_name, is_weekend, month, month_name
```

## Importing Sales Data

### Parse PMIX PDFs

```bash
# Dry run (parse + validate, no BigQuery)
python scripts/import_pmix.py --pmix-dir pmix/ --dry-run

# Full import
python scripts/import_pmix.py --pmix-dir pmix/
```

### Refresh ML Results

ML forecasts and anomaly detection are refreshed daily via scheduled query. Manual refresh:

```bash
bq query --nouse_legacy_sql < schema/refresh_ml_tables.sql
```

## Agent Configuration

When creating an agent in the app:

| Field | Value |
|-------|-------|
| Project ID | `fdsanalytics` |
| Dataset | `ai` |
| Table | `restaurant_analytics` |

### Recommended System Instructions

```
You are a concise restaurant analytics assistant. Keep answers brief and scannable.

DATA AVAILABLE (ai.restaurant_analytics view):
- Sales: report_date, item_name, category, net_sales, quantity_sold
- Weather: avg_temp_f, had_rain, had_snow
- Events: event_names, has_local_event
- Time: day_name, is_weekend, month_name

FORECASTING: Use ai.sales_forecast for predictions
DATA COVERAGE: Use ai.data_quality to validate date ranges

Keep responses short. Lead with the key insight.
```

## Project Structure

```
ca_quickstart/
├── app.py                 # Streamlit entry point
├── state.py               # Session state management
├── app_pages/             # Multi-page app modules
├── utils/                 # Helper utilities
├── scripts/
│   ├── parse_pmix_pdf.py  # PDF parser
│   └── import_pmix.py     # Bulk import to BigQuery
├── schema/                # BigQuery DDL scripts
│   ├── create_item_sales.sql
│   ├── create_ai_view.sql
│   ├── create_bqml_model.sql
│   └── ...
├── pmix/                  # PMIX PDF files (gitignored)
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml       # GCP project ID
├── CLAUDE.md              # Detailed project context
└── POC_IMPLEMENTATION_PLAN.md
```

## Useful Commands

```bash
# Query the AI view
bq query --nouse_legacy_sql "SELECT * FROM ai.restaurant_analytics LIMIT 10"

# Check data quality
bq query --nouse_legacy_sql "SELECT * FROM ai.data_quality"

# Get sales forecast
bq query --nouse_legacy_sql "SELECT * FROM ai.sales_forecast"

# List events
bq query --nouse_legacy_sql "SELECT event_name, COUNT(*) FROM insights.expanded_events GROUP BY 1"
```

## Data Sources

- **Sales**: SpotOn POS PMIX reports (Dec 2024 - Sep 2025)
- **Weather**: NOAA GSOD from Joliet Regional Airport
- **Events**: Frankfort IL community calendar

## License

Based on [Google's CA API Quickstart](https://github.com/looker-open-source/ca-api-quickstarts). See original repository for license terms.
