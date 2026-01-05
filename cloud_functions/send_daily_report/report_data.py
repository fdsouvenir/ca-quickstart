"""
BigQuery queries for daily email report data.

Fetches all metrics needed for the daily report:
- Yesterday's sales summary
- Top categories
- Period comparisons (WoW, MoM, YoY)
- Recent anomalies
- 5-day forecast
- 30-day trend for charts
- Category forecast
- Top seller
"""

from datetime import date
from google.cloud import bigquery


def fetch_report_data(client: bigquery.Client, report_date: date) -> dict:
    """
    Fetch all data needed for the daily report.

    Args:
        client: BigQuery client
        report_date: The date to report on (usually yesterday)

    Returns:
        Dictionary with all report data sections
    """
    return {
        'yesterday': fetch_yesterday_summary(client, report_date),
        'top_categories': fetch_top_categories(client, report_date),
        'comparisons': fetch_period_comparisons(client, report_date),
        'anomalies': fetch_recent_anomalies(client, report_date),
        'forecast': fetch_forecast(client),
        'trend': fetch_30day_trend(client, report_date),
        'top_items': fetch_top_items(client, report_date),
        'top_seller': fetch_top_seller(client, report_date),
    }


def fetch_yesterday_summary(client: bigquery.Client, report_date: date) -> dict | None:
    """Fetch yesterday's summary from ai.daily_summary."""
    query = """
        SELECT
            report_date,
            total_net_sales,
            total_quantity_sold,
            total_discount,
            unique_items_sold,
            line_item_count,
            avg_temp_f,
            max_temp_f,
            min_temp_f,
            precipitation_in,
            had_rain,
            had_snow,
            event_names,
            event_count,
            day_name,
            is_weekend
        FROM `fdsanalytics.ai.daily_summary`
        WHERE report_date = @report_date
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = list(client.query(query, job_config=job_config).result())
    return dict(results[0]) if results else None


def fetch_top_categories(client: bigquery.Client, report_date: date) -> list[dict]:
    """Fetch top 5 categories by sales for the report date."""
    query = """
        SELECT
            primary_category,
            SUM(net_sales) as total_sales,
            SUM(quantity_sold) as total_quantity
        FROM `fdsanalytics.ai.restaurant_analytics`
        WHERE report_date = @report_date
        GROUP BY primary_category
        ORDER BY total_sales DESC
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = client.query(query, job_config=job_config).result()
    return [dict(row) for row in results]


def fetch_period_comparisons(client: bigquery.Client, report_date: date) -> dict | None:
    """Compare report_date to same day last week, last month, and last year."""
    query = """
        WITH current_day AS (
            SELECT total_net_sales, total_quantity_sold, day_name
            FROM `fdsanalytics.ai.daily_summary`
            WHERE report_date = @report_date
            LIMIT 1
        ),
        last_week AS (
            SELECT total_net_sales, total_quantity_sold
            FROM `fdsanalytics.ai.daily_summary`
            WHERE report_date = DATE_SUB(@report_date, INTERVAL 7 DAY)
            LIMIT 1
        ),
        last_month AS (
            SELECT total_net_sales, total_quantity_sold
            FROM `fdsanalytics.ai.daily_summary`
            WHERE report_date = DATE_SUB(@report_date, INTERVAL 1 MONTH)
            LIMIT 1
        ),
        last_year AS (
            SELECT total_net_sales, total_quantity_sold
            FROM `fdsanalytics.ai.daily_summary`
            WHERE report_date = DATE_SUB(@report_date, INTERVAL 1 YEAR)
            LIMIT 1
        )
        SELECT
            cd.day_name,
            cd.total_net_sales as current_sales,
            cd.total_quantity_sold as current_quantity,
            -- Week-over-week
            ROUND(100.0 * (cd.total_net_sales - lw.total_net_sales) /
                  NULLIF(lw.total_net_sales, 0), 1) as wow_sales_pct,
            ROUND(100.0 * (cd.total_quantity_sold - lw.total_quantity_sold) /
                  NULLIF(lw.total_quantity_sold, 0), 1) as wow_qty_pct,
            -- Month-over-month
            ROUND(100.0 * (cd.total_net_sales - lm.total_net_sales) /
                  NULLIF(lm.total_net_sales, 0), 1) as mom_sales_pct,
            ROUND(100.0 * (cd.total_quantity_sold - lm.total_quantity_sold) /
                  NULLIF(lm.total_quantity_sold, 0), 1) as mom_qty_pct,
            -- Year-over-year
            ROUND(100.0 * (cd.total_net_sales - ly.total_net_sales) /
                  NULLIF(ly.total_net_sales, 0), 1) as yoy_sales_pct,
            ROUND(100.0 * (cd.total_quantity_sold - ly.total_quantity_sold) /
                  NULLIF(ly.total_quantity_sold, 0), 1) as yoy_qty_pct
        FROM current_day cd
        LEFT JOIN last_week lw ON TRUE
        LEFT JOIN last_month lm ON TRUE
        LEFT JOIN last_year ly ON TRUE
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = list(client.query(query, job_config=job_config).result())
    return dict(results[0]) if results else None


def fetch_recent_anomalies(client: bigquery.Client, report_date: date) -> list[dict]:
    """Fetch anomalies for the report date, grouped by category."""
    query = """
        WITH grouped AS (
            SELECT
                category_name,
                parent_category,
                day_name,
                report_date,
                MAX(CASE WHEN metric_type = 'sales' THEN ROUND(actual_value, 0) END) as sales_actual,
                MAX(CASE WHEN metric_type = 'sales' THEN ROUND(predicted_value, 0) END) as sales_predicted,
                MAX(CASE WHEN metric_type = 'sales' THEN anomaly_type END) as sales_anomaly_type,
                MAX(CASE WHEN metric_type = 'quantity' THEN ROUND(actual_value, 0) END) as qty_actual,
                MAX(CASE WHEN metric_type = 'quantity' THEN ROUND(predicted_value, 0) END) as qty_predicted,
                MAX(CASE WHEN metric_type = 'quantity' THEN anomaly_type END) as qty_anomaly_type,
                MAX(CASE WHEN metric_type = 'sales' THEN ABS(actual_value - predicted_value) END) as sales_deviation
            FROM `fdsanalytics.ai.category_anomalies`
            WHERE is_anomaly = TRUE AND report_date = @report_date
            GROUP BY category_name, parent_category, day_name, report_date
        )
        SELECT * FROM grouped
        ORDER BY sales_deviation DESC NULLS LAST
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = client.query(query, job_config=job_config).result()
    return [dict(row) for row in results]


def fetch_top_items(client: bigquery.Client, report_date: date) -> list[dict]:
    """Fetch top 5 best-selling items for the report date."""
    query = """
        SELECT
            item_name,
            category,
            SUM(quantity_sold) as quantity,
            ROUND(SUM(net_sales), 0) as sales
        FROM `fdsanalytics.ai.restaurant_analytics`
        WHERE report_date = @report_date
        GROUP BY item_name, category
        ORDER BY sales DESC
        LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = client.query(query, job_config=job_config).result()
    return [dict(row) for row in results]


def fetch_forecast(client: bigquery.Client) -> list[dict]:
    """Fetch 5-day sales forecast."""
    query = """
        SELECT
            forecast_date,
            day_name,
            is_weekend,
            ROUND(predicted_sales, 0) as predicted_sales,
            ROUND(lower_bound, 0) as lower_bound,
            ROUND(upper_bound, 0) as upper_bound,
            confidence_level
        FROM `fdsanalytics.ai.sales_forecast`
        WHERE forecast_date >= CURRENT_DATE()
        ORDER BY forecast_date
        LIMIT 5
    """
    results = client.query(query).result()
    return [dict(row) for row in results]


def fetch_30day_trend(client: bigquery.Client, report_date: date) -> list[dict]:
    """Fetch last 30 days of sales for trend chart."""
    query = """
        SELECT
            report_date,
            day_name,
            total_net_sales,
            total_quantity_sold,
            avg_temp_f
        FROM `fdsanalytics.ai.daily_summary`
        WHERE report_date > DATE_SUB(@report_date, INTERVAL 30 DAY)
            AND report_date <= @report_date
        ORDER BY report_date
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = client.query(query, job_config=job_config).result()
    return [dict(row) for row in results]


def fetch_top_seller(client: bigquery.Client, report_date: date) -> dict | None:
    """Fetch the #1 top-selling item by sales for the report date."""
    query = """
        SELECT
            item_name,
            ROUND(SUM(net_sales), 0) as sales
        FROM `fdsanalytics.ai.restaurant_analytics`
        WHERE report_date = @report_date
        GROUP BY item_name
        ORDER BY sales DESC
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("report_date", "DATE", str(report_date))
        ]
    )
    results = list(client.query(query, job_config=job_config).result())
    return dict(results[0]) if results else None
