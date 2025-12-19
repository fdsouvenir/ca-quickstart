-- Unified AI view for restaurant analytics
-- Pre-joins weather and events so LLMs don't need complex join logic
-- Aggregates events to day-level to prevent row duplication on multi-event days

CREATE OR REPLACE VIEW ai.restaurant_analytics AS
SELECT
  -- Sales data
  s.report_date,
  s.location,
  l.display_name as location_name,
  l.region,
  s.primary_category,
  s.category,
  s.item_name,
  s.quantity_sold,
  s.net_sales,
  s.discount,

  -- Weather (pre-joined from insights.local_weather)
  w.avg_temp_f,
  w.max_temp_f,
  w.min_temp_f,
  w.had_rain,
  w.had_snow,
  w.precipitation_in,

  -- Events (aggregated to day-level to prevent row duplication)
  e.event_names,
  e.event_types,
  e.event_count,
  e.event_count > 0 as has_local_event,

  -- Time intelligence (pre-computed for easy filtering)
  EXTRACT(DAYOFWEEK FROM s.report_date) as day_of_week,
  FORMAT_DATE('%A', s.report_date) as day_name,
  EXTRACT(WEEK FROM s.report_date) as week_number,
  EXTRACT(MONTH FROM s.report_date) as month,
  FORMAT_DATE('%B', s.report_date) as month_name,
  EXTRACT(YEAR FROM s.report_date) as year,
  EXTRACT(DAYOFWEEK FROM s.report_date) IN (1, 7) as is_weekend

FROM restaurant_analytics.item_sales s
-- Join to locations dimension for region mapping
JOIN restaurant_analytics.locations l ON s.location = l.location
-- Join weather by date
LEFT JOIN insights.local_weather w ON s.report_date = w.weather_date
-- Join events by date AND region (aggregated to prevent row duplication)
LEFT JOIN (
  -- Aggregate events to one row per day per region
  SELECT
    event_date,
    region,
    STRING_AGG(event_name, ', ' ORDER BY event_name) as event_names,
    STRING_AGG(DISTINCT event_type, ', ' ORDER BY event_type) as event_types,
    COUNT(*) as event_count
  FROM insights.expanded_events
  GROUP BY event_date, region
) e ON s.report_date = e.event_date AND l.region = e.region;
