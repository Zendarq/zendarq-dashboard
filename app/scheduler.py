"""APScheduler wiring: periodically refresh weather data in the background."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app import db
from app.config import WEATHER_REFRESH_SECONDS
from app.sources import weather as weather_source

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def refresh_all_weather() -> None:
    """Fetch weather for all cities and persist to SQLite."""
    log.info("refreshing weather…")
    try:
        for data in weather_source.fetch_all():
            db.store_city_weather(data)
            log.info("stored weather for %s", data["id"])
    except Exception:  # noqa: BLE001
        log.exception("weather refresh failed")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        refresh_all_weather,
        "interval",
        seconds=WEATHER_REFRESH_SECONDS,
        id="weather_refresh",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("scheduler started (every %ss)", WEATHER_REFRESH_SECONDS)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
