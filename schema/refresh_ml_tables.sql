-- Script to refresh ML result tables
-- Run daily via scheduled query at 6 AM
-- DELETE+INSERT pattern (could use MERGE for atomic upsert in future)

-- Refresh forecast results
DELETE FROM insights.sales_forecast_results WHERE TRUE;

INSERT INTO insights.sales_forecast_results
SELECT
  DATE(forecast_timestamp) as forecast_date,
  forecast_value as predicted_sales,
  prediction_interval_lower_bound as lower_bound,
  prediction_interval_upper_bound as upper_bound,
  confidence_level,
  CURRENT_TIMESTAMP() as refreshed_at
FROM ML.FORECAST(
  MODEL insights.sales_model,
  STRUCT(14 AS horizon, 0.9 AS confidence_level)
);

-- Refresh anomaly results
DELETE FROM insights.sales_anomaly_results WHERE TRUE;

INSERT INTO insights.sales_anomaly_results
SELECT
  DATE(report_date) as report_date,
  total_sales as actual_sales,
  -- predicted_sales not directly available, use midpoint of bounds
  (COALESCE(lower_bound, total_sales) + COALESCE(upper_bound, total_sales)) / 2 as predicted_sales,
  lower_bound,
  upper_bound,
  anomaly_probability,
  is_anomaly,
  CASE
    WHEN is_anomaly = TRUE AND total_sales > upper_bound THEN 'spike'
    WHEN is_anomaly = TRUE AND total_sales < lower_bound THEN 'drop'
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
