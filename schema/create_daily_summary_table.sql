-- Daily Summary Table for Correlation Analysis
-- Grain: One row per day per location
-- Refreshed by scheduled query (add to refresh_ml_tables.sql)
--
-- WHY THIS EXISTS:
-- The item-level view (ai.restaurant_analytics) causes aggregation bugs when
-- the CA agent sums weather columns. Weather values repeat on every item row,
-- so SUM(precipitation_in) multiplies precipitation by item count.
-- This table pre-aggregates correctly.

CREATE OR REPLACE TABLE `fdsanalytics.ai.daily_summary` AS
SELECT
  -- === GRAIN ===
  report_date,
  location,
  location_name,
  region,

  -- === SALES (SUM - additive across items) ===
  SUM(quantity_sold) as total_quantity_sold,
  SUM(net_sales) as total_net_sales,
  SUM(discount) as total_discount,
  COUNT(DISTINCT item_name) as unique_items_sold,
  COUNT(*) as line_item_count,

  -- === WEATHER (MAX - same value repeats on every row) ===
  MAX(avg_temp_f) as avg_temp_f,
  MAX(max_temp_f) as max_temp_f,
  MAX(min_temp_f) as min_temp_f,
  MAX(precipitation_in) as precipitation_in,
  MAX(had_rain) as had_rain,
  MAX(had_snow) as had_snow,

  -- === EVENTS (MAX - already aggregated in source) ===
  MAX(event_names) as event_names,
  MAX(event_types) as event_types,
  MAX(event_count) as event_count,
  MAX(has_local_event) as has_local_event,

  -- === TIME DIMENSIONS (MAX - one value per day) ===
  MAX(day_of_week) as day_of_week,
  MAX(day_name) as day_name,
  MAX(week_number) as week_number,
  MAX(month) as month,
  MAX(month_name) as month_name,
  MAX(year) as year,
  MAX(is_weekend) as is_weekend

FROM `fdsanalytics.ai.restaurant_analytics`
GROUP BY report_date, location, location_name, region;
