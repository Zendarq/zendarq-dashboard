"""Central configuration for zendarq-dashboard."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "dashboard.db"

# Weather sources (Open-Meteo, no API key required)
CITIES = [
    {"id": "nyc",     "name": "New York City", "lat": 40.7128,  "lon": -74.0060},
    {"id": "tokyo",   "name": "Tokyo",         "lat": 35.6762,  "lon": 139.6503},
    {"id": "chicago", "name": "Chicago",       "lat": 41.8781,  "lon": -87.6298},
]

CITY_BY_ID = {c["id"]: c for c in CITIES}

# How often the scheduler refreshes weather data (seconds)
WEATHER_REFRESH_SECONDS = 15 * 60

# Open-Meteo request timeout (seconds)
HTTP_TIMEOUT = 12
