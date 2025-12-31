"""
QuickChart.io URL builders for email charts.

Generates chart URLs that can be embedded directly in HTML emails.
QuickChart renders Chart.js configs server-side and returns PNG images.

Free tier: 500 charts/month (plenty for daily emails)
Docs: https://quickchart.io/documentation/
"""

import json
import urllib.parse

QUICKCHART_BASE = "https://quickchart.io/chart"
DEFAULT_WIDTH = 500
DEFAULT_HEIGHT = 250
BACKGROUND_COLOR = "white"

# Brand colors
COLOR_PRIMARY = "#4285F4"  # Google Blue
COLOR_SUCCESS = "#34A853"  # Green
COLOR_WARNING = "#FBBC04"  # Yellow
COLOR_DANGER = "#EA4335"   # Red
CATEGORY_COLORS = ["#4285F4", "#34A853", "#FBBC04", "#EA4335", "#9E69AF", "#FF6D01"]


def build_chart_url(config: dict, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> str:
    """Build a QuickChart URL from a Chart.js config."""
    encoded = urllib.parse.quote(json.dumps(config, separators=(',', ':')))
    return f"{QUICKCHART_BASE}?c={encoded}&w={width}&h={height}&bkg={BACKGROUND_COLOR}"


def build_all_charts(data: dict) -> dict:
    """
    Build all chart URLs for the daily report.

    Args:
        data: Report data from fetch_report_data()

    Returns:
        Dictionary of chart URLs keyed by chart name
    """
    charts = {}

    if data.get('trend'):
        charts['sales_trend'] = build_sales_trend_chart(data['trend'])

    if data.get('top_categories'):
        charts['category_breakdown'] = build_category_chart(data['top_categories'])

    if data.get('forecast'):
        charts['forecast'] = build_forecast_chart(data['forecast'])

    return charts


def build_sales_trend_chart(trend_data: list[dict]) -> str:
    """Build 7-day sales trend bar chart."""
    labels = [d['day_name'][:3] for d in trend_data]
    values = [round(d['total_net_sales'] or 0, 0) for d in trend_data]

    config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": "Sales ($)",
                "data": values,
                "backgroundColor": COLOR_PRIMARY,
                "borderRadius": 4
            }]
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": "Last 7 Days Sales",
                    "font": {"size": 14}
                }
            },
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "ticks": {"callback": "${{value}}"}
                }
            }
        }
    }

    return build_chart_url(config)


def build_category_chart(categories: list[dict]) -> str:
    """Build category breakdown pie chart."""
    # Clean up category names (remove parentheses)
    labels = [c['primary_category'].strip('()') for c in categories]
    values = [round(c['total_sales'] or 0, 0) for c in categories]

    config = {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": values,
                "backgroundColor": CATEGORY_COLORS[:len(labels)]
            }]
        },
        "options": {
            "plugins": {
                "legend": {
                    "position": "right",
                    "labels": {"boxWidth": 12}
                },
                "title": {
                    "display": True,
                    "text": "Sales by Category",
                    "font": {"size": 14}
                },
                "datalabels": {
                    "display": True,
                    "formatter": "(value) => '$' + value.toLocaleString()",
                    "color": "#fff",
                    "font": {"weight": "bold"}
                }
            }
        }
    }

    return build_chart_url(config, width=450, height=250)


def build_forecast_chart(forecast_data: list[dict]) -> str:
    """Build 5-day forecast line chart with confidence bounds."""
    labels = [f"{d['day_name'][:3]}" for d in forecast_data]
    predicted = [d['predicted_sales'] for d in forecast_data]
    lower = [d['lower_bound'] for d in forecast_data]
    upper = [d['upper_bound'] for d in forecast_data]

    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Predicted",
                    "data": predicted,
                    "borderColor": COLOR_PRIMARY,
                    "backgroundColor": COLOR_PRIMARY,
                    "fill": False,
                    "tension": 0.1,
                    "pointRadius": 5
                },
                {
                    "label": "Upper Bound",
                    "data": upper,
                    "borderColor": "rgba(66, 133, 244, 0.3)",
                    "backgroundColor": "rgba(66, 133, 244, 0.1)",
                    "fill": "+1",
                    "tension": 0.1,
                    "pointRadius": 0,
                    "borderDash": [5, 5]
                },
                {
                    "label": "Lower Bound",
                    "data": lower,
                    "borderColor": "rgba(66, 133, 244, 0.3)",
                    "backgroundColor": "transparent",
                    "fill": False,
                    "tension": 0.1,
                    "pointRadius": 0,
                    "borderDash": [5, 5]
                }
            ]
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": "5-Day Sales Forecast",
                    "font": {"size": 14}
                }
            },
            "scales": {
                "y": {
                    "beginAtZero": False,
                    "ticks": {"callback": "${{value}}"}
                }
            }
        }
    }

    return build_chart_url(config)
