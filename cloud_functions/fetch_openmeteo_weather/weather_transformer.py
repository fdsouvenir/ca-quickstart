"""
Transform Open-Meteo API responses to BigQuery schema format.
Handles both historical and forecast data.
"""

from datetime import datetime
from typing import Dict, List, Any, Optional

# WMO Weather Code to human-readable condition mapping
# https://open-meteo.com/en/docs
WMO_CODE_MAP = {
    0: "Clear",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Freezing Drizzle",
    57: "Heavy Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Light Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Hail",
    99: "Severe Thunderstorm",
}


def get_weather_condition(code: Optional[int]) -> str:
    """Convert WMO weather code to human-readable string."""
    if code is None:
        return "Unknown"
    return WMO_CODE_MAP.get(code, f"Code {code}")


def is_rain_code(code: Optional[int]) -> bool:
    """Check if weather code indicates rain."""
    if code is None:
        return False
    # Drizzle (51-57), Rain (61-67), Showers (80-82), Thunderstorm (95-99)
    return code in range(51, 68) or code in range(80, 83) or code in range(95, 100)


def is_snow_code(code: Optional[int]) -> bool:
    """Check if weather code indicates snow."""
    if code is None:
        return False
    # Snow (71-77), Snow Showers (85-86)
    return code in range(71, 78) or code in range(85, 87)


def transform_historical(api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform historical API response to local_weather table format.

    Args:
        api_response: Open-Meteo archive API response

    Returns:
        List of dicts matching local_weather schema
    """
    daily = api_response.get("daily", {})
    dates = daily.get("time", [])

    records = []
    for i, date_str in enumerate(dates):
        weather_code = daily.get("weather_code", [None] * len(dates))[i]
        rain_sum = daily.get("rain_sum", [0] * len(dates))[i] or 0
        snow_sum = daily.get("snowfall_sum", [0] * len(dates))[i] or 0

        record = {
            "weather_date": date_str,
            "avg_temp_f": daily.get("temperature_2m_mean", [None] * len(dates))[i],
            "max_temp_f": daily.get("temperature_2m_max", [None] * len(dates))[i],
            "min_temp_f": daily.get("temperature_2m_min", [None] * len(dates))[i],
            "precipitation_in": daily.get("precipitation_sum", [None] * len(dates))[i],
            "had_rain": rain_sum > 0 or is_rain_code(weather_code),
            "had_snow": snow_sum > 0 or is_snow_code(weather_code),
            "wind_speed_mph": daily.get("wind_speed_10m_max", [None] * len(dates))[i],
            "wind_gust_mph": daily.get("wind_gusts_10m_max", [None] * len(dates))[i],
            "weather_code": weather_code,
            "weather_condition": get_weather_condition(weather_code),
            "cloud_cover_pct": _to_int(daily.get("cloud_cover_mean", [None] * len(dates))[i]),
            "humidity_pct": _to_int(daily.get("relative_humidity_2m_mean", [None] * len(dates))[i]),
            "uv_index": daily.get("uv_index_max", [None] * len(dates))[i],
            # Keep legacy columns as NULL (they'll be deprecated)
            "visibility_miles": None,
            "wind_speed_knots": None,
        }
        records.append(record)

    return records


def transform_forecast(api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform forecast API response to weather_forecast table format.

    Args:
        api_response: Open-Meteo forecast API response

    Returns:
        List of dicts matching weather_forecast schema
    """
    daily = api_response.get("daily", {})
    dates = daily.get("time", [])
    now = datetime.utcnow().isoformat()

    records = []
    for i, date_str in enumerate(dates):
        weather_code = daily.get("weather_code", [None] * len(dates))[i]
        precip_prob = daily.get("precipitation_probability_max", [None] * len(dates))[i]

        record = {
            "forecast_date": date_str,
            "updated_at": now,
            "high_temp_f": daily.get("temperature_2m_max", [None] * len(dates))[i],
            "low_temp_f": daily.get("temperature_2m_min", [None] * len(dates))[i],
            "avg_temp_f": daily.get("temperature_2m_mean", [None] * len(dates))[i],
            "precipitation_in": daily.get("precipitation_sum", [None] * len(dates))[i],
            "precipitation_probability_pct": _to_int(precip_prob),
            "rain_likely": bool(is_rain_code(weather_code) or (precip_prob and precip_prob > 30)),
            "snow_likely": bool(is_snow_code(weather_code)),
            "wind_speed_mph": daily.get("wind_speed_10m_max", [None] * len(dates))[i],
            "wind_gust_mph": daily.get("wind_gusts_10m_max", [None] * len(dates))[i],
            "weather_code": weather_code,
            "weather_condition": get_weather_condition(weather_code),
            "cloud_cover_pct": _to_int(daily.get("cloud_cover_mean", [None] * len(dates))[i]),
            "humidity_pct": _to_int(daily.get("relative_humidity_2m_mean", [None] * len(dates))[i]),
            "uv_index": daily.get("uv_index_max", [None] * len(dates))[i],
        }
        records.append(record)

    return records


def merge_historical_responses(responses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge multiple historical API responses into single record list.
    Used when fetching large date ranges in chunks.

    Args:
        responses: List of API responses from fetch_date_range

    Returns:
        Combined list of transformed records
    """
    all_records = []
    for response in responses:
        records = transform_historical(response)
        all_records.extend(records)
    return all_records


def _to_int(value: Optional[float]) -> Optional[int]:
    """Safely convert float to int."""
    if value is None:
        return None
    return int(round(value))
