"""
HTML rendering for daily email report.

Uses Jinja2 to render the email template with report data and charts.
"""

import os
from datetime import date, datetime
from jinja2 import Environment, FileSystemLoader


def format_number(value) -> str:
    """Format a number with commas (e.g., 1234 -> 1,234)."""
    if value is None:
        return "0"
    try:
        return f"{int(round(value)):,}"
    except (ValueError, TypeError):
        return str(value)


def render_email_html(data: dict, charts: dict, report_date: date) -> str:
    """
    Render the daily report email HTML.

    Args:
        data: Report data from fetch_report_data()
        charts: Chart URLs from build_all_charts()
        report_date: The date being reported on

    Returns:
        Rendered HTML string
    """
    # Get template directory (relative to this file)
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))

    # Add custom filters
    env.filters['format_number'] = format_number

    # Load template
    template = env.get_template('daily_report.html')

    # Format dates for display
    report_date_formatted = report_date.strftime('%A, %B %d, %Y')
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')

    # Render template with data
    return template.render(
        report_date=report_date,
        report_date_formatted=report_date_formatted,
        generated_at=generated_at,
        yesterday=data.get('yesterday'),
        wow=data.get('wow'),
        top_categories=data.get('top_categories'),
        top_items=data.get('top_items', []),
        anomalies=data.get('anomalies', []),
        forecast=data.get('forecast', []),
        trend=data.get('trend', []),
        charts=charts
    )
