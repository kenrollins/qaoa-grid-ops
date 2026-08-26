"""Client for gridops-residency — the owner-only GB10 residency control plane.

This module FORWARDS Ken's identity; it does not assert it. The app's token
(GRIDOPS_APP_TOKEN) grants nothing on its own — the service requires it to
arrive alongside a `lab-owner` identity copied verbatim from the headers Caddy
handed us. If the app is compromised, it can still only act as whoever is
actually signed in.

The headers are deliberately RENAMED on the way out (X-Gridops-Auth-*, not
X-Authentik-*): the residency service does not sit behind Caddy, so an
X-Authentik-* header arriving there would come from an unauthenticated network
peer and must be indistinguishable-by-name from nothing at all.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from src.lab.identity import Viewer

RESIDENCY_URL = os.getenv("GRIDOPS_RESIDENCY_URL", "http://10.0.13.200:8610").rstrip("/")
APP_TOKEN = os.getenv("GRIDOPS_APP_TOKEN", "")
# A claim can take minutes: unloading a 120B, then booting cuStateVec.
TIMEOUT = int(os.getenv("GRIDOPS_RESIDENCY_TIMEOUT", "900"))
STATUS_TIMEOUT = int(os.getenv("GRIDOPS_RESIDENCY_STATUS_TIMEOUT", "15"))


class ResidencyError(RuntimeError):
    """A refusal or failure worth showing the operator verbatim."""


def configured() -> bool:
    return bool(APP_TOKEN)


def _call(method: str, path: str, viewer: Viewer,
          body: dict | None = None, timeout: int | None = None) -> dict[str, Any]:
    if not APP_TOKEN:
        raise ResidencyError(
            "This deployment has no GRIDOPS_APP_TOKEN, so it cannot reach the "
            "residency control plane. Use tools/gb10-gpu from xr7620.")
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {APP_TOKEN}",
        # Forwarded verbatim from Caddy's post-forward-auth headers. The service
        # checks lab-owner against these itself.
        "X-Gridops-Auth-User": viewer.user,
        "X-Gridops-Auth-Groups": ",".join(viewer.groups),
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{RESIDENCY_URL}{path}", data=data,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        # The service explains its refusals; show that, not "HTTP Error 409".
        try:
            detail = json.loads(exc.read()).get("detail")
        except Exception:
            detail = None
        raise ResidencyError(f"{exc.code} — {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ResidencyError(
            f"cannot reach the residency control plane at {RESIDENCY_URL}: {exc.reason}") from exc


def status(viewer: Viewer) -> dict[str, Any]:
    """Non-mutating. Safe to poll."""
    return _call("GET", "/status", viewer, timeout=STATUS_TIMEOUT)


def claim(viewer: Viewer, lease_seconds: int = 3600, reason: str = "") -> dict[str, Any]:
    return _call("POST", "/claim", viewer,
                 {"lease_seconds": int(lease_seconds), "reason": reason})


def release(viewer: Viewer, reason: str = "") -> dict[str, Any]:
    return _call("POST", "/release", viewer, {"reason": reason})
