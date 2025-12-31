-- Weather training views for ARIMA_PLUS_XREG models
-- These views prepare data for BQML models that use weather as external regressors

-- View 1: Daily sales with weather features (for training)
-- Aggregates item_sales to daily level and joins weather data
CREATE OR REPLACE VIEW `fdsanalytics.insights.daily_sales_with_weather` AS
SELECT
    d.report_date,
    d.total_net_sales as total_sales,

    -- Weather features (with sensible defaults for missing data)
    COALESCE(w.avg_temp_f, 50.0) as avg_temp_f,
    COALESCE(w.precipitation_in, 0.0) as precipitation_in,
    COALESCE(w.wind_speed_mph, w.wind_speed_knots * 1.15078, 5.0) as wind_speed_mph,
    CASE WHEN COALESCE(w.had_rain, FALSE) THEN 1 ELSE 0 END as is_rainy,
    CASE WHEN COALESCE(w.had_snow, FALSE) THEN 1 ELSE 0 END as is_snowy,

    -- Time features
    d.is_weekend
FROM (
    SELECT
        report_date,
        SUM(total_net_sales) as total_net_sales,
        MAX(CAST(is_weekend AS INT64)) as is_weekend
    FROM `fdsanalytics.ai.daily_summary`
    GROUP BY report_date
) d
LEFT JOIN `fdsanalytics.insights.local_weather` w
    ON d.report_date = w.weather_date
ORDER BY d.report_date;


-- View 2: Combined actual + forecast weather for ML predictions
-- Used to provide future regressor values to ML.FORECAST()
CREATE OR REPLACE VIEW `fdsanalytics.insights.weather_for_forecast` AS

-- Historical actuals (from local_weather)
SELECT
    weather_date as date,
    avg_temp_f,
    precipitation_in,
    COALESCE(wind_speed_mph, wind_speed_knots * 1.15078, 5.0) as wind_speed_mph,
    CASE WHEN had_rain THEN 1 ELSE 0 END as is_rainy,
    CASE WHEN had_snow THEN 1 ELSE 0 END as is_snowy,
    EXTRACT(DAYOFWEEK FROM weather_date) IN (1, 7) as is_weekend,
    'actual' as source
FROM `fdsanalytics.insights.local_weather`

UNION ALL

-- Future forecasts (from weather_forecast)
SELECT
    forecast_date as date,
    avg_temp_f,
    precipitation_in,
    wind_speed_mph,
    CASE WHEN rain_likely THEN 1 ELSE 0 END as is_rainy,
    CASE WHEN snow_likely THEN 1 ELSE 0 END as is_snowy,
    EXTRACT(DAYOFWEEK FROM forecast_date) IN (1, 7) as is_weekend,
    'forecast' as source
FROM `fdsanalytics.insights.weather_forecast`
WHERE forecast_date > CURRENT_DATE();


-- View 3: Future regressor values for ML.FORECAST
-- This is the exact format needed by ARIMA_PLUS_XREG forecasting
CREATE OR REPLACE VIEW `fdsanalytics.insights.future_weather_regressors` AS
SELECT
    forecast_date as report_date,
    COALESCE(avg_temp_f, 50.0) as avg_temp_f,
    COALESCE(precipitation_in, 0.0) as precipitation_in,
    COALESCE(wind_speed_mph, 5.0) as wind_speed_mph,
    CASE WHEN rain_likely THEN 1 ELSE 0 END as is_rainy,
    CASE WHEN snow_likely THEN 1 ELSE 0 END as is_snowy,
    CASE WHEN EXTRACT(DAYOFWEEK FROM forecast_date) IN (1, 7) THEN 1 ELSE 0 END as is_weekend
FROM `fdsanalytics.insights.weather_forecast`
WHERE forecast_date > CURRENT_DATE()
ORDER BY forecast_date
LIMIT 14;


-- View 4: Category sales with weather (for future category-level XREG models)
-- Uses ai.restaurant_analytics (item-level) since daily_summary doesn't have category
CREATE OR REPLACE VIEW `fdsanalytics.insights.category_sales_with_weather` AS
SELECT
    d.report_date,
    d.primary_category,
    d.total_sales,
    d.total_quantity,

    -- Weather features
    COALESCE(w.avg_temp_f, 50.0) as avg_temp_f,
    COALESCE(w.precipitation_in, 0.0) as precipitation_in,
    COALESCE(w.wind_speed_mph, w.wind_speed_knots * 1.15078, 5.0) as wind_speed_mph,
    CASE WHEN COALESCE(w.had_rain, FALSE) THEN 1 ELSE 0 END as is_rainy,
    CASE WHEN COALESCE(w.had_snow, FALSE) THEN 1 ELSE 0 END as is_snowy,

    -- Time features
    d.is_weekend
FROM (
    SELECT
        report_date,
        primary_category,
        SUM(net_sales) as total_sales,
        SUM(quantity_sold) as total_quantity,
        MAX(CAST(is_weekend AS INT64)) as is_weekend
    FROM `fdsanalytics.ai.restaurant_analytics`
    GROUP BY report_date, primary_category
) d
LEFT JOIN `fdsanalytics.insights.local_weather` w
    ON d.report_date = w.weather_date
ORDER BY d.report_date, d.primary_category;
