"""Page: Command Center — the operational surface.

The three-step contingency scenario, and nothing else. Everything explanatory
moved to its own page when the six-tab structure was flattened: a visitor who
wants to drive the demo should not have to pick past five other destinations to
find the one button that starts it.
"""

from __future__ import annotations

import streamlit as st

from src.simulation import power_flow as pf
from src.simulation.grid_model import apply_fault, build_grid
from src.simulation.qaoa_engine import run_islanding_optimization
from src.ui import components as ui
from src.ui import control_room as cr


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


def render(spec, backend: dict, layers: int, pref: str, steps: int = 30,
           grid=None, fault: list | None = None) -> None:
    fault = fault or []
    step = st.session_state.get("demo_step", 0)
    base = pf.calibrate_ratings(grid if grid is not None else build_grid(spec))
    faulted_graph = apply_fault(base, fault)
    fault_label = ", ".join(
        f"{base.nodes[u]['name']} ↔ {base.nodes[v]['name']} "
        f"({base.edges[u, v].get('base_flow_mw', 0):.0f} MW, "
        f"{base.edges[u, v].get('kv', 115)} kV)" for u, v in fault) or "—"

    # ── The control bar: one obvious next action at every step ──────────
    bar = st.columns([1, 1, 1, 3])
    if bar[0].button("① Normal", width="stretch",
                     type="primary" if step == 0 else "secondary"):
        st.session_state["demo_step"] = 0
        st.session_state.pop("run", None)
        st.rerun()
    if bar[1].button("② ⚡ Trip the line", width="stretch", disabled=not fault,
                     type="primary" if step == 1 else "secondary"):
        st.session_state["demo_step"] = 1
        st.session_state.pop("run", None)
        st.rerun()
    if bar[2].button("③ 🚀 Solve it", width="stretch", disabled=not fault,
                     type="primary" if step == 2 else "secondary"):
        with st.spinner(f"Searching {2 ** spec.n_nodes:,} possible grid splits on "
                        f"{backend['label']}…"):
            st.session_state["run"] = run_islanding_optimization(
                spec, layers=layers, steps=steps, backend_preference=pref,
                graph=base, fault=fault)
        st.session_state["demo_step"] = 2
        st.rerun()
    if not fault:
        bar[3].info("Pick a contingency in the sidebar to enable steps ② and ③.")

    run = st.session_state.get("run")

    # ── Step 0 — the grid, running ──────────────────────────────────────
    if step == 0 or not fault:
        sol = pf.solve(base)
        st.markdown(f"""
<div class="narrate ok">
  <div class="h">① Normal operation</div>
  <p>A {spec.n_nodes}-substation transmission network carrying
  <b>{sol.total_load_mw:,.0f} MW</b> to customers, running at
  <b>{sol.frequency_hz:.2f} Hz</b>. Squares are power stations, circles are
  substations delivering load. Arrows are the electricity itself — thicker,
  lighter lines are the high-voltage backbone, and the arrows move faster where a
  line is working harder.</p>
  <p>Every line is inside its rating; the busiest is at
  <b>{sol.worst_loading * 100:.0f}%</b>. Nothing is wrong — and that is the point
  of looking at it now, so the next screen means something.</p>
  <p class="cue">▶ Watch the power move — the arrows run faster on harder-working
  lines. When you have the picture, press <b>② Trip the line</b> above.</p>
</div>""", unsafe_allow_html=True)
        st.markdown(cr.instrument_strip(sol, pf.cascade_risk(sol), "normal state"),
                    unsafe_allow_html=True)
        cr.render_animated(cr.animate(cr.one_line_diagram(base, sol), base, sol),
                           key="normal")
        st.markdown(cr.loading_key(sol), unsafe_allow_html=True)

    # ── Step 1 — the fault ──────────────────────────────────────────────
    elif step == 1:
        sol = pf.solve(faulted_graph)
        risk = pf.cascade_risk(sol)
        worst = ", ".join(
            f"{faulted_graph.nodes[u]['name']}↔{faulted_graph.nodes[v]['name']} "
            f"at <b>{ld * 100:.0f}%</b>" for u, v, ld in sol.overloads[:3]) or "none"
        st.markdown(f"""
<div class="narrate crit">
  <div class="h">② A line just failed — {fault_label}</div>
  <p>The power that line was carrying did not stop. It <b>rerouted</b> onto
  whatever lines remain, and those lines were not built for it. Watch the arrows:
  they have redistributed, and the overloaded corridors are now running hot.</p>
  <p>Lines beyond their safe rating: {worst}. A line held above its rating
  overheats, sags, and its own protection trips it out — which pushes its power
  onto the next line, which trips too. <b>That chain reaction is how a blackout
  happens</b>, and it is how the 2003 Northeast blackout began.</p>
  <p>Nobody has intervened yet. The operator has minutes, sometimes seconds, to
  decide where to deliberately break the grid apart so the failure cannot spread.
  The number of ways to split {spec.n_nodes} substations into two groups is
  <b>{2 ** spec.n_nodes:,}</b>.</p>
  <p class="cue">▶ Press <b>③ Solve it</b> above.</p>
</div>""", unsafe_allow_html=True)
        st.markdown(cr.instrument_strip(sol, risk, "no operator action taken"),
                    unsafe_allow_html=True)
        cr.render_animated(
            cr.animate(cr.one_line_diagram(faulted_graph, sol), faulted_graph, sol),
            key="fault")
        st.markdown(cr.loading_key(sol), unsafe_allow_html=True)
        st.markdown(f'<div class="callout"><div class="h">Security assessment</div>'
                    f'<p>{risk["note"]} Highest loading <b>{risk["worst"]:.0f}%</b>.</p>'
                    f'</div>', unsafe_allow_html=True)

    # ── Step 2 — the answer ─────────────────────────────────────────────
    elif step == 2 and run is not None:
        r, res = run.report, run.result
        sol = run.flow_islanded
        risk = pf.cascade_risk(sol)
        opened = {tuple(sorted((u, v))) for u, v, _ in r.severed_lines}
        sel = res.get("selection") or {}
        isl = sol.island_state

        st.markdown(f"""
<div class="narrate accent">
  <div class="h">③ The quantum algorithm chose where to cut</div>
  <p>QAOA searched all <b>{2 ** run.model.n_qubits:,}</b> possible ways to split this
  grid — one qubit per substation — and returned an answer in
  <b>{res.get('seconds', 0):.2f} seconds</b> on the {backend['label']}.</p>
  <p>It does not test the options one at a time. It puts all
  {2 ** run.model.n_qubits:,} of them into superposition at once, then uses
  interference to make the good splits more likely to be measured and the bad ones
  cancel out. What comes back is not a single answer but a
  <b>shortlist</b> — the {sel.get('candidates_screened', 0)} most probable splits —
  and each was then checked against real power-flow physics.
  {'The most likely one was also the best.' if sel.get('chosen_was_argmax')
   else 'A less-likely candidate turned out to be electrically better, and won.'}</p>
  <p>The plan: open <b>{len(r.severed_lines)}</b> breaker(s), forming
  <b>{len(isl)}</b> self-sufficient islands
  ({' and '.join(f"{len(s['nodes'])} substations at {s['frequency_hz']:.2f} Hz"
              for s in isl[:2])}{' and more' if len(isl) > 2 else ''}). Each island
  now generates its own power instead of leaning on the rest of the network.</p>
  <p class="cue">▶ Compare the three states below — then open
  <b>How it works</b> to see how the answer was found, or
  <b>Why it needs this hardware</b> for what it cost to compute.</p>
</div>""", unsafe_allow_html=True)

        # The before / no-action / after comparison is the payoff of the whole
        # demo. It previously sat below a 640 px diagram, where a room does not
        # scroll to it.
        st.markdown(_state_cards(run), unsafe_allow_html=True)

        st.markdown(cr.instrument_strip(sol, risk, "islanding plan applied"),
                    unsafe_allow_html=True)
        cr.render_animated(
            cr.animate(cr.one_line_diagram(faulted_graph, sol, r, opened=opened),
                       faulted_graph, sol, opened=opened),
            key="islanded")
        st.markdown(cr.loading_key(sol), unsafe_allow_html=True)

        if run.exact:
            # is_optimal refers to the plan ACTUALLY APPLIED, which is chosen
            # for electrical security rather than for lowest energy. Saying
            # "did not reach the optimum" here would read as a failure when it
            # is a deliberate trade the objective cannot express.
            if run.is_optimal:
                verdict = ("<b>matches the exact optimum</b> of the objective — the "
                           "quantum result is provably the best available split")
            else:
                verdict = ("<b>deliberately differs</b> from the objective's exact "
                           "optimum: the energy-minimising split ran a line beyond its "
                           "thermal rating, so a different candidate from the quantum "
                           "shortlist was applied instead")
            st.markdown(f"""
<div class="callout" style="border-left-color:var(--ok);
 background:rgba(61,220,151,.06);border-color:rgba(61,220,151,.32)">
  <div class="h" style="color:var(--ok)">Checked against the exact answer</div>
  <p>At {run.model.n_qubits} qubits every one of the
  <b>{2 ** run.model.n_qubits:,}</b> partitions can still be brute-forced and compared.
  The applied plan {verdict}.</p>
  <p>Above roughly 20 qubits that check stops being affordable — an algorithm can be
  quietly, confidently wrong with nothing to catch it. That is precisely why this work
  happens at sizes where truth is still computable.</p>
</div>""", unsafe_allow_html=True)

        log, side = st.columns([3, 2])
        with log:
            st.markdown("###### Event log")
            st.markdown(cr.alarm_log(cr.build_events(run)), unsafe_allow_html=True)
            st.caption("Sequence and content derive from the solved power flow; "
                       "timestamps are synthesised for presentation.")
        with side:
            st.download_button("⬇  Download islanding schedule (JSON)",
                               ui.partition_report_json(run),
                               file_name=f"islanding-schedule-{run.model.n_qubits}q.json",
                               mime="application/json", width="stretch")
            st.plotly_chart(
                ui.convergence_figure(run.energy_history,
                                      run.exact["energy"] if run.exact else None),
                width="stretch")
    else:
        st.info("Press **③ Solve it** to run the optimization.")

