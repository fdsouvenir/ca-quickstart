-- Create email recipients table for daily report
-- Recipients can be managed via simple INSERT/UPDATE/DELETE statements

CREATE TABLE IF NOT EXISTS `fdsanalytics.insights.email_recipients` (
  email STRING NOT NULL,
  name STRING,
  active BOOL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Example: Add recipients
-- INSERT INTO `fdsanalytics.insights.email_recipients` (email, name, active)
-- VALUES
--   ('owner@example.com', 'Owner', TRUE),
--   ('manager@example.com', 'Manager', TRUE);

-- Example: Deactivate a recipient (soft delete)
-- UPDATE `fdsanalytics.insights.email_recipients`
-- SET active = FALSE
-- WHERE email = 'manager@example.com';

-- Example: List active recipients
-- SELECT * FROM `fdsanalytics.insights.email_recipients` WHERE active = TRUE;
