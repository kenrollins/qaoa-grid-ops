"""Page: Command Center — the operational surface.

Four tabs: the islanding result, the quantum explainer, the circuit internals,
and the capability envelope. Architecture lives on its own page.
"""

from __future__ import annotations

import streamlit as st

from src.simulation.grid_model import apply_fault, build_grid
from src.simulation import power_flow as pf
from src.simulation.qaoa_engine import scaling_probe, verify_fast_path
from src.ui import components as ui
from src.ui import control_room as cr
from src.ui.views import limits as limits_view
from src.ui.views import quantum as quantum_view


def _state_cards(run) -> str:
    """Three states side by side — the whole story in one glance."""
    states = [
        ("Before the fault", run.flow_intact, "System intact and secure."),
        ("Fault, no action", run.flow_post_fault, "What happens if nobody intervenes."),
        ("Islanding applied", run.flow_islanded, "The plan QAOA returned."),
    ]
    out = []
    for name, sol, sub in states:
        if sol is None:
            continue
        r = pf.cascade_risk(sol)
        hl = ("SECURE" if r["level"] == "secure"
              else ("CASCADE RISK" if r["level"] == "cascade" else "ELEVATED"))
        out.append(
            f'<div class="statecard {r["level"]}"><div class="st">{name}</div>'
            f'<div class="hl">{hl}</div>'
            f'<div class="dt">{sub}<br>'
            f'Peak line <b>{sol.worst_loading * 100:.0f}%</b> · '
            f'{len(sol.overloads)} overload(s)<br>'
            f'{sol.served_mw:,.0f} MW served · {sol.shed_mw:,.0f} MW shed · '
            f'{sol.frequency_hz:.2f} Hz</div></div>')
    return f'<div class="statebar">{"".join(out)}</div>'


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
            # The landing state gets the SAME control-room treatment as a solved
            # run. Previously this branch fell back to a plain graph, so anyone
            # who had not yet pressed Run — i.e. everyone arriving at the page —
            # saw none of the instrumentation and concluded nothing had changed.
            base0 = pf.calibrate_ratings(grid if grid is not None else build_grid(spec))
            g0 = apply_fault(base0, fault)
            sol0 = pf.solve(g0)
            risk0 = pf.cascade_risk(sol0)

            if fault:
                lines = ", ".join(
                    f"{g0.nodes[u]['name']} ↔ {g0.nodes[v]['name']} "
                    f"({g0.edges[u, v].get('base_flow_mw', g0.edges[u, v]['flow_mw']):.0f} MW)"
                    for u, v in fault)
                st.error(f"⚡ **CONTINGENCY — line fault:** {lines} · "
                         f"peak line loading now **{sol0.worst_loading * 100:.0f}%** across "
                         f"**{len(sol0.overloads)}** overloaded line(s). "
                         "Press **🚀 Run Hybrid Optimization** for an islanding response.")
            else:
                st.info("Grid intact and secure. Select a contingency in the sidebar.")

            st.markdown(
                cr.instrument_strip(sol0, risk0,
                                    "awaiting operator action" if fault else "normal state"),
                unsafe_allow_html=True)
            st.plotly_chart(cr.one_line_diagram(g0, sol0), width="stretch")
            if risk0["level"] != "secure":
                st.markdown(
                    f'<div class="callout"><div class="h">Security assessment</div>'
                    f'<p>{risk0["note"]} Highest loading <b>{risk0["worst"]:.0f}%</b> of '
                    f'rating. No islanding action has been taken.</p></div>',
                    unsafe_allow_html=True)
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

            # ── Control-room view ────────────────────────────────────────
            st.markdown(_state_cards(run), unsafe_allow_html=True)

            view = st.radio(
                "Network state", ["① Before the fault", "② Fault — no action",
                                  "③ After islanding"],
                index=1, horizontal=True, label_visibility="collapsed",
                help="Step through the contingency the way an operator lives it.")

            opened = {tuple(sorted((u, v))) for u, v, _ in r.severed_lines}
            if view.startswith("①"):
                sol, rep, shown_open, cap = run.flow_intact, None, set(), "Normal state"
            elif view.startswith("②"):
                sol, rep, shown_open, cap = (run.flow_post_fault, None, set(),
                                             "Fault on the system, no operator action")
            else:
                sol, rep, shown_open, cap = (run.flow_islanded, r, opened,
                                             "Islanding plan applied")

            if sol is not None:
                risk = pf.cascade_risk(sol)
                st.markdown(cr.instrument_strip(sol, risk, cap), unsafe_allow_html=True)
                st.plotly_chart(
                    cr.one_line_diagram(run.graph, sol, rep, opened=shown_open),
                    width="stretch")
                if risk["level"] != "secure":
                    st.markdown(
                        f'<div class="callout"><div class="h">Security assessment</div>'
                        f'<p>{risk["note"]} Highest loading <b>{risk["worst"]:.0f}%</b> '
                        f'of rating.</p></div>', unsafe_allow_html=True)

            log, side = st.columns([3, 2])
            with log:
                st.markdown("###### Event log")
                st.markdown(cr.alarm_log(cr.build_events(run)), unsafe_allow_html=True)
                st.caption("Sequence and content are derived from the solved power "
                           "flow; timestamps are synthesised for presentation.")
            with side:
                sel = run.result.get("selection") or {}
                st.markdown(ui.card_html("How this plan was chosen", f"""
<p>QAOA returns a <strong>distribution</strong> over partitions, not one answer. The top
<strong>{sel.get('candidates_screened', 0)}</strong> measured states were each screened with a
DC power flow, and the electrically securest was kept.</p>
<p>{'The most probable outcome was also the best.' if sel.get('chosen_was_argmax')
   else f"A <strong>lower-probability</strong> candidate won: the most likely one peaked at "
        f"{(sel.get('argmax_worst_loading') or 0) * 100:.0f}% loading, the chosen plan at "
        f"{(sel.get('chosen_worst_loading') or 0) * 100:.0f}%."}</p>
<p>This is the hybrid loop as intended — the quantum stage proposes, classical physics
disposes. Every candidate came off the circuit.</p>"""), unsafe_allow_html=True)

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

    # ── Tab 3 — internals + the limits argument ──────────────────────────────
    with tab3:
        sub_hard, sub_circuit = st.tabs(
            ["⚠️  Why this is hard, and where the walls are",
             "🔬  This circuit, gate by gate"])

        with sub_hard:
            limits_view.render(run)

        with sub_circuit:
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
