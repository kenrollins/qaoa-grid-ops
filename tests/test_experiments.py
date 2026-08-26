import json

from src.simulation.experiments import (
    ExperimentRecord, SCHEMA_VERSION, records_csv, records_json,
)


def _record():
    return ExperimentRecord(
        schema_version=SCHEMA_VERSION, experiment_id="abc", created_at="2026-08-26T00:00:00Z",
        label="baseline", source_revision="test", n_qubits=4, grid_seed=7,
        faulted_lines=[[0, 1]], layers=1, optimizer_steps=10,
        objective={"flow": 0.5, "balance": 2.0, "size": 0.2},
        formulation="analytic",
        formulation_diagnostics={"formulation": "analytic"},
        execution_mode="exact-statevector", shots=None, depolarizing=None,
        backend="local-cpu", backend_label="CPU", kernel="NumPy", wall_seconds=0.1,
        expectation_energy=-1.2, selected_energy=-2.0, exact_energy=-2.0,
        expectation_ratio=0.6, solution_ratio=1.0, concentration=3.0,
        argmax_bitstring="0011", selected_bitstring="0011", selected_was_argmax=True,
        candidates_screened=4, feasible=True, overloads=0, worst_loading=0.8,
        served_mw=100.0, shed_mw=5.0, baseline_served_mw=95.0, advantage_mw=5.0,
        top_states=[{"bitstring": "0011", "probability": 0.2}],
        energy_history=[0.0, -1.2],
    )


def test_experiment_round_trip():
    original = _record()
    value = json.loads(original.to_json())
    assert ExperimentRecord.from_dict(value) == original


def test_collection_exports_are_portable():
    record = _record()
    assert json.loads(records_json([record]))["experiments"][0]["experiment_id"] == "abc"
    csv_text = records_csv([record])
    assert "experiment_id" in csv_text and "abc" in csv_text


def test_unknown_schema_is_rejected():
    value = _record().to_dict()
    value["schema_version"] = 999
    try:
        ExperimentRecord.from_dict(value)
    except ValueError as exc:
        assert "Unsupported experiment schema" in str(exc)
    else:
        raise AssertionError("unknown schema accepted")
