-- Tables for ML results (materialized for cost efficiency)
-- Refreshed daily via scheduled query
-- Avoids re-running ML functions on every query

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
