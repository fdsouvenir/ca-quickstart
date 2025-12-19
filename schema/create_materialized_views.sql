-- Materialized views for common aggregations
-- Auto-refresh when base data changes
-- Replaces manual populate_daily_insights() stored procedure

-- Daily totals (replaces daily_comparisons logic)
-- Note: Materialized views don't support COUNT(DISTINCT), so we use COUNT(*)
CREATE MATERIALIZED VIEW IF NOT EXISTS insights.daily_totals AS
SELECT
  report_date,
  location,
  SUM(net_sales) as total_sales,
  SUM(quantity_sold) as total_quantity,
  COUNT(*) as item_rows
FROM restaurant_analytics.item_sales
GROUP BY 1, 2;

-- Category daily (replaces category_trends)
CREATE MATERIALIZED VIEW IF NOT EXISTS insights.category_daily AS
SELECT
  report_date,
  location,
  primary_category,
  category,
  SUM(net_sales) as sales_total,
  SUM(quantity_sold) as quantity_total,
  COUNT(*) as item_rows
FROM restaurant_analytics.item_sales
GROUP BY 1, 2, 3, 4;
