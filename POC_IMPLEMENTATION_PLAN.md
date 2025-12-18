# POC Implementation Plan: Denormalized Schema with BQML

> **Status**: READY FOR IMPLEMENTATION
> **Last Updated**: 2025-12-18
> **Previous Document**: PMIX_PARSER_PLAN.md (superseded)

---

## Context for Next Agent

### What This Project Is

This is a **Conversational Analytics** app for a restaurant in Frankfort, IL. The end goal is an **AI-powered just-in-time UI/report builder** where business owners ask natural language questions and get instant answers with visualizations.

**Data Flow:**
```
SpotOn POS (restaurant) -> PMIX PDF exports -> BigQuery -> Gemini Data Analytics API -> User
```

The PMIX PDF parsing is a **temporary stopgap** because we don't have SpotOn API access yet. Once approved, we'll pull data directly from: https://developers.spoton.com/restaurant/reference/getlocations

### Why We're Refactoring

The original implementation had architectural issues:

1. **Loaded to wrong table**: Parser wrote to `insights.top_items` but should write to `restaurant_analytics` tables
2. **Used EAV pattern**: The `restaurant_analytics.metrics` table stores each metric (net_sales, quantity_sold, discount) as separate rows - 3x the data, complex queries
3. **JSON dimensions**: Category/item stored as JSON strings requiring `JSON_EXTRACT_SCALAR()` on every query
4. **Unused stored procedures**: Complex procedures (`populate_daily_insights`, `query_metrics`) were built but never integrated
5. **No partitioning/clustering**: Missing basic BigQuery optimizations
6. **Hard for LLMs**: The schema requires complex multi-join queries that LLMs struggle to generate correctly
7. **Multi-event day duplication**: Current view joins directly to events table, causing row multiplication when multiple events occur on the same day
8. **Hardcoded city name**: Events table was named `frankfort_events`, preventing multi-city expansion

### The New Architecture

**FROM:**
```
PMIX PDFs -> parse_pmix_pdf.py -> insights.top_items (flat file, wrong place)
                              -> restaurant_analytics.metrics (EAV, 3x rows, JSON)
                              -> populate_daily_insights() (unused)
                              -> insights.category_trends, etc.
```

**TO:**
```
PMIX PDFs -> parse_pmix_pdf.py -> restaurant_analytics.item_sales (denormalized, 1 row per item)
                              -> restaurant_analytics.locations (dimension table)
                              -> insights.local_events (renamed, with region support)
                              -> insights.expanded_events (view with recurrence logic)
                              -> ai.restaurant_analytics (unified view with weather/events pre-joined)
                              -> Materialized views for aggregations
                              -> BQML model for forecasting + anomaly detection
                              -> Materialized tables for ML results (daily refresh)
```

---

## Key Decisions (with Reasoning)

| Decision | Choice | Reason |
|----------|--------|--------|
| Target table | `restaurant_analytics.item_sales` | Proper fact table in the analytics dataset |
| Schema design | Denormalized (1 row = 1 item) | LLMs generate simpler queries; 3x less data than EAV |
| JSON dimensions | Flat columns | No `JSON_EXTRACT_SCALAR()` needed; proper types |
| Unified view | `ai.restaurant_analytics` | Pre-joins weather/events so LLM doesn't need to know join logic |
| AI dataset | New `ai` dataset | Clean separation between raw data and LLM-facing views |
| AI view type | **Regular view** (not materialized) | BigQuery materialized views cannot use JOINs; this view has multiple JOINs |
| Reports table | DROP | Not needed - `report_date` is in item_sales directly |
| Stored procedures | KEEP but deprecate | May be useful reference; too complex for LLM use |
| Old metrics table | Don't migrate | Data came from buggy parser; fresh import is cleaner |
| Partitioning | By `report_date` | Essential for BQ cost/performance with time-series data |
| Clustering | By `primary_category, category` | Common filter columns for faster scans |
| Multi-event days | Aggregate to day-level with STRING_AGG | Prevents row duplication; keeps one row per item-day |
| Events table name | `local_events` (was `frankfort_events`) | Generic name supports multi-city expansion |
| Event recurrence | Explicit `recurrence_type` column | Heuristic based on date range fails for multi-week daily events (see below) |
| Location-region mapping | New `locations` dimension table | Cleanly links restaurant locations to geographic regions for event joins |
| Closed days (`[CLOSED]` rows) | Don't emit from parser | Inferred from missing dates; API will handle explicitly in production |
| BQML models | Single model for both forecast + anomaly | Same underlying ARIMA_PLUS model serves both purposes |
| ML results | Materialized tables with daily refresh | Lower cost than re-running ML functions on every query |
| `source_file` field | Renamed to `data_source` | Supports both PDF imports and future SpotOn API data lineage |

### Why Explicit `recurrence_type` Instead of Date Range Heuristic

The original plan used a 7-day threshold to guess if an event was weekly-recurring or consecutive-daily:
```sql
-- Old approach (flawed)
WHERE DATE_DIFF(end_date, event_date, DAY) > 7  -- Assumed weekly
WHERE DATE_DIFF(end_date, event_date, DAY) <= 7  -- Assumed consecutive
```

**Problem:** A 15-day daily festival would be treated as weekly (generating ~2 rows instead of 15).

| Scenario | Duration | Actual Pattern | Old Result | New Result |
|----------|----------|----------------|------------|------------|
| Fall Fest | 3 days | Daily | Correct | Correct |
| Country Market | 183 days | Weekly Sundays | Correct | Correct |
| 2-Week Festival | 15 days | Daily | **Wrong** (2 rows) | Correct (15 rows) |

**Solution:** Make recurrence explicit in the data with `recurrence_type` column:
- `'single'` - One-day event
- `'daily'` - Runs every day in the date range
- `'weekly'` - Runs once per week on the start day's weekday

---

## Current State of Parser

The parser itself (`scripts/parse_pmix_pdf.py`) is **working correctly** and validated:
- 200/200 days parsed successfully
- 0 errors, 0 flagged
- 27,251 records, $1,535,454.82 total sales
- Handles both old format (Dec 2024 - Mar 2025) and new format (Apr 2025+)

What needs to change is the **output format** and **target table**, not the parsing logic.

---

## BigQuery Resources

### Current (to be deprecated/modified)

| Resource | Status | Action |
|----------|--------|--------|
| `restaurant_analytics.metrics` | Deprecated | Keep for reference, mark deprecated |
| `restaurant_analytics.reports` | Unused | DROP |
| `insights.top_items` | Wrong location | Mark deprecated |
| `insights.frankfort_events` | Hardcoded city | Rename to `local_events`, add columns |
| `insights.category_trends` | Wrong source | Mark deprecated |
| Various stored procedures | Unused | Mark deprecated |

### New (to be created)

| Resource | Type | Purpose |
|----------|------|---------|
| `ai` dataset | Dataset | LLM-facing views (clean separation) |
| `restaurant_analytics.item_sales` | Table | Denormalized fact table (partitioned/clustered) |
| `restaurant_analytics.locations` | Table | Dimension table mapping locations to regions |
| `insights.local_events` | Table | Renamed from `frankfort_events`, with `recurrence_type` and `region` |
| `insights.expanded_events` | View | Expands multi-day events to one row per occurrence |
| `ai.restaurant_analytics` | View | Unified view with weather/events pre-joined |
| `ai.restaurant_analytics_extended` | View | Unified view with anomaly data |
| `ai.sales_forecast` | View | 14-day sales forecast |
| `ai.data_quality` | View | Data coverage metadata for AI self-validation |
| `insights.daily_totals` | Materialized View | Daily aggregations |
| `insights.category_daily` | Materialized View | Category-level daily aggregations |
| `insights.sales_model` | BQML Model | Single ARIMA_PLUS for forecasting and anomaly detection |
| `insights.sales_forecast_results` | Table | Materialized forecast results (daily refresh) |
| `insights.sales_anomaly_results` | Table | Materialized anomaly results (daily refresh) |

---

## TL;DR Execution Order

```bash
# 1. Create ai dataset and core tables
bq mk --dataset --location=us-central1 fdsanalytics:ai
bq query --nouse_legacy_sql < schema/create_item_sales.sql
bq query --nouse_legacy_sql < schema/create_locations.sql

# 2. Migrate events table (rename + add columns)
bq query --nouse_legacy_sql < schema/migrate_events.sql

# 3. Create expanded events view (uses recurrence_type)
bq query --nouse_legacy_sql < schema/create_expanded_events.sql

# 4. Update parser scripts (code changes)
# - scripts/parse_pmix_pdf.py: customer_id -> location, add data_source, remove [CLOSED] rows
# - scripts/import_pmix.py: target -> restaurant_analytics.item_sales

# 5. Run import
python scripts/import_pmix.py --pmix-dir pmix/ --dry-run
python scripts/import_pmix.py --pmix-dir pmix/

# 6. Create AI view, data quality view, and materialized views
bq query --nouse_legacy_sql < schema/create_ai_view.sql
bq query --nouse_legacy_sql < schema/create_data_quality_view.sql
bq query --nouse_legacy_sql < schema/create_materialized_views.sql

# 7. Verify data import
bq query --nouse_legacy_sql "SELECT COUNT(*), SUM(net_sales) FROM ai.restaurant_analytics"
# Expected: ~27,251 rows (minus [CLOSED] rows), ~$1,535,454.82

# 8. Create BQML model (takes a few minutes to train)
bq query --nouse_legacy_sql < schema/create_bqml_model.sql

# 9. Create ML result tables and populate
bq query --nouse_legacy_sql < schema/create_ml_tables.sql
bq query --nouse_legacy_sql < schema/refresh_ml_tables.sql

# 10. Create AI views for ML results
bq query --nouse_legacy_sql < schema/create_ml_views.sql

# 11. Verify BQML
bq query --nouse_legacy_sql "SELECT * FROM ai.sales_forecast LIMIT 7"
bq query --nouse_legacy_sql "SELECT * FROM insights.sales_anomaly_results WHERE is_anomaly = TRUE LIMIT 5"

# 12. Set up scheduled query for daily ML refresh (use BigQuery Console UI)
# See Phase 7 for details

# 13. Cleanup old tables (after verification)
bq query --nouse_legacy_sql "DROP TABLE restaurant_analytics.reports"
```

---

## Phase 1: Schema Changes

### 1.1 Create New Denormalized Table

**Why denormalized?** An LLM can easily generate:
```sql
SELECT item_name, net_sales FROM item_sales WHERE report_date = '2025-06-14'
```

But struggles with EAV:
```sql
SELECT JSON_EXTRACT_SCALAR(m.dimensions, '$.item_name'), m.metric_value
FROM metrics m JOIN reports r ON m.report_id = r.report_id
WHERE m.metric_name = 'net_sales' AND r.report_date = '2025-06-14'
```

**File:** `schema/create_item_sales.sql`
```sql
CREATE TABLE restaurant_analytics.item_sales (
  -- Keys
  report_date DATE NOT NULL,
  location STRING NOT NULL,

  -- Dimensions (flat, not JSON)
  primary_category STRING,
  category STRING,
  item_name STRING NOT NULL,

  -- Facts (all metrics as columns)
  quantity_sold INT64,
  net_sales FLOAT64,
  discount FLOAT64,

  -- Metadata
  data_source STRING,  -- e.g., "pmix-pdf:pmix-senso-2025-06-14.pdf" or "spoton-api:txn-123"
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY report_date
CLUSTER BY primary_category, category
OPTIONS (
  description = 'Denormalized item-level sales from POS system. One row per item per day.'
);
```

### 1.2 Create Locations Dimension Table

**Why a locations table?** Links restaurant locations to geographic regions for event joins. When you have locations in multiple cities, the view needs to know which local events apply to which location.

**File:** `schema/create_locations.sql`
```sql
CREATE TABLE restaurant_analytics.locations (
  location STRING NOT NULL,      -- Primary key, matches item_sales.location
  region STRING NOT NULL,        -- Matches local_events.region (e.g., 'frankfort-il')
  display_name STRING,           -- Human-readable name for UI (e.g., 'Senso Sushi')
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
  description = 'Dimension table mapping restaurant locations to geographic regions for event joins.'
);

-- Insert initial location
INSERT INTO restaurant_analytics.locations (location, region, display_name)
VALUES ('senso-sushi', 'frankfort-il', 'Senso Sushi');
```

### 1.3 Migrate Events Table

**Why rename and restructure?**
- `frankfort_events` hardcodes the city name - prevents multi-city expansion
- Adding `recurrence_type` eliminates buggy date-range heuristic
- Adding `region` enables proper location-to-event joins

**File:** `schema/migrate_events.sql`
```sql
-- Create new table with updated schema
CREATE TABLE insights.local_events (
  event_date DATE NOT NULL,
  event_name STRING NOT NULL,
  event_type STRING,
  recurrence_type STRING DEFAULT 'single',  -- 'single', 'daily', 'weekly'
  end_date DATE,
  region STRING NOT NULL,  -- e.g., 'frankfort-il'
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
  description = 'Local events by region. Used to correlate sales with community events.'
);

-- Migrate existing data with recurrence_type based on known patterns
INSERT INTO insights.local_events (event_date, event_name, event_type, recurrence_type, end_date, region)
SELECT
  event_date,
  event_name,
  event_type,
  CASE
    -- Weekly recurring events (known from data analysis)
    WHEN event_name IN ('Country Market', 'Cruisin Frankfort', 'Fridays on the Green', 'Concerts on the Green')
      THEN 'weekly'
    -- Multi-day consecutive events
    WHEN is_multi_day = TRUE THEN 'daily'
    -- Single-day events
    ELSE 'single'
  END as recurrence_type,
  end_date,
  'frankfort-il' as region  -- All existing events are Frankfort
FROM insights.frankfort_events;

-- Verify migration
-- SELECT recurrence_type, COUNT(*) FROM insights.local_events GROUP BY 1;

-- After verification, drop old table:
-- DROP TABLE insights.frankfort_events;
```

### 1.4 Create Expanded Events View

**Why expand events?** The source `local_events` table stores multi-day events as a single row with start/end dates. We need one row per event-day for proper joining.

**File:** `schema/create_expanded_events.sql`
```sql
-- Expand multi-day events to one row per occurrence
CREATE OR REPLACE VIEW insights.expanded_events AS

-- Single-day events: use as-is
SELECT
  event_date,
  event_name,
  event_type,
  region
FROM insights.local_events
WHERE recurrence_type = 'single'
  OR recurrence_type IS NULL
  OR end_date IS NULL  -- Safety: treat as single if no end date

UNION ALL

-- Daily recurring events: expand to each day in range
SELECT
  day as event_date,
  event_name,
  event_type,
  region
FROM insights.local_events,
  UNNEST(GENERATE_DATE_ARRAY(event_date, end_date, INTERVAL 1 DAY)) as day
WHERE recurrence_type = 'daily'
  AND end_date IS NOT NULL

UNION ALL

-- Weekly recurring events: expand to each week on the same weekday
SELECT
  day as event_date,
  event_name,
  event_type,
  region
FROM insights.local_events,
  UNNEST(GENERATE_DATE_ARRAY(event_date, end_date, INTERVAL 1 WEEK)) as day
WHERE recurrence_type = 'weekly'
  AND end_date IS NOT NULL;
```

### 1.5 Create Unified AI View

**Why a unified view?** Business owners ask questions like "what sells best on rainy days?" The LLM shouldn't need to know that weather is in a different table with a different join key. Pre-join everything.

**Why aggregate events to day-level?** Prevents row duplication when multiple events occur on the same day. Uses STRING_AGG to combine event names into a readable comma-separated list.

**Note:** This is a **regular view**, not a materialized view. BigQuery materialized views cannot use JOINs.

**File:** `schema/create_ai_view.sql`
```sql
CREATE OR REPLACE VIEW ai.restaurant_analytics AS
SELECT
  -- Sales data
  s.report_date,
  s.location,
  l.display_name as location_name,
  l.region,
  s.primary_category,
  s.category,
  s.item_name,
  s.quantity_sold,
  s.net_sales,
  s.discount,

  -- Weather (pre-joined from insights.local_weather)
  w.avg_temp_f,
  w.max_temp_f,
  w.min_temp_f,
  w.had_rain,
  w.had_snow,
  w.precipitation_in,

  -- Events (aggregated to day-level to prevent row duplication)
  e.event_names,
  e.event_types,
  e.event_count,
  e.event_count > 0 as has_local_event,

  -- Time intelligence (pre-computed for easy filtering)
  EXTRACT(DAYOFWEEK FROM s.report_date) as day_of_week,
  FORMAT_DATE('%A', s.report_date) as day_name,
  EXTRACT(WEEK FROM s.report_date) as week_number,
  EXTRACT(MONTH FROM s.report_date) as month,
  FORMAT_DATE('%B', s.report_date) as month_name,
  EXTRACT(YEAR FROM s.report_date) as year,
  EXTRACT(DAYOFWEEK FROM s.report_date) IN (1, 7) as is_weekend

FROM restaurant_analytics.item_sales s
-- Join to locations dimension for region mapping
JOIN restaurant_analytics.locations l ON s.location = l.location
-- Join weather by date
LEFT JOIN insights.local_weather w ON s.report_date = w.weather_date
-- Join events by date AND region (aggregated to prevent row duplication)
LEFT JOIN (
  -- Aggregate events to one row per day per region
  SELECT
    event_date,
    region,
    STRING_AGG(event_name, ', ' ORDER BY event_name) as event_names,
    STRING_AGG(DISTINCT event_type, ', ' ORDER BY event_type) as event_types,
    COUNT(*) as event_count
  FROM insights.expanded_events
  GROUP BY event_date, region
) e ON s.report_date = e.event_date AND l.region = e.region;
```

### 1.6 Create Materialized Views for Common Aggregations

**Why materialized views?** Auto-refresh when base data changes. Replaces the manual `populate_daily_insights()` stored procedure.

**Note:** These CAN be materialized views because they're simple GROUP BYs on a single table (no JOINs).

**File:** `schema/create_materialized_views.sql`
```sql
-- Daily totals (replaces daily_comparisons logic)
CREATE MATERIALIZED VIEW insights.daily_totals AS
SELECT
  report_date,
  location,
  SUM(net_sales) as total_sales,
  SUM(quantity_sold) as total_quantity,
  COUNT(DISTINCT item_name) as unique_items
FROM restaurant_analytics.item_sales
GROUP BY 1, 2;

-- Category daily (replaces category_trends)
CREATE MATERIALIZED VIEW insights.category_daily AS
SELECT
  report_date,
  location,
  primary_category,
  category,
  SUM(net_sales) as sales_total,
  SUM(quantity_sold) as quantity_total,
  COUNT(DISTINCT item_name) as item_count
FROM restaurant_analytics.item_sales
GROUP BY 1, 2, 3, 4;
```

### 1.7 Create Data Quality View for AI Self-Validation

**Why a data quality view?** Helps the AI answer questions about data coverage like "do we have data for this date range?" without hallucinating.

**File:** `schema/create_data_quality_view.sql`
```sql
CREATE OR REPLACE VIEW ai.data_quality AS
SELECT
  MIN(report_date) as earliest_date,
  MAX(report_date) as latest_date,
  COUNT(DISTINCT report_date) as days_with_data,
  COUNT(*) as total_records,
  SUM(net_sales) as total_sales,
  -- Gap detection: expected days minus actual days
  DATE_DIFF(MAX(report_date), MIN(report_date), DAY) + 1
    - COUNT(DISTINCT report_date) as missing_days,
  -- Location breakdown
  STRING_AGG(DISTINCT location, ', ') as locations
FROM restaurant_analytics.item_sales;
```

---

## Phase 2: Parser Updates

### 2.1 Update Output Format

**File:** `scripts/parse_pmix_pdf.py`

Change output from:
```json
{
  "customer_id": "senso-sushi",
  "report_date": "2025-06-14",
  "primary_category": "(Food)",
  "category": "Kids",
  "item_name": "Kids Chicken Bento (GF)",
  "quantity_sold": 5,
  "net_sales": 75.0,
  "discount": 0.0
}
```

To:
```json
{
  "report_date": "2025-06-14",
  "location": "senso-sushi",
  "primary_category": "(Food)",
  "category": "Kids",
  "item_name": "Kids Chicken Bento (GF)",
  "quantity_sold": 5,
  "net_sales": 75.0,
  "discount": 0.0,
  "data_source": "pmix-pdf:pmix-senso-2025-06-14.pdf"
}
```

**Changes needed:**
- Rename `customer_id` -> `location` (clearer semantics for multi-location future)
- Rename `source_file` -> `data_source` with format `"pmix-pdf:{filename}"` (supports future SpotOn API: `"spoton-api:{txn-id}"`)
- Remove `rank` (computed at query time if needed)
- **Do NOT emit rows with `item_name = '[CLOSED]'`** (closed days inferred from missing dates; API will handle in production)

### 2.2 Update Import Script

**File:** `scripts/import_pmix.py`

**Changes needed:**
- Target table: `restaurant_analytics.item_sales` (not `insights.top_items`)
- Delete uses partition-aligned WHERE clause
- Load uses explicit schema or auto-detect

```python
# Delete command (partition-pruned for efficiency)
DELETE FROM `restaurant_analytics.item_sales`
WHERE report_date BETWEEN '{start_date}' AND '{end_date}'
  AND location = 'senso-sushi'

# Load command
bq load \
  --source_format=NEWLINE_DELIMITED_JSON \
  --replace=false \
  restaurant_analytics.item_sales \
  /tmp/pmix_output.json
```

---

## Phase 3: Migration

### 3.1 Create Dataset and Tables

```bash
# Create new ai dataset (us-central1 to match existing data)
bq mk --dataset --location=us-central1 fdsanalytics:ai

# Run schema creation (one-time)
bq query --nouse_legacy_sql < schema/create_item_sales.sql
bq query --nouse_legacy_sql < schema/create_locations.sql
bq query --nouse_legacy_sql < schema/migrate_events.sql
bq query --nouse_legacy_sql < schema/create_expanded_events.sql
bq query --nouse_legacy_sql < schema/create_ai_view.sql
bq query --nouse_legacy_sql < schema/create_materialized_views.sql
```

### 3.2 Backup Existing Data

```bash
# Backup current metrics table (has buggy data but keep for reference)
bq cp restaurant_analytics.metrics restaurant_analytics.metrics_backup_20251218

# Backup current insights tables
bq cp insights.top_items insights.top_items_backup_20251218

# Backup events before migration
bq cp insights.frankfort_events insights.frankfort_events_backup_20251218
```

### 3.3 Run Fresh Import

```bash
cd /home/souvy/ca_quickstart
source venv/bin/activate

# Dry run first (parses all PDFs, validates, shows summary)
python scripts/import_pmix.py --pmix-dir pmix/ --dry-run

# Full import to new table
python scripts/import_pmix.py --pmix-dir pmix/
```

### 3.4 Verify Import

```sql
-- Check row counts and totals
SELECT COUNT(*) as rows,
       COUNT(DISTINCT report_date) as days,
       SUM(net_sales) as total_sales
FROM restaurant_analytics.item_sales
WHERE location = 'senso-sushi';
-- Expected: ~27,251 rows (minus [CLOSED] rows), 200 days, ~$1,535,454.82

-- Verify no duplicate (date, location, item) combinations
SELECT report_date, location, item_name, COUNT(*) as dupes
FROM restaurant_analytics.item_sales
GROUP BY 1, 2, 3
HAVING COUNT(*) > 1;
-- Expected: 0 rows (each item appears once per day)

-- Spot check June 14 (known good reference date)
SELECT SUM(net_sales) as total
FROM restaurant_analytics.item_sales
WHERE report_date = '2025-06-14'
  AND location = 'senso-sushi';
-- Expected: $13,106.94

-- Test the unified view with weather and events
SELECT item_name, net_sales, avg_temp_f, had_rain, event_names, event_count
FROM ai.restaurant_analytics
WHERE report_date = '2025-06-14'
ORDER BY net_sales DESC
LIMIT 5;

-- Verify no row duplication on multi-event days
SELECT report_date, COUNT(*) as item_count
FROM ai.restaurant_analytics
WHERE event_count > 1
GROUP BY 1
ORDER BY 1
LIMIT 5;
-- Should match item counts from item_sales for the same dates

-- Verify events expanded correctly
SELECT event_name, COUNT(*) as occurrences
FROM insights.expanded_events
WHERE region = 'frankfort-il'
GROUP BY 1
ORDER BY 2 DESC;
-- Country Market should have ~26 rows (weekly Apr-Oct)

-- Verify no row duplication in AI view (critical for multi-event days)
SELECT report_date, location, item_name, COUNT(*) as cnt
FROM ai.restaurant_analytics
GROUP BY 1, 2, 3
HAVING COUNT(*) > 1;
-- Expected: 0 rows (STRING_AGG should prevent duplication)

-- Verify partition pruning is working
-- Run with --dry_run to check bytes scanned
-- bq query --dry_run --use_legacy_sql=false "SELECT * FROM restaurant_analytics.item_sales WHERE report_date = '2025-06-14'"
-- Should show bytes scanned ≈ single partition, not full table
```

---

## Phase 4: Update App Configuration

### 4.1 Update CLAUDE.md

Update the agent configuration section:
- Dataset: `ai` (for the unified view)
- Table: `restaurant_analytics`

### 4.2 Update System Prompt for Gemini Agent

```
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

ANOMALY DETECTION (ai.restaurant_analytics_extended view):
- anomaly_probability, is_anomaly, anomaly_type
- "Were there any unusual sales days?" -> WHERE is_anomaly = TRUE
- "Show me sales spikes" -> WHERE anomaly_type = 'spike'

DATA COVERAGE (ai.data_quality view):
- earliest_date, latest_date, days_with_data, total_records, total_sales, missing_days
- Use this view to validate date ranges before answering questions
- "What date range do we have data for?" -> SELECT * FROM ai.data_quality
```

---

## Phase 5: Cleanup (After Verification)

### 5.1 Drop Unused Tables

```sql
-- Drop reports table (not needed with denormalized schema)
DROP TABLE IF EXISTS restaurant_analytics.reports;

-- Drop old events table after migration verified
DROP TABLE IF EXISTS insights.frankfort_events;

-- Deprecate (don't drop yet) old tables
ALTER TABLE restaurant_analytics.metrics
SET OPTIONS (description = 'DEPRECATED 2025-12-18: Use item_sales instead. Data from buggy parser.');

ALTER TABLE insights.top_items
SET OPTIONS (description = 'DEPRECATED 2025-12-18: Use ai.restaurant_analytics view instead');
```

### 5.2 Deprecate Old Stored Procedures

Keep for reference but mark deprecated:
- `insights.populate_daily_insights` - Replaced by materialized views
- `restaurant_analytics.query_metrics` - Direct queries on item_sales are simpler
- `insights.sp_get_category_trends` - Use category_daily materialized view
- `insights.sp_get_daily_summary` - Use daily_totals materialized view
- `insights.sp_get_top_items_from_insights` - Query item_sales directly
- `insights.get_forecast` - Replaced by BQML
- `insights.get_anomalies` - Replaced by BQML

### 5.3 Update unified_analytics View (Backward Compatibility)

```sql
-- Create alias for backward compatibility (if anything uses old view)
CREATE OR REPLACE VIEW insights.unified_analytics AS
SELECT * FROM ai.restaurant_analytics;
```

---

## Phase 6: BQML Models

### 6.1 Single Model for Forecasting and Anomaly Detection

**Why one model?** Both forecasting and anomaly detection use the same underlying ARIMA_PLUS model trained on daily sales. No need to train twice.

**File:** `schema/create_bqml_model.sql`
```sql
-- Single ARIMA_PLUS model for both forecasting and anomaly detection
CREATE OR REPLACE MODEL insights.sales_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_sales',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT
  report_date,
  SUM(net_sales) as total_sales
FROM restaurant_analytics.item_sales
WHERE location = 'senso-sushi'
GROUP BY report_date;
```

**Note:** `holiday_region = 'US'` captures federal holidays but not local Frankfort events (Country Market, Oktoberfest). This is a BQML limitation - ARIMA_PLUS doesn't support custom external regressors easily. The model will still learn from the historical patterns during these events.

### 6.2 ML Result Tables (Materialized for Cost Efficiency)

**Why materialized tables instead of views?** Views that call ML.FORECAST() or ML.DETECT_ANOMALIES() re-run the ML function on every query. This is:
- Expensive (BQML costs per query)
- Slow
- Unnecessary since forecasts/anomalies don't change until new data arrives

**Trade-off:** If someone imports new sales data mid-day, the forecasts won't reflect it until the next refresh. Acceptable for a restaurant analytics use case.

**File:** `schema/create_ml_tables.sql`
```sql
-- Table for forecast results (refreshed daily)
CREATE TABLE IF NOT EXISTS insights.sales_forecast_results (
  forecast_date DATE,
  predicted_sales FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  confidence_level FLOAT64,
  refreshed_at TIMESTAMP
);

-- Table for anomaly detection results (refreshed daily)
CREATE TABLE IF NOT EXISTS insights.sales_anomaly_results (
  report_date DATE,
  actual_sales FLOAT64,
  predicted_sales FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  anomaly_probability FLOAT64,
  is_anomaly BOOLEAN,
  anomaly_type STRING,
  refreshed_at TIMESTAMP
);
```

**File:** `schema/refresh_ml_tables.sql`
```sql
-- Refresh forecast results (run daily via scheduled query)
DELETE FROM insights.sales_forecast_results WHERE TRUE;

INSERT INTO insights.sales_forecast_results
SELECT
  forecast_timestamp as forecast_date,
  forecast_value as predicted_sales,
  prediction_interval_lower_bound as lower_bound,
  prediction_interval_upper_bound as upper_bound,
  confidence_level,
  CURRENT_TIMESTAMP() as refreshed_at
FROM ML.FORECAST(
  MODEL insights.sales_model,
  STRUCT(14 AS horizon, 0.9 AS confidence_level)
);

-- Refresh anomaly results (run daily via scheduled query)
DELETE FROM insights.sales_anomaly_results WHERE TRUE;

INSERT INTO insights.sales_anomaly_results
SELECT
  report_date,
  total_sales as actual_sales,
  predicted_total_sales as predicted_sales,
  lower_bound,
  upper_bound,
  anomaly_probability,
  is_anomaly,
  CASE
    WHEN total_sales > upper_bound THEN 'spike'
    WHEN total_sales < lower_bound THEN 'drop'
    ELSE 'normal'
  END as anomaly_type,
  CURRENT_TIMESTAMP() as refreshed_at
FROM ML.DETECT_ANOMALIES(
  MODEL insights.sales_model,
  STRUCT(0.95 AS anomaly_prob_threshold),
  (
    SELECT report_date, SUM(net_sales) as total_sales
    FROM restaurant_analytics.item_sales
    WHERE location = 'senso-sushi'
    GROUP BY report_date
  )
);
```

### 6.3 AI Views for ML Results

**File:** `schema/create_ml_views.sql`
```sql
-- Forecast view for AI queries
CREATE OR REPLACE VIEW ai.sales_forecast AS
SELECT
  forecast_date,
  predicted_sales,
  lower_bound,
  upper_bound,
  confidence_level,
  FORMAT_DATE('%A', forecast_date) as day_name,
  EXTRACT(DAYOFWEEK FROM forecast_date) IN (1, 7) as is_weekend,
  refreshed_at
FROM insights.sales_forecast_results;

-- Extended restaurant analytics with anomaly data
CREATE OR REPLACE VIEW ai.restaurant_analytics_extended AS
SELECT
  r.*,
  a.anomaly_probability,
  a.is_anomaly,
  a.anomaly_type
FROM ai.restaurant_analytics r
LEFT JOIN insights.sales_anomaly_results a ON r.report_date = a.report_date;
```

---

## Phase 7: Scheduled Query Setup

### 7.1 Create Scheduled Query (BigQuery Console)

**Important:** The `bq query --schedule` syntax shown in some documentation doesn't work as expected. Use the BigQuery Console UI instead:

1. Go to BigQuery Console > Scheduled Queries
2. Click "Create scheduled query"
3. Name: "Daily ML Refresh"
4. Schedule: Daily at 6:00 AM (America/Chicago timezone)
5. Query: Paste contents of `schema/refresh_ml_tables.sql`
6. Processing location: us-central1

Alternatively, use `bq mk --transfer_config`:
```bash
bq mk --transfer_config \
  --project_id=fdsanalytics \
  --data_source=scheduled_query \
  --target_dataset=insights \
  --display_name="Daily ML Refresh" \
  --schedule="every day 06:00" \
  --params='{"query":"... SQL here ..."}'
```

### 7.2 Future Enhancement: MERGE Instead of DELETE+INSERT

**Current approach:** DELETE all rows, then INSERT new rows. Has a brief race condition where table is empty.

**Better approach (future):** Use MERGE statement for atomic upsert. Not critical for a 6 AM refresh when no one is querying, but cleaner.

---

## Files to Modify

| File | Changes |
|------|---------|
| `scripts/parse_pmix_pdf.py` | Rename `customer_id` -> `location`, add `data_source` field (format: `pmix-pdf:{filename}`), skip `[CLOSED]` rows |
| `scripts/import_pmix.py` | Change target table to `restaurant_analytics.item_sales`, update delete/load SQL |
| `CLAUDE.md` | Update agent config section, system prompt |

## New Files to Create

| File | Purpose |
|------|---------|
| `schema/create_item_sales.sql` | DDL for new denormalized table |
| `schema/create_locations.sql` | DDL for locations dimension table |
| `schema/migrate_events.sql` | Migrate frankfort_events to local_events with new columns |
| `schema/create_expanded_events.sql` | View expanding multi-day events using recurrence_type |
| `schema/create_ai_view.sql` | Unified AI view definition |
| `schema/create_data_quality_view.sql` | Data coverage view for AI self-validation |
| `schema/create_materialized_views.sql` | Aggregation materialized views |
| `schema/create_bqml_model.sql` | Single ARIMA_PLUS model |
| `schema/create_ml_tables.sql` | Tables for ML results |
| `schema/refresh_ml_tables.sql` | Script to refresh ML results |
| `schema/create_ml_views.sql` | AI-facing views for ML data |

---

## Rollback Plan

If issues arise:
1. Old data preserved in `*_backup_20251218` tables
2. Old stored procedures still exist (just deprecated)
3. Can restore events by: `bq cp insights.frankfort_events_backup_20251218 insights.frankfort_events`
4. Can restore metrics by: `bq cp restaurant_analytics.metrics_backup_20251218 restaurant_analytics.metrics`

---

## Success Criteria

1. All 200 days imported to `item_sales` with correct totals (~27,251 rows minus [CLOSED], ~$1,535,454.82)
2. No duplicate (date, location, item_name) rows in item_sales
3. `insights.expanded_events` correctly expands using recurrence_type (Country Market = ~26 weekly rows)
4. `ai.restaurant_analytics` view returns results with weather/events pre-joined, no row duplication
5. Simple queries work: `SELECT * FROM ai.restaurant_analytics WHERE had_rain LIMIT 10`
6. Materialized views created and auto-refresh on data changes
7. Query costs reduced (verify partition pruning with EXPLAIN)
8. Gemini agent can answer questions like "top sellers on rainy weekends" with simple generated SQL
9. Single BQML model trained successfully
10. `ai.sales_forecast` returns 14-day predictions from materialized table
11. `insights.sales_anomaly_results` identifies unusual days from materialized table
12. Scheduled query configured for daily ML refresh at 6 AM
13. Agent can answer "what are predicted sales for next week?" and "were there any unusual sales days?"

---

## Future Enhancements

### Required (Tied to SpotOn API Implementation)

| Enhancement | Reason |
|-------------|--------|
| **Model Retraining Schedule** | Once live data flows in, model needs periodic retraining (weekly or monthly) to learn from new patterns. Current plan only refreshes results, not the model itself. |
| **Closed Days Handling** | API should explicitly report closed days. Consider a `closed_days` table or explicit handling in item_sales. |
| **data_source Format** | API data should use format `spoton-api:{transaction-id}` for lineage |

### Nice to Have

| Enhancement | Description |
|-------------|-------------|
| **Multi-location** | Schema ready via `location` column; just add more locations to `locations` table |
| **Real-time** | Consider Pub/Sub -> BigQuery streaming for live POS data |
| **Weather Forecasting** | Join NOAA forecast data with sales forecast for planning |
| **Item-level Forecasting** | ARIMA_PLUS with `time_series_id_col` for individual items |
| **Forecast Accuracy Tracking** | Morning report comparing yesterday's prediction vs actual; archive to `forecast_accuracy` table |
| **Category-level Forecasting** | Separate ARIMA_PLUS model with `time_series_id_col = 'primary_category'` |
| **MERGE for ML Refresh** | Replace DELETE+INSERT with atomic MERGE to eliminate race condition (low priority) |

---

## Reference: Existing Parser Details

The parser handles two PDF formats automatically:

| Feature | Old Format (Dec 2024 - Mar 2025) | New Format (Apr 2025+) |
|---------|----------------------------------|------------------------|
| Quantity | Decimals: `7.00` | Integers: `7` |
| Currency | Space after $: `$ 56.00` | No space: `$56.00` |
| Extraction | pdfplumber table extraction | Word-position extraction |
| PDFs | 77 files | 136 files |

**Column boundaries (new format):**
- Category (menu group): x < 85
- Item name: 85 <= x < 185
- Quantity: 185 <= x < 220
- Currency values: x >= 220

**Validation log:** `pmix/validation_log.json` (200 entries, all approved)

---

## Reference: Bugs Previously Fixed

These bugs were fixed in the parser and are documented for context:

1. **"Kids Kids" Category Parsing** - Category column boundary narrowed from x<100 to x<85
2. **Items with 100% Category Sales Skipped** - Added check for item_name presence before skipping
3. **Gift Card Overcounting (Old Format)** - Added subtotal detection to table parser

See git history for details.

---

## Reference: Events Data

### Current Events in frankfort_events (to be migrated)

| Event | Pattern | Date Range | recurrence_type |
|-------|---------|------------|-----------------|
| Country Market | Weekly Sundays | Apr 27 - Oct 26 | weekly |
| Cruisin Frankfort | Weekly Mondays | Jun 2 - Sep 22 | weekly |
| Fridays on the Green | Weekly Fridays | Jun 6 - Jul 25 | weekly |
| Concerts on the Green | Weekly Sundays | Jun 15 - Aug 24 | weekly |
| Bluegrass Fest | Consecutive 2 days | Jul 12-13 | daily |
| Fall Fest | Consecutive 3 days | Aug 30 - Sep 1 | daily |
| Frankforter Oktoberfest | Consecutive 2 days | Oct 10-11 | daily |
| Home for the Holidays | Consecutive 2 days | Dec 13-14 | daily |
| Single-day events | One day only | Various | single |

### Events Source

Events scraped from: https://www.frankfortil.org/residents/special_events/index.php

To add new events:
```sql
INSERT INTO `fdsanalytics.insights.local_events`
VALUES ('2026-07-04', 'Fourth of July Fireworks', 'patriotic', 'single', NULL, 'frankfort-il', CURRENT_TIMESTAMP());
```
