"""gridops-qsim — the quantum simulation service on the Dell Pro Max GB10.

Runs on the GB10 (aarch64, Blackwell sm_121) and owns the statevector. The
Streamlit front end on xr7620 talks to it over VLAN 13. Nothing about the grid
problem lives here — the service takes couplings and returns energies, which
keeps the domain model in one place and this process purely computational.

WHY THIS EXISTS AS A SERVICE, and not as `import qiskit_aer` in the UI:
`qiskit-aer-gpu` publishes x86_64 wheels ONLY. There is no aarch64 build, so it
cannot be installed on the GB10 at all. The GPU path on Grace Blackwell runs
through CuPy + cuQuantum's own cuStateVec bindings, both of which do ship
aarch64 wheels. Splitting the UI from the compute is therefore not an
architectural preference — it is the only way to put this workload on a GB10.

Run:
    uvicorn server:app --host 0.0.0.0 --port 8600
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import Any

# The shared math lives in the project's src/ tree, rsynced alongside this file.
sys.path.insert(0, os.getenv("GRIDOPS_ROOT", "/opt/gridops"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from src.simulation import qaoa_core  # noqa: E402

app = FastAPI(title="gridops-qsim", version="1.0")

# Fraction of FREE device memory a single request may claim. The GB10's memory
# is UNIFIED — an over-allocation here does not just fail this request, it can
# evict a co-resident inference model and take a neighbouring service down.
MEMORY_SAFETY = float(os.getenv("GRIDOPS_MEMORY_SAFETY", "0.55"))
WORKING_SET_FACTOR = 1.6  # complex128 state + float64 diagonal + tiled scratch


def _cupy():
    import cupy as cp

    return cp


def _device_state() -> dict:
    try:
        cp = _cupy()
        dev = cp.cuda.Device(0)
        free, total = dev.mem_info
        cp.arange(8).sum()  # prove the CUDA context is genuinely usable
        return {
            "ok": True,
            "device": "NVIDIA GB10 (Grace Blackwell)",
            "compute_capability": str(dev.compute_capability),
            "free_memory_bytes": int(free),
            "total_memory_bytes": int(total),
            "max_qubits": _max_qubits(int(free)),
        }
    except Exception as exc:
        return {"ok": False, "device": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}


def _max_qubits(free_bytes: int) -> int:
    budget = free_bytes * MEMORY_SAFETY
    n = 0
    while n < 40 and (1 << (n + 1)) * 16 * WORKING_SET_FACTOR <= budget:
        n += 1
    return n


def _guard(n_qubits: int) -> None:
    """Refuse a request that would not fit, with a number instead of an OOM."""
    st = _device_state()
    if not st["ok"]:
        raise HTTPException(503, f"GPU unavailable: {st.get('detail')}")
    need = (1 << n_qubits) * 16 * WORKING_SET_FACTOR
    budget = st["free_memory_bytes"] * MEMORY_SAFETY
    if need > budget:
        raise HTTPException(
            507,
            f"{n_qubits} qubits needs ~{need / 2**30:.1f} GiB working set; "
            f"only {budget / 2**30:.1f} GiB is safely available "
            f"(ceiling right now: {st['max_qubits']} qubits). "
            "Free resident models on the GB10 or reduce the grid size.",
        )


class OptimizeRequest(BaseModel):
    n_qubits: int = Field(ge=2, le=34)
    couplings: list[tuple[int, int, float]]
    offset: float = 0.0
    layers: int = Field(default=2, ge=1, le=8)
    steps: int = Field(default=30, ge=1, le=400)
    mode: str = "diagonal"
    seed: int = 11
    top_k: int = 12


class EvaluateRequest(BaseModel):
    n_qubits: int = Field(ge=2, le=34)
    couplings: list[tuple[int, int, float]]
    offset: float = 0.0
    layers: int = Field(default=2, ge=1, le=8)


class EquivalenceRequest(BaseModel):
    n_qubits: int = Field(ge=2, le=20)
    couplings: list[tuple[int, int, float]]
    offset: float = 0.0
    layers: int = Field(default=2, ge=1, le=6)


@app.get("/health")
def health() -> dict:
    st = _device_state()
    st["service"] = "gridops-qsim"
    st["detail"] = st.get("detail", "cuStateVec via cuquantum-python + CuPy")
    return st


@app.post("/qaoa/optimize")
def optimize(req: OptimizeRequest) -> dict:
    """Full QAOA parameter optimization. Returns the answer and the path to it."""
    _guard(req.n_qubits)
    cp = _cupy()
    try:
        res = qaoa_core.optimize_qaoa(
            n_qubits=req.n_qubits,
            couplings=[(i, j, v) for i, j, v in req.couplings],
            offset=req.offset,
            layers=req.layers,
            steps=req.steps,
            xp=cp,
            seed=req.seed,
            mode=req.mode,
            top_k=req.top_k,
        )
    except cp.cuda.memory.OutOfMemoryError as exc:
        raise HTTPException(507, f"GPU out of memory: {exc}") from exc
    finally:
        cp.get_default_memory_pool().free_all_blocks()

    d = res.to_dict()
    st = _device_state()
    d["backend"] = "gb10"
    d["device"] = st.get("device", "NVIDIA GB10")
    d["compute_capability"] = st.get("compute_capability", "")
    d["top_states"] = [(s["bitstring"], s["probability"]) for s in d["top_states"]]
    return d


@app.post("/qaoa/evaluate")
def evaluate(req: EvaluateRequest) -> dict:
    """One energy evaluation, timed. The unit of the scaling curve."""
    _guard(req.n_qubits)
    cp = _cupy()
    couplings = [(i, j, v) for i, j, v in req.couplings]
    try:
        t0 = time.perf_counter()
        diag = qaoa_core.cost_diagonal(req.n_qubits, couplings, req.offset, xp=cp)
        cp.cuda.Stream.null.synchronize()
        t_diag = time.perf_counter() - t0

        t1 = time.perf_counter()
        sv = qaoa_core.qaoa_statevector(
            req.n_qubits, diag, [0.3] * req.layers, [0.5] * req.layers, xp=cp
        )
        energy = qaoa_core.expectation(sv, diag, cp)
        cp.cuda.Stream.null.synchronize()
        t_eval = time.perf_counter() - t1

        peak = int(cp.get_default_memory_pool().used_bytes())
        del sv, diag
        return {
            "n_qubits": req.n_qubits,
            "energy": energy,
            "seconds": t_eval,
            "diagonal_build_seconds": t_diag,
            "statevector_bytes": (1 << req.n_qubits) * 16,
            "peak_pool_bytes": peak,
            "backend": "gb10",
        }
    except cp.cuda.memory.OutOfMemoryError as exc:
        raise HTTPException(507, f"GPU out of memory: {exc}") from exc
    finally:
        cp.get_default_memory_pool().free_all_blocks()


@app.post("/qaoa/verify")
def verify(req: EquivalenceRequest) -> dict:
    """Prove the diagonal fast path == gate-by-gate RZZ, on this hardware."""
    _guard(req.n_qubits)
    cp = _cupy()
    try:
        return qaoa_core.verify_equivalence(
            req.n_qubits,
            [(i, j, v) for i, j, v in req.couplings],
            req.offset,
            layers=req.layers,
            xp=cp,
        )
    finally:
        cp.get_default_memory_pool().free_all_blocks()
