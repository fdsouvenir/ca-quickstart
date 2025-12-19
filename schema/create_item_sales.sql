-- Denormalized item-level sales table
-- One row per item per day (not EAV pattern)
-- Partitioned by report_date for cost efficiency
-- Clustered by category columns for faster scans

CREATE TABLE IF NOT EXISTS restaurant_analytics.item_sales (
  -- Keys
  report_date DATE NOT NULL,
  location STRING NOT NULL,

  -- Dimensions (flat, not JSON)
  primary_category STRING,
  category STRING,
  item_name STRING NOT NULL,

  -- Facts (all metrics as columns)
  quantity_sold INT64,
  net_sales FLOAT64,
  discount FLOAT64,

  -- Metadata
  data_source STRING,  -- e.g., "pmix-pdf:pmix-senso-2025-06-14.pdf" or "spoton-api:txn-123"
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY report_date
CLUSTER BY primary_category, category
OPTIONS (
  description = 'Denormalized item-level sales from POS system. One row per item per day.'
);
