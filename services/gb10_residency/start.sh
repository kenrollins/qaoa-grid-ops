#!/usr/bin/env bash
# Start gridops-residency by hand (systemd is the normal path — see
# gridops-residency.service). Foreground: this is a control plane, so when you
# run it yourself you want to watch it.
set -euo pipefail

GRIDOPS_ROOT="${GRIDOPS_ROOT:-$HOME/gridops}"
VENV="${GRIDOPS_VENV:-$GRIDOPS_ROOT/.venv}"
BIND="${GRIDOPS_RESIDENCY_BIND:-10.0.13.200}"
PORT="${GRIDOPS_RESIDENCY_PORT:-8610}"
ENV_FILE="${GRIDOPS_RESIDENCY_ENV:-$HOME/.config/gridops/residency.env}"

# Credentials live in a 600 file, never on the command line (ps is world-readable).
if [ -r "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
else
  echo "WARNING — no $ENV_FILE; the service will FAIL CLOSED and refuse every caller" >&2
fi

cd "$(dirname "$0")"
# `residency:app`, never `server:app` — gridops-qsim's start/stop pkills that
# pattern and would take this process with it. See residency.py.
exec "$VENV/bin/uvicorn" residency:app --host "$BIND" --port "$PORT" --no-access-log
