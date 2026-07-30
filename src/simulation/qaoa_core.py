"""QAOA statevector math, written once for both NumPy and CuPy.

Every routine here takes an array module `xp` (either `numpy` or `cupy`) and is
otherwise identical, so the GB10 runs the same lines of code as a laptop. That
is not a convenience — it is what makes the demo defensible. The GB10 is not
running a different, friendlier algorithm; it is running *this* algorithm with
more memory underneath it.

── Why this simulates 30 qubits instead of dying at 22 ──────────────────────
The islanding cost Hamiltonian is DIAGONAL in the computational basis: H_C is
built entirely from Z_i Z_j terms, so it has no off-diagonal elements. Two
consequences, both exploited here:

  * The cost unitary exp(-i γ H_C) is a single elementwise phase multiply over
    the statevector — O(2^n) — rather than p·n(n-1)/2 separate two-qubit gate
    applications, each of which would also be O(2^n). For a dense 24-node
    problem at p=4 that is 1104 gate passes collapsed into 4.
  * The energy expectation ⟨ψ|H_C|ψ⟩ = Σ_x |ψ(x)|² H(x) is EXACT from the
    statevector. No shot sampling, no sampling noise, no estimator variance —
    the convergence curve the operator watches is the true expectation, not a
    noisy estimate of it.

This is a standard and well-known statevector optimisation, not a shortcut that
changes the answer: `qaoa_statevector(..., mode="gates")` applies every RZZ
individually and returns a state identical to the fast path to floating-point
precision. `verify_equivalence()` proves it on demand, and the demo exposes that
check rather than asking anyone to take it on faith.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

Couplings = dict[tuple[int, int], float] | list[tuple[int, int, float]]


def _as_triples(couplings: Couplings) -> list[tuple[int, int, float]]:
    if isinstance(couplings, dict):
        return [(int(i), int(j), float(v)) for (i, j), v in couplings.items()]
    return [(int(i), int(j), float(v)) for i, j, v in couplings]


# ── The diagonal of the cost Hamiltonian ─────────────────────────────────────

def cost_diagonal(
    n_qubits: int,
    couplings: Couplings,
    offset: float = 0.0,
    xp: Any = np,
    dtype: Any = None,
    tile_qubits: int = 22,
) -> Any:
    """H(x) for every basis state x, as a length-2ⁿ vector.

    Spins are s_i(x) = 1 - 2·bit_i(x) with bit 0 the least significant, matching
    the little-endian convention used everywhere else in this project.

    Computed in TILES. The obvious implementation caches one ±1 spin array per
    qubit and reuses it across all O(n²) coupling terms — which costs n·2ⁿ bytes
    and is perfectly fine at 24 qubits (400 MB) but demands 30 GB at 30 qubits,
    on top of the 17 GB statevector. Tiling caps the scratch at n·2^tile_qubits
    (~500 MB) and keeps the reuse, so the memory that matters stays available to
    the statevector itself — which is the entire point of running on a box with
    128 GB of unified memory.
    """
    dtype = dtype or xp.float64
    dim = 1 << n_qubits
    diag = xp.empty(dim, dtype=dtype)

    triples = _as_triples(couplings)
    tile_bits = min(tile_qubits, n_qubits)
    tile = 1 << tile_bits

    base = xp.arange(tile, dtype=xp.int64)
    for start in range(0, dim, tile):
        idx = base + start
        spins = [(1 - 2 * ((idx >> k) & 1)).astype(xp.int8) for k in range(n_qubits)]
        block = xp.full(tile, float(offset), dtype=dtype)
        for i, j, jij in triples:
            block += jij * (spins[i] * spins[j]).astype(dtype)
        diag[start:start + tile] = block
        del spins, block

    del base
    return diag


# ── Applying gates ───────────────────────────────────────────────────────────

def _apply_1q(sv: Any, n_qubits: int, target: int, m00, m01, m10, m11, xp: Any) -> Any:
    """Apply a 2×2 matrix to `target` via a stride reshape.

    Little-endian: qubit t owns stride 2^t, so the statevector viewed as
    (high, 2, low) has the target axis in the middle. No data movement, no
    kron, no temporary of size 2ⁿ×2.
    """
    low = 1 << target
    high = 1 << (n_qubits - target - 1)
    v = sv.reshape(high, 2, low)
    a0 = v[:, 0, :]
    a1 = v[:, 1, :]
    n0 = m00 * a0 + m01 * a1
    n1 = m10 * a0 + m11 * a1
    v[:, 0, :] = n0
    v[:, 1, :] = n1
    return sv


def apply_mixer(sv: Any, n_qubits: int, beta: float, xp: Any, custatevec_ctx=None) -> Any:
    """The QAOA mixer: RX(2β) on every qubit.

    RX(θ) = [[cos θ/2, -i sin θ/2], [-i sin θ/2, cos θ/2]], so with θ = 2β the
    entries are cos β and -i sin β.
    """
    c = float(np.cos(beta))
    s = float(np.sin(beta))
    m01 = m10 = complex(0.0, -s)
    m00 = m11 = complex(c, 0.0)

    if custatevec_ctx is not None:
        for t in range(n_qubits):
            custatevec_ctx.apply_matrix_1q(sv, t, [m00, m01, m10, m11])
        return sv

    for t in range(n_qubits):
        _apply_1q(sv, n_qubits, t, m00, m01, m10, m11, xp)
    return sv


def apply_cost_diagonal(sv: Any, diag: Any, gamma: float, xp: Any, tile_qubits: int = 24) -> Any:
    """exp(-i γ H_C) for diagonal H_C — one elementwise phase multiply.

    Applied in tiles. Written as the natural one-liner, `sv *= xp.exp(-1j*gamma*diag)`
    allocates TWO full-width complex128 temporaries — 34 GB of scratch at 30
    qubits on top of a 17 GB statevector, which is how a run with plenty of
    nominal headroom still dies. Tiling holds scratch to a fixed ~500 MB.
    """
    dim = sv.size
    tile = 1 << min(tile_qubits, int(np.log2(dim)))
    for s in range(0, dim, tile):
        e = s + tile
        sv[s:e] *= xp.exp((-1j * gamma) * diag[s:e])
    return sv


def apply_cost_gates(sv: Any, n_qubits: int, couplings: Couplings, gamma: float, xp: Any) -> Any:
    """The same unitary, applied one RZZ gate at a time.

    Deliberately slow. This exists to demonstrate that the fast diagonal path is
    an optimisation and not a different algorithm — see verify_equivalence().
    """
    dim = 1 << n_qubits
    idx = xp.arange(dim, dtype=xp.int64)
    for i, j, jij in _as_triples(couplings):
        si = 1 - 2 * ((idx >> i) & 1)
        sj = 1 - 2 * ((idx >> j) & 1)
        sv *= xp.exp((-1j * gamma * jij) * (si * sj).astype(xp.float64))
    return sv


# ── The circuit ──────────────────────────────────────────────────────────────

def qaoa_statevector(
    n_qubits: int,
    diag: Any,
    gammas: Sequence[float],
    betas: Sequence[float],
    xp: Any = np,
    mode: str = "diagonal",
    couplings: Couplings | None = None,
    custatevec_ctx=None,
) -> Any:
    """Evolve |+⟩^⊗n through p alternating cost/mixer layers."""
    dim = 1 << n_qubits
    amp = 1.0 / np.sqrt(dim)
    sv = xp.full(dim, amp, dtype=xp.complex128)

    for gamma, beta in zip(gammas, betas):
        if mode == "gates":
            if couplings is None:
                raise ValueError("mode='gates' requires the couplings")
            apply_cost_gates(sv, n_qubits, couplings, float(gamma), xp)
        else:
            apply_cost_diagonal(sv, diag, float(gamma), xp)
        apply_mixer(sv, n_qubits, float(beta), xp, custatevec_ctx)

    return sv


def expectation(sv: Any, diag: Any, xp: Any = np) -> float:
    """⟨ψ|H_C|ψ⟩, exact — H_C is diagonal so this is a weighted probability sum."""
    probs = xp.abs(sv) ** 2
    return float(xp.sum(probs * diag))


def probabilities(sv: Any, xp: Any = np) -> Any:
    return xp.abs(sv) ** 2


def top_bitstrings(sv: Any, n_qubits: int, k: int = 10, xp: Any = np) -> list[tuple[str, float]]:
    """The k most probable measurement outcomes, as little-endian bitstrings."""
    probs = probabilities(sv, xp)
    k = min(k, probs.size)
    # argpartition is O(dim); a full sort of a 2^30 array is not affordable.
    part = xp.argpartition(probs, probs.size - k)[probs.size - k:]
    order = part[xp.argsort(probs[part])][::-1]
    idxs = [int(x) for x in (order.get() if hasattr(order, "get") else order)]
    return [(format(i, f"0{n_qubits}b"), float(probs[i])) for i in idxs]


# ── Optimisation ─────────────────────────────────────────────────────────────

@dataclass
class QAOAResult:
    n_qubits: int
    layers: int
    steps_run: int
    energy_history: list[float] = field(default_factory=list)
    best_energy: float = float("inf")
    best_params: list[float] = field(default_factory=list)
    top_states: list[tuple[str, float]] = field(default_factory=list)
    best_bitstring: str = ""
    seconds: float = 0.0
    seconds_per_eval: float = 0.0
    statevector_bytes: int = 0
    backend: str = "local"
    device: str = ""
    mode: str = "diagonal"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["top_states"] = [{"bitstring": b, "probability": p} for b, p in self.top_states]
        return d


def optimize_qaoa(
    n_qubits: int,
    couplings: Couplings,
    offset: float = 0.0,
    layers: int = 2,
    steps: int = 30,
    xp: Any = np,
    seed: int = 11,
    mode: str = "diagonal",
    custatevec_ctx=None,
    progress: Callable[[int, float], None] | None = None,
    top_k: int = 64,
) -> QAOAResult:
    """Run QAOA end to end and report both the answer and how it was reached.

    The optimiser is SciPy's COBYLA when available (derivative-free, which suits
    a landscape whose gradients are expensive and noisy) with a deterministic
    random-restart fallback so the demo never hard-depends on SciPy.

    `energy_history` records the best-so-far energy per step, so the convergence
    curve shown to an operator is monotone and reads as progress rather than as
    the optimiser's raw thrashing.
    """
    t0 = time.perf_counter()
    diag = cost_diagonal(n_qubits, couplings, offset, xp=xp)

    rng = np.random.default_rng(seed)
    p = int(layers)
    n_evals = 0

    def energy_of(params: np.ndarray, diag=diag) -> float:
        # `diag` is bound as a default argument, NOT captured from the enclosing
        # scope: the enclosing `diag` is deleted at the end of this function to
        # free 2ⁿ·8 bytes on the GPU, and a closure capture would make any later
        # call raise NameError. The default binding keeps the array alive exactly
        # as long as this function object.
        nonlocal n_evals
        n_evals += 1
        gammas, betas = params[:p], params[p:]
        sv = qaoa_statevector(
            n_qubits, diag, gammas, betas, xp=xp, mode=mode,
            couplings=couplings if mode == "gates" else None,
            custatevec_ctx=custatevec_ctx,
        )
        e = expectation(sv, diag, xp)
        del sv
        return e

    history: list[float] = []
    best_e, best_p = float("inf"), None

    def record(params: np.ndarray) -> float:
        """Evaluate, track the global best, and append best-so-far to history."""
        nonlocal best_e, best_p
        e = energy_of(params)
        if e < best_e:
            best_e, best_p = e, np.array(params, dtype=float)
        history.append(best_e)
        if progress is not None:
            progress(len(history), best_e)
        return e

    # γ scale is set by the SPREAD of the cost function, not by any single
    # coupling. exp(-iγH) separates basis states by relative phase γ·ΔH, so the
    # useful window is γ ~ 1/σ(H). Scaling by max|J| instead — the intuitive
    # choice — overshoots increasingly as the problem gets denser, because many
    # terms feed σ(H) while max|J| describes one. Measured on the dense 12-node
    # objective as normalised at the time (66 couplings, σ(H)≈3.5, max|J|≈2.5):
    # it searched γ up to 1.26 when the informative range ends near 0.45 — 2.8×
    # too wide — so most of a 30-step budget was spent in the over-rotated
    # regime that looks like noise. (On today's normalised objective the same
    # mistake is ~1.5–2×; see the Learn tab's measured σ(H)/max|J| table. It is
    # NOT √(term count) — that shortcut assumes equal-magnitude independent
    # terms and this objective's three terms are deliberately scaled apart.)
    sigma = float(xp.std(diag))
    sigma = sigma if sigma > 1e-9 else 1.0
    gamma_hi = float(np.pi / (2.0 * sigma))

    try:
        from scipy.optimize import minimize
        used = "layerwise-interp+cobyla"
    except Exception:
        minimize = None  # type: ignore[assignment]
        used = "layerwise-interp+random-restart"

    def _local_search(x0: np.ndarray, q: int, budget: int) -> tuple[np.ndarray, float]:
        """Optimise the 2q parameters of a q-layer circuit within `budget` evals."""
        local_best_e, local_best_x = float("inf"), np.array(x0, dtype=float)
        start = len(history)

        def obj(params: np.ndarray) -> float:
            nonlocal local_best_e, local_best_x
            e = record(np.asarray(params, dtype=float))
            if e < local_best_e:
                local_best_e, local_best_x = e, np.array(params, dtype=float)
            return e

        if minimize is not None:
            try:
                minimize(obj, x0, method="COBYLA",
                         options={"maxiter": budget, "rhobeg": 0.3, "tol": 1e-8})
            except Exception:
                pass
        while len(history) - start < budget:
            obj(local_best_x + rng.normal(0, 0.1, 2 * q))
        return local_best_x, local_best_e

    def _ramp(scale: float, q: int) -> np.ndarray:
        """Annealing-inspired linear-ramp schedule for q layers.

        QAOA at depth p approximates a Trotterised adiabatic sweep: the cost
        angle γ should grow across the layers while the mixer angle β shrinks.
        Seeding with that shape collapses the search to essentially ONE
        meaningful degree of freedom (how far to sweep), which is what makes a
        10–50 step budget viable at all.

        This replaced a layer-growing INTERP schedule that split the budget
        across p levels. With `steps` as low as 10 that left ~3 COBYLA
        iterations per level in up to 8 dimensions — the optimiser never moved
        off its starting point and returned γ≈0, i.e. the UNEVOLVED |+⟩ state,
        whose energy is exactly the Hamiltonian's offset. Runs looked converged
        and were measured at ratio 0.128 while doing no optimisation at all.
        """
        frac = (np.arange(q) + 0.5) / q
        gammas = scale * gamma_hi * frac
        betas = scale * (np.pi / 2) * (1.0 - frac)
        return np.concatenate([gammas, betas])

    # Stage 1 — scan the single ramp-scale parameter. Cheap and it reliably
    # lands in a basin where the cost unitary is actually doing something.
    scan = np.linspace(0.15, 1.0, min(7, max(3, steps // 4)))
    scored = [(record(_ramp(float(s), p)), _ramp(float(s), p)) for s in scan]
    x0 = min(scored, key=lambda t: t[0])[1]

    # Stage 2 — spend everything left refining all 2p parameters jointly.
    remaining = max(4, steps - len(history))
    current, _ = _local_search(x0, p, remaining)

    # Honour the requested step count so the convergence curve matches the UI.
    while len(history) < steps:
        record((best_p if best_p is not None else current) + rng.normal(0, 0.08, 2 * p))

    final_params = best_p if best_p is not None else current
    sv = qaoa_statevector(
        n_qubits, diag, final_params[:p], final_params[p:], xp=xp, mode=mode,
        couplings=couplings if mode == "gates" else None,
        custatevec_ctx=custatevec_ctx,
    )
    tops = top_bitstrings(sv, n_qubits, k=top_k, xp=xp)
    del sv, diag

    elapsed = time.perf_counter() - t0
    return QAOAResult(
        n_qubits=n_qubits,
        layers=p,
        steps_run=len(history),
        energy_history=[float(x) for x in history],
        best_energy=float(best_e),
        best_params=[float(x) for x in final_params],
        top_states=tops,
        best_bitstring=tops[0][0] if tops else "",
        seconds=elapsed,
        seconds_per_eval=elapsed / max(1, n_evals),
        statevector_bytes=(1 << n_qubits) * 16,
        mode=mode,
        notes=[f"optimizer={used}", f"energy_evaluations={n_evals}"],
    )


def verify_equivalence(
    n_qubits: int, couplings: Couplings, offset: float, layers: int = 2, xp: Any = np
) -> dict:
    """Prove the fast diagonal path equals gate-by-gate RZZ application.

    Returns the max amplitude deviation between the two. Exposed in the UI so
    the optimisation is auditable rather than asserted.
    """
    rng = np.random.default_rng(3)
    gammas = rng.uniform(0, 0.7, layers)
    betas = rng.uniform(0, np.pi / 2, layers)
    diag = cost_diagonal(n_qubits, couplings, offset, xp=xp)

    a = qaoa_statevector(n_qubits, diag, gammas, betas, xp=xp, mode="diagonal")
    b = qaoa_statevector(
        n_qubits, diag, gammas, betas, xp=xp, mode="gates", couplings=couplings
    )
    # The gate path omits the constant offset phase, which is unobservable.
    phase = xp.exp(-1j * float(np.sum(gammas)) * float(offset))
    dev = xp.max(xp.abs(a - b * phase))
    dev = float(dev.get() if hasattr(dev, "get") else dev)
    return {
        "n_qubits": n_qubits,
        "layers": int(layers),
        "max_amplitude_deviation": dev,
        "equivalent": dev < 1e-9,
    }
