"""Who is holding this session, per the lab's forward-auth headers.

THE CONTRACT (see services/gb10_residency/README.md for the full version):
Caddy's `(authgate)` snippet STRIPS all twelve `X-Authentik-*` request headers
from the client, then REPLACES them from Authentik's forward-auth response.
Strip first, trust second — so on a request that came through Caddy, these
headers are Authentik's word, not the caller's.

WHERE THAT TRUST STOPS: 10.0.13.103:8501 is directly reachable on the DMZ. A
request that did not traverse Caddy carries whatever headers its sender chose.
That is why this module is NOT the security boundary and never claims to be:

  * the boundary for opening the app at all is the Authentik group binding
    (foundation/authentik/groups-and-policies.py — lab-owner only since
    2026-08-26);
  * the boundary for MUTATING GB10 residency is gridops-residency, which
    re-checks lab-owner itself against a service credential it holds.

This module exists so the UI does not offer an operator a control they cannot
use. Hiding a button is manners, not access control.

FAIL CLOSED, the same way the portal does: no header, an unparseable header, or
any doubt at all yields a non-owner.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

OWNER_GROUP = os.getenv("GRIDOPS_OWNER_GROUP", "lab-owner")

# Authentik has serialized the groups header with both "|" and "," across
# versions. Guessing one would silently demote the owner.
_SEP = re.compile(r"[|,\n]")


@dataclass(frozen=True)
class Viewer:
    user: str
    groups: tuple[str, ...]
    is_owner: bool
    behind_proxy: bool

    @property
    def label(self) -> str:
        if not self.behind_proxy:
            return "direct (no forward-auth headers)"
        return self.user or "authenticated"


def _headers() -> dict:
    """Streamlit's request headers, or {} when there is no request context.

    st.context.headers landed in Streamlit 1.37; the app pins >=1.30, and a
    local `streamlit run` has no proxy in front of it either way. Both cases
    must degrade to "not the owner", never to an exception on page load.
    """
    try:
        import streamlit as st

        return dict(st.context.headers or {})
    except Exception:
        return {}


def current_viewer() -> Viewer:
    headers = {k.lower(): v for k, v in _headers().items()}
    raw_groups = headers.get("x-authentik-groups", "")
    user = (headers.get("x-authentik-username") or "").strip()
    groups = tuple(g.strip() for g in _SEP.split(raw_groups) if g.strip())
    behind_proxy = bool(user or raw_groups)
    return Viewer(
        user=user,
        groups=groups,
        is_owner=OWNER_GROUP in groups,
        behind_proxy=behind_proxy,
    )
