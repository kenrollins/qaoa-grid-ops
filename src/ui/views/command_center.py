"""Page: Command Center — the operational surface.

Four tabs: the islanding result, the quantum explainer, the circuit internals,
and the capability envelope. Architecture lives on its own page.
"""

from __future__ import annotations

import streamlit as st

from src.simulation.grid_model import apply_fault, build_grid
from src.simulation.qaoa_engine import scaling_probe, verify_fast_path
from src.ui import components as ui
from src.ui.views import quantum as quantum_view


def render(spec, backend: dict, layers: int, pref: str,
           grid=None, fault: list | None = None) -> None:
    run = st.session_state.get("run")
    fault = fault or []
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
            g0 = apply_fault(grid if grid is not None else build_grid(spec), fault)
            if fault:
                lines = ", ".join(f"{g0.nodes[u]['name']} ↔ {g0.nodes[v]['name']} "
                                  f"({g0.edges[u, v]['flow_mw']:.0f} MW)" for u, v in fault)
                st.error(f"⚡ **CONTINGENCY — line fault:** {lines}. "
                         "Press **🚀 Run Hybrid Optimization** to compute an islanding response.")
            else:
                st.info("Grid intact. Select a contingency and press "
                        "**🚀 Run Hybrid Optimization** in the sidebar.")
            st.plotly_chart(ui.topology_figure(g0), width="stretch")
        else:
            r, res = run.report, run.result
            for w in run.warnings:
                st.warning(w)

            if run.fault:
                lines = ", ".join(f"{run.graph.nodes[u]['name']} ↔ {run.graph.nodes[v]['name']} "
                                  f"({f:.0f} MW)" for u, v, f in run.fault)
                st.error(f"⚡ **CONTINGENCY — line fault:** {lines} · "
                         f"islanding response computed in {res.get('seconds', 0):.2f} s")

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

            # ── Load accounting: what the plan costs, and how it compares ────
            if run.load_after_plan and run.baseline_load:
                lp, lb, l0 = run.load_after_plan, run.baseline_load, run.load_before
                delta = run.mw_better_than_baseline
                cols = st.columns(3)
                cols[0].markdown(ui.metric_html(
                    "Load served — QAOA plan", f"{lp.served_mw:,.0f}", "MW",
                    f"{lp.served_fraction * 100:.1f}% of {l0.total_load_mw:,.0f} MW demand · "
                    f"{lp.shed_mw:,.0f} MW shed",
                    kind="ok" if lp.shed_mw <= lb.shed_mw else "warn"), unsafe_allow_html=True)
                cols[1].markdown(ui.metric_html(
                    "Load served — classical baseline", f"{lb.served_mw:,.0f}", "MW",
                    f"spectral bisection · {lb.shed_mw:,.0f} MW shed"
                    + ("" if run.baseline_report.feasible else " · INFEASIBLE")),
                    unsafe_allow_html=True)
                cols[2].markdown(ui.metric_html(
                    "QAOA vs classical", f"{delta:+,.0f}", "MW",
                    "load kept on that spectral bisection sheds" if delta > 0
                    else ("identical outcome" if abs(delta) < 0.5
                          else "classical served more — see note"),
                    kind="ok" if delta > 0.5 else ("crit" if delta < -0.5 else "")),
                    unsafe_allow_html=True)

                if delta < -0.5:
                    st.markdown(f"""
<div class="callout">
  <div class="h">Honest result — the classical baseline won this one</div>
  <p>QAOA returned the <strong>true optimum of the stated objective</strong>
  {'(verified by brute force)' if run.is_optimal else ''}, yet served
  <strong>{abs(delta):,.0f} MW less</strong> than spectral bisection. That is a statement
  about the <em>objective</em>, not the solver: the balance term penalises an island with
  surplus generation exactly as hard as one with a deficit, though only deficits shed load.</p>
  <p>Objective alignment is the open algorithm problem here, and it is the kind of thing
  this platform exists to expose. Try raising <strong>Island power balance</strong>.</p>
</div>""", unsafe_allow_html=True)

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
gates. This is an <strong>optimization, not an approximation</strong> — and you can check that
here rather than take it on faith.</p>"""), unsafe_allow_html=True)

            if st.button("🔍  Verify: apply every RZZ gate individually and compare"):
                with st.spinner("Running both paths on the live backend…"):
                    st.session_state["verify"] = verify_fast_path(
                        run.model, layers=run.result.get("layers", layers),
                        backend_preference=pref)

            v = st.session_state.get("verify")
            if v:
                if v.get("error"):
                    st.error(f"Verification failed: {v['error']}")
                else:
                    dev = v.get("max_amplitude_deviation", 0.0)
                    ok = v.get("equivalent")
                    st.markdown(f"""
<div class="callout" style="border-left-color:var(--{'ok' if ok else 'crit'});
     background:rgba(61,220,151,.06);border-color:rgba(61,220,151,.32)">
  <div class="h" style="color:var(--{'ok' if ok else 'crit'})">
    {'Verified equivalent' if ok else 'NOT equivalent'} — {v.get('n_qubits')} qubits,
    p={v.get('layers')}, on {v.get('backend')}</div>
  <p>Maximum amplitude deviation between the diagonal fast path and gate-by-gate RZZ
  application: <strong>{dev:.3e}</strong>
  {'— floating-point noise, i.e. the two are the same unitary.' if ok
   else '— above tolerance, the fast path is NOT reproducing the gate sequence.'}</p>
</div>""", unsafe_allow_html=True)
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
