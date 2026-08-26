"""Versioned, portable records for controlled algorithm experiments.

The live ``IslandingRun`` contains NetworkX graphs and rich solver objects that
are useful inside the application but unsuitable as durable artifacts.  This
module deliberately flattens a run to claims that can be compared, exported,
and replayed without importing Streamlit or contacting a compute backend.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.config.settings import GridSpec
    from src.simulation.qaoa_engine import IslandingRun


SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ExperimentRecord:
    schema_version: int
    experiment_id: str
    created_at: str
    label: str
    source_revision: str
    n_qubits: int
    grid_seed: int
    faulted_lines: list[list[int]]
    layers: int
    optimizer_steps: int
    objective: dict[str, float]
    formulation: str
    formulation_diagnostics: dict[str, Any]
    execution_mode: str
    shots: int | None
    depolarizing: float | None
    backend: str
    backend_label: str
    kernel: str
    wall_seconds: float
    expectation_energy: float | None
    selected_energy: float
    exact_energy: float | None
    expectation_ratio: float | None
    solution_ratio: float | None
    concentration: float | None
    argmax_bitstring: str
    selected_bitstring: str
    selected_was_argmax: bool
    candidates_screened: int
    feasible: bool
    overloads: int
    worst_loading: float
    served_mw: float
    shed_mw: float
    baseline_served_mw: float | None
    advantage_mw: float | None
    top_states: list[dict[str, Any]]
    energy_history: list[float]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExperimentRecord:
        version = int(value.get("schema_version", 0))
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported experiment schema {version}; expected {SCHEMA_VERSION}")
        return cls(**value)


def _top_states(result: dict) -> list[dict[str, Any]]:
    rows = []
    for state in result.get("top_states") or []:
        if isinstance(state, dict):
            rows.append({"bitstring": str(state.get("bitstring", "")),
                         "probability": float(state.get("probability", 0.0))})
        else:
            rows.append({"bitstring": str(state[0]), "probability": float(state[1])})
    return rows


def record_from_run(run: IslandingRun, spec: GridSpec, *, layers: int,
                    steps: int, label: str = "Interactive run",
                    execution_mode: str = "exact-statevector", shots: int | None = None,
                    depolarizing: float | None = None, source_revision: str = "unknown",
                    notes: str = "") -> ExperimentRecord:
    result = run.result
    selection = result.get("selection") or {}
    exact_energy = run.exact.get("energy") if run.exact else None
    served = run.load_after_plan.served_mw if run.load_after_plan else 0.0
    shed = run.load_after_plan.shed_mw if run.load_after_plan else 0.0
    baseline = run.baseline_load.served_mw if run.baseline_load else None
    identity = {
        "created_at": datetime.now(UTC).isoformat(), "seed": spec.seed,
        "n": spec.n_nodes, "layers": layers, "steps": steps,
        "objective": asdict(spec.weights), "selected": run.report.bitstring,
    }
    digest = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    return ExperimentRecord(
        schema_version=SCHEMA_VERSION, experiment_id=digest,
        created_at=identity["created_at"], label=label, source_revision=source_revision,
        n_qubits=run.model.n_qubits, grid_seed=spec.seed,
        faulted_lines=[[int(u), int(v)] for u, v, _ in run.fault],
        layers=int(result.get("layers", layers)), optimizer_steps=int(steps),
        objective={k: float(v) for k, v in asdict(spec.weights).items()},
        formulation=spec.formulation,
        formulation_diagnostics=dict(run.model.metadata),
        execution_mode=execution_mode, shots=shots, depolarizing=depolarizing,
        backend=run.backend.name, backend_label=run.backend.label,
        kernel=str(result.get("kernels", run.backend.detail)),
        wall_seconds=float(run.wall_seconds),
        expectation_energy=(float(result["best_energy"])
                            if result.get("best_energy") is not None else None),
        selected_energy=float(run.report.energy),
        exact_energy=float(exact_energy) if exact_energy is not None else None,
        expectation_ratio=run.expectation_ratio, solution_ratio=run.solution_ratio,
        concentration=run.concentration,
        argmax_bitstring=str(result.get("best_bitstring", "")),
        selected_bitstring=run.report.bitstring,
        selected_was_argmax=bool(selection.get("chosen_was_argmax", True)),
        candidates_screened=int(selection.get("candidates_screened", 1)),
        feasible=bool(run.report.feasible),
        overloads=int(selection.get("chosen_overloads", 0)),
        worst_loading=float(selection.get("chosen_worst_loading", 0.0)),
        served_mw=float(served), shed_mw=float(shed),
        baseline_served_mw=float(baseline) if baseline is not None else None,
        advantage_mw=(float(served - baseline) if baseline is not None else None),
        top_states=_top_states(result),
        energy_history=[float(v) for v in run.energy_history], notes=notes,
    )


def records_json(records: list[ExperimentRecord]) -> str:
    return json.dumps({"schema_version": SCHEMA_VERSION,
                       "experiments": [r.to_dict() for r in records]}, indent=2)


def records_csv(records: list[ExperimentRecord]) -> str:
    if not records:
        return ""
    rows = []
    for record in records:
        row = record.to_dict()
        for key in ("objective", "formulation_diagnostics", "faulted_lines",
                    "top_states", "energy_history"):
            row[key] = json.dumps(row[key], separators=(",", ":"))
        rows.append(row)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def save_records(records: list[ExperimentRecord], directory: Path) -> Path:
    """Persist an explicitly requested snapshot beneath ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"experiments-{stamp}.json"
    path.write_text(records_json(records), encoding="utf-8")
    return path
