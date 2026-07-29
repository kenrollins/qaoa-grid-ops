"""Grid Ops — Hybrid Quantum-Classical Grid Optimization.

Streamlit entrypoint. Runs on xr7620; the statevector runs on the Dell Pro Max
GB10 across VLAN 13. See BRIEF.md for the design and the claim this demonstrates.

Two pages — Command Center (operate) and Architecture (explain). The sidebar and
the backend probe live HERE, above the navigation, so both pages share one set of
controls and one view of the hardware rather than probing it twice.
"""

from __future__ import annotations

import streamlit as st

from src.config.settings import (
    GridSpec, LAYERS_DEFAULT, LAYERS_MAX, LAYERS_MIN, ObjectiveWeights,
    QUBIT_DEFAULT, QUBIT_MAX, QUBIT_MIN, STEPS_DEFAULT, STEPS_MAX, STEPS_MIN,
)
from src.simulation.qaoa_engine import run_islanding_optimization, select_backend
from src.ui import components as ui
from src.ui.views import architecture as architecture_view
from src.ui.views import command_center as command_center_view

st.set_page_config(
    page_title="Grid Ops — Hybrid Quantum-Classical Grid Optimization",
    page_icon="⚡", layout="wide", initial_sidebar_state="expanded",
)
st.markdown(ui.load_css(), unsafe_allow_html=True)


@st.cache_data(ttl=20, show_spinner=False)
def _backend(pref: str) -> dict:
    """Probe the compute backend. Cached briefly so page switches stay snappy
    while still reflecting a claim/release within ~20s."""
    return select_backend(pref).to_dict()


# ── Shared sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Contingency Parameters")
    n_nodes = st.slider("Substation nodes (qubits)", QUBIT_MIN, QUBIT_MAX, QUBIT_DEFAULT,
                        help="One qubit per substation. Search space is 2^n partitions.")
    layers = st.slider("QAOA circuit layers  p", LAYERS_MIN, LAYERS_MAX, LAYERS_DEFAULT,
                       help="Circuit depth. Deeper concentrates probability on better partitions.")
    steps = st.slider("Classical optimization steps", STEPS_MIN, STEPS_MAX, STEPS_DEFAULT,
                      help="Iterations of the classical outer loop over (γ, β).")

    st.markdown("## Objective Weights")
    w_flow = st.slider("Minimize interrupted flow", 0.0, 2.0, 1.0, 0.05)
    w_bal = st.slider("Island power balance", 0.0, 2.0, 1.0, 0.05)
    w_size = st.slider("Island size balance", 0.0, 1.0, 0.35, 0.05,
                       help="Prevents the degenerate 'one island' answer.")

    st.markdown("## Compute")
    pref = st.selectbox("Backend", ["gb10", "local", "auto"], index=0,
                        format_func=lambda x: {"gb10": "Dell Pro Max GB10 (cuStateVec)",
                                               "local": "This host", "auto": "Auto"}[x])
    seed = st.number_input("Grid seed", 1, 9999, 7, help="Deterministic topology.")
    run_clicked = st.button("🚀 Run Hybrid Optimization", width="stretch", type="primary")

spec = GridSpec(n_nodes=n_nodes, seed=int(seed),
                weights=ObjectiveWeights(flow=w_flow, balance=w_bal, size=w_size))

backend = _backend(pref)
state = "live" if backend["available"] else "down"
free_gb = backend["free_memory_bytes"] / 2**30 if backend["free_memory_bytes"] else 0
detail = (f"{backend['max_qubits']} qubit ceiling · {free_gb:.0f} GiB free"
          if backend["available"] else backend["detail"])
st.markdown(ui.header_html(backend["label"], state, detail), unsafe_allow_html=True)

if not backend["available"]:
    st.error(f"Compute backend unavailable — {backend['detail']}. "
             "Run `tools/gb10-gpu claim` to bring the GB10 up, "
             "or switch Backend to 'This host'.")

if run_clicked:
    with st.spinner(f"Optimizing {n_nodes}-substation islanding on {backend['label']}…"):
        st.session_state["run"] = run_islanding_optimization(
            spec, layers=layers, steps=steps, backend_preference=pref)


# ── Pages ────────────────────────────────────────────────────────────────────
def _command_center() -> None:
    command_center_view.render(spec, backend, layers, pref)


def _architecture() -> None:
    architecture_view.render(backend)


nav = st.navigation([
    st.Page(_command_center, title="Command Center", icon="⚡", default=True),
    st.Page(_architecture, title="Architecture", icon="🏗️"),
])
nav.run()
