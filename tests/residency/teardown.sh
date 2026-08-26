#!/usr/bin/env bash
# Kill ONLY the stub processes, by their full and distinctive command lines.
pkill -9 -f 'uvicorn residency:app --host 127.0.0.1 --port 18610' >/dev/null 2>&1 || true
pkill -9 -f 'uvicorn stub_orch:app --host 127.0.0.1 --port 19000' >/dev/null 2>&1 || true
pkill -9 -f 'uvicorn stub_qsim:app --host 127.0.0.1 --port 18600' >/dev/null 2>&1 || true
sleep 1
echo "remaining test listeners:"; ss -ltnp 2>/dev/null | grep -E '1(8610|8600|9000)' || echo "  none"
echo
echo "PRODUCTION processes (must all still be here):"
systemctl --user is-active gb10-vllm-orchestrator gridops-residency
ss -ltn 2>/dev/null | grep -E ':(9000|8610|8600)\b' || true
