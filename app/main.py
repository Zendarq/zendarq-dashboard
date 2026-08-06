"""zendarq-dashboard — FastAPI app.

Serves the mobile-first dashboard and a small JSON API backed by SQLite.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db, scheduler
from app.config import CITY_BY_ID, STATIC_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    sched = scheduler.start_scheduler()
    # Immediate first fetch so the dashboard isn't empty on boot.
    sched.add_job(scheduler.refresh_all_weather, "date", run_date=None)  # runs once, now
    sched.add_job(scheduler.refresh_fx, "date", run_date=None)           # runs once, now
    yield
    scheduler.stop_scheduler()


app = FastAPI(title="zendarq-dashboard", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(STATIC_DIR) / "index.html")


@app.get("/api/current")
async def api_current() -> dict:
    rows = db.get_current()
    out = []
    for row in rows:
        city = CITY_BY_ID.get(row["city"], {})
        out.append({
            "id": row["city"],
            "name": city.get("name", row["city"]),
            "lat": city.get("lat"),
            "lon": city.get("lon"),
            "tz": row["tz"] or "UTC",
            "fetched_at": row["fetched_at"],
            "temp_c": row["temp_c"],
            "feels_like_c": row["feels_like_c"],
            "humidity": row["humidity"],
            "wind_kmh": row["wind_kmh"],
            "precip_mm": row["precip_mm"],
            "code": row["weather_code"],
            "is_day": row["is_day"],
        })
    return {"cities": out}


@app.get("/api/hourly")
async def api_hourly(city: str, limit: int = 24) -> dict:
    if city not in CITY_BY_ID:
        raise HTTPException(status_code=404, detail=f"unknown city: {city}")
    return {"city": city, "points": db.get_hourly(city, limit=limit)}


@app.get("/api/daily")
async def api_daily(city: str) -> dict:
    if city not in CITY_BY_ID:
        raise HTTPException(status_code=404, detail=f"unknown city: {city}")
    return {"city": city, "days": db.get_daily(city)}


@app.get("/api/fx")
async def api_fx() -> dict:
    return {"pairs": db.get_fx()}


@app.post("/api/refresh")
async def api_refresh() -> dict:
    """Force a weather refresh right now (runs async so the UI isn't blocked)."""
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(scheduler.refresh_all_weather)
    return {"ok": True}
