"""
Open-Meteo API client for fetching weather data.
Handles both historical archive and forecast endpoints.
"""

import requests
from datetime import date, timedelta
from typing import Dict, List, Any, Optional

# Frankfort, IL coordinates
LATITUDE = 41.1958
LONGITUDE = -87.8487
TIMEZONE = "America/Chicago"

# API endpoints
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Daily variables to fetch
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "weather_code",
    "cloud_cover_mean",
    "relative_humidity_2m_mean",
    "uv_index_max",
]

# Additional forecast-only variables
FORECAST_VARIABLES = DAILY_VARIABLES + [
    "precipitation_probability_max",
]


def fetch_historical(start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Fetch historical weather data from Open-Meteo Archive API.

    Args:
        start_date: First date to fetch (inclusive)
        end_date: Last date to fetch (inclusive)

    Returns:
        API response as dict with 'daily' key containing weather data

    Raises:
        requests.RequestException: If API call fails
    """
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "wind_speed_unit": "mph",
    }

    response = requests.get(ARCHIVE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_forecast(days: int = 14) -> Dict[str, Any]:
    """
    Fetch weather forecast from Open-Meteo Forecast API.

    Args:
        days: Number of forecast days (default 14, max 16)

    Returns:
        API response as dict with 'daily' key containing forecast data

    Raises:
        requests.RequestException: If API call fails
    """
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": ",".join(FORECAST_VARIABLES),
        "timezone": TIMEZONE,
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "wind_speed_unit": "mph",
        "forecast_days": days,
    }

    response = requests.get(FORECAST_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_yesterday() -> Dict[str, Any]:
    """
    Convenience function to fetch yesterday's weather.

    Returns:
        API response for yesterday's date
    """
    yesterday = date.today() - timedelta(days=1)
    return fetch_historical(yesterday, yesterday)


def fetch_date_range(start_date: date, end_date: date,
                     chunk_size: int = 365) -> List[Dict[str, Any]]:
    """
    Fetch historical data in chunks (for large date ranges).
    Open-Meteo archive has limits on single requests.

    Args:
        start_date: First date to fetch
        end_date: Last date to fetch
        chunk_size: Max days per request (default 365)

    Returns:
        List of API responses
    """
    responses = []
    current_start = start_date

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=chunk_size - 1), end_date)
        response = fetch_historical(current_start, current_end)
        responses.append(response)
        current_start = current_end + timedelta(days=1)

    return responses
