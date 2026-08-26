#!/usr/bin/env bash
# Run as a FILE, never as `ssh gb10 '<inline>'`: the inline form puts these
# pkill patterns into the remote shell's own command line, so pkill kills the
# session running the test. That is exactly the class of bug the residency
# service's module rename guards against.
cd ~/restest
VP=/home/rollik/gridops/.venv/bin
T="Authorization: Bearer op-test-token"

loaded(){ curl -s http://127.0.0.1:19000/status | python3 -c 'import json,sys;print(",".join(m["model_id"] for m in json.load(sys.stdin)["models"] if m["loaded"]))'; }
brief(){ python3 -c '
import json,sys
d=json.load(sys.stdin)
print("  state="+str(d.get("state")), "record="+str(d.get("pre_claim_models")), "pending="+str(d.get("pending_restore")))
for p in (d.get("progress") or [])[-6:]: print("   ", p["status"], p["step"], "—", p["detail"][:80])
'; }
resid_up(){ setsid nohup bash -c ". ~/restest/env.sh; cd ~/restest; exec $VP/python -m uvicorn residency:app --host 127.0.0.1 --port 18610 --no-access-log" >> res.log 2>&1 < /dev/null & sleep 4; }
orch_up(){ STUB_DELAY="$1" setsid nohup $VP/python -m uvicorn stub_orch:app --host 127.0.0.1 --port 19000 >> orch.log 2>&1 < /dev/null & sleep 3; }

echo "=== 6. HARD-KILLED CLAIM (SIGKILL, no graceful drain) ==="
pkill -f 'uvicorn stub_orch:app' >/dev/null 2>&1 || true
sleep 1
orch_up 6
echo "loaded at start: [$(loaded)]"

curl -s -m 90 -X POST -H "$T" http://127.0.0.1:18610/claim > /dev/null 2>&1 &
sleep 9
echo "  killing the control plane mid-claim..."
pkill -9 -f 'uvicorn residency:app --host 127.0.0.1' >/dev/null 2>&1 || true
sleep 2
echo "loaded after the kill: [$(loaded)]   (expect a PARTIAL evacuation)"

echo "  restarting the control plane..."
resid_up
echo "state after restart:"
curl -s -H "$T" http://127.0.0.1:18610/status | brief

echo
echo "=== 7. RELEASE recovers the interrupted claim ==="
curl -s -m 180 -X POST -H "$T" http://127.0.0.1:18610/release | brief
echo "loaded after recovery release: [$(loaded)]   (expect nemotron-120b,qwen35-a3b)"
