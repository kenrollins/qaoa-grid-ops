"""Engine: plan selection, and honest reporting of what actually ran."""

from src.simulation import power_flow as pf
from src.simulation import qaoa_engine as eng
from src.simulation.grid_model import evaluate_partition


def test_selection_prefers_feasible_plans(faulted, model):
    """A viable plan must always beat a non-viable one, whatever the energy."""
    n = model.n_qubits
    feasible, infeasible = None, None
    for s in range(1 << n):
        bits = format(s, f"0{n}b")
        rep = evaluate_partition(faulted, model, bits)
        if rep.feasible and feasible is None:
            feasible = bits
        if not rep.feasible and infeasible is None:
            infeasible = bits
        if feasible and infeasible:
            break
    result = {"top_states": [(infeasible, 0.9), (feasible, 0.01)],
              "best_bitstring": infeasible}
    rep, sel = eng._select_plan(faulted, model, result, None)
    assert rep.feasible, "selection returned an infeasible plan over a feasible one"
    assert not sel["chosen_was_argmax"]


def test_security_outranks_load_shed(faulted, model):
    """Locks a deliberate decision that looks wrong and is not.

    Ranking shed-MW above overload count accepts a cascade to avoid shedding,
    and a cascade sheds everything. Real practice is security-constrained.
    """
    n = model.n_qubits
    secure, overloaded = None, None
    for s in range(1 << n):
        bits = format(s, f"0{n}b")
        rep = evaluate_partition(faulted, model, bits)
        if not rep.feasible:
            continue
        opened = {tuple(sorted((u, v))) for u, v, _ in rep.severed_lines}
        sol = pf.solve(faulted, opened=opened)
        if not sol.overloads and secure is None:
            secure = (bits, sol.shed_mw)
        if sol.overloads and overloaded is None and sol.shed_mw < 1e-9:
            overloaded = (bits, sol.shed_mw)
        if secure and overloaded:
            break
    if not (secure and overloaded):
        import pytest
        pytest.skip("this grid has no secure/overloaded pair to contrast")
    # The overloaded plan sheds LESS; security must still win.
    assert secure[1] >= overloaded[1]
    result = {"top_states": [(overloaded[0], 0.9), (secure[0], 0.01)],
              "best_bitstring": overloaded[0]}
    rep, sel = eng._select_plan(faulted, model, result, None)
    assert sel["chosen_overloads"] == 0, "selection preferred an overloading plan"


def test_local_run_never_claims_gb10(monkeypatch, spec, grid):
    """Regression guard for a reporting bug: when the GB10 was unreachable the
    result was labelled backend 'gb10' because that is what was REQUESTED. A
    local CPU run reported itself as GB10 hardware."""
    monkeypatch.setattr(eng, "select_backend",
                        lambda pref="gb10": eng.BackendInfo(
                            name="gb10", label="GB10", available=False,
                            detail="unreachable"))
    line = pf.worst_contingency(grid)
    run = eng.run_islanding_optimization(spec, layers=1, steps=8,
                                         backend_preference="gb10",
                                         graph=grid, fault=[line] if line else [],
                                         compute_exact=False)
    assert run.result["backend"] != "gb10", "local run claimed GB10 hardware"
    assert run.warnings, "silent fallback — no warning raised"
    assert "LOCALLY" in run.warnings[0]
