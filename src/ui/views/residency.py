"""The GB10 residency panel — owner only, and only ever a FACE on the API.

Every button here is a call to gridops-residency, which re-checks `lab-owner`
itself from the identity this app forwards. Nothing in this file is a security
control: it exists so an operator can see the machine's state and act on it, and
so a non-owner is not shown a control that would be refused. If someone deletes
this whole file, the boundary is exactly as strong.

The long operations are honest about being long. An evacuation settles in
seconds; restoring a cold 120B has been measured at ~10 minutes. The API is
authoritative and its state is durable, so if the browser gives up mid-claim the
operation still finishes — reopen the page and read /status.
"""

from __future__ import annotations

import time

import streamlit as st

from src.lab import residency as api
from src.lab.identity import Viewer

_LEASES = {"1 hour": 3600, "4 hours": 14400, "8 hours": 28800, "24 hours": 86400}

_STATE_COPY = {
    "released":      ("✅", "Released — the orchestrator holds the GB10."),
    "claimed":       ("⚡", "Claimed — gridops-qsim holds the GB10."),
    "claiming":      ("⏳", "Claiming — evacuation in flight."),
    "releasing":     ("⏳", "Releasing — restoration in flight."),
    "needs_release": ("⚠️", "INTERRUPTED — an evacuation record is outstanding. "
                            "Release to restore the recorded models."),
    "degraded":      ("⚠️", "DEGRADED — the last release did not restore everything. "
                            "Release again to finish."),
}


def _render_state(data: dict) -> None:
    icon, copy = _STATE_COPY.get(data.get("state", ""), ("•", data.get("state", "unknown")))
    st.markdown(f"**{icon} {copy}**")

    if data.get("holder"):
        st.caption(f"Held by {data['holder']} ({data.get('principal')})")
    remaining = data.get("lease_remaining_seconds")
    if data.get("state") == "claimed" and remaining is not None:
        st.caption(f"Lease: {remaining // 60}m {remaining % 60}s left "
                   "— it auto-releases when this runs out.")
    if data.get("pre_claim_models"):
        st.caption("Restores on release: " + ", ".join(data["pre_claim_models"]))
    if data.get("pending_restore"):
        st.warning("Not yet restored: " + ", ".join(data["pending_restore"]))
    if data.get("last_error"):
        st.error(data["last_error"])

    observed = data.get("observed") or {}
    if observed:
        loaded = observed.get("loaded_models")
        if loaded is None:
            lanes = "orchestrator unreachable"
        elif loaded:
            lanes = ", ".join(loaded)
        else:
            lanes = "none"
        st.caption(f"Orchestrator: {lanes}")
        if observed.get("qsim_serving"):
            st.caption(f"qsim ceiling: {observed.get('qsim_max_qubits')} qubits")

    steps = data.get("progress") or []
    if steps:
        with st.expander("Progress log", expanded=False):
            for step in steps[-25:]:
                stamp = time.strftime("%H:%M:%S", time.localtime(step.get("t", 0)))
                detail = f" — {step['detail']}" if step.get("detail") else ""
                st.text(f"{stamp}  {step.get('status',''):<8} {step.get('step','')}{detail}")


def sidebar_panel(viewer: Viewer) -> None:
    """Owner-only. Renders nothing at all for anyone else."""
    if not viewer.is_owner:
        return

    st.markdown("## GB10 residency")
    if not api.configured():
        st.caption("No control-plane credential in this deployment — "
                   "use `tools/gb10-gpu` from xr7620.")
        return

    try:
        data = api.status(viewer)
    except api.ResidencyError as exc:
        st.warning(f"Residency control plane: {exc}")
        return

    _render_state(data)

    state = data.get("state")
    busy = state in ("claiming", "releasing")

    lease_label = st.selectbox("Lease", list(_LEASES), index=0, disabled=busy,
                               help="The claim auto-releases when the lease expires, so a "
                                    "demo that ends abruptly does not hold the lab's "
                                    "inference hostage.")

    st.caption("⚠ Claiming EVACUATES the orchestrator's resident models. LiteLLM stays "
               "up, but lanes backed by those GB10 processes cannot serve until release "
               "restores exactly that set.")

    left, right = st.columns(2)
    with left:
        claim_clicked = st.button("Claim", width="stretch", disabled=busy,
                                  type="primary" if state != "claimed" else "secondary")
    with right:
        release_clicked = st.button("Release", width="stretch", disabled=busy)

    if claim_clicked:
        _run("Claiming the GB10 — evacuating models, then starting qsim…",
             lambda: api.claim(viewer, _LEASES[lease_label], reason="command center"))
    if release_clicked:
        _run("Releasing the GB10 — stopping qsim, then restoring the recorded models…",
             lambda: api.release(viewer, reason="command center"))


def _run(spinner: str, call) -> None:
    try:
        with st.spinner(spinner):
            call()
    except api.ResidencyError as exc:
        st.error(str(exc))
        return
    # The backend probe is cached for 20s; drop it so the header reflects the
    # machine we just changed instead of the one we found.
    st.cache_data.clear()
    st.rerun()
