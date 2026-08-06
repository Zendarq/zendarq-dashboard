#!/usr/bin/env bash
# Deploy zendarq-dashboard to the VPS: pull latest from GitHub, restart service.
set -euo pipefail

echo "→ pulling latest on VPS…"
ssh vps 'cd /opt/zendarq-dashboard && git pull -q origin main && venv/bin/pip install -q -r requirements.txt && systemctl restart zendarq-dashboard && sleep 4 && systemctl is-active zendarq-dashboard'

echo "→ verifying from outside…"
curl -sf -o /dev/null -w "https://dashboard.zendarq.online → HTTP %{http_code} (%{time_total}s)\n" https://dashboard.zendarq.online/
echo "Deployed ✓"
