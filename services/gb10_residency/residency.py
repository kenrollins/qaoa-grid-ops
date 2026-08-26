"""gridops-residency — the owner-only control plane for GB10 residency.

The GB10's 128 GiB is UNIFIED memory, shared by two tenants that speak different
protocols:

  * the **GB10 vLLM orchestrator** (:9000), whose models back `lab/*` and `pip/*`
    lanes on the LiteLLM gateway; and
  * **gridops-qsim** (:8600), a TYPED simulation API — optimize / evaluate /
    realism / health. It is NOT an OpenAI-compatible endpoint and must never be
    registered as a gateway model lane: routing it as an LLM would throw away
    every one of those verbs and buy no metering semantics in return.

They cannot both hold the pool. The integration point is therefore RESIDENCY,
not request routing, and this service is the one place that arbitrates it:

    claim   record the loaded model set -> unload it -> start qsim
    release stop qsim -> load back EXACTLY the recorded set

WHY THIS RUNS ON THE GB10
    Starting and stopping qsim is local process control. A control plane living
    off-box would need an SSH key into the GB10 held by a DMZ container, and a
    second network hop that can fail halfway through an evacuation. Here, the
    only thing that crosses the network is the *decision*.

WHY IT IS NOT A WEB PAGE
    It has no Caddy site block, no hostname, and no browser path. Nothing about
    it is public. See AUTHORIZATION below for what does reach it.

AUTHORIZATION — read this before changing a line of it
    Hiding the buttons in Streamlit is not access control. This service decides
    for itself, from two independent facts:

    1. A SERVICE CREDENTIAL (`Authorization: Bearer ...`) proving the caller is
       one of the two principals allowed to ask at all:
         * the APP token  — held by the qaoa-grid-ops container. On its own it
           grants NOTHING. It must arrive with a forwarded lab-owner identity.
         * the OPERATOR token — held by Ken on xr7620 for tools/gb10-gpu. It is
           self-authorizing, because possession of an operator secret on the
           operator's own host IS operator authority, the same way SSH is.

    2. A FORWARDED IDENTITY, for the app principal: `X-Gridops-Auth-User` and
       `X-Gridops-Auth-Groups`, which the Streamlit app copies VERBATIM from the
       `X-Authentik-Username` / `X-Authentik-Groups` headers Caddy handed it.
       `lab-owner` must be in that list.

    The headers are DELIBERATELY RENAMED rather than passed through as
    `X-Authentik-*`. This service does not sit behind Caddy, so an
    `X-Authentik-Groups` arriving here would be a header from an unauthenticated
    network peer — indistinguishable, by name alone, from one Caddy had stripped
    and replaced. Renaming makes the trust chain impossible to misread: these
    values are believable ONLY because the bearer token proves who forwarded
    them. See README.md for the full contract.

DURABILITY
    The evacuation record is written to disk, fsynced, BEFORE the first unload,
    and cleared only once every recorded model is loaded again. That ordering is
    the whole recovery story: a claim killed halfway through still leaves enough
    on disk for `release` to put the machine back exactly as it was. If there is
    no record, release does not guess.

NAMED `residency:app`, NOT `server:app`
    gridops-qsim is stopped with `pkill -f "uvicorn server:app ... --port 8600"`, and
    its own start.sh does the same before booting. If this service were also
    `server:app`, every qsim start or stop would kill the control plane driving
    it — mid-evacuation, with models unloaded. The module name is load-bearing.

Run:
    uvicorn residency:app --host 10.0.13.200 --port 8610
"""

from __future__ import annotations

import asyncio
import fcntl
import hmac
import ipaddress
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Configuration ────────────────────────────────────────────────────────────
ORCHESTRATOR_URL = os.getenv("GRIDOPS_ORCHESTRATOR_URL", "http://10.0.13.200:9000").rstrip("/")
QSIM_URL = os.getenv("GRIDOPS_QSIM_URL", "http://10.0.13.200:8600").rstrip("/")
QSIM_START = os.path.expanduser(
    os.getenv("GRIDOPS_QSIM_START", "~/gridops/services/gb10_qsim/start.sh"))
# Specific ON PURPOSE — see the module docstring. A bare "uvicorn server:app"
# also matches other uvicorn processes on this box.
QSIM_PORT = os.getenv("GRIDOPS_QSIM_PORT", "8600")
QSIM_PATTERN = os.getenv(
    "GRIDOPS_QSIM_PATTERN", f"uvicorn server:app --host 0.0.0.0 --port {QSIM_PORT}")

STATE_DIR = Path(os.path.expanduser(
    os.getenv("GRIDOPS_STATE_DIR", "~/.local/state/gridops-residency")))
STATE_FILE = STATE_DIR / "residency.json"
LOCK_FILE = STATE_DIR / "residency.lock"

OWNER_GROUP = os.getenv("GRIDOPS_OWNER_GROUP", "lab-owner")
APP_TOKEN = os.getenv("GRIDOPS_APP_TOKEN", "")
OPERATOR_TOKEN = os.getenv("GRIDOPS_OPERATOR_TOKEN", "")

LEASE_DEFAULT = int(os.getenv("GRIDOPS_LEASE_DEFAULT", "3600"))
LEASE_MAX = int(os.getenv("GRIDOPS_LEASE_MAX", "86400"))
LEASE_TICK = int(os.getenv("GRIDOPS_LEASE_TICK", "30"))

# Empty = no network restriction (the bearer token is still required). Set it in
# the env file to the callers that legitimately exist; see README.md.
ALLOW_RAW = os.getenv("GRIDOPS_ALLOW", "").strip()

# Long, because these really are long. A 120B unload settles in seconds but a
# cold load has been measured at ~10 minutes on this box.
HTTP_TIMEOUT = int(os.getenv("GRIDOPS_HTTP_TIMEOUT", "900"))
PROBE_TIMEOUT = 5
QSIM_BOOT_SECONDS = int(os.getenv("GRIDOPS_QSIM_BOOT_SECONDS", "90"))
PROGRESS_KEEP = 300

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await _reconcile_on_start()
    watchdog = asyncio.create_task(_lease_watchdog())
    try:
        yield
    finally:
        watchdog.cancel()


app = FastAPI(title="gridops-residency", version="1.0",
              docs_url=None, redoc_url=None, lifespan=_lifespan)


# ── Small helpers ────────────────────────────────────────────────────────────
def _now() -> float:
    return time.time()


def _allowed_networks() -> list[Any]:
    nets = []
    for token in ALLOW_RAW.replace(",", " ").split():
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            # A malformed entry must not silently widen the allowlist to
            # "everything", nor narrow it to nothing without saying so.
            print(f"gridops-residency: ignoring unparseable GRIDOPS_ALLOW entry {token!r}")
    return nets


ALLOW_NETS = _allowed_networks()


def _http_json(method: str, url: str, body: dict | None = None, timeout: int = HTTP_TIMEOUT):
    """One blocking JSON call. stdlib only, on purpose.

    This service shares the qsim venv, which carries CuPy and cuQuantum. Adding
    httpx/requests there to make four HTTP calls is not worth the dependency
    surface on a box whose Python environment is load-bearing for the GPU path.
    Callers run this off the event loop via asyncio.to_thread.
    """
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


async def _orchestrator_status() -> dict | None:
    try:
        return await asyncio.to_thread(
            _http_json, "GET", f"{ORCHESTRATOR_URL}/status", None, PROBE_TIMEOUT * 4)
    except Exception:
        return None


async def _loaded_models() -> list[str] | None:
    """Exactly the model_ids the orchestrator reports as loaded, in its own order."""
    status = await _orchestrator_status()
    if status is None:
        return None
    return [m["model_id"] for m in status.get("models", []) if m.get("loaded")]


async def _qsim_health() -> dict | None:
    try:
        return await asyncio.to_thread(
            _http_json, "GET", f"{QSIM_URL}/health", None, PROBE_TIMEOUT)
    except Exception:
        return None


# ── Durable state ────────────────────────────────────────────────────────────
# States:
#   released       nothing claimed; no evacuation record outstanding
#   claiming       an evacuation is in flight
#   claimed        qsim holds the machine; a lease is running
#   releasing      a restoration is in flight
#   needs_release  INTERRUPTED. An evacuation record exists and the machine is
#                  not in a claimed state. Release will finish the job; claim
#                  will resume it. This is the state that makes a half-finished
#                  operation recoverable instead of a mystery.
#   degraded       release ran but at least one recorded model did not come back.
#                  The record is KEPT so a retry can finish it.
EMPTY_STATE: dict[str, Any] = {
    "state": "released",
    "claim_id": None,
    "holder": None,
    "principal": None,
    "pre_claim_models": [],
    "pending_restore": [],
    "claimed_at": None,
    "lease_seconds": None,
    "lease_expires_at": None,
    "released_at": None,
    "released_by": None,
    "last_error": None,
    "progress": [],
    "updated_at": None,
}


def _read_state() -> dict[str, Any]:
    try:
        raw = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return dict(EMPTY_STATE)
    merged = dict(EMPTY_STATE)
    merged.update(raw)
    return merged


def _write_state(state: dict[str, Any]) -> None:
    """Atomic + fsynced. The evacuation record is the only thing standing between
    an interrupted claim and a machine nobody knows how to put back, so it is
    written the careful way: temp file, fsync the file, rename, fsync the dir."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, STATE_FILE)
    dirfd = os.open(STATE_DIR, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def _progress(state: dict[str, Any], step: str, status: str, detail: str = "") -> None:
    state["progress"].append({"t": _now(), "step": step, "status": status, "detail": detail})
    del state["progress"][:-PROGRESS_KEEP]


# ── Serialization ────────────────────────────────────────────────────────────
# Two layers, because they stop different things:
#   the asyncio.Lock serializes requests inside THIS process;
#   the flock stops a second process (a stray uvicorn, a hand-run copy) from
#   evacuating the machine at the same time. Only one may hold the GB10.
_op_lock = asyncio.Lock()
_busy: str | None = None


class _FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def __enter__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            self.fd = None
            raise HTTPException(
                409,
                "another gridops-residency process holds the GB10 operation lock",
            ) from exc
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
        return False


# ── Authorization ────────────────────────────────────────────────────────────
def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _match_token(presented: str) -> str | None:
    """Which principal, if any. Constant-time so a wrong token leaks no prefix."""
    if presented and OPERATOR_TOKEN and hmac.compare_digest(presented, OPERATOR_TOKEN):
        return "operator"
    if presented and APP_TOKEN and hmac.compare_digest(presented, APP_TOKEN):
        return "app"
    return None


def _groups(request: Request) -> list[str]:
    """Separator-agnostic, matching the portal: Authentik has serialized this
    header with both '|' and ',' across versions, and guessing wrong would
    silently demote the owner."""
    raw = request.headers.get("X-Gridops-Auth-Groups", "")
    out: list[str] = []
    for part in raw.replace("|", ",").replace("\n", ",").split(","):
        part = part.strip()
        if part:
            out.append(part)
    return out


def _reject_browsers(request: Request) -> None:
    """This API has no browser story. A browser announces itself: every modern
    engine attaches Sec-Fetch-* to fetch, XHR and navigation alike, and sends
    Origin on anything cross-origin. Refuse those outright and emit no CORS
    headers anywhere, so a page that somehow reaches this port can neither
    navigate to it nor read a response from it."""
    if request.headers.get("Sec-Fetch-Mode") or request.headers.get("Sec-Fetch-Site"):
        raise HTTPException(403, "gridops-residency is not browser-reachable")
    if request.headers.get("Origin"):
        raise HTTPException(403, "gridops-residency is not browser-reachable")


def _check_network(request: Request) -> None:
    if not ALLOW_NETS:
        return
    peer = request.client.host if request.client else ""
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError as exc:
        raise HTTPException(403, "caller address not recognised") from exc
    if not any(addr in net for net in ALLOW_NETS):
        raise HTTPException(403, "caller address is not on the residency allowlist")


def authorize(request: Request) -> dict[str, str]:
    """Every non-/health endpoint goes through here, /status included.

    /status is non-mutating but it still reports the lab's inference residency,
    so it is owner-only too. 'Read-only' is not the same as 'public'.
    """
    _reject_browsers(request)
    _check_network(request)

    if not APP_TOKEN and not OPERATOR_TOKEN:
        # FAIL CLOSED. An unconfigured service must refuse everyone rather than
        # quietly serve the GB10's residency controls to the whole DMZ.
        raise HTTPException(
            503, "gridops-residency has no credentials configured; refusing all callers")

    principal = _match_token(_bearer(request))
    if principal is None:
        raise HTTPException(401, "a valid service credential is required")

    if principal == "operator":
        # Self-authorizing, and say so in the record rather than inventing a name.
        who = request.headers.get("X-Gridops-Auth-User", "").strip() or "operator"
        return {"principal": "operator", "user": who, "groups": [OWNER_GROUP]}

    # The app principal carries no authority of its own — it forwards Ken's.
    groups = _groups(request)
    user = request.headers.get("X-Gridops-Auth-User", "").strip()
    if OWNER_GROUP not in groups:
        raise HTTPException(
            403,
            f"forwarded identity is not in {OWNER_GROUP}; "
            "GB10 residency is an owner-only control")
    if not user:
        raise HTTPException(403, "forwarded identity carries no username")
    return {"principal": "app", "user": user, "groups": groups}


# ── The operations ───────────────────────────────────────────────────────────
async def _stop_qsim() -> None:
    await asyncio.to_thread(
        subprocess.run, ["pkill", "-f", QSIM_PATTERN], check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Observable truth over a possibly-stale PID: it is stopped when it stops
    # answering, not when a signal was delivered.
    for _ in range(15):
        if await _qsim_health() is None:
            return
        await asyncio.sleep(1)
    raise RuntimeError("gridops-qsim is still answering after pkill")


async def _start_qsim() -> dict:
    await asyncio.to_thread(
        subprocess.run, ["/bin/bash", QSIM_START], check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=QSIM_BOOT_SECONDS + 30)
    deadline = _now() + QSIM_BOOT_SECONDS
    while _now() < deadline:
        health = await _qsim_health()
        if health and health.get("ok"):
            return health
        await asyncio.sleep(2)
    raise RuntimeError(
        f"gridops-qsim did not become healthy within {QSIM_BOOT_SECONDS}s "
        f"(check: ssh gb10 'tail -40 ~/gridops/qsim.log')")


async def _unload(model_id: str) -> None:
    await asyncio.to_thread(
        _http_json, "POST", f"{ORCHESTRATOR_URL}/unload", {"model_id": model_id})


async def _load(model_id: str) -> None:
    await asyncio.to_thread(
        _http_json, "POST", f"{ORCHESTRATOR_URL}/load", {"model_id": model_id})


async def _do_claim(state: dict[str, Any]) -> None:
    """Evacuate the orchestrator, then start qsim.

    Ordering is deliberate and not negotiable: the evacuation record hits the
    disk BEFORE the first unload. Reverse them and a crash between the two
    leaves a model unloaded with nothing on disk saying it should come back.
    """
    # THE safety property: never overwrite an existing evacuation record. If one
    # is on disk, a previous claim got far enough to change the machine, and the
    # models now loaded are NOT what should be restored — re-recording here would
    # replace the truth with an empty list and strand them permanently.
    resuming = bool(state.get("pre_claim_models"))

    if not resuming:
        loaded = await _loaded_models()
        if loaded is None:
            raise RuntimeError(
                f"the GB10 orchestrator is not answering at {ORCHESTRATOR_URL} — "
                "refusing to claim a machine whose residency cannot be read")
        state["pre_claim_models"] = loaded
        state["pending_restore"] = list(loaded)
        _progress(state, "record-residency", "ok",
                  f"recorded {len(loaded)} loaded model(s): {', '.join(loaded) or 'none'}")
        _write_state(state)          # <- durable BEFORE anything is touched
    else:
        _progress(state, "record-residency", "ok",
                  "resuming an interrupted claim; keeping the existing record: "
                  + (", ".join(state["pre_claim_models"]) or "none"))

    for model_id in list(state["pre_claim_models"]):
        still_loaded = await _loaded_models()
        if still_loaded is not None and model_id not in still_loaded:
            _progress(state, f"unload:{model_id}", "skipped", "already unloaded")
            continue
        _progress(state, f"unload:{model_id}", "running",
                  "its LiteLLM lane is unavailable from here until release")
        _write_state(state)
        await _unload(model_id)
        _progress(state, f"unload:{model_id}", "ok", "")
        _write_state(state)

    _progress(state, "start-qsim", "running", "")
    _write_state(state)
    health = await _start_qsim()
    _progress(state, "start-qsim", "ok",
              f"ceiling {health.get('max_qubits')} qubits, "
              f"{health.get('free_memory_bytes', 0) / 2**30:.1f} GiB free")

    state["state"] = "claimed"
    state["last_error"] = None
    _write_state(state)


async def _do_release(state: dict[str, Any], released_by: str) -> None:
    """Stop qsim, then load back EXACTLY what was recorded — no more, no less."""
    if await _qsim_health() is not None:
        _progress(state, "stop-qsim", "running", "")
        _write_state(state)
        await _stop_qsim()
        _progress(state, "stop-qsim", "ok", "")
    else:
        _progress(state, "stop-qsim", "skipped", "not serving")
    _write_state(state)

    record = list(state.get("pre_claim_models") or [])
    if not record:
        # The one thing this service will never do is invent a residency.
        _progress(state, "restore", "skipped",
                  "no evacuation record — not guessing which models should be loaded")
        state["state"] = "released"
        state["pending_restore"] = []
    else:
        loaded_now = await _loaded_models()
        failed: list[str] = []
        for model_id in record:
            if loaded_now is not None and model_id in loaded_now:
                _progress(state, f"load:{model_id}", "skipped", "already loaded")
                continue
            _progress(state, f"load:{model_id}", "running", "")
            _write_state(state)
            try:
                await _load(model_id)
            except Exception as exc:
                failed.append(model_id)
                _progress(state, f"load:{model_id}", "fail", f"{type(exc).__name__}: {exc}")
            else:
                _progress(state, f"load:{model_id}", "ok", "")
            _write_state(state)

        final = await _loaded_models()
        missing = [m for m in record if final is not None and m not in final] or failed
        if missing:
            # Keep the record. A retry of /release finishes the job; clearing it
            # here would strand the models with nothing left saying they belong.
            state["pending_restore"] = missing
            state["state"] = "degraded"
            state["last_error"] = "did not restore: " + ", ".join(missing)
            _progress(state, "restore", "fail", state["last_error"])
        else:
            state["pending_restore"] = []
            state["pre_claim_models"] = []
            state["state"] = "released"
            _progress(state, "restore", "ok",
                      "restored exactly the pre-claim set: " + (", ".join(record) or "none"))

    state["released_at"] = _now()
    state["released_by"] = released_by
    state["claim_id"] = None
    state["lease_expires_at"] = None
    _write_state(state)


async def _run_operation(kind: str, state: dict[str, Any], released_by: str = "") -> dict:
    global _busy
    try:
        if kind == "claim":
            await _do_claim(state)
        else:
            await _do_release(state, released_by)
    except HTTPException:
        raise
    except Exception as exc:
        state["last_error"] = f"{type(exc).__name__}: {exc}"
        # An interrupted operation with a record outstanding is `needs_release`,
        # never `released`: it names the work left to do.
        state["state"] = "needs_release" if state.get("pre_claim_models") else "released"
        _progress(state, kind, "fail", state["last_error"])
        _write_state(state)
    finally:
        _busy = None
    return state


# ── API ──────────────────────────────────────────────────────────────────────
class ClaimRequest(BaseModel):
    lease_seconds: int = Field(default=LEASE_DEFAULT, ge=60, le=LEASE_MAX)
    reason: str = Field(default="", max_length=200)


class ReleaseRequest(BaseModel):
    reason: str = Field(default="", max_length=200)


def _public(state: dict[str, Any], extra: dict | None = None) -> dict:
    out = {k: v for k, v in state.items() if k != "progress"}
    out["progress"] = state["progress"][-40:]
    out["busy"] = _busy
    if state.get("lease_expires_at"):
        out["lease_remaining_seconds"] = max(0, int(state["lease_expires_at"] - _now()))
    if extra:
        out.update(extra)
    return out


@app.get("/health")
async def health():
    """Liveness only — deliberately says nothing about the lab. systemd and any
    future probe need this without a credential; it must therefore leak nothing."""
    return {"status": "ok", "service": "gridops-residency"}


@app.get("/status")
async def status(request: Request):
    """Non-mutating, always. It reads; it never claims, releases, loads,
    unloads, starts or stops anything — including as a side effect of
    reconciliation, which happens only at startup and on an explicit operation."""
    authorize(request)
    state = _read_state()
    orch = await _orchestrator_status()
    qsim = await _qsim_health()
    return _public(state, {
        "observed": {
            "orchestrator_reachable": orch is not None,
            "loaded_models": ([m["model_id"] for m in orch.get("models", []) if m.get("loaded")]
                              if orch else None),
            "qsim_serving": bool(qsim and qsim.get("ok")),
            "qsim_max_qubits": (qsim or {}).get("max_qubits"),
        },
        "endpoints": {"orchestrator": ORCHESTRATOR_URL, "qsim": QSIM_URL},
    })


@app.post("/claim")
async def claim(request: Request, body: ClaimRequest | None = None):
    """Take the GB10 for Grid Ops. Idempotent.

    Already claimed -> 200, no work done, lease renewed.
    Interrupted     -> resumes from the existing evacuation record.
    """
    who = authorize(request)
    body = body or ClaimRequest()
    global _busy

    if _op_lock.locked():
        raise HTTPException(409, f"a {_busy or 'residency'} operation is already running")

    async with _op_lock:
        with _FileLock(LOCK_FILE):
            state = _read_state()

            if state["state"] == "claimed":
                qsim = await _qsim_health()
                if qsim and qsim.get("ok"):
                    state["lease_seconds"] = body.lease_seconds
                    state["lease_expires_at"] = _now() + body.lease_seconds
                    _progress(state, "claim", "noop",
                              f"already claimed by {state.get('holder')}; lease renewed "
                              f"to {body.lease_seconds}s by {who['user']}")
                    _write_state(state)
                    return JSONResponse(_public(state, {"changed": False}), status_code=200)
                # The record says claimed, the machine disagrees. Trust the machine.
                _progress(state, "claim", "reconcile",
                          "state said claimed but qsim is not serving; resuming the claim")
                state["state"] = "claiming"

            if state["state"] in ("releasing", "claiming"):
                raise HTTPException(409, f"a {state['state']} operation is in flight")

            if state["state"] == "degraded":
                raise HTTPException(
                    409,
                    "the previous release did not restore " +
                    ", ".join(state.get("pending_restore") or []) +
                    " — retry POST /release before claiming again")

            _busy = "claim"
            state["state"] = "claiming"
            state["claim_id"] = secrets.token_hex(8)
            state["holder"] = who["user"]
            state["principal"] = who["principal"]
            state["claimed_at"] = _now()
            state["lease_seconds"] = body.lease_seconds
            state["lease_expires_at"] = _now() + body.lease_seconds
            state["released_at"] = None
            state["released_by"] = None
            state["last_error"] = None
            _progress(state, "claim", "start",
                      f"{who['principal']}:{who['user']}"
                      + (f" — {body.reason}" if body.reason else ""))
            _write_state(state)

            state = await _run_operation("claim", state)
            code = 200 if state["state"] == "claimed" else 500
            return JSONResponse(_public(state, {"changed": True}), status_code=code)


@app.post("/release")
async def release(request: Request, body: ReleaseRequest | None = None):
    """Give the GB10 back. Idempotent, and the recovery path for an interrupted
    claim: it restores exactly the recorded set, whatever state got us here."""
    who = authorize(request)
    body = body or ReleaseRequest()
    global _busy

    if _op_lock.locked():
        raise HTTPException(409, f"a {_busy or 'residency'} operation is already running")

    async with _op_lock:
        with _FileLock(LOCK_FILE):
            state = _read_state()

            if state["state"] == "released" and not state.get("pre_claim_models"):
                qsim = await _qsim_health()
                if not (qsim and qsim.get("ok")):
                    _progress(state, "release", "noop", f"already released ({who['user']})")
                    _write_state(state)
                    return JSONResponse(_public(state, {"changed": False}), status_code=200)
                # Nothing on record, but qsim is up — someone started it by hand.
                # Stopping it is still the right answer; there is just nothing to
                # restore, and the log will say so.
                _progress(state, "release", "reconcile",
                          "no claim on record but qsim is serving; stopping it anyway")

            if state["state"] == "claiming":
                raise HTTPException(
                    409, "a claim is in flight; wait for it to settle, then release")

            _busy = "release"
            state["state"] = "releasing"
            _progress(state, "release", "start",
                      f"{who['principal']}:{who['user']}"
                      + (f" — {body.reason}" if body.reason else ""))
            _write_state(state)

            state = await _run_operation("release", state, released_by=who["user"])
            code = 200 if state["state"] == "released" else 500
            return JSONResponse(_public(state, {"changed": True}), status_code=code)


# ── Startup reconciliation + the lease watchdog ──────────────────────────────
async def _reconcile_on_start():
    """A restart must never silently mutate the GB10 — but it must not lie about
    the state either. Observe, record what is actually true, and leave the
    machine alone. If a claim died mid-flight, the state becomes `needs_release`,
    which names the outstanding work without performing it unasked."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = _read_state()
    was = state["state"]
    qsim = await _qsim_health()
    serving = bool(qsim and qsim.get("ok"))

    if was in ("claiming", "releasing"):
        if serving and was == "claiming":
            state["state"] = "claimed"
            if not state.get("lease_expires_at"):
                state["lease_seconds"] = LEASE_DEFAULT
                state["lease_expires_at"] = _now() + LEASE_DEFAULT
            _progress(state, "recover", "ok",
                      f"restarted mid-{was}; qsim is serving, so the claim stands")
        elif state.get("pre_claim_models"):
            state["state"] = "needs_release"
            _progress(state, "recover", "attention",
                      f"restarted mid-{was} with an outstanding evacuation record "
                      f"({', '.join(state['pre_claim_models'])}); POST /release to restore")
        else:
            state["state"] = "released"
            _progress(state, "recover", "ok", f"restarted mid-{was}; nothing outstanding")
        _write_state(state)
    elif was == "claimed" and not serving and state.get("pre_claim_models"):
        state["state"] = "needs_release"
        _progress(state, "recover", "attention",
                  "state said claimed but qsim is not serving; "
                  "POST /release to restore the recorded models")
        _write_state(state)


async def _lease_watchdog():
    """Automatic release on lease expiry. A demo that ends when someone closes a
    laptop must not hold the lab's inference hostage until Ken notices."""
    while True:
        await asyncio.sleep(LEASE_TICK)
        try:
            state = _read_state()
            if state["state"] != "claimed":
                continue
            expires = state.get("lease_expires_at")
            if not expires or _now() < expires:
                continue
            if _op_lock.locked():
                continue
            global _busy
            async with _op_lock:
                with _FileLock(LOCK_FILE):
                    state = _read_state()
                    if state["state"] != "claimed":
                        continue
                    if not state.get("lease_expires_at") or _now() < state["lease_expires_at"]:
                        continue
                    _busy = "release"
                    state["state"] = "releasing"
                    _progress(state, "lease-expiry", "start",
                              f"lease of {state.get('lease_seconds')}s held by "
                              f"{state.get('holder')} expired; releasing automatically")
                    _write_state(state)
                    await _run_operation("release", state, released_by="lease-expiry")
        except Exception as exc:  # a watchdog that can die is not a watchdog
            print(f"gridops-residency: lease watchdog error: {type(exc).__name__}: {exc}")
