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

# Start from a clean slate: the stub is authoritative and so is the state file.
rm -f state/residency.json
pkill -f 'uvicorn stub_qsim:app --host 127.0.0.1 --port 18600' >/dev/null 2>&1 || true
orch_up 0 "nemotron-120b,qwen35-a3b" "qwen35-a3b"
resid_up

echo "=== 10. DEGRADED — a model refuses to come back; the record must be KEPT ==="
echo "  baseline loaded: [$(loaded)]"
curl -s -m 90 -X POST -H "$T" http://127.0.0.1:18610/claim >/dev/null
echo "  claimed; loaded now: [$(loaded)]  (expect empty)"
echo "  release, with qwen35-a3b rigged to fail its load:"
curl -s -m 120 -X POST -H "$T" http://127.0.0.1:18610/release | brief
echo "  loaded: [$(loaded)]   (expect nemotron-120b only)"
echo "  -> claim must REFUSE while degraded:"
curl -s -X POST -H "$T" http://127.0.0.1:18610/claim | brief
echo "  -> repair the backend, retry release; it must finish from the KEPT record:"
orch_up 0 "nemotron-120b" ""
curl -s -m 120 -X POST -H "$T" http://127.0.0.1:18610/release | brief
echo "  loaded: [$(loaded)]   (expect nemotron-120b,qwen35-a3b)"
