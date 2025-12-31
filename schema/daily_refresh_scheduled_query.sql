-- Daily ML Refresh Script
-- Runs at 6 AM America/Chicago

-- Refresh total sales forecast
DELETE FROM insights.sales_forecast_results WHERE TRUE;
INSERT INTO insights.sales_forecast_results
SELECT DATE(forecast_timestamp) as forecast_date, forecast_value as predicted_sales,
  prediction_interval_lower_bound as lower_bound, prediction_interval_upper_bound as upper_bound,
  confidence_level, CURRENT_TIMESTAMP() as refreshed_at
FROM ML.FORECAST(MODEL insights.sales_model, STRUCT(14 AS horizon, 0.9 AS confidence_level));

-- Refresh total sales anomalies
DELETE FROM insights.sales_anomaly_results WHERE TRUE;
INSERT INTO insights.sales_anomaly_results
SELECT DATE(report_date) as report_date, total_sales as actual_sales,
  (COALESCE(lower_bound, total_sales) + COALESCE(upper_bound, total_sales)) / 2 as predicted_sales,
  lower_bound, upper_bound, anomaly_probability, is_anomaly,
  CASE WHEN is_anomaly = TRUE AND total_sales > upper_bound THEN 'spike'
       WHEN is_anomaly = TRUE AND total_sales < lower_bound THEN 'drop' ELSE 'normal' END as anomaly_type,
  CURRENT_TIMESTAMP() as refreshed_at
FROM ML.DETECT_ANOMALIES(MODEL insights.sales_model, STRUCT(0.90 AS anomaly_prob_threshold),
  (SELECT report_date, SUM(net_sales) as total_sales FROM restaurant_analytics.item_sales WHERE location = 'senso-sushi' GROUP BY report_date));

-- Refresh daily summary
CREATE OR REPLACE TABLE ai.daily_summary AS
SELECT report_date, location, location_name, region,
  SUM(quantity_sold) as total_quantity_sold, SUM(net_sales) as total_net_sales, SUM(discount) as total_discount,
  COUNT(DISTINCT item_name) as unique_items_sold, COUNT(*) as line_item_count,
  MAX(avg_temp_f) as avg_temp_f, MAX(max_temp_f) as max_temp_f, MAX(min_temp_f) as min_temp_f,
  MAX(precipitation_in) as precipitation_in, MAX(had_rain) as had_rain, MAX(had_snow) as had_snow,
  MAX(event_names) as event_names, MAX(event_types) as event_types, MAX(event_count) as event_count,
  MAX(has_local_event) as has_local_event, MAX(day_of_week) as day_of_week, MAX(day_name) as day_name,
  MAX(week_number) as week_number, MAX(month) as month, MAX(month_name) as month_name,
  MAX(year) as year, MAX(is_weekend) as is_weekend
FROM ai.restaurant_analytics GROUP BY report_date, location, location_name, region;

-- Primary Category Forecasts
DELETE FROM insights.primary_category_sales_forecast_results WHERE TRUE;
INSERT INTO insights.primary_category_sales_forecast_results
SELECT DATE(forecast_timestamp), primary_category, forecast_value, prediction_interval_lower_bound,
  prediction_interval_upper_bound, confidence_level, CURRENT_TIMESTAMP()
FROM ML.FORECAST(MODEL insights.primary_category_sales_model, STRUCT(14 AS horizon, 0.9 AS confidence_level));

DELETE FROM insights.primary_category_qty_forecast_results WHERE TRUE;
INSERT INTO insights.primary_category_qty_forecast_results
SELECT DATE(forecast_timestamp), primary_category, forecast_value, prediction_interval_lower_bound,
  prediction_interval_upper_bound, confidence_level, CURRENT_TIMESTAMP()
FROM ML.FORECAST(MODEL insights.primary_category_qty_model, STRUCT(14 AS horizon, 0.9 AS confidence_level));

-- Fine Category Forecasts
DELETE FROM insights.category_sales_forecast_results WHERE TRUE;
INSERT INTO insights.category_sales_forecast_results
SELECT DATE(forecast_timestamp), category, forecast_value, prediction_interval_lower_bound,
  prediction_interval_upper_bound, confidence_level, CURRENT_TIMESTAMP()
FROM ML.FORECAST(MODEL insights.category_sales_model, STRUCT(14 AS horizon, 0.9 AS confidence_level));

DELETE FROM insights.category_qty_forecast_results WHERE TRUE;
INSERT INTO insights.category_qty_forecast_results
SELECT DATE(forecast_timestamp), category, forecast_value, prediction_interval_lower_bound,
  prediction_interval_upper_bound, confidence_level, CURRENT_TIMESTAMP()
FROM ML.FORECAST(MODEL insights.category_qty_model, STRUCT(14 AS horizon, 0.9 AS confidence_level));

-- =====================================================
-- CATEGORY-LEVEL ANOMALY DETECTION (Z-Score Based)
-- Uses statistical z-scores instead of ML.DETECT_ANOMALIES
-- which doesn't work well with multi-series ARIMA models
-- =====================================================

-- Primary Category Anomalies
DELETE FROM insights.primary_category_anomaly_results WHERE TRUE;

-- Primary Category Sales Anomalies
INSERT INTO insights.primary_category_anomaly_results
WITH category_stats AS (
  SELECT primary_category, AVG(total_sales) as mean_val, STDDEV(total_sales) as stddev_val
  FROM insights.primary_category_daily_dense GROUP BY 1
),
with_zscore AS (
  SELECT d.report_date, d.primary_category, d.total_sales as actual_value,
    s.mean_val as predicted_value,
    s.mean_val - 2.5 * s.stddev_val as lower_bound,
    s.mean_val + 2.5 * s.stddev_val as upper_bound,
    (d.total_sales - s.mean_val) / NULLIF(s.stddev_val, 0) as zscore
  FROM insights.primary_category_daily_dense d
  JOIN category_stats s ON d.primary_category = s.primary_category
)
SELECT report_date, primary_category, 'sales' as metric_type,
  actual_value, predicted_value, lower_bound, upper_bound,
  ABS(zscore) / 4.0 as anomaly_probability,
  ABS(zscore) > 2.5 as is_anomaly,
  CASE WHEN zscore > 2.5 THEN 'spike' WHEN zscore < -2.5 THEN 'drop' ELSE 'normal' END as anomaly_type,
  CURRENT_TIMESTAMP() as refreshed_at
FROM with_zscore;

-- Primary Category Quantity Anomalies
INSERT INTO insights.primary_category_anomaly_results
WITH category_stats AS (
  SELECT primary_category, AVG(total_quantity) as mean_val, STDDEV(total_quantity) as stddev_val
  FROM insights.primary_category_daily_dense GROUP BY 1
),
with_zscore AS (
  SELECT d.report_date, d.primary_category, d.total_quantity as actual_value,
    s.mean_val as predicted_value,
    s.mean_val - 2.5 * s.stddev_val as lower_bound,
    s.mean_val + 2.5 * s.stddev_val as upper_bound,
    (d.total_quantity - s.mean_val) / NULLIF(s.stddev_val, 0) as zscore
  FROM insights.primary_category_daily_dense d
  JOIN category_stats s ON d.primary_category = s.primary_category
)
SELECT report_date, primary_category, 'quantity' as metric_type,
  actual_value, predicted_value, lower_bound, upper_bound,
  ABS(zscore) / 4.0 as anomaly_probability,
  ABS(zscore) > 2.5 as is_anomaly,
  CASE WHEN zscore > 2.5 THEN 'spike' WHEN zscore < -2.5 THEN 'drop' ELSE 'normal' END as anomaly_type,
  CURRENT_TIMESTAMP() as refreshed_at
FROM with_zscore;

-- Fine Category Anomalies
DELETE FROM insights.category_anomaly_results WHERE TRUE;

-- Fine Category Sales Anomalies
INSERT INTO insights.category_anomaly_results
WITH category_stats AS (
  SELECT category, AVG(total_sales) as mean_val, STDDEV(total_sales) as stddev_val
  FROM insights.category_daily_dense GROUP BY 1
),
with_zscore AS (
  SELECT d.report_date, d.category, d.total_sales as actual_value,
    s.mean_val as predicted_value,
    s.mean_val - 2.5 * s.stddev_val as lower_bound,
    s.mean_val + 2.5 * s.stddev_val as upper_bound,
    (d.total_sales - s.mean_val) / NULLIF(s.stddev_val, 0) as zscore
  FROM insights.category_daily_dense d
  JOIN category_stats s ON d.category = s.category
)
SELECT report_date, category, 'sales' as metric_type,
  actual_value, predicted_value, lower_bound, upper_bound,
  ABS(zscore) / 4.0 as anomaly_probability,
  ABS(zscore) > 2.5 as is_anomaly,
  CASE WHEN zscore > 2.5 THEN 'spike' WHEN zscore < -2.5 THEN 'drop' ELSE 'normal' END as anomaly_type,
  CURRENT_TIMESTAMP() as refreshed_at
FROM with_zscore;

-- Fine Category Quantity Anomalies
INSERT INTO insights.category_anomaly_results
WITH category_stats AS (
  SELECT category, AVG(total_quantity) as mean_val, STDDEV(total_quantity) as stddev_val
  FROM insights.category_daily_dense GROUP BY 1
),
with_zscore AS (
  SELECT d.report_date, d.category, d.total_quantity as actual_value,
    s.mean_val as predicted_value,
    s.mean_val - 2.5 * s.stddev_val as lower_bound,
    s.mean_val + 2.5 * s.stddev_val as upper_bound,
    (d.total_quantity - s.mean_val) / NULLIF(s.stddev_val, 0) as zscore
  FROM insights.category_daily_dense d
  JOIN category_stats s ON d.category = s.category
)
SELECT report_date, category, 'quantity' as metric_type,
  actual_value, predicted_value, lower_bound, upper_bound,
  ABS(zscore) / 4.0 as anomaly_probability,
  ABS(zscore) > 2.5 as is_anomaly,
  CASE WHEN zscore > 2.5 THEN 'spike' WHEN zscore < -2.5 THEN 'drop' ELSE 'normal' END as anomaly_type,
  CURRENT_TIMESTAMP() as refreshed_at
FROM with_zscore;
