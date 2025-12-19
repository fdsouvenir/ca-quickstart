-- Single ARIMA_PLUS model for both forecasting and anomaly detection
-- Trained on daily total sales
-- holiday_region = 'US' captures federal holidays (not local Frankfort events)

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
