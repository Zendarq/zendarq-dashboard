"""APScheduler wiring: periodically refresh weather data in the background."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app import db
from app.config import FX_REFRESH_SECONDS, WEATHER_REFRESH_SECONDS
from app.sources import fx as fx_source
from app.sources import news as news_source
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


def refresh_fx() -> None:
    """Fetch latest FX rates; backfill 30-day history on first run."""
    log.info("refreshing fx…")
    try:
        latest = fx_source.fetch_latest()
        for pair, rate in latest.items():
            db.upsert_fx(pair, rate, datetime.now().isoformat(timespec="seconds"))
        # Backfill history once per pair (weekend-gap aware: skip nothing, ECB fills weekdays)
        for pair in latest:
            if db.fx_history_empty(pair):
                history = fx_source.fetch_history().get(pair, [])
                if history:
                    db.insert_fx_history(pair, history)
                    log.info("backfilled fx history for %s (%d points)", pair, len(history))
    except Exception:  # noqa: BLE001
        log.exception("fx refresh failed")


def refresh_news() -> None:
    """Fetch top stories from all news feeds (in-memory cache)."""
    news_source.fetch_feeds()


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
    _scheduler.add_job(
        refresh_fx,
        "interval",
        seconds=FX_REFRESH_SECONDS,
        id="fx_refresh",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        refresh_news,
        "interval",
        seconds=news_source.NEWS_REFRESH_SECONDS,
        id="news_refresh",
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
