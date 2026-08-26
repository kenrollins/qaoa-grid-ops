"""Page: controlled run history and algorithm comparison."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import COLORS
from src.simulation.experiments import ExperimentRecord, records_csv, records_json, save_records
from src.simulation.connectivity import estimate_routing
from src.simulation.qaoa_engine import run_realism


def _comparison_rows(records: list[ExperimentRecord]) -> list[dict]:
    return [{
        "Run": r.label, "Formulation": r.formulation, "Mode": r.execution_mode,
        "Fit NRMSE": r.formulation_diagnostics.get("validation_nrmse"), "Qubits": r.n_qubits,
        "p": r.layers, "Steps": r.optimizer_steps, "Backend": r.backend,
        "Expectation": r.expectation_energy, "Selected energy": r.selected_energy,
        "Exact energy": r.exact_energy, "Concentration": r.concentration,
        "Served MW": r.served_mw, "Shed MW": r.shed_mw,
        "Overloads": r.overloads, "Worst loading": r.worst_loading,
        "vs baseline MW": r.advantage_mw, "Seconds": r.wall_seconds,
        "Selected argmax": r.selected_was_argmax,
    } for r in records]


def _outcome_figure(records: list[ExperimentRecord]) -> go.Figure:
    fig = go.Figure()
    labels = [r.label for r in records]
    fig.add_bar(name="Load served", x=labels, y=[r.served_mw for r in records],
                marker_color=COLORS["ok"])
    fig.add_bar(name="Load shed", x=labels, y=[r.shed_mw for r in records],
                marker_color=COLORS["crit"])
    fig.update_layout(barmode="group", template="plotly_dark", height=350,
                      paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["plot_bg"],
                      title="Operational outcome", yaxis_title="MW",
                      font=dict(color=COLORS["text"]))
    return fig


def render(records: list[ExperimentRecord], current_run=None, pref: str = "gb10") -> None:
    st.markdown("## Algorithm Lab")
    st.markdown("""
This page treats each solve as a controlled experiment. Compare the mathematical objective,
the quantum distribution, and the plan that survived classical grid-security screening.
Changing one factor at a time is what turns emulation into algorithm development.
""")
    with st.expander("Presenter guide — objective-alignment story", expanded=not records):
        st.markdown("""
1. In the sidebar choose **Guided → Baseline algorithm**, set **8 substations**, and use seed 7.
2. Return to **Command Center**, trip the line, and solve it. Say: *“First we optimize the
   objective an engineer wrote down.”*
3. Choose **Operational surrogate experiment** without changing the grid, seed, or fault, then
   solve again. Say: *“Now the emulator scores candidate partitions with power flow and fits the
   best quadratic proxy the quantum circuit can consume.”*
4. Return here and select both runs. Compare **served MW**, **overloads**, and **Fit NRMSE**.
5. Close with: *“The solver can optimize either Hamiltonian. Emulation tells us whether the
   Hamiltonian represents the decision we actually care about.”*

Use 8 qubits for the narrated comparison because all 256 partitions are available as training
and ground truth. The fit error remains visible: the operational target contains threshold and
power-flow behavior that no unconstrained quadratic model can reproduce exactly.
""")
    if not records:
        st.info("Run a scenario in the Command Center. Each completed solve will appear here.")
        return

    st.markdown("### Hardware preview: admit physical reality one factor at a time")
    st.caption("The optimized angles stay fixed. Only measurement and noise change.")
    if current_run is not None:
        params = current_run.result.get("best_params") or []
        p = int(current_run.result.get("layers", 0))
        c1, c2, c3 = st.columns([1, 1, 1])
        shots = c1.select_slider("Measurement shots", [256, 1024, 2048, 8192], value=2048)
        noise = c2.select_slider("Depolarizing noise / qubit / layer",
                                 [0.001, 0.005, 0.01, 0.02], value=0.01,
                                 format_func=lambda value: f"{value * 100:.1f}%")
        if c3.button("Compare ideal, sampled, and noisy", type="primary", width="stretch"):
            if not params or p < 1:
                st.error("The current run did not return optimized circuit parameters.")
            else:
                with st.spinner("Running the same circuit under three execution models…"):
                    st.session_state["lab_realism"] = run_realism(
                        current_run.model, params[:p], params[p:], shots=shots,
                        depolarizing=noise, backend_preference=pref)
        realism = st.session_state.get("lab_realism")
        if realism:
            if realism.get("error"):
                st.warning(realism["error"])
            else:
                rr = realism.get("results", [])
                st.dataframe(pd.DataFrame([{
                    "Execution model": item.get("label"),
                    "Expectation": item.get("energy"),
                    "Best observed state": item.get("best_bitstring") or "not retained",
                    "Shot error": item.get("shot_error"), "Purity": item.get("purity"),
                    "Memory GiB": item.get("memory_bytes", 0) / 2**30,
                    "Seconds": item.get("seconds"),
                } for item in rr]), width="stretch", hide_index=True)
                st.caption("Ideal exposes the complete state. Finite shots expose only samples. "
                           "Noise changes the state itself; purity 1.0 is perfectly coherent.")
    else:
        st.info("Run a scenario to enable the hardware-preview comparison.")

    if current_run is not None:
        st.markdown("### Connectivity preview")
        st.markdown("The emulator applies the dense Hamiltonian directly. A sparse device must "
                    "move logical qubits together before many of those interactions can occur.")
        coupling_rows = [(i, j, value) for (i, j), value in current_run.model.couplings.items()]
        routing = [estimate_routing(current_run.model.n_qubits, coupling_rows, topology,
                                    layers=int(current_run.result.get("layers", 1)))
                   for topology in ("All-to-all emulator", "Square-grid device",
                                    "Ring device", "Linear device")]
        st.dataframe(pd.DataFrame([r.to_dict() for r in routing]),
                     width="stretch", hide_index=True)
        st.caption("Planning estimate, not target-device transpilation: identity placement, "
                   "shortest paths, restore-after-use SWAPs, and three two-qubit gates per SWAP.")

    options = {f"{r.created_at[11:19]} · {r.label} · {r.experiment_id}": r for r in records}
    chosen = st.multiselect("Experiments to compare", list(options),
                            default=list(options)[-min(3, len(options)):])
    selected = [options[key] for key in chosen]
    if not selected:
        st.warning("Select at least one experiment.")
        return

    st.dataframe(pd.DataFrame(_comparison_rows(selected)), width="stretch", hide_index=True)
    st.plotly_chart(_outcome_figure(selected), width="stretch")

    st.markdown("#### The four answers")
    answer_rows = [{
        "Run": r.label, "Exact QUBO optimum": r.exact_energy,
        "QAOA argmax": r.argmax_bitstring, "Applied plan": r.selected_bitstring,
        "Changed by security screen": not r.selected_was_argmax,
        "Candidates screened": r.candidates_screened,
    } for r in selected]
    st.dataframe(pd.DataFrame(answer_rows), width="stretch", hide_index=True)

    a, b, c = st.columns(3)
    a.download_button("Download JSON", records_json(selected),
                      file_name="qaoa-experiments.json", mime="application/json",
                      width="stretch")
    b.download_button("Download CSV", records_csv(selected),
                      file_name="qaoa-experiments.csv", mime="text/csv", width="stretch")
    if c.button("Save snapshot to data/experiments", width="stretch"):
        path = save_records(selected, Path("data/experiments"))
        st.success(f"Saved {len(selected)} experiment(s) to {path}")
