-- Expanded events view
-- Expands multi-day events to one row per occurrence
-- Uses recurrence_type to properly handle weekly vs daily patterns

CREATE OR REPLACE VIEW insights.expanded_events AS

-- Single-day events: use as-is
SELECT
  event_date,
  event_name,
  event_type,
  region
FROM insights.local_events
WHERE recurrence_type = 'single'
  OR recurrence_type IS NULL
  OR end_date IS NULL  -- Safety: treat as single if no end date

UNION ALL

-- Daily recurring events: expand to each day in range
SELECT
  day as event_date,
  event_name,
  event_type,
  region
FROM insights.local_events,
  UNNEST(GENERATE_DATE_ARRAY(event_date, end_date, INTERVAL 1 DAY)) as day
WHERE recurrence_type = 'daily'
  AND end_date IS NOT NULL

UNION ALL

-- Weekly recurring events: expand to each week on the same weekday
SELECT
  day as event_date,
  event_name,
  event_type,
  region
FROM insights.local_events,
  UNNEST(GENERATE_DATE_ARRAY(event_date, end_date, INTERVAL 1 WEEK)) as day
WHERE recurrence_type = 'weekly'
  AND end_date IS NOT NULL;
