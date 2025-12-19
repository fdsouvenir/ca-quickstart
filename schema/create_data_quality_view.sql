-- Data quality view for AI self-validation
-- Helps the AI answer questions about data coverage
-- Prevents hallucination about date ranges that don't exist

CREATE OR REPLACE VIEW ai.data_quality AS
SELECT
  MIN(report_date) as earliest_date,
  MAX(report_date) as latest_date,
  COUNT(DISTINCT report_date) as days_with_data,
  COUNT(*) as total_records,
  SUM(net_sales) as total_sales,
  -- Gap detection: expected days minus actual days
  DATE_DIFF(MAX(report_date), MIN(report_date), DAY) + 1
    - COUNT(DISTINCT report_date) as missing_days,
  -- Location breakdown
  STRING_AGG(DISTINCT location, ', ') as locations
FROM restaurant_analytics.item_sales;
