"""QAOA Grid Ops — Hybrid Quantum-Classical Grid Optimization.

Streamlit entrypoint. Runs on xr7620; the statevector runs on the Dell Pro Max
GB10 across VLAN 13. See BRIEF.md for the design and the claim this demonstrates.

Two pages — Command Center (operate) and Architecture (explain). The sidebar and
the backend probe live HERE, above the navigation, so both pages share one set of
controls and one view of the hardware rather than probing it twice.
"""

from __future__ import annotations

import streamlit as st

from src.lab.identity import current_viewer
from src.config.settings import (
    GridSpec, LAYERS_DEFAULT, LAYERS_MAX, LAYERS_MIN, ObjectiveWeights,
    QUBIT_DEFAULT, QUBIT_MAX, QUBIT_MIN, STEPS_DEFAULT, STEPS_MAX, STEPS_MIN,
)
from src.simulation.grid_model import build_grid
from src.simulation.experiments import record_from_run
from src.simulation.power_flow import calibrate_ratings, worst_contingency
from src.simulation.qaoa_engine import (
    run_islanding_optimization, run_signature, select_backend,
)
from src.ui import components as ui
from src.ui.views import architecture as architecture_view
from src.ui.views import command_center as command_center_view
from src.ui.views import experiments as experiments_view
from src.ui.views import how_it_works as how_it_works_view
from src.ui.views import limits as limits_view
from src.ui.views import notes as notes_view
from src.ui.views import residency as residency_view
from src.ui.views import sources as sources_view

st.set_page_config(
    page_title="QAOA Grid Ops — Hybrid Quantum-Classical Grid Optimization",
    page_icon="⚡", layout="wide", initial_sidebar_state="expanded",
)
st.markdown(ui.load_css(), unsafe_allow_html=True)

# Who is holding this session, per Caddy's post-forward-auth headers. Used ONLY
# to decide what to render — the app is lab-owner-only in Authentik, and the
# residency API re-checks the group itself. See src/lab/identity.py.
VIEWER = current_viewer()


@st.cache_data(ttl=20, show_spinner=False)
def _backend(pref: str) -> dict:
    """Probe the compute backend. Cached briefly so page switches stay snappy
    while still reflecting a claim/release within ~20s."""
    return select_backend(pref).to_dict()


# ── Shared sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Algorithm experiment")
    control_mode = st.radio("Control mode", ["Guided", "Advanced"], horizontal=True,
                            help="Guided presets change one meaningful design choice. "
                                 "Advanced exposes every parameter.")
    preset = "Improved algorithm"
    if control_mode == "Guided":
        preset = st.selectbox("Hypothesis", [
            "Baseline algorithm", "Under-trained circuit", "Operational surrogate experiment",
        ], index=0)
        preset_values = {
            "Baseline algorithm": (1, 20, 0.5, 2.0, 0.2, "analytic"),
            "Under-trained circuit": (1, 10, 0.5, 2.0, 0.2, "analytic"),
            "Operational surrogate experiment": (
                2, 30, 0.5, 2.0, 0.2, "operational-surrogate"),
        }
        layers, steps, w_flow, w_bal, w_size, formulation = preset_values[preset]
        hypothesis = {
            "Baseline algorithm": "Can a shallow, conventionally trained circuit concentrate useful plans?",
            "Under-trained circuit": "What happens when the classical outer loop has too little budget?",
            "Operational surrogate experiment": (
                "Can emulator-scored power-flow outcomes be compressed into a useful QUBO?"),
        }[preset]
        st.caption(hypothesis)

    st.markdown("## Contingency Parameters")
    n_nodes = st.slider("Substation nodes (qubits)", QUBIT_MIN, QUBIT_MAX, QUBIT_DEFAULT,
                        help="One qubit per substation. Search space is 2^n partitions.")
    if control_mode == "Advanced":
        layers = st.slider("QAOA circuit layers  p", LAYERS_MIN, LAYERS_MAX, LAYERS_DEFAULT,
                           help="Circuit depth. Deeper concentrates probability on better partitions.")
        steps = st.slider("Classical optimization steps", STEPS_MIN, STEPS_MAX, STEPS_DEFAULT,
                          help="Iterations of the classical outer loop over (γ, β).")

        st.markdown("## Objective Weights")
        w_flow = st.slider("Minimize interrupted flow", 0.0, 2.0, 0.5, 0.05)
        w_bal = st.slider("Island power balance", 0.0, 4.0, 2.0, 0.05)
        w_size = st.slider("Island size balance", 0.0, 1.0, 0.2, 0.05,
                           help="Prevents the degenerate 'one island' answer. "
                                "Lowering this wins more load but starts returning "
                                "electrically infeasible plans.")
        formulation = st.selectbox(
            "Objective formulation", ["analytic", "operational-surrogate"],
            format_func=lambda value: {
                "analytic": "Analytic 3-term QUBO",
                "operational-surrogate": "Emulator-fitted operational QUBO",
            }[value], help="The surrogate fits a quadratic model to power-flow-scored partitions.")
    else:
        st.caption(f"Preset: p={layers}, {steps} optimizer evaluations, "
                   f"weights {w_flow:.1f}/{w_bal:.1f}/{w_size:.1f}")

    st.markdown("## Contingency")
    fault_mode = st.radio(
        "Line fault", ["None — intact grid", "Trip the most critical line", "Choose a line"],
        index=1, help="The disturbance the islanding plan is responding to.")

    st.markdown("## Compute")
    pref = st.selectbox("Backend", ["gb10", "local", "auto"], index=0,
                        format_func=lambda x: {"gb10": "Dell Pro Max GB10 (cuStateVec)",
                                               "local": "This host", "auto": "Auto"}[x])
    seed = st.number_input("Grid seed", 1, 9999, 7, help="Deterministic topology.")
    run_clicked = st.button("ENGAGE SEQUENCE", width="stretch", type="primary")

    # Owner-only, and renders nothing at all for anyone else.
    residency_view.sidebar_panel(VIEWER)

spec = GridSpec(n_nodes=n_nodes, seed=int(seed), formulation=formulation,
                weights=ObjectiveWeights(flow=w_flow, balance=w_bal, size=w_size))

# Resolve the fault against THIS grid. Done here, above the navigation, so the
# selector can list real line names and both pages see the same contingency.
_grid = calibrate_ratings(build_grid(spec))
fault: list[tuple[int, int]] = []
if fault_mode == "Trip the most critical line":
    crit = worst_contingency(_grid)
    if crit:
        fault = [crit]
elif fault_mode == "Choose a line":
    opts = sorted(_grid.edges(), key=lambda e: -_grid.edges[e]["flow_mw"])
    with st.sidebar:
        pick = st.selectbox(
            "Line to trip", opts,
            format_func=lambda e: (f"{_grid.nodes[e[0]]['name']} ↔ {_grid.nodes[e[1]]['name']}"
                                   f"  ({_grid.edges[e]['flow_mw']:.0f} MW)"))
    fault = [tuple(pick)]

backend = _backend(pref)
state = "live" if backend["available"] else "down"
free_gb = backend["free_memory_bytes"] / 2**30 if backend["free_memory_bytes"] else 0
detail = (f"{backend['max_qubits']} qubit ceiling · {free_gb:.0f} GiB free"
          if backend["available"] else backend["detail"])
st.markdown(ui.header_html(backend["label"], state, detail), unsafe_allow_html=True)

if not backend["available"]:
    if VIEWER.is_owner:
        st.error(f"Compute backend unavailable — {backend['detail']}. "
                 "Claim the GB10 from **GB10 residency** in the sidebar (or "
                 "`tools/gb10-gpu claim` from xr7620), or switch Backend to "
                 "'This host'. Claiming evacuates the orchestrator's resident "
                 "models; release restores exactly that set.")
    else:
        st.error(f"Compute backend unavailable — {backend['detail']}. "
                 "The GB10 is not currently serving this demo. "
                 "Switch Backend to 'This host' to keep exploring.")

_sig = run_signature(spec, layers, steps, pref, fault)

if run_clicked:
    try:
        with st.spinner(f"Optimizing {n_nodes}-substation islanding on {backend['label']}…"):
            st.session_state["run"] = run_islanding_optimization(
                spec, layers=layers, steps=steps, backend_preference=pref,
                graph=_grid, fault=fault)
            st.session_state["run_sig"] = _sig
            history = st.session_state.setdefault("experiments", [])
            history.append(record_from_run(
                st.session_state["run"], spec, layers=layers, steps=steps,
                label=(preset if control_mode == "Guided"
                       else f"{n_nodes}q p={layers} · seed {int(seed)}"),
            ))
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    # Advance the scenario. Previously this button stored a run and left the
    # step where it was, so a demo driver pressed the big primary control and
    # watched nothing happen.
    st.session_state["demo_step"] = 2 if fault else 0
    st.rerun()


# ── Pages ────────────────────────────────────────────────────────────────────
# Five URL-addressable destinations rather than six tabs plus nested sub-tabs.
# Tabs cannot be linked to — you could not send someone "the wall" — and the
# thesis was buried two levels deep behind a label promising gate diagrams.
# Order follows the two real journeys: drive the demo, then ask "was that real?",
# then "why does this need this hardware?".
def _command_center() -> None:
    command_center_view.render(spec, backend, layers, pref, steps=steps,
                               grid=_grid, fault=fault, sig=_sig)


def _how_it_works() -> None:
    how_it_works_view.render(st.session_state.get("run"), n_nodes=n_nodes,
                             layers=layers, seed=int(seed), pref=pref)


def _experiments() -> None:
    experiments_view.render(st.session_state.get("experiments", []),
                            current_run=st.session_state.get("run"), pref=pref)


def _why_hardware() -> None:
    limits_view.render(st.session_state.get("run"), backend=backend,
                       layers=layers, pref=pref)


def _architecture() -> None:
    architecture_view.render(backend)


def _notes() -> None:
    notes_view.render()


def _sources() -> None:
    sources_view.render()


nav = st.navigation([
    st.Page(_command_center, title="Command Center", icon="⚡", default=True),
    st.Page(_experiments, title="Algorithm Lab", icon="🧪"),
    st.Page(_how_it_works, title="How it works", icon="⚛️"),
    st.Page(_why_hardware, title="Why it needs this hardware", icon="🧱"),
    st.Page(_architecture, title="Architecture", icon="🏗️"),
    st.Page(_notes, title="Technical notes", icon="📓"),
    st.Page(_sources, title="Sources", icon="📚"),
])
nav.run()
