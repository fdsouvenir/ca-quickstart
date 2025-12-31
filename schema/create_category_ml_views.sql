-- AI-facing views for category-level forecasts and anomaly detection
-- These views combine sales and quantity forecasts for easier querying

-- =====================================================
-- FORECAST VIEWS
-- =====================================================

-- Primary Category Forecast (combined sales + quantity)
-- Use for: "How many beers should I expect to sell next Saturday?"
CREATE OR REPLACE VIEW ai.primary_category_forecast AS
SELECT
  s.forecast_date,
  s.primary_category,
  FORMAT_DATE('%A', s.forecast_date) as day_name,
  EXTRACT(DAYOFWEEK FROM s.forecast_date) IN (1, 7) as is_weekend,
  -- Sales forecast
  ROUND(s.predicted_sales, 2) as predicted_sales,
  ROUND(s.lower_bound, 2) as sales_lower_bound,
  ROUND(s.upper_bound, 2) as sales_upper_bound,
  -- Quantity forecast
  ROUND(q.predicted_quantity, 0) as predicted_quantity,
  ROUND(q.lower_bound, 0) as quantity_lower_bound,
  ROUND(q.upper_bound, 0) as quantity_upper_bound,
  -- Metadata
  s.confidence_level,
  s.refreshed_at
FROM insights.primary_category_sales_forecast_results s
JOIN insights.primary_category_qty_forecast_results q
  ON s.forecast_date = q.forecast_date
  AND s.primary_category = q.primary_category;

-- Fine Category Forecast (combined sales + quantity)
-- Use for: "Forecast Classic Rolls for next week"
CREATE OR REPLACE VIEW ai.category_forecast AS
SELECT
  s.forecast_date,
  s.category,
  fc.primary_category,
  FORMAT_DATE('%A', s.forecast_date) as day_name,
  EXTRACT(DAYOFWEEK FROM s.forecast_date) IN (1, 7) as is_weekend,
  -- Sales forecast
  ROUND(s.predicted_sales, 2) as predicted_sales,
  ROUND(s.lower_bound, 2) as sales_lower_bound,
  ROUND(s.upper_bound, 2) as sales_upper_bound,
  -- Quantity forecast
  ROUND(q.predicted_quantity, 0) as predicted_quantity,
  ROUND(q.lower_bound, 0) as quantity_lower_bound,
  ROUND(q.upper_bound, 0) as quantity_upper_bound,
  -- Metadata
  s.confidence_level,
  s.refreshed_at
FROM insights.category_sales_forecast_results s
JOIN insights.category_qty_forecast_results q
  ON s.forecast_date = q.forecast_date
  AND s.category = q.category
LEFT JOIN insights.forecastable_categories fc
  ON s.category = fc.category;

-- =====================================================
-- ANOMALY VIEWS
-- =====================================================

-- Unified Category Anomalies View (both granularities, both metrics)
-- Use for: "Any unusual beer sales recently?"
CREATE OR REPLACE VIEW ai.category_anomalies AS
-- Primary category anomalies
SELECT
  'primary_category' as granularity,
  primary_category as category_name,
  NULL as parent_category,
  report_date,
  FORMAT_DATE('%A', report_date) as day_name,
  metric_type,
  ROUND(actual_value, 2) as actual_value,
  ROUND(predicted_value, 2) as predicted_value,
  ROUND(lower_bound, 2) as lower_bound,
  ROUND(upper_bound, 2) as upper_bound,
  anomaly_probability,
  is_anomaly,
  anomaly_type,
  refreshed_at
FROM insights.primary_category_anomaly_results

UNION ALL

-- Fine category anomalies
SELECT
  'category' as granularity,
  ca.category as category_name,
  fc.primary_category as parent_category,
  ca.report_date,
  FORMAT_DATE('%A', ca.report_date) as day_name,
  ca.metric_type,
  ROUND(ca.actual_value, 2) as actual_value,
  ROUND(ca.predicted_value, 2) as predicted_value,
  ROUND(ca.lower_bound, 2) as lower_bound,
  ROUND(ca.upper_bound, 2) as upper_bound,
  ca.anomaly_probability,
  ca.is_anomaly,
  ca.anomaly_type,
  ca.refreshed_at
FROM insights.category_anomaly_results ca
LEFT JOIN insights.forecastable_categories fc
  ON ca.category = fc.category;

-- =====================================================
-- DATA QUALITY VIEW
-- =====================================================

-- Category Forecast Quality (shows which categories are forecastable)
-- Use for: "Which categories have enough data for forecasting?"
CREATE OR REPLACE VIEW ai.category_forecast_quality AS
SELECT
  category,
  primary_category,
  first_sale_date,
  days_since_first_sale,
  CASE
    WHEN days_since_first_sale >= 200 THEN 'high'
    WHEN days_since_first_sale >= 100 THEN 'medium'
    ELSE 'low'
  END as forecast_confidence
FROM insights.forecastable_categories
ORDER BY days_since_first_sale DESC;
