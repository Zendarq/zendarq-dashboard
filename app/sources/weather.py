"""Open-Meteo weather client. Free, no API key needed.

Fetches current conditions, hourly temps, and a 7-day forecast
for each configured city in a single request.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import CITIES, HTTP_TIMEOUT

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "is_day,precipitation,weather_code,wind_speed_10m"
)
HOURLY_FIELDS = "temperature_2m,precipitation_probability"
DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "sunrise,sunset,precipitation_probability_max"
)

# WMO weather codes -> (description, emoji)
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"),
    57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"),
    67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"),
    73: ("Moderate snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Light showers", "🌦️"),
    81: ("Moderate showers", "🌧️"),
    82: ("Violent showers", "⛈️"),
    85: ("Snow showers", "🌨️"),
    86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm, hail", "⛈️"),
    99: ("Thunderstorm, hail", "⛈️"),
}


def describe_code(code: int, is_day: int = 1) -> tuple[str, str]:
    label, emoji = WMO_CODES.get(code, ("Unknown", "❓"))
    if code == 0 and not is_day:
        emoji = "🌙"
    if code in (1, 2) and not is_day:
        emoji = "☁️" if code == 2 else "🌙"
    return label, emoji


def fetch_city_weather(city: dict[str, Any]) -> dict[str, Any]:
    """Fetch current + hourly + daily for one city. Raises on failure."""
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "current": CURRENT_FIELDS,
        "hourly": HOURLY_FIELDS,
        "daily": DAILY_FIELDS,
        "timezone": "auto",
        "forecast_days": 7,
    }
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    cur = data.get("current", {})
    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    return {
        "id": city["id"],
        "name": city["name"],
        "tz": data.get("timezone", "UTC"),
        "fetched_at": cur.get("time", ""),
        "temp_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "precip_mm": cur.get("precipitation"),
        "code": cur.get("weather_code"),
        "is_day": cur.get("is_day"),
        "hourly": {
            "times": hourly.get("time", []),
            "temps": hourly.get("temperature_2m", []),
            "precip_prob": hourly.get("precipitation_probability", []),
        },
        "daily": {
            "dates": daily.get("time", []),
            "codes": daily.get("weather_code", []),
            "tmax": daily.get("temperature_2m_max", []),
            "tmin": daily.get("temperature_2m_min", []),
            "sunrise": daily.get("sunrise", []),
            "sunset": daily.get("sunset", []),
            "precip_prob_max": daily.get("precipitation_probability_max", []),
        },
    }


def fetch_all() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for city in CITIES:
        try:
            results.append(fetch_city_weather(city))
        except Exception as exc:  # noqa: BLE001 - keep one bad city from killing the batch
            errors.append(f"{city['id']}: {exc}")
            log.warning("weather fetch failed for %s: %s", city["id"], exc)
    if errors:
        log.error("weather fetch errors: %s", "; ".join(errors))
    return results
