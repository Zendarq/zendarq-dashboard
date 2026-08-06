# zendarq-dashboard

Personal daily dashboard — mobile-first, dark theme. Currently: live weather for NYC, Tokyo, and Chicago with 24h charts and 7-day forecasts. More sources (stocks, RSS, GitHub radar) on the way.

## Stack

- **Backend:** FastAPI + APScheduler + SQLite (data history)
- **Frontend:** Alpine.js + Chart.js, no build step, served by FastAPI
- **Data:** Open-Meteo (free, no API key)
- **Deploy:** systemd + uvicorn behind nginx + certbot on the VPS

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

## API

| Endpoint | Description |
|---|---|
| `GET /api/current` | Current conditions for all cities |
| `GET /api/hourly?city=nyc` | Hourly temps + precip probability (default 24h) |
| `GET /api/daily?city=nyc` | 7-day forecast with sunrise/sunset |
| `POST /api/refresh` | Force a data refresh |

Cities live in `app/config.py` — add/remove entries and the dashboard picks them up.

## Deploy (VPS)

1. Clone repo to `/opt/zendarq-dashboard`
2. `python3 -m venv venv && venv/bin/pip install -r requirements.txt`
3. Install `zendarq-dashboard.service` (uvicorn on 127.0.0.1:8001, user www-data)
4. nginx site: `dashboard.zendarq.online` → `127.0.0.1:8001`, then `certbot --nginx -d dashboard.zendarq.online`
