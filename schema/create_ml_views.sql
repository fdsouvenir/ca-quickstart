-- AI-facing views for ML results
-- Simple interface for LLMs to query forecasts and anomalies

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
