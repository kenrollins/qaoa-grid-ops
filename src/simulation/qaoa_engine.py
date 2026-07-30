"""Execution facade: where the quantum math actually runs.

The UI never imports CuPy, never opens a CUDA context, and never cares which
machine answered. It calls `run_islanding_optimization()` and gets numbers back.
That separation is what lets the Streamlit front end live on xr7620 while the
statevector lives on the GB10.

Three backends, in preference order:

  gb10   — HTTP to the cuStateVec service on the GB10 (10.0.13.200:8600).
           THE product path. Blackwell + 128 GB unified memory.
  local  — CuPy in-process if this host has a usable GPU, else NumPy.
           A convenience for iterating when the GB10 is busy. NOT the story.
  auto   — gb10 if it answers /health, otherwise local.

Backend selection is explicit and always reported back to the UI, because a
demo that silently degrades to CPU while claiming GPU acceleration is worse
than one that fails loudly.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np

from src.config.settings import (
    DEFAULT_BACKEND,
    GB10_QSIM_URL,
    GB10_REQUEST_TIMEOUT,
    GridSpec,
    statevector_bytes,
)
from src.simulation.grid_model import (
    IsingModel,
    LoadReport,
    PartitionReport,
    apply_fault,
    build_grid,
    build_ising,
    evaluate_partition,
    faulted_edges,
    live_edges,
    load_report,
    spectral_baseline,
)
from src.simulation import power_flow as pf
from src.simulation import qaoa_core


# ── Backend discovery ────────────────────────────────────────────────────────

@dataclass
class BackendInfo:
    name: str                 # "gb10" | "local-gpu" | "local-cpu"
    label: str                # human-facing
    device: str = ""
    available: bool = False
    free_memory_bytes: int = 0
    total_memory_bytes: int = 0
    max_qubits: int = 0
    detail: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _http_json(url: str, payload: dict | None = None, timeout: int = 10) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def probe_gb10(url: str = GB10_QSIM_URL, timeout: int = 5) -> BackendInfo:
    """Ask the GB10 what it can do right now.

    `max_qubits` is reported live rather than hard-coded, because the GB10's
    unified memory is shared with whatever inference workload is resident. The
    ceiling genuinely moves depending on whether the NIM is loaded, and the demo
    should say so instead of pretending the number is a constant.
    """
    info = BackendInfo(name="gb10", label="Dell Pro Max GB10 · Grace Blackwell")
    try:
        h = _http_json(f"{url}/health", timeout=timeout)
        info.available = True
        info.device = h.get("device", "NVIDIA GB10")
        info.free_memory_bytes = int(h.get("free_memory_bytes", 0))
        info.total_memory_bytes = int(h.get("total_memory_bytes", 0))
        info.max_qubits = int(h.get("max_qubits", 0))
        info.detail = h.get("detail", "")
    except Exception as exc:
        info.detail = f"unreachable: {type(exc).__name__}"
    return info


def probe_local() -> BackendInfo:
    """Local in-process compute — CuPy if a GPU is usable, else NumPy."""
    try:
        import cupy as cp

        dev = cp.cuda.Device(0)
        free, total = dev.mem_info
        cp.arange(8).sum()  # force a real kernel; a broken CUDA install fails here
        return BackendInfo(
            name="local-gpu",
            label="Local GPU (CuPy)",
            device=f"compute capability {dev.compute_capability}",
            available=True,
            free_memory_bytes=int(free),
            total_memory_bytes=int(total),
            max_qubits=_max_qubits_for(int(free)),
            detail="in-process CuPy",
        )
    except Exception:
        pass

    return BackendInfo(
        name="local-cpu",
        label="Local CPU (NumPy)",
        device="host",
        available=True,
        max_qubits=24,
        detail="NumPy fallback — no GPU in this process",
    )


def _max_qubits_for(free_bytes: int, safety: float = 0.55) -> int:
    """Largest n whose full working set fits in `free_bytes`.

    Working set is ~1.6x the statevector: the complex128 state (16 B/amplitude),
    the float64 cost diagonal (8 B/amplitude), plus tiled scratch. `safety`
    keeps a margin so a run does not evict a co-resident inference model — on a
    unified-memory box, an OOM here can take a neighbour's service down with it.
    """
    if free_bytes <= 0:
        return 0
    budget = free_bytes * safety
    n = 0
    while n < 40 and statevector_bytes(n + 1) * 1.6 <= budget:
        n += 1
    return n


def select_backend(preference: str = DEFAULT_BACKEND) -> BackendInfo:
    if preference == "local":
        return probe_local()
    gb10 = probe_gb10()
    if gb10.available:
        return gb10
    if preference == "gb10":
        gb10.detail += " — GB10 requested but not answering"
        return gb10
    return probe_local()


# ── The run ──────────────────────────────────────────────────────────────────

@dataclass
class IslandingRun:
    """Everything the UI needs from one optimization, in one object."""

    graph: nx.Graph
    model: IsingModel
    result: dict
    report: PartitionReport
    backend: BackendInfo
    wall_seconds: float
    exact: dict | None = None
    warnings: list[str] = field(default_factory=list)
    # Contingency context — the three states an operator compares.
    fault: list[tuple[int, int, float]] = field(default_factory=list)
    load_before: LoadReport | None = None   # intact grid, one connected system
    load_after_fault: LoadReport | None = None   # post-fault, no islanding action
    load_after_plan: LoadReport | None = None    # after the QAOA islanding plan

    # Classical spectral bisection on the same post-fault grid.
    baseline_report: PartitionReport | None = None
    baseline_load: LoadReport | None = None

    # Solved DC power flow for the three states an operator compares. These are
    # what the control-room view renders — every MW, loading %, and frequency on
    # screen comes from one of these solutions.
    flow_intact: "pf.FlowSolution | None" = None
    flow_post_fault: "pf.FlowSolution | None" = None
    flow_islanded: "pf.FlowSolution | None" = None

    @property
    def mw_shed_by_plan(self) -> float:
        """Load shed as the COST of separating. Islanding is never free."""
        return self.load_after_plan.shed_mw if self.load_after_plan else 0.0

    @property
    def mw_better_than_baseline(self) -> float:
        """MW of load QAOA keeps on that classical spectral bisection does not.

        The operator's bottom line, and the fair comparison: both methods are
        separating the same faulted grid, so the difference is attributable to
        the objective, not to the hardware. Positive means QAOA served more.
        """
        if not (self.baseline_load and self.load_after_plan):
            return 0.0
        return round(self.load_after_plan.served_mw - self.baseline_load.served_mw, 1)

    @property
    def energy_history(self) -> list[float]:
        return self.result.get("energy_history", [])

    @property
    def expectation_ratio(self) -> float | None:
        """Optimum relative to the final ⟨H⟩ — the OPTIMISER's objective.

        This is what QAOA literature usually calls the approximation ratio, and
        it is stubbornly modest (~0.25 here) because ⟨H⟩ averages over the whole
        measurement distribution, most of which is still junk at low depth. It
        is NOT a statement about the answer the operator receives.
        """
        if not self.exact:
            return None
        best = self.result.get("best_energy")
        opt = self.exact.get("energy")
        if best in (None, 0) or opt is None:
            return None
        return float(opt / best)

    @property
    def solution_ratio(self) -> float | None:
        """Optimum relative to the energy of the bitstring actually returned.

        This is the number that answers 'is the islanding plan any good'. On
        every grid measured so far it is 1.000 — QAOA returns the true optimum,
        sometimes as its Z₂-symmetric complement (an identical partition).

        Reporting only expectation_ratio would understate the result by ~4x;
        reporting only this would overstate how well the optimiser converged.
        The demo shows both.
        """
        if not self.exact:
            return None
        opt = self.exact.get("energy")
        got = self.report.energy
        if opt is None or abs(got) < 1e-12:
            return None
        return float(opt / got)

    @property
    def is_optimal(self) -> bool | None:
        """Did QAOA land exactly on the ground state? None if unverified."""
        if not self.exact:
            return None
        return abs(self.report.energy - self.exact["energy"]) < 1e-6

    @property
    def concentration(self) -> float | None:
        """How far the top outcome beats a uniform random guess.

        1.0 means the circuit did nothing. This rises monotonically with circuit
        depth even when ⟨H⟩ barely moves, which makes it the honest live signal
        that adding layers is buying something.
        """
        tops = self.result.get("top_states") or []
        if not tops:
            return None
        p_top = tops[0][1] if isinstance(tops[0], (list, tuple)) else tops[0]["probability"]
        return float(p_top * (1 << self.model.n_qubits))


def run_islanding_optimization(
    spec: GridSpec,
    layers: int = 2,
    steps: int = 30,
    backend_preference: str = DEFAULT_BACKEND,
    mode: str = "diagonal",
    compute_exact: bool = True,
    exact_limit: int = 16,
    graph: nx.Graph | None = None,
    fault: list[tuple[int, int]] | None = None,
) -> IslandingRun:
    """Build the grid, solve the islanding QUBO with QAOA, evaluate the answer.

    `fault` trips the given lines before solving — the contingency the islanding
    plan is responding to.
    """
    t0 = time.perf_counter()
    base = graph if graph is not None else build_grid(spec)
    # Rate the lines against the INTACT network before anything is faulted.
    # Calibrating on an already-faulted grid makes the fault look normal by
    # construction — the post-fault case measured *below* intact loading.
    base = pf.calibrate_ratings(base)
    g = apply_fault(base, fault or [])
    model = build_ising(g, spec.weights)
    backend = select_backend(backend_preference)
    warnings: list[str] = []

    if backend.max_qubits and spec.n_nodes > backend.max_qubits:
        warnings.append(
            f"{spec.n_nodes} qubits exceeds this backend's live ceiling of "
            f"{backend.max_qubits}. Free memory on the target, or reduce the grid."
        )

    payload = {
        "n_qubits": model.n_qubits,
        "couplings": [[i, j, v] for (i, j), v in model.couplings.items()],
        "offset": model.offset,
        "layers": int(layers),
        "steps": int(steps),
        "mode": mode,
    }

    if backend.name == "gb10" and backend.available:
        try:
            result = _http_json(
                f"{GB10_QSIM_URL}/qaoa/optimize", payload, timeout=GB10_REQUEST_TIMEOUT
            )
        except Exception as exc:
            warnings.append(
                f"GB10 run failed ({type(exc).__name__}) — fell back to local compute. "
                "Results are still correct but the hardware claim does not hold."
            )
            backend = probe_local()
            result = _run_local(payload, backend)
    else:
        result = _run_local(payload, backend)

    # ── Physics-aware post-selection ─────────────────────────────────────────
    # QAOA returns a DISTRIBUTION over partitions, not a single answer. Taking
    # only the argmax throws that away — and the argmax is chosen by an objective
    # with no notion of thermal limits, so it routinely returns a plan that
    # balances generation while overloading a 70 MVA line (measured: 202% worst
    # loading, against 137% for taking no action at all).
    #
    # So: screen the top measured states with a real DC power flow and keep the
    # one that is electrically securest. This is the hybrid loop working as
    # intended — the quantum stage proposes a shortlist, classical physics
    # disposes. Every candidate here was produced by the circuit; none is
    # invented classically.
    report, selection = _select_plan(g, model, result, spec)
    result["selection"] = selection

    exact = None
    if compute_exact and model.n_qubits <= exact_limit:
        from src.simulation.grid_model import brute_force_ground_state

        bits, energy = brute_force_ground_state(model)
        exact = {
            "bitstring": bits,
            "energy": energy,
            "report": evaluate_partition(g, model, bits),
        }

    # The three states an operator compares. "After fault, no action" is the
    # honest baseline: the network fragments along whatever live paths remain,
    # and each fragment can only serve its own generation. Without this
    # comparison the plan has nothing to be better THAN.
    live_graph = nx.Graph(live_edges(g))
    live_graph.add_nodes_from(g.nodes())
    fragments = [sorted(c) for c in nx.connected_components(live_graph)]

    base_bits = spectral_baseline(g)
    base_report = evaluate_partition(g, model, base_bits)

    # Solve the three network states.
    opened = {tuple(sorted((u, v))) for u, v, _ in report.severed_lines}
    flow_intact = pf.solve(base)
    flow_post_fault = pf.solve(g)
    flow_islanded = pf.solve(g, opened=opened)

    return IslandingRun(
        graph=g,
        model=model,
        result=result,
        report=report,
        backend=backend,
        wall_seconds=time.perf_counter() - t0,
        exact=exact,
        warnings=warnings,
        fault=faulted_edges(g),
        load_before=load_report(base, [list(base.nodes())]),
        load_after_fault=load_report(g, fragments),
        load_after_plan=load_report(g, [report.island_a, report.island_b]),
        baseline_report=base_report,
        baseline_load=load_report(g, [base_report.island_a, base_report.island_b]),
        flow_intact=flow_intact,
        flow_post_fault=flow_post_fault,
        flow_islanded=flow_islanded,
    )


def _plan_score(g: nx.Graph, model: IsingModel, bits: str) -> tuple:
    """Rank a candidate partition the way an operator would.

    Order of precedence: electrically viable first, then keep the lights on,
    then stay within thermal ratings, then minimise disruption. Energy is the
    last tiebreak — it is the proxy, not the goal.
    """
    rep = evaluate_partition(g, model, bits)
    opened = {tuple(sorted((u, v))) for u, v, _ in rep.severed_lines}
    sol = pf.solve(g, opened=opened)
    # THERMAL SECURITY OUTRANKS LOAD SERVED. Ranking shed-MW first looks
    # operator-friendly and is exactly wrong: it accepts a cascade to avoid
    # shedding, and a cascade sheds everything. Measured on the default grid,
    # shed-first chose a plan with 2 lines at 202% over available plans with
    # zero overloads. Real practice is security-constrained: stay inside the
    # ratings, THEN keep as much load on as possible.
    return (
        not rep.feasible,            # viable plans first
        len(sol.overloads),          # then no line beyond rating
        round(sol.worst_loading, 3), # then lowest peak loading
        round(sol.shed_mw, 1),       # then keep load on
        rep.interrupted_mw,          # then least disruption
        rep.energy,                  # then the Hamiltonian's opinion
    ), rep, sol


def _select_plan(g: nx.Graph, model: IsingModel, result: dict, spec: GridSpec):
    """Choose among the circuit's most probable outcomes using DC power flow."""
    tops = result.get("top_states") or []
    cands: list[str] = []
    for s in tops:
        b = s[0] if isinstance(s, (list, tuple)) else s.get("bitstring")
        if b:
            cands.append(b)
    argmax = result.get("best_bitstring") or ("0" * model.n_qubits)
    if argmax not in cands:
        cands.insert(0, argmax)
    if not cands:
        cands = [argmax]

    scored = [( _plan_score(g, model, b), b) for b in cands]
    scored.sort(key=lambda t: t[0][0])
    (best_key, best_rep, best_sol), best_bits = scored[0][0], scored[0][1]

    arg_key = next((k for (k, _, _), b in scored if b == argmax), None)
    selection = {
        "candidates_screened": len(cands),
        "chosen_bitstring": best_bits,
        "chosen_was_argmax": best_bits == argmax,
        "chosen_overloads": len(best_sol.overloads),
        "chosen_worst_loading": round(best_sol.worst_loading, 3),
        "chosen_shed_mw": best_sol.shed_mw,
        # Indices track _plan_score's tuple order: (infeasible, overloads,
        # worst_loading, shed, interrupted, energy).
        "argmax_overloads": arg_key[1] if arg_key else None,
        "argmax_worst_loading": arg_key[2] if arg_key else None,
        "argmax_shed_mw": arg_key[3] if arg_key else None,
    }
    result["best_bitstring"] = best_bits
    return best_rep, selection


def _run_local(payload: dict, backend: BackendInfo) -> dict:
    """Execute the same qaoa_core routines in this process."""
    xp: Any = np
    if backend.name == "local-gpu":
        import cupy as cp

        xp = cp

    res = qaoa_core.optimize_qaoa(
        n_qubits=payload["n_qubits"],
        couplings=[(i, j, v) for i, j, v in payload["couplings"]],
        offset=payload["offset"],
        layers=payload["layers"],
        steps=payload["steps"],
        xp=xp,
        mode=payload.get("mode", "diagonal"),
    )
    d = res.to_dict()
    d["backend"] = backend.name
    d["device"] = backend.device
    d["top_states"] = [(s["bitstring"], s["probability"]) for s in d["top_states"]]
    return d


def scaling_probe(
    n_values: list[int], layers: int = 2, backend_preference: str = DEFAULT_BACKEND
) -> list[dict]:
    """Measure one energy evaluation at each size — the capability curve.

    This is what replaces a CPU-vs-GPU bar chart: not 'we are N times faster
    than something else', but 'here is how far this machine goes, and here is
    where the working set stops fitting on hardware that is not this machine'.
    """
    backend = select_backend(backend_preference)
    rows: list[dict] = []
    for n in n_values:
        row: dict = {
            "n_qubits": n,
            "statevector_bytes": statevector_bytes(n),
            "working_set_bytes": int(statevector_bytes(n) * 1.6),
            "backend": backend.name,
        }
        if backend.max_qubits and n > backend.max_qubits:
            row.update(status="exceeds_memory", seconds=None)
        else:
            spec = GridSpec(n_nodes=n)
            g = build_grid(spec)
            m = build_ising(g, spec.weights)
            try:
                if backend.name == "gb10" and backend.available:
                    r = _http_json(
                        f"{GB10_QSIM_URL}/qaoa/evaluate",
                        {
                            "n_qubits": n,
                            "couplings": [[i, j, v] for (i, j), v in m.couplings.items()],
                            "offset": m.offset,
                            "layers": layers,
                        },
                        timeout=GB10_REQUEST_TIMEOUT,
                    )
                    row.update(status="ok", seconds=r.get("seconds"), energy=r.get("energy"))
                else:
                    t0 = time.perf_counter()
                    xp: Any = np
                    if backend.name == "local-gpu":
                        import cupy as cp

                        xp = cp
                    diag = qaoa_core.cost_diagonal(n, m.couplings, m.offset, xp=xp)
                    sv = qaoa_core.qaoa_statevector(
                        n, diag, [0.3] * layers, [0.5] * layers, xp=xp
                    )
                    e = qaoa_core.expectation(sv, diag, xp)
                    row.update(status="ok", seconds=time.perf_counter() - t0, energy=e)
            except Exception as exc:
                row.update(status=f"failed: {type(exc).__name__}", seconds=None)
        rows.append(row)
    return rows


def verify_fast_path(model: IsingModel, layers: int = 2,
                     backend_preference: str = DEFAULT_BACKEND) -> dict:
    """Prove on the live backend that the diagonal fast path == gate-by-gate RZZ.

    The demo's speed rests on applying exp(-iγH_C) as one phase multiply instead
    of thousands of RZZ gates. That is an optimisation, not an approximation --
    and this makes it checkable on demand rather than asserted in a footnote.

    Capped at 18 qubits: the gate path is O(p·n²) full passes over the
    statevector, so an unbounded check would hang the UI on a big grid.
    """
    n = min(model.n_qubits, 18)
    couplings = [[i, j, v] for (i, j), v in model.couplings.items() if i < n and j < n]
    backend = select_backend(backend_preference)
    payload = {"n_qubits": n, "couplings": couplings,
               "offset": model.offset, "layers": int(min(layers, 4))}

    if backend.name == "gb10" and backend.available:
        try:
            out = _http_json(f"{GB10_QSIM_URL}/qaoa/verify", payload,
                             timeout=GB10_REQUEST_TIMEOUT)
            out["backend"] = "gb10"
            out["device"] = backend.device
            return out
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}", "backend": "gb10"}

    xp: Any = np
    if backend.name == "local-gpu":
        import cupy as cp
        xp = cp
    out = qaoa_core.verify_equivalence(
        n, [(i, j, v) for i, j, v in couplings], model.offset, layers=payload["layers"], xp=xp)
    out["backend"] = backend.name
    out["device"] = backend.device
    return out


def run_realism(model: IsingModel, gammas, betas, shots: int = 2048,
                depolarizing: float = 0.01,
                backend_preference: str = DEFAULT_BACKEND) -> dict:
    """Ideal vs finite-shot vs noisy, on the live backend.

    Capped at 14 qubits by default from the caller: the density matrix is
    2^(2n), so 14 qubits is already 4 GB and 17 is 256 GB. That cap is not a
    limitation of the demo, it IS the demo.
    """
    backend = select_backend(backend_preference)
    payload = {
        "n_qubits": model.n_qubits,
        "couplings": [[i, j, v] for (i, j), v in model.couplings.items()],
        "offset": model.offset,
        "gammas": list(gammas), "betas": list(betas),
        "shots": int(shots), "depolarizing": float(depolarizing),
    }
    if backend.name == "gb10" and backend.available:
        try:
            return _http_json(f"{GB10_QSIM_URL}/qaoa/realism", payload,
                              timeout=GB10_REQUEST_TIMEOUT)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}", "backend": "gb10"}

    from src.simulation import noise as nz
    xp: Any = np
    if backend.name == "local-gpu":
        import cupy as cp
        xp = cp
    res = nz.compare_realism(
        model.n_qubits, [(i, j, v) for i, j, v in payload["couplings"]],
        model.offset, gammas, betas, shots=shots, depolarizing=depolarizing, xp=xp)
    return {"backend": backend.name, "device": backend.device,
            "max_qubits_clean": backend.max_qubits,
            "max_qubits_noisy": nz.max_noisy_qubits(backend.free_memory_bytes or 2**33),
            "results": [r.to_dict() for r in res]}
