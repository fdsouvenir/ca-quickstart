-- Create weather_forecast table for 14-day forecasts
-- This table is refreshed daily with "always latest" approach
-- Data comes from Open-Meteo Forecast API

CREATE TABLE IF NOT EXISTS `fdsanalytics.insights.weather_forecast` (
    -- Primary key
    forecast_date DATE NOT NULL,              -- The future date being predicted

    -- Metadata
    updated_at TIMESTAMP NOT NULL,            -- When this forecast was fetched

    -- Temperature (Fahrenheit)
    high_temp_f FLOAT64,
    low_temp_f FLOAT64,
    avg_temp_f FLOAT64,

    -- Precipitation
    precipitation_in FLOAT64,                 -- Expected precipitation in inches
    precipitation_probability_pct INT64,      -- 0-100% chance of precipitation
    rain_likely BOOL,                         -- True if rain expected
    snow_likely BOOL,                         -- True if snow expected

    -- Wind
    wind_speed_mph FLOAT64,                   -- Max wind speed
    wind_gust_mph FLOAT64,                    -- Max wind gusts

    -- Conditions
    weather_code INT64,                       -- WMO weather code
    weather_condition STRING,                 -- Human readable (Clear, Rain, Snow, etc.)
    cloud_cover_pct INT64,                    -- 0-100%
    humidity_pct INT64,                       -- Relative humidity 0-100%
    uv_index FLOAT64                          -- UV index
);

-- Note: This table is truncated and reloaded daily
-- Each morning, we get fresh 14-day forecasts from Open-Meteo
-- The forecast_date column contains future dates (today + 1 to today + 14)
