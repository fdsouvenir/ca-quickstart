"""
Cloud Function: send-daily-report

Sends daily analytics email at 7 AM CT.
Triggered by Cloud Scheduler via HTTP.

Environment variables:
- PROJECT_ID: GCP project ID (default: fdsanalytics)
- SENDGRID_API_KEY: Can be set directly or fetched from Secret Manager
"""

import json
import os
from datetime import datetime, timedelta, timezone

import functions_framework
from google.cloud import bigquery, secretmanager
import google.cloud.logging

from report_data import fetch_report_data
from report_charts import build_all_charts
from report_html import render_email_html

# Try to import sendgrid, provide helpful error if missing
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Content
except ImportError:
    SendGridAPIClient = None

PROJECT_ID = os.environ.get('PROJECT_ID', 'fdsanalytics')
CT_OFFSET = timezone(timedelta(hours=-6))  # Central Time (CST)

# Initialize clients
bq_client = bigquery.Client(project=PROJECT_ID)
secret_client = secretmanager.SecretManagerServiceClient()

# Set up Cloud Logging
logging_client = google.cloud.logging.Client(project=PROJECT_ID)
logger = logging_client.logger("daily-report")


def log_info(message: str, **kwargs):
    """Log info message with structured data."""
    logger.log_struct({
        "severity": "INFO",
        "message": message,
        **kwargs
    })


def log_error(message: str, **kwargs):
    """Log error message with structured data."""
    logger.log_struct({
        "severity": "ERROR",
        "message": message,
        **kwargs
    })


def get_sendgrid_key() -> str:
    """Fetch SendGrid API key from Secret Manager or environment."""
    # First check environment variable
    key = os.environ.get('SENDGRID_API_KEY')
    if key:
        return key

    # Fall back to Secret Manager
    try:
        name = f"projects/{PROJECT_ID}/secrets/sendgrid-api-key/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        raise ValueError(f"Failed to get SendGrid API key: {e}")


def get_recipients() -> list[str]:
    """Fetch recipient emails from BigQuery."""
    query = """
        SELECT email FROM `fdsanalytics.insights.email_recipients`
        WHERE active = TRUE
    """
    results = bq_client.query(query).result()
    return [row.email for row in results]


def log_report(report_date, status: str, recipient_count: int = None, error_message: str = None):
    """Log report send attempt to BigQuery."""
    row = {
        "report_date": str(report_date),
        "sent_at": datetime.utcnow().isoformat(),
        "status": status,
        "recipient_count": recipient_count,
        "error_message": error_message[:500] if error_message else None
    }

    try:
        table_ref = bq_client.dataset('insights').table('email_report_log')
        errors = bq_client.insert_rows_json(table_ref, [row])
        if errors:
            log_error(f"Failed to log report: {errors}")
    except Exception as e:
        log_error(f"Failed to log report: {e}")


def is_already_sent(report_date) -> bool:
    """Check if email was already sent for this date."""
    query = f"""
        SELECT 1 FROM `fdsanalytics.insights.email_report_log`
        WHERE report_date = '{report_date}' AND status = 'success'
        LIMIT 1
    """
    results = list(bq_client.query(query).result())
    return len(results) > 0


def send_email(recipients: list[str], subject: str, html_content: str) -> dict:
    """Send email via SendGrid."""
    if SendGridAPIClient is None:
        raise ImportError("sendgrid package not installed")

    sg = SendGridAPIClient(get_sendgrid_key())

    # SendGrid requires a verified sender domain or single sender
    from_email = os.environ.get('FROM_EMAIL', 'analytics@fdsconsulting.com')

    message = Mail(
        from_email=from_email,
        to_emails=recipients,
        subject=subject,
        html_content=Content("text/html", html_content)
    )

    response = sg.send(message)

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers)
    }


@functions_framework.http
def send_daily_report(request):
    """
    HTTP Cloud Function entry point.

    Fetches yesterday's analytics data, generates charts, renders HTML email,
    and sends via SendGrid to all active recipients.

    Query parameters:
        test_date: Optional date override for testing (YYYY-MM-DD format)

    Returns:
        JSON response with status and details
    """
    # Check for test date override
    test_date = request.args.get('test_date') if request else None

    if test_date:
        try:
            report_date = datetime.strptime(test_date, '%Y-%m-%d').date()
            log_info(f"Using test date override: {report_date}")
        except ValueError:
            return {
                'status': 'error',
                'message': f'Invalid test_date format: {test_date}. Use YYYY-MM-DD'
            }
    else:
        # Calculate yesterday's date in Central Time
        now_ct = datetime.now(CT_OFFSET)
        report_date = (now_ct - timedelta(days=1)).date()

    log_info(f"Starting daily report for {report_date}")

    # Check if already sent (prevent duplicates)
    if is_already_sent(report_date):
        log_info(f"Email already sent for {report_date}", report_date=str(report_date))
        return {
            'status': 'already_sent',
            'message': f'Email already sent for {report_date}',
            'report_date': str(report_date)
        }

    try:
        # Fetch all report data
        log_info("Fetching report data from BigQuery")
        data = fetch_report_data(bq_client, report_date)

        # Check if we have data for yesterday
        if not data.get('yesterday'):
            log_info(f"No data available for {report_date}", report_date=str(report_date))
            log_report(report_date, 'no_data', error_message='No sales data for report date')
            return {
                'status': 'no_data',
                'message': f'No data available for {report_date}',
                'report_date': str(report_date)
            }

        # Build chart URLs
        log_info("Building charts")
        charts = build_all_charts(data)

        # Render HTML email
        log_info("Rendering email HTML")
        html_content = render_email_html(data, charts, report_date)

        # Get recipients
        recipients = get_recipients()
        if not recipients:
            log_info("No active recipients found")
            log_report(report_date, 'no_recipients')
            return {
                'status': 'no_recipients',
                'message': 'No active recipients configured',
                'report_date': str(report_date)
            }

        log_info(f"Sending email to {len(recipients)} recipients")

        # Send email
        subject = f"Senso Sushi Daily Report - {report_date.strftime('%B %d, %Y')}"
        result = send_email(recipients, subject, html_content)

        # Log success
        log_info(
            f"Daily report sent successfully",
            report_date=str(report_date),
            recipients=len(recipients),
            sendgrid_status=result['status_code']
        )
        log_report(report_date, 'success', len(recipients))

        return {
            'status': 'success',
            'report_date': str(report_date),
            'recipients': len(recipients),
            'sendgrid_status': result['status_code']
        }

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        log_error(f"Failed to send daily report: {error_msg}", report_date=str(report_date))
        log_report(report_date, 'failed', error_message=error_msg)

        return {
            'status': 'error',
            'message': error_msg,
            'report_date': str(report_date)
        }, 500
