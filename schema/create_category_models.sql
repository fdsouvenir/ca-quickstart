-- BQML ARIMA_PLUS models for category-level forecasting
-- Uses time_series_id_col for multi-series forecasting
-- Trains on dense views (zero-filled days for continuous time series)

-- =====================================================
-- PRIMARY CATEGORY MODELS (6 categories)
-- =====================================================

-- Primary Category Sales Model
CREATE OR REPLACE MODEL insights.primary_category_sales_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_sales',
  time_series_id_col = 'primary_category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, primary_category, total_sales
FROM insights.primary_category_daily_dense;

-- Primary Category Quantity Model
CREATE OR REPLACE MODEL insights.primary_category_qty_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_quantity',
  time_series_id_col = 'primary_category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, primary_category, total_quantity
FROM insights.primary_category_daily_dense;

-- =====================================================
-- FINE CATEGORY MODELS (~20+ categories with 100+ days)
-- =====================================================

-- Fine Category Sales Model
CREATE OR REPLACE MODEL insights.category_sales_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_sales',
  time_series_id_col = 'category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, category, total_sales
FROM insights.category_daily_dense;

-- Fine Category Quantity Model
CREATE OR REPLACE MODEL insights.category_qty_model
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'report_date',
  time_series_data_col = 'total_quantity',
  time_series_id_col = 'category',
  auto_arima = TRUE,
  data_frequency = 'DAILY',
  holiday_region = 'US'
) AS
SELECT report_date, category, total_quantity
FROM insights.category_daily_dense;
