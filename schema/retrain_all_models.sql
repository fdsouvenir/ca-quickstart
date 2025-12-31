-- Weekly model retraining script
-- Run every Sunday night via scheduled query (e.g., 2 AM)
-- Rebuilds ALL models to capture new categories and updated patterns
--
-- Schedule in BigQuery Console:
--   1. Go to BigQuery > Scheduled queries
--   2. Create new scheduled query
--   3. Set schedule: Weekly on Sunday at 2:00 AM America/Chicago
--   4. Use this SQL as the query

-- =====================================================
-- RETRAIN TOTAL SALES MODEL
-- =====================================================

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

-- =====================================================
-- RETRAIN PRIMARY CATEGORY MODELS
-- =====================================================

-- Retrain Primary Category Sales Model
CREATE OR REPLACE MODEL insights.primary_category_sales_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_sales',
  time_series_id_col = 'primary_category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, primary_category, total_sales
FROM insights.primary_category_daily_dense;

-- Retrain Primary Category Quantity Model
CREATE OR REPLACE MODEL insights.primary_category_qty_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_quantity',
  time_series_id_col = 'primary_category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, primary_category, total_quantity
FROM insights.primary_category_daily_dense;

-- =====================================================
-- RETRAIN FINE CATEGORY MODELS
-- =====================================================

-- Retrain Fine Category Sales Model
CREATE OR REPLACE MODEL insights.category_sales_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_sales',
  time_series_id_col = 'category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, category, total_sales
FROM insights.category_daily_dense;

-- Retrain Fine Category Quantity Model
CREATE OR REPLACE MODEL insights.category_qty_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_quantity',
  time_series_id_col = 'category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, category, total_quantity
FROM insights.category_daily_dense;
