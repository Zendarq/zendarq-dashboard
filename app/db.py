"""SQLite storage layer. One connection per call (thread-safe)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS current_weather (
    city        TEXT PRIMARY KEY,
    tz          TEXT,
    fetched_at  TEXT,
    temp_c      REAL,
    feels_like_c REAL,
    humidity    REAL,
    wind_kmh    REAL,
    precip_mm   REAL,
    weather_code INTEGER,
    is_day      INTEGER
);

CREATE TABLE IF NOT EXISTS hourly_weather (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    city        TEXT NOT NULL,
    ts          TEXT NOT NULL,
    temp_c      REAL,
    precip_prob INTEGER
);

CREATE TABLE IF NOT EXISTS daily_weather (
    city            TEXT NOT NULL,
    date            TEXT NOT NULL,
    weather_code    INTEGER,
    tmax_c          REAL,
    tmin_c          REAL,
    sunrise         TEXT,
    sunset          TEXT,
    precip_prob_max INTEGER,
    PRIMARY KEY (city, date)
);

CREATE INDEX IF NOT EXISTS idx_hourly_city_ts ON hourly_weather(city, ts);

DROP INDEX IF EXISTS idx_hourly_city_ts_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_hourly_city_ts_unique ON hourly_weather(city, ts);

CREATE TABLE IF NOT EXISTS fx_latest (
    pair        TEXT PRIMARY KEY,
    rate        REAL,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS fx_history (
    pair    TEXT NOT NULL,
    date    TEXT NOT NULL,
    rate    REAL,
    PRIMARY KEY (pair, date)
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(SCHEMA)


def upsert_current(row: dict[str, Any]) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO current_weather
               (city, tz, fetched_at, temp_c, feels_like_c, humidity,
                wind_kmh, precip_mm, weather_code, is_day)
               VALUES (:city, :tz, :fetched_at, :temp_c, :feels_like_c, :humidity,
                       :wind_kmh, :precip_mm, :code, :is_day)
               ON CONFLICT(city) DO UPDATE SET
                 tz=excluded.tz, fetched_at=excluded.fetched_at,
                 temp_c=excluded.temp_c, feels_like_c=excluded.feels_like_c,
                 humidity=excluded.humidity, wind_kmh=excluded.wind_kmh,
                 precip_mm=excluded.precip_mm, weather_code=excluded.weather_code,
                 is_day=excluded.is_day""",
            row,
        )


def insert_hourly(city: str, times: list[str], temps: list[float], precip_prob: list[int]) -> None:
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO hourly_weather (city, ts, temp_c, precip_prob) VALUES (?,?,?,?)",
            [(city, t, temp, prob) for t, temp, prob in zip(times, temps, precip_prob)],
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat(timespec="minutes")
        conn.execute("DELETE FROM hourly_weather WHERE city=? AND ts < ?", (city, cutoff))


def insert_daily(city: str, days: dict[str, Any]) -> None:
    with _conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO daily_weather
               (city, date, weather_code, tmax_c, tmin_c, sunrise, sunset, precip_prob_max)
               VALUES (?,?,?,?,?,?,?,?)""",
            [
                (city, d, code, tmax, tmin, sunrise, sunset, prob)
                for d, code, tmax, tmin, sunrise, sunset, prob in zip(
                    days["dates"], days["codes"], days["tmax"], days["tmin"],
                    days["sunrise"], days["sunset"], days["precip_prob_max"],
                )
            ],
        )


def store_city_weather(data: dict[str, Any]) -> None:
    row = dict(data)
    row["city"] = row.pop("id")
    upsert_current(row)
    insert_hourly(data["id"], data["hourly"]["times"], data["hourly"]["temps"], data["hourly"]["precip_prob"])
    insert_daily(data["id"], data["daily"])


def get_current() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM current_weather").fetchall()
    return [dict(r) for r in rows]


def get_hourly(city: str, limit: int = 48) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, temp_c, precip_prob FROM hourly_weather WHERE city=? ORDER BY ts ASC LIMIT ?",
            (city, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily(city: str) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_weather WHERE city=? ORDER BY date", (city,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- FX ----------

def upsert_fx(pair: str, rate: float, updated_at: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO fx_latest (pair, rate, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(pair) DO UPDATE SET rate=excluded.rate, updated_at=excluded.updated_at",
            (pair, rate, updated_at),
        )


def insert_fx_history(pair: str, points: list[tuple[str, float]]) -> None:
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO fx_history (pair, date, rate) VALUES (?,?,?)",
            [(pair, d, r) for d, r in points],
        )


def fx_history_empty(pair: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM fx_history WHERE pair=? LIMIT 1", (pair,)).fetchone()
    return row is None


def get_fx() -> list[dict[str, Any]]:
    with _conn() as conn:
        latest = {r["pair"]: dict(r) for r in conn.execute("SELECT * FROM fx_latest").fetchall()}
        rows = conn.execute(
            "SELECT pair, date, rate FROM fx_history ORDER BY date"
        ).fetchall()
    history: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        history.setdefault(r["pair"], []).append({"date": r["date"], "rate": r["rate"]})
    out = []
    for pair, lr in latest.items():
        out.append({
            "pair": pair,
            "rate": lr["rate"],
            "updated_at": lr["updated_at"],
            "history": history.get(pair, []),
        })
    return out
