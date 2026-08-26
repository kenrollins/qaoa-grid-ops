#!/usr/bin/env bash
cd ~/restest
VP=/home/rollik/gridops/.venv/bin
T="Authorization: Bearer op-test-token"
loaded(){ curl -s http://127.0.0.1:19000/status | python3 -c 'import json,sys;print(",".join(m["model_id"] for m in json.load(sys.stdin)["models"] if m["loaded"]))'; }
brief(){ python3 -c '
import json,sys
d=json.load(sys.stdin)
if "state" not in d: print("  REFUSED:", d.get("detail")); raise SystemExit
print("  state="+str(d.get("state")), "record="+str(d.get("pre_claim_models")), "pending="+str(d.get("pending_restore")))
for p in (d.get("progress") or [])[-5:]: print("   ", p["status"], p["step"], "—", p["detail"][:80])
'; }
resid_up(){ setsid nohup bash -c ". ~/restest/env.sh; cd ~/restest; exec $VP/python -m uvicorn residency:app --host 127.0.0.1 --port 18610 --no-access-log" >> res.log 2>&1 < /dev/null & sleep 4; }
orch_up(){ pkill -f 'uvicorn stub_orch:app' >/dev/null 2>&1 || true; sleep 1
  STUB_DELAY="$1" STUB_LOADED="${2:-nemotron-120b,qwen35-a3b}" STUB_FAIL_LOAD="${3:-}" \
  setsid nohup $VP/python -m uvicorn stub_orch:app --host 127.0.0.1 --port 19000 >> orch.log 2>&1 < /dev/null & sleep 3; }

echo "=== 8. RESUME an interrupted claim with POST /claim ==="
resid_up(){ pkill -9 -f 'uvicorn residency:app --host 127.0.0.1' >/dev/null 2>&1 || true; sleep 1
  setsid nohup bash -c ". ~/restest/env.sh; cd ~/restest; exec $VP/python -m uvicorn residency:app --host 127.0.0.1 --port 18610 --no-access-log" >> res.log 2>&1 < /dev/null & sleep 4; }

rm -f state/residency.json
pkill -f 'uvicorn stub_qsim:app --host 127.0.0.1 --port 18600' >/dev/null 2>&1 || true
orch_up 0
resid_up

echo "=== 11. RESUME guard re-verified after the code change ==="
orch_up 6
curl -s -m 90 -X POST -H "$T" http://127.0.0.1:18610/claim >/dev/null 2>&1 &
sleep 9; pkill -9 -f 'uvicorn residency:app --host 127.0.0.1' >/dev/null 2>&1 || true; sleep 2
resid_up
echo "  after hard kill:"; curl -s -H "$T" http://127.0.0.1:18610/status | brief
curl -s -m 180 -X POST -H "$T" http://127.0.0.1:18610/claim | brief
curl -s -m 180 -X POST -H "$T" http://127.0.0.1:18610/release >/dev/null
echo "  restored: [$(loaded)]"

echo
echo "=== 12. LEASE TIMEOUT — automatic release ==="
orch_up 0
rm -f state/residency.json; resid_up
echo "  baseline loaded: [$(loaded)]"
curl -s -m 90 -X POST -H "$T" -H 'Content-Type: application/json' \
  -d '{"lease_seconds":60,"reason":"lease test"}' http://127.0.0.1:18610/claim | brief
echo "  loaded during claim: [$(loaded)]   (expect empty)"
echo "  waiting out the 60s lease (watchdog ticks every 2s)..."
for i in $(seq 1 13); do
  sleep 6
  st=$(curl -s -H "$T" http://127.0.0.1:18610/status | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')
  echo "    t+$((i*6))s  state=$st  loaded=[$(loaded)]"
  [ "$st" = "released" ] && break
done
echo "  final:"; curl -s -H "$T" http://127.0.0.1:18610/status | brief
echo "  loaded after auto-release: [$(loaded)]   (expect nemotron-120b,qwen35-a3b)"
