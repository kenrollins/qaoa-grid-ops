#!/usr/bin/env bash
# Start gridops-qsim on the GB10, detached from the invoking shell.
#
# `nohup ... &` inside an `ssh host 'cmd'` is NOT enough: when the SSH session
# closes, the process group is signalled and uvicorn dies with it. setsid moves
# the server into its own session so it survives the disconnect. This bit us
# during bring-up — the service appeared to start, answered /health once, and
# was gone by the next request.
set -euo pipefail

GRIDOPS_ROOT="${GRIDOPS_ROOT:-$HOME/gridops}"
VENV="${GRIDOPS_VENV:-$GRIDOPS_ROOT/.venv}"
PORT="${GRIDOPS_PORT:-8600}"
LOG="${GRIDOPS_LOG:-$GRIDOPS_ROOT/qsim.log}"

cd "$GRIDOPS_ROOT/services/gb10_qsim"

pkill -f "uvicorn server:app" 2>/dev/null || true
sleep 1

GRIDOPS_ROOT="$GRIDOPS_ROOT" setsid nohup \
  "$VENV/bin/uvicorn" server:app --host 0.0.0.0 --port "$PORT" \
  >> "$LOG" 2>&1 < /dev/null &

for _ in $(seq 1 30); do
  sleep 1
  if curl -sf -m 2 "http://127.0.0.1:$PORT/health" > /dev/null; then
    echo "gridops-qsim up on :$PORT"
    curl -s "http://127.0.0.1:$PORT/health"
    echo
    exit 0
  fi
done

echo "gridops-qsim FAILED to start; last log lines:" >&2
tail -20 "$LOG" >&2
exit 1
