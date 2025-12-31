-- Helper views for category-level forecasting
-- These views create dense time series with zero-filled days for accurate ARIMA forecasting

-- Calendar spine: All dates from data range
CREATE OR REPLACE VIEW insights.date_spine AS
SELECT date
FROM UNNEST(GENERATE_DATE_ARRAY(
  (SELECT MIN(report_date) FROM restaurant_analytics.item_sales),
  (SELECT MAX(report_date) FROM restaurant_analytics.item_sales)
)) AS date;

-- All categories that have ever had a sale (with first sale date)
CREATE OR REPLACE VIEW insights.all_categories AS
SELECT
  primary_category,
  category,
  MIN(report_date) as first_sale_date
FROM restaurant_analytics.item_sales
WHERE location = 'senso-sushi'
GROUP BY 1, 2;

-- Dense primary category daily (with zero-fill for no-sale days)
-- Every date × primary_category combination, filling missing days with 0
CREATE OR REPLACE VIEW insights.primary_category_daily_dense AS
WITH spine AS (
  SELECT d.date, ac.primary_category
  FROM insights.date_spine d
  CROSS JOIN (SELECT DISTINCT primary_category FROM insights.all_categories) ac
),
actuals AS (
  SELECT
    report_date,
    primary_category,
    SUM(net_sales) as total_sales,
    SUM(quantity_sold) as total_quantity
  FROM restaurant_analytics.item_sales
  WHERE location = 'senso-sushi'
  GROUP BY 1, 2
)
SELECT
  s.date as report_date,
  s.primary_category,
  COALESCE(a.total_sales, 0) as total_sales,
  COALESCE(a.total_quantity, 0) as total_quantity
FROM spine s
LEFT JOIN actuals a ON s.date = a.report_date AND s.primary_category = a.primary_category;

-- Dense fine category daily (with zero-fill, filtered to 100+ day categories)
-- Only includes categories that have been around for 100+ days
CREATE OR REPLACE VIEW insights.category_daily_dense AS
WITH spine AS (
  SELECT d.date, ac.primary_category, ac.category
  FROM insights.date_spine d
  CROSS JOIN insights.all_categories ac
  WHERE d.date >= ac.first_sale_date  -- Only from first sale onwards
),
actuals AS (
  SELECT
    report_date,
    primary_category,
    category,
    SUM(net_sales) as total_sales,
    SUM(quantity_sold) as total_quantity
  FROM restaurant_analytics.item_sales
  WHERE location = 'senso-sushi'
  GROUP BY 1, 2, 3
),
category_days AS (
  SELECT category, COUNT(DISTINCT date) as days_since_first_sale
  FROM spine
  GROUP BY 1
)
SELECT
  s.date as report_date,
  s.primary_category,
  s.category,
  COALESCE(a.total_sales, 0) as total_sales,
  COALESCE(a.total_quantity, 0) as total_quantity
FROM spine s
LEFT JOIN actuals a ON s.date = a.report_date AND s.category = a.category
INNER JOIN category_days cd ON s.category = cd.category
WHERE cd.days_since_first_sale >= 100;  -- Only categories with 100+ days since first sale

-- Forecastable categories (for reference/debugging - shows which categories are included)
CREATE OR REPLACE VIEW insights.forecastable_categories AS
SELECT
  category,
  primary_category,
  first_sale_date,
  DATE_DIFF(CURRENT_DATE(), first_sale_date, DAY) as days_since_first_sale
FROM insights.all_categories
WHERE DATE_DIFF(CURRENT_DATE(), first_sale_date, DAY) >= 100;
