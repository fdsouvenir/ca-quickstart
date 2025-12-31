-- Update local_weather table schema for Open-Meteo migration
-- Adds new columns for extended weather data
-- Run this BEFORE backfilling with Open-Meteo data

-- Add new columns to existing table
ALTER TABLE `fdsanalytics.insights.local_weather`
ADD COLUMN IF NOT EXISTS wind_speed_mph FLOAT64,
ADD COLUMN IF NOT EXISTS wind_gust_mph FLOAT64,
ADD COLUMN IF NOT EXISTS weather_code INT64,
ADD COLUMN IF NOT EXISTS weather_condition STRING,
ADD COLUMN IF NOT EXISTS cloud_cover_pct INT64,
ADD COLUMN IF NOT EXISTS humidity_pct INT64,
ADD COLUMN IF NOT EXISTS uv_index FLOAT64;

-- Note: visibility_miles and wind_speed_knots columns from NOAA will be deprecated
-- but kept for backward compatibility. New data will use wind_speed_mph instead.

-- Weather code reference (WMO Standard):
-- 0: Clear sky
-- 1: Mainly clear
-- 2: Partly cloudy
-- 3: Overcast
-- 45: Fog
-- 48: Depositing rime fog
-- 51: Light drizzle
-- 53: Moderate drizzle
-- 55: Dense drizzle
-- 61: Slight rain
-- 63: Moderate rain
-- 65: Heavy rain
-- 71: Slight snow
-- 73: Moderate snow
-- 75: Heavy snow
-- 77: Snow grains
-- 80: Slight rain showers
-- 81: Moderate rain showers
-- 82: Violent rain showers
-- 85: Slight snow showers
-- 86: Heavy snow showers
-- 95: Thunderstorm
-- 96: Thunderstorm with slight hail
-- 99: Thunderstorm with heavy hail
