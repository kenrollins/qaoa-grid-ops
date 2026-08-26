#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pkill -f "uvicorn stub_qsim:app --host 127.0.0.1 --port 18600" 2>/dev/null || true
sleep 0.5
setsid nohup python3 -m uvicorn stub_qsim:app --host 127.0.0.1 --port 18600 \
  >> qsim.log 2>&1 < /dev/null &
for _ in $(seq 1 20); do
  sleep 0.5
  curl -sf -m 2 http://127.0.0.1:18600/health >/dev/null && exit 0
done
exit 1
