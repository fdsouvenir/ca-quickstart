-- Create import log table for tracking PMIX PDF imports
-- Used by Cloud Functions for idempotency and audit trail

CREATE TABLE IF NOT EXISTS `fdsanalytics.insights.pmix_import_log` (
    file_name STRING NOT NULL,
    report_date DATE NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    status STRING NOT NULL,  -- 'success', 'failed', 'skipped'
    record_count INT64,
    total_sales FLOAT64,
    error_message STRING
);

-- Bootstrap existing data (run once before enabling pipeline)
-- This prevents re-importing the ~289 PDFs already in item_sales
/*
INSERT INTO `fdsanalytics.insights.pmix_import_log` (file_name, report_date, status, record_count, total_sales)
SELECT
  CONCAT('pmix-senso-', CAST(report_date AS STRING), '.pdf') AS file_name,
  report_date,
  'success' AS status,
  COUNT(*) AS record_count,
  SUM(net_sales) AS total_sales
FROM `fdsanalytics.restaurant_analytics.item_sales`
WHERE location = 'senso-sushi'
GROUP BY report_date;
*/
