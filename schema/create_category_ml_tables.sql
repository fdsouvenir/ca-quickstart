-- Result tables for category-level forecasts and anomaly detection
-- Materialized results for fast querying (populated by refresh_ml_tables.sql)

-- =====================================================
-- FORECAST RESULT TABLES (4 tables)
-- =====================================================

-- Primary Category Sales Forecasts
CREATE TABLE IF NOT EXISTS insights.primary_category_sales_forecast_results (
  forecast_date DATE,
  primary_category STRING,
  predicted_sales FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  confidence_level FLOAT64,
  refreshed_at TIMESTAMP
);

-- Primary Category Quantity Forecasts
CREATE TABLE IF NOT EXISTS insights.primary_category_qty_forecast_results (
  forecast_date DATE,
  primary_category STRING,
  predicted_quantity FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  confidence_level FLOAT64,
  refreshed_at TIMESTAMP
);

-- Fine Category Sales Forecasts
CREATE TABLE IF NOT EXISTS insights.category_sales_forecast_results (
  forecast_date DATE,
  category STRING,
  predicted_sales FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  confidence_level FLOAT64,
  refreshed_at TIMESTAMP
);

-- Fine Category Quantity Forecasts
CREATE TABLE IF NOT EXISTS insights.category_qty_forecast_results (
  forecast_date DATE,
  category STRING,
  predicted_quantity FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  confidence_level FLOAT64,
  refreshed_at TIMESTAMP
);

-- =====================================================
-- ANOMALY RESULT TABLES (2 tables - combined metrics)
-- =====================================================

-- Primary Category Anomalies (both sales and quantity)
CREATE TABLE IF NOT EXISTS insights.primary_category_anomaly_results (
  report_date DATE,
  primary_category STRING,
  metric_type STRING,  -- 'sales' or 'quantity'
  actual_value FLOAT64,
  predicted_value FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  anomaly_probability FLOAT64,
  is_anomaly BOOLEAN,
  anomaly_type STRING,  -- 'spike', 'drop', 'normal'
  refreshed_at TIMESTAMP
);

-- Fine Category Anomalies (both sales and quantity)
CREATE TABLE IF NOT EXISTS insights.category_anomaly_results (
  report_date DATE,
  category STRING,
  metric_type STRING,  -- 'sales' or 'quantity'
  actual_value FLOAT64,
  predicted_value FLOAT64,
  lower_bound FLOAT64,
  upper_bound FLOAT64,
  anomaly_probability FLOAT64,
  is_anomaly BOOLEAN,
  anomaly_type STRING,  -- 'spike', 'drop', 'normal'
  refreshed_at TIMESTAMP
);
