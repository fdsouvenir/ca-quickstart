-- Migrate frankfort_events to local_events
-- Adds recurrence_type column for proper event expansion
-- Adds region column for multi-city support

-- Create new table with updated schema
CREATE TABLE IF NOT EXISTS insights.local_events (
  event_date DATE NOT NULL,
  event_name STRING NOT NULL,
  event_type STRING,
  recurrence_type STRING DEFAULT 'single',  -- 'single', 'daily', 'weekly'
  end_date DATE,
  region STRING NOT NULL,  -- e.g., 'frankfort-il'
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
  description = 'Local events by region. Used to correlate sales with community events.'
);

-- Migrate existing data with recurrence_type based on known patterns
INSERT INTO insights.local_events (event_date, event_name, event_type, recurrence_type, end_date, region)
SELECT
  event_date,
  event_name,
  event_type,
  CASE
    -- Weekly recurring events (known from data analysis)
    WHEN event_name IN ('Country Market', 'Cruisin Frankfort', 'Fridays on the Green', 'Concerts on the Green')
      THEN 'weekly'
    -- Multi-day consecutive events
    WHEN is_multi_day = TRUE THEN 'daily'
    -- Single-day events
    ELSE 'single'
  END as recurrence_type,
  end_date,
  'frankfort-il' as region  -- All existing events are Frankfort
FROM insights.frankfort_events;

-- After verification, drop old table:
-- DROP TABLE insights.frankfort_events;
