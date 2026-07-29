"""Page: Command Center — the operational surface.

Four tabs: the islanding result, the quantum explainer, the circuit internals,
and the capability envelope. Architecture lives on its own page.
"""

from __future__ import annotations

import streamlit as st

from src.simulation.grid_model import build_grid
from src.simulation.qaoa_engine import scaling_probe
from src.ui import components as ui
from src.ui.views import quantum as quantum_view


def render(spec, backend: dict, layers: int, pref: str) -> None:
    run = st.session_state.get("run")
    free_gb = backend.get("free_memory_bytes", 0) / 2**30
    total_gb = backend.get("total_memory_bytes", 0) / 2**30

    tab1, tab2, tab3, tab4 = st.tabs([
        "🗺️  Grid Topology & Microgrid Islanding",
        "⚛️  The Quantum Part",
        "🔬  Under the Hood: Circuit & Qubit Operations",
        "📊  Simulation Capability",
    ])

    # ── Tab 1 — the result ───────────────────────────────────────────────────
    with tab1:
        if run is None:
            st.info("Set the contingency parameters and press "
                    "**🚀 Run Hybrid Optimization** in the sidebar.")
            st.plotly_chart(ui.topology_figure(build_grid(spec)), width="stretch")
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
                f"{res.get('steps_run')} steps · {res.get('backend')}"),
                unsafe_allow_html=True)
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
<p>Brute force over all <strong>{2 ** run.model.n_qubits:,}</strong> partitions was computed
for comparison. QAOA's returned plan <strong>{verdict}</strong>.</p>
<p>Solution ratio <strong>{run.solution_ratio:.3f}</strong> · expectation ratio
<strong>{run.expectation_ratio:.3f}</strong> · concentration
<strong>{run.concentration:.1f}x</strong> uniform.</p>
<p>The two ratios differ because ⟨H⟩ averages the whole measurement distribution, while the
operator receives the single best partition.</p>"""), unsafe_allow_html=True)
                else:
                    st.markdown(ui.card_html("Verification", f"""
<p>At {run.model.n_qubits} qubits the exact optimum is not brute-forced
({2 ** run.model.n_qubits:,} partitions), so optimality is <strong>not claimed</strong>.</p>
<p>Concentration <strong>{(run.concentration or 0):.1f}x</strong> over a uniform guess is the
evidence the circuit is doing work.</p>"""), unsafe_allow_html=True)

            st.download_button(
                "⬇  Download islanding schedule (JSON)",
                ui.partition_report_json(run),
                file_name=f"islanding-schedule-{run.model.n_qubits}q.json",
                mime="application/json")

    # ── Tab 2 — the explainer ────────────────────────────────────────────────
    with tab2:
        quantum_view.render(run=run, n_nodes=spec.n_nodes, layers=layers)

    # ── Tab 3 — internals ────────────────────────────────────────────────────
    with tab3:
        n = run.model.n_qubits if run else spec.n_nodes
        nc = run.model.n_terms if run else n * (n - 1) // 2
        st.markdown(f'<div class="circuit">{ui.circuit_ascii(n, layers, nc)}</div>',
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
<p>The cost Hamiltonian is diagonal in the computational basis, so exp(-iγH<sub>C</sub>) is
applied as a single elementwise phase multiply rather than as thousands of individual RZZ
gates. This is an <strong>optimization, not an approximation</strong>: applying every RZZ
separately produces an identical state to within 1e-16, which the GB10 service verifies on
request via <code>POST /qaoa/verify</code>.</p>"""), unsafe_allow_html=True)
        else:
            st.info("Run an optimization to populate the measured statevector distribution.")

    # ── Tab 4 — capability ───────────────────────────────────────────────────
    with tab4:
        st.markdown(ui.card_html("The capability claim", f"""
<p>The Dell Pro Max GB10 is the <strong>entry point</strong> of this hardware class, and it is
the floor of the claim, not the ceiling: <strong>{backend.get('max_qubits', 0)} qubits</strong>
of dense all-to-all QAOA right now, bounded by unified memory ({free_gb:.0f} GiB free of
{total_gb:.0f} GiB). Larger GPU configurations move that number up.</p>
<p>The binding constraint is <strong>memory, not speed</strong>. A complex128 statevector costs
16 bytes per amplitude and doubles per qubit; the working set here is ~1.6x that, covering the
cost diagonal and tiled scratch. This chart is not a speedup ratio against other hardware — it
is how large a problem this machine holds, and how long one energy evaluation takes at each
size.</p>"""), unsafe_allow_html=True)

        if st.button("🔥  Run Live Capability Sweep", type="primary"):
            ns = [n for n in [8, 12, 16, 20, 22, 24, 26]
                  if n <= max(backend.get("max_qubits", 8), 8)]
            with st.spinner(f"Sweeping {len(ns)} problem sizes on {backend['label']}…"):
                st.session_state["sweep"] = scaling_probe(
                    ns, layers=layers, backend_preference=pref)

        sweep = st.session_state.get("sweep")
        if sweep:
            st.plotly_chart(ui.scaling_figure(sweep, ceiling=backend.get("max_qubits")),
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

        st.plotly_chart(ui.memory_figure(ceiling_bytes=backend.get("free_memory_bytes", 0)),
                        width="stretch")
