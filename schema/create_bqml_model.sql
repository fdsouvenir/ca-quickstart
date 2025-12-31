-- ARIMA_PLUS_XREG model with weather as external regressors
-- Trained on daily total sales with weather features
-- Uses weather forecasts for future predictions

-- Note: Run schema/create_weather_training_views.sql first to create
-- the insights.daily_sales_with_weather view

CREATE OR REPLACE MODEL insights.sales_model
OPTIONS(
  model_type = 'ARIMA_PLUS_XREG',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_sales',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT
  report_date,
  total_sales,
  -- Weather regressors
  avg_temp_f,
  precipitation_in,
  is_rainy,
  is_snowy,
  -- Time features
  is_weekend
FROM insights.daily_sales_with_weather
WHERE report_date <= CURRENT_DATE();

-- Note on external regressors:
-- When using ML.FORECAST() with this model, you must provide future values
-- for all regressors. The insights.future_weather_regressors view provides
-- this data from the weather_forecast table.
--
-- Example forecast query:
--   SELECT * FROM ML.FORECAST(
--     MODEL insights.sales_model,
--     STRUCT(14 AS horizon, 0.9 AS confidence_level),
--     (SELECT * FROM insights.future_weather_regressors)
--   )
