"""Grid Ops — Hybrid Quantum-Classical Grid Optimization.

Streamlit entrypoint. Runs on xr7620; the statevector runs on the Dell Pro Max
GB10 across VLAN 13. See BRIEF.md for the design and the claim this demonstrates.
"""

from __future__ import annotations

import streamlit as st

from src.config.settings import (
    COLORS, GridSpec, LAYERS_DEFAULT, LAYERS_MAX, LAYERS_MIN, ObjectiveWeights,
    QUBIT_DEFAULT, QUBIT_MAX, QUBIT_MIN, STEPS_DEFAULT, STEPS_MAX, STEPS_MIN,
)
from src.simulation.qaoa_engine import (
    run_islanding_optimization, scaling_probe, select_backend,
)
from src.ui import components as ui

st.set_page_config(
    page_title="Grid Ops — Hybrid Quantum-Classical Grid Optimization",
    page_icon="⚡", layout="wide", initial_sidebar_state="expanded",
)
st.markdown(ui.load_css(), unsafe_allow_html=True)


@st.cache_data(ttl=20, show_spinner=False)
def _backend(pref: str):
    return select_backend(pref).to_dict()


# ── Sidebar ──────────────────────────────────────────────────────────────────
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

b = _backend(pref)
state = "live" if b["available"] else "down"
free_gb = b["free_memory_bytes"] / 2**30 if b["free_memory_bytes"] else 0
detail = (f"{b['max_qubits']} qubit ceiling · {free_gb:.0f} GiB free"
          if b["available"] else b["detail"])
st.markdown(ui.header_html(b["label"], state, detail), unsafe_allow_html=True)

if not b["available"]:
    st.error(f"Compute backend unavailable — {b['detail']}. "
             "Start gridops-qsim on the GB10, or switch Backend to 'This host'.")

if run_clicked:
    with st.spinner(f"Optimizing {n_nodes}-substation islanding on {b['label']}…"):
        st.session_state["run"] = run_islanding_optimization(
            spec, layers=layers, steps=steps, backend_preference=pref)

run = st.session_state.get("run")

tab1, tab2, tab3, tab4 = st.tabs([
    "🗺️  Grid Topology & Microgrid Islanding",
    "📊  Simulation Capability",
    "🔬  Under the Hood: Circuit & Qubit Operations",
    "🏗️  Technology Stack Architecture",
])

# ── Tab 1 ────────────────────────────────────────────────────────────────────
with tab1:
    if run is None:
        st.info("Set the contingency parameters and press **🚀 Run Hybrid Optimization**.")
        st.plotly_chart(ui.topology_figure(__import__(
            "src.simulation.grid_model", fromlist=["build_grid"]).build_grid(spec)),
            width="stretch")
    else:
        r, res = run.report, run.result
        for w in run.warnings:
            st.warning(w)

        c = st.columns(4)
        c[0].markdown(ui.metric_html(
            "Interrupted flow", f"{r.interrupted_mw:,.0f}", "MW",
            f"{len(r.severed_lines)} lines severed"), unsafe_allow_html=True)
        c[1].markdown(ui.metric_html(
            "Island A / B", f"{len(r.island_a)} / {len(r.island_b)}", "nodes",
            f"net {r.imbalance_a_mw:+,.0f} / {r.imbalance_b_mw:+,.0f} MW"),
            unsafe_allow_html=True)
        c[2].markdown(ui.metric_html(
            "Solve time", f"{res.get('seconds', 0):.2f}", "s",
            f"{res.get('steps_run')} steps · {res.get('backend')}"), unsafe_allow_html=True)
        c[3].markdown(ui.metric_html(
            "Plan status", "FEASIBLE" if r.feasible else "INFEASIBLE", "",
            "; ".join(r.notes) if r.notes else "generation + contiguity verified",
            kind="ok" if r.feasible else "crit"), unsafe_allow_html=True)

        st.plotly_chart(ui.topology_figure(run.graph, r), width="stretch")

        left, right = st.columns([3, 2])
        with left:
            st.plotly_chart(
                ui.convergence_figure(run.energy_history,
                                      run.exact["energy"] if run.exact else None),
                width="stretch")
        with right:
            if run.exact:
                verdict = ("matches the exact optimum" if run.is_optimal
                           else "did not reach the exact optimum")
                st.markdown(ui.card_html("Verification", f"""
<p>Brute force over all <strong>{2 ** run.model.n_qubits:,}</strong> partitions was
computed for comparison. QAOA's returned plan <strong>{verdict}</strong>.</p>
<p>Solution ratio <strong>{run.solution_ratio:.3f}</strong> · expectation ratio
<strong>{run.expectation_ratio:.3f}</strong> · concentration
<strong>{run.concentration:.1f}x</strong> uniform.</p>
<p>The two ratios differ because ⟨H⟩ averages the whole measurement
distribution, while the operator receives the single best partition.</p>"""),
                    unsafe_allow_html=True)
            else:
                st.markdown(ui.card_html("Verification", f"""
<p>At {run.model.n_qubits} qubits the exact optimum is not brute-forced
({2 ** run.model.n_qubits:,} partitions), so optimality is
<strong>not claimed</strong> here.</p>
<p>Concentration <strong>{(run.concentration or 0):.1f}x</strong> over a uniform
guess is the evidence the circuit is doing work.</p>"""), unsafe_allow_html=True)

        st.download_button(
            "⬇  Download islanding schedule (JSON)",
            ui.partition_report_json(run),
            file_name=f"islanding-schedule-{run.model.n_qubits}q.json",
            mime="application/json")

# ── Tab 2 ────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown(ui.card_html("The capability claim", f"""
<p>The Dell Pro Max GB10 is the <strong>entry point</strong> of this hardware class,
and it is the floor of the claim, not the ceiling: <strong>{b['max_qubits']} qubits</strong>
of dense all-to-all QAOA right now, bounded by unified memory
({free_gb:.0f} GiB free of {b['total_memory_bytes'] / 2**30:.0f} GiB).
Larger GPU configurations move that number up.</p>
<p>The binding constraint is <strong>memory, not speed</strong>. A complex128 statevector
costs 16 bytes per amplitude and doubles per qubit; the working set here is ~1.6x that,
covering the cost diagonal and tiled scratch. This chart is not a speedup ratio against
other hardware — it is how large a problem this machine holds, and how long one energy
evaluation takes at each size.</p>"""), unsafe_allow_html=True)

    if st.button("🔥  Run Live Capability Sweep", type="primary"):
        ns = [n for n in [8, 12, 16, 20, 22, 24, 26] if n <= max(b["max_qubits"], 8)]
        with st.spinner(f"Sweeping {len(ns)} problem sizes on {b['label']}…"):
            st.session_state["sweep"] = scaling_probe(ns, layers=layers, backend_preference=pref)

    sweep = st.session_state.get("sweep")
    if sweep:
        st.plotly_chart(ui.scaling_figure(sweep, ceiling=b["max_qubits"]),
                        width="stretch")
        import pandas as pd

        st.dataframe(pd.DataFrame([{
            "Qubits": r["n_qubits"],
            "Partitions": f"{2 ** r['n_qubits']:,}",
            "Statevector": f"{r['statevector_bytes'] / 2**20:,.1f} MiB",
            "Working set": f"{r['working_set_bytes'] / 2**20:,.1f} MiB",
            "Time / evaluation": (f"{r['seconds']:.3f} s" if r.get("seconds") else "—"),
            "Status": r["status"],
        } for r in sweep]), width="stretch", hide_index=True)

    st.plotly_chart(ui.memory_figure(ceiling_bytes=b["free_memory_bytes"]),
                    width="stretch")

# ── Tab 3 ────────────────────────────────────────────────────────────────────
with tab3:
    n = run.model.n_qubits if run else n_nodes
    nc = run.model.n_terms if run else 0
    st.markdown(f'<div class="circuit">{ui.circuit_ascii(n, layers, nc or n * (n - 1) // 2)}</div>',
                unsafe_allow_html=True)
    st.markdown("")

    if run:
        st.plotly_chart(ui.probability_figure(run.result.get("top_states", []), n),
                        width="stretch")
        params = run.result.get("best_params", [])
        p = run.result.get("layers", layers)
        cols = st.columns(2)
        cols[0].markdown(ui.card_html("Optimized cost angles γ", "".join(
            f"<p>γ<sub>{i+1}</sub> = <strong>{v:.4f}</strong></p>"
            for i, v in enumerate(params[:p]))), unsafe_allow_html=True)
        cols[1].markdown(ui.card_html("Optimized mixer angles β", "".join(
            f"<p>β<sub>{i+1}</sub> = <strong>{v:.4f}</strong></p>"
            for i, v in enumerate(params[p:]))), unsafe_allow_html=True)
        st.markdown(ui.card_html("Simulation note", """
<p>The cost Hamiltonian is diagonal in the computational basis, so
exp(-iγH<sub>C</sub>) is applied as a single elementwise phase multiply rather than
as thousands of individual RZZ gates. This is an <strong>optimization, not an
approximation</strong>: applying every RZZ separately produces an identical state to
within 1e-16, which the GB10 service will verify on request via
<code>POST /qaoa/verify</code>.</p>"""), unsafe_allow_html=True)
    else:
        st.info("Run an optimization to populate the measured statevector distribution.")

# ── Tab 4 ────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown(f"""
<div class="layer"><div class="tier">Layer 1 — Interface & Orchestration</div>
<div class="name">Operations Command Center</div>
<div class="desc">Contingency parameters, topology visualization, convergence telemetry,
and the exportable islanding schedule. Runs on classical infrastructure; holds no
quantum state.</div><div class="tech">Streamlit · Plotly · xr7620</div></div>

<div class="layer"><div class="tier">Layer 2 — Quantum Formulation</div>
<div class="name">QUBO / Ising Model + QAOA Ansatz</div>
<div class="desc">Substation topology, generation and load become a quadratic
unconstrained binary optimization: minimize interrupted flow, hold each island
power-balanced, forbid the degenerate partition. Encoded as an Ising Hamiltonian and
solved with the Quantum Approximate Optimization Algorithm.</div>
<div class="tech">NumPy · NetworkX · SciPy COBYLA outer loop</div></div>

<div class="layer"><div class="tier">Layer 3 — Hardware Acceleration</div>
<div class="name">NVIDIA cuQuantum · cuStateVec</div>
<div class="desc">Dense statevector evolution over 2<sup>n</sup> amplitudes. In NISQ-era
hybrid algorithms the overwhelming majority of wall-clock is classical — parameter
optimization, circuit evolution, and expectation evaluation — which is precisely the
work this layer absorbs.</div>
<div class="tech">cuquantum-python-cu12 · CuPy · CUDA 12</div></div>

<div class="layer hw"><div class="tier">Layer 4 — Dell Infrastructure Backbone</div>
<div class="name">Dell Pro Max with GB10 — Grace Blackwell</div>
<div class="desc">{b['total_memory_bytes'] / 2**30:.0f} GiB of unified memory, compute
capability {b.get('compute_capability', '12.1')}, on-premise and air-gappable. Unified
memory is the binding resource for statevector simulation, and it is why this desktop-class
system carries <strong>{b['max_qubits']} qubits</strong> of dense all-to-all QAOA. Grid
topology, generation profiles, and contingency plans never leave the building — no public
cloud QPU, no third-party API.</div>
<div class="tech">TAA-compliant · on-premise · {b.get('device', 'NVIDIA GB10')}</div></div>
""", unsafe_allow_html=True)

    st.markdown(ui.card_html("Why classical hardware decides hybrid quantum outcomes", """
<p>QAOA is a <strong>hybrid</strong> algorithm. A quantum processor would evaluate the cost
expectation; every other part of the loop — building the Hamiltonian, proposing (γ, β),
converging the optimizer, decoding bitstrings into an islanding plan — is classical and runs
here. In the NISQ era, that classical share dominates.</p>
<p>The same infrastructure that simulates the quantum state today is the infrastructure that
will <strong>drive real QPUs</strong> tomorrow. Algorithm development, validation against exact
solutions, and operator tooling all happen on this hardware first.</p>"""),
        unsafe_allow_html=True)
