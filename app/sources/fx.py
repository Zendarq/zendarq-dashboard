"""Currency rates via Frankfurter (ECB reference rates). Free, no API key.

Base: https://api.frankfurter.dev/v1  (api.frankfurter.app 301-redirects here)
- Latest:  GET /v1/latest?from=USD&to=JPY,CAD,EUR
- History: GET /v1/<start>..<end>?from=USD&to=JPY,CAD,EUR   (one request per range)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from app.config import FX_HISTORY_DAYS, FX_PAIRS, HTTP_TIMEOUT

log = logging.getLogger(__name__)

BASE_URL = "https://api.frankfurter.dev/v1"
LATEST_URL = f"{BASE_URL}/latest"
HISTORY_URL = f"{BASE_URL}/{{start}}..{{end}}"


def _quotes() -> str:
    return ",".join(q for _, q in FX_PAIRS)


def fetch_latest() -> dict[str, float]:
    """Return {pair: rate} e.g. {"USD/JPY": 146.32}."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.get(LATEST_URL, params={"from": "USD", "to": _quotes()})
        resp.raise_for_status()
        data = resp.json()
    rates = data.get("rates", {})
    out: dict[str, float] = {}
    for base, quote in FX_PAIRS:
        if quote in rates:
            out[f"{base}/{quote}"] = float(rates[quote])
    return out


def fetch_history(days: int = FX_HISTORY_DAYS) -> dict[str, list[tuple[str, float]]]:
    """Return {pair: [(date_iso, rate), ...]} oldest -> newest."""
    end = date.today()
    start = end - timedelta(days=days)
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.get(
            HISTORY_URL.format(start=start.isoformat(), end=end.isoformat()),
            params={"from": "USD", "to": _quotes()},
        )
        resp.raise_for_status()
        data = resp.json()
    by_pair: dict[str, list[tuple[str, float]]] = {f"{b}/{q}": [] for b, q in FX_PAIRS}
    for day, rates in sorted(data.get("rates", {}).items()):
        for base, quote in FX_PAIRS:
            if quote in rates:
                by_pair[f"{base}/{quote}"].append((day, float(rates[quote])))
    return by_pair
