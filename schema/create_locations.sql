-- Locations dimension table
-- Maps restaurant locations to geographic regions for event joins
-- When you have locations in multiple cities, this links them to their local events

CREATE TABLE IF NOT EXISTS restaurant_analytics.locations (
  location STRING NOT NULL,      -- Primary key, matches item_sales.location
  region STRING NOT NULL,        -- Matches local_events.region (e.g., 'frankfort-il')
  display_name STRING,           -- Human-readable name for UI (e.g., 'Senso Sushi')
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
  description = 'Dimension table mapping restaurant locations to geographic regions for event joins.'
);

-- Insert initial location
INSERT INTO restaurant_analytics.locations (location, region, display_name)
VALUES ('senso-sushi', 'frankfort-il', 'Senso Sushi');
