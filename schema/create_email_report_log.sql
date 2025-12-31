-- Create email report log table for tracking sent reports
-- Follows same pattern as insights.pmix_import_log

CREATE TABLE IF NOT EXISTS `fdsanalytics.insights.email_report_log` (
  report_date DATE NOT NULL,
  sent_at TIMESTAMP,
  status STRING,           -- 'success', 'failed', 'no_data', 'no_recipients'
  recipient_count INT64,
  error_message STRING
);

-- Example: Check recent report sends
-- SELECT * FROM `fdsanalytics.insights.email_report_log`
-- ORDER BY sent_at DESC LIMIT 10;

-- Example: Find failed reports
-- SELECT * FROM `fdsanalytics.insights.email_report_log`
-- WHERE status = 'failed';
