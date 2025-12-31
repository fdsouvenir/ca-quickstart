-- Create weather_import_log table for tracking weather fetch operations
-- Similar pattern to pmix_import_log

CREATE TABLE IF NOT EXISTS `fdsanalytics.insights.weather_import_log` (
    -- What was fetched
    fetch_date DATE NOT NULL,                 -- The date of the fetch operation
    fetch_type STRING NOT NULL,               -- 'historical', 'forecast', or 'backfill'

    -- When and status
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    status STRING NOT NULL,                   -- 'success', 'failed'

    -- Results
    record_count INT64,                       -- Number of records inserted/updated
    date_range_start DATE,                    -- First date in fetched data
    date_range_end DATE,                      -- Last date in fetched data

    -- Error tracking
    error_message STRING
);

-- Example entries:
-- fetch_date=2025-12-31, fetch_type='historical', status='success', record_count=1
--   (daily fetch of yesterday's actual weather)
-- fetch_date=2025-12-31, fetch_type='forecast', status='success', record_count=14
--   (daily fetch of 14-day forecast)
-- fetch_date=2025-12-31, fetch_type='backfill', status='success', record_count=730
--   (one-time historical backfill)
