"""Finite shots and device noise — the two realities the ideal simulation skips.

The clean path in `qaoa_core` reads ⟨H⟩ exactly out of the statevector. No
physical quantum computer can do that, and pretending otherwise is what makes a
demo look easy. This module adds the two things that make it hard:

  1. **Finite shots.** A real device returns samples, not expectations. You run
     the circuit N times, histogram the bitstrings, and estimate ⟨H⟩ from that.
     The estimate carries statistical error ~σ(H)/√N, which lands directly in
     the classical optimiser's objective — it is now searching for a minimum on
     a surface that jitters every time it looks.

  2. **Device noise.** Gates misfire, qubits decohere. Modelling that requires
     tracking a DENSITY MATRIX ρ rather than a statevector ψ, because the system
     is now in a statistical mixture rather than a pure state.

── Why noise squares the memory, concretely ────────────────────────────────
A statevector is 2^n amplitudes. A density matrix is 2^n × 2^n = **2^(2n)**.

    12 qubits →   256 MB          (statevector: 64 KB)
    14 qubits →   4.0 GB
    15 qubits →    16 GB          — the same memory as a 30-qubit statevector
    16 qubits →    64 GB

That is the whole argument for memory capacity in one table, and this module
makes it measurable rather than asserted: run the same problem clean and noisy
on the same box and watch the ceiling halve.

The noise model is **per-qubit depolarising** applied after each QAOA layer —
the standard first-order model. It is not a device-calibrated model (no T1/T2,
no gate-specific error rates, no crosstalk, no readout error), and it should not
be presented as one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.simulation import qaoa_core


def density_matrix_bytes(n_qubits: int) -> int:
    """complex128 density matrix: 2^n × 2^n × 16 bytes."""
    return (1 << (2 * n_qubits)) * 16


def max_noisy_qubits(free_bytes: int, safety: float = 0.5, working: float = 2.2) -> int:
    """Largest n whose density matrix plus scratch fits in `free_bytes`.

    `working` covers the Pauli-conjugation temporaries the depolarising channel
    needs; the channel cannot be done fully in place.
    """
    budget = free_bytes * safety
    n = 0
    while n < 24 and density_matrix_bytes(n + 1) * working <= budget:
        n += 1
    return n


# ── Finite-shot estimation ───────────────────────────────────────────────────

def sample_expectation(
    probs: Any, diag: Any, shots: int, rng: np.random.Generator, xp: Any = np
) -> tuple[float, float]:
    """Estimate ⟨H⟩ from `shots` measurements. Returns (estimate, standard error).

    Samples bitstring indices from the true distribution, then averages the cost
    of what came back — exactly what you get off a real device, and nothing more.
    """
    p = probs.get() if hasattr(probs, "get") else np.asarray(probs)
    d = diag.get() if hasattr(diag, "get") else np.asarray(diag)

    p = np.maximum(p, 0.0)
    total = p.sum()
    if total <= 0:
        return float("nan"), float("nan")
    p = p / total

    idx = rng.choice(p.size, size=int(shots), p=p)
    vals = d[idx]
    est = float(vals.mean())
    # Standard error of the mean — how much of the wobble is just the shot count.
    sem = float(vals.std(ddof=1) / np.sqrt(shots)) if shots > 1 else float("inf")
    return est, sem


# ── Density-matrix evolution ─────────────────────────────────────────────────

def _rho_apply_1q(rho: Any, n: int, t: int, m: Any, xp: Any) -> Any:
    """ρ → A_t ρ A_t† for a 2×2 matrix `m` acting on qubit t.

    Applied as two passes over ρ — once on the row index, once on the column —
    using the same stride reshape as the statevector path. Avoids ever forming
    the 2^n × 2^n Kronecker product of the operator, which would be absurd.
    """
    dim = 1 << n
    low, high = 1 << t, 1 << (n - t - 1)

    # Rows: view as (high, 2, low, dim)
    v = rho.reshape(high, 2, low, dim)
    a0 = v[:, 0, :, :].copy()
    a1 = v[:, 1, :, :].copy()
    v[:, 0, :, :] = m[0, 0] * a0 + m[0, 1] * a1
    v[:, 1, :, :] = m[1, 0] * a0 + m[1, 1] * a1
    del a0, a1

    # Columns: conjugate transpose of the same operator
    v = rho.reshape(dim, high, 2, low)
    b0 = v[:, :, 0, :].copy()
    b1 = v[:, :, 1, :].copy()
    mc = xp.conj(m)
    v[:, :, 0, :] = mc[0, 0] * b0 + mc[0, 1] * b1
    v[:, :, 1, :] = mc[1, 0] * b0 + mc[1, 1] * b1
    del b0, b1
    return rho


def depolarize(rho: Any, n: int, p: float, xp: Any) -> Any:
    """Per-qubit depolarising channel: ρ → (1-p)ρ + (p/3)(XρX + YρY + ZρZ).

    The standard first-order error model — applied in CLOSED FORM, not as three
    explicit Pauli conjugations. The single-qubit identity
    ρ + XρX + YρY + ZρZ = 2·(I ⊗ Tr_t ρ) collapses the channel to block
    arithmetic on qubit t's 2×2 row/column structure:

        B00 → (1−2p/3)·B00 + (2p/3)·B11      populations mix toward each other
        B11 → (2p/3)·B00 + (1−2p/3)·B11
        B01, B10 → (1−4p/3)·B01, B10         coherences damp

    Same channel, exactly (verified against the conjugation form at 1e-16).
    The literal implementation copied the full ρ four times per qubit per
    layer — at 14 qubits that is 4 GB per copy and was the dominant cost of
    noisy runs. This form touches ρ once per qubit with one quarter-size temp.
    """
    if p <= 0:
        return rho
    a = 1.0 - 2.0 * p / 3.0     # diagonal-block self weight
    b = 2.0 * p / 3.0           # diagonal-block exchange weight
    c = 1.0 - 4.0 * p / 3.0     # coherence damping

    for t in range(n):
        low, high = 1 << t, 1 << (n - t - 1)
        v = rho.reshape(high, 2, low, high, 2, low)
        b00 = v[:, 0, :, :, 0, :]
        b11 = v[:, 1, :, :, 1, :]
        tmp = b00.copy()
        b00 *= a
        b00 += b * b11
        b11 *= a
        b11 += b * tmp
        del tmp
        v[:, 0, :, :, 1, :] *= c
        v[:, 1, :, :, 0, :] *= c
    return rho


def qaoa_density_matrix(
    n_qubits: int,
    diag: Any,
    gammas,
    betas,
    depolarizing: float = 0.0,
    xp: Any = np,
) -> Any:
    """Evolve ρ through p QAOA layers with depolarising noise after each."""
    dim = 1 << n_qubits
    amp = 1.0 / dim                      # |+><+| has every entry equal to 1/2^n
    rho = xp.full((dim, dim), amp, dtype=xp.complex128)

    for gamma, beta in zip(gammas, betas, strict=True):
        # Diagonal cost unitary on ρ: ρ_ij → e^{-iγ(d_i - d_j)} ρ_ij. An outer
        # product of phases, not a matrix multiply.
        ph = xp.exp((-1j * float(gamma)) * diag)
        rho *= ph[:, None]
        rho *= xp.conj(ph)[None, :]
        del ph

        c, s = float(np.cos(beta)), float(np.sin(beta))
        m = xp.array([[c, -1j * s], [-1j * s, c]], dtype=xp.complex128)
        for t in range(n_qubits):
            _rho_apply_1q(rho, n_qubits, t, m, xp)

        rho = depolarize(rho, n_qubits, depolarizing, xp)

    return rho


def density_probabilities(rho: Any, xp: Any = np) -> Any:
    """Measurement distribution = the diagonal of ρ."""
    return xp.real(xp.diagonal(rho))


def density_expectation(rho: Any, diag: Any, xp: Any = np) -> float:
    """⟨H⟩ = Tr(ρH) — and for diagonal H that is just diag(ρ)·H."""
    return float(xp.sum(density_probabilities(rho, xp) * diag))


def purity(rho: Any, xp: Any = np) -> float:
    """Tr(ρ²) — 1.0 for a pure state, 1/2^n for maximally mixed.

    The single most legible number for "how much has noise destroyed here".
    """
    return float(xp.real(xp.sum(rho * rho.T)))


# ── The comparison the demo is actually about ────────────────────────────────

@dataclass
class RealismResult:
    """One run under a given set of physical realities."""

    label: str
    energy: float
    best_bitstring: str = ""
    seconds: float = 0.0
    memory_bytes: int = 0
    shots: int | None = None
    shot_error: float | None = None
    depolarizing: float | None = None
    purity: float | None = None
    top_states: list = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def compare_realism(
    n_qubits: int,
    couplings,
    offset: float,
    gammas,
    betas,
    shots: int = 1024,
    depolarizing: float = 0.01,
    xp: Any = np,
    seed: int = 5,
) -> list[RealismResult]:
    """Run the SAME circuit three ways: ideal, finite-shot, and noisy.

    Same parameters, same problem — the only thing that changes is how much
    physical reality is admitted. That is the comparison that shows why
    developing on hardware you can afford to simulate matters.
    """
    rng = np.random.default_rng(seed)
    out: list[RealismResult] = []

    # 1. Ideal — exact expectation from the statevector.
    t0 = time.perf_counter()
    diag = qaoa_core.cost_diagonal(n_qubits, couplings, offset, xp=xp)
    sv = qaoa_core.qaoa_statevector(n_qubits, diag, gammas, betas, xp=xp)
    probs = qaoa_core.probabilities(sv, xp)
    e_ideal = qaoa_core.expectation(sv, diag, xp)
    tops = qaoa_core.top_bitstrings(sv, n_qubits, k=8, xp=xp)
    out.append(RealismResult(
        label="Ideal", energy=e_ideal, best_bitstring=tops[0][0] if tops else "",
        seconds=time.perf_counter() - t0, memory_bytes=(1 << n_qubits) * 16,
        top_states=tops, purity=1.0,
        note="Exact expectation read straight out of the statevector. "
             "No physical device can do this."))

    # 2. Finite shots — same state, but you only get samples off it.
    t0 = time.perf_counter()
    est, sem = sample_expectation(probs, diag, shots, rng, xp)
    out.append(RealismResult(
        label=f"{shots:,} shots", energy=est, shots=shots, shot_error=sem,
        seconds=time.perf_counter() - t0, memory_bytes=(1 << n_qubits) * 16,
        purity=1.0,
        note=f"Estimated from {shots:,} measurements of a perfect device. "
             f"Statistical error alone is ±{sem:.3f}."))
    del sv, probs

    # 3. Noisy — density matrix, and the memory bill that comes with it.
    t0 = time.perf_counter()
    rho = qaoa_density_matrix(n_qubits, diag, gammas, betas,
                              depolarizing=depolarizing, xp=xp)
    e_noisy = density_expectation(rho, diag, xp)
    pur = purity(rho, xp)
    dprobs = density_probabilities(rho, xp)
    k = min(8, dprobs.size)
    part = xp.argpartition(dprobs, dprobs.size - k)[dprobs.size - k:]
    order = part[xp.argsort(dprobs[part])][::-1]
    idxs = [int(x) for x in (order.get() if hasattr(order, "get") else order)]
    ntops = [(format(i, f"0{n_qubits}b"), float(dprobs[i])) for i in idxs]
    out.append(RealismResult(
        label=f"Noisy ({depolarizing * 100:.1f}% / qubit / layer)",
        energy=e_noisy, best_bitstring=ntops[0][0] if ntops else "",
        seconds=time.perf_counter() - t0,
        memory_bytes=density_matrix_bytes(n_qubits),
        depolarizing=depolarizing, purity=pur, top_states=ntops,
        note=f"Density-matrix simulation with per-qubit depolarising noise. "
             f"Purity fell to {pur:.3f} (1.0 is a perfect state). "
             f"Memory cost is 2^(2n), not 2^n."))
    del rho, diag
    return out


# ── Quantum trajectories — noise without the density matrix ──────────────────
#
# WHAT THIS IS, in one paragraph.
#
# A density matrix tracks every possible noisy outcome simultaneously, and pays
# 2^(2n) memory to do it. A TRAJECTORY does the opposite: run the circuit ONCE
# as an ordinary statevector, and each time noise would act, roll dice and apply
# one specific random error. That single run is wrong -- it is one arbitrary way
# the noise could have landed. But run it many times with different dice and
# average the results, and you converge on exactly what the density matrix would
# have told you.
#
# The trade is memory for repetition. Each trajectory costs 2^n instead of
# 2^(2n), so noisy simulation reaches roughly the same qubit count as clean
# simulation. What you give up is exactness: the answer carries statistical
# error that shrinks as 1/sqrt(N_trajectories), so halving the error costs four
# times the runs. Trajectories are independent, so that cost is pure throughput
# -- it parallelises perfectly across GPUs, where the density matrix needs one
# machine big enough to hold the whole thing.
#
# WHY IT IS VALID for depolarising noise. The channel
#     rho -> (1-p) rho + (p/3)(X rho X + Y rho Y + Z rho Z)
# is already written as a probabilistic mixture. Applying I with probability
# (1-p) and each Pauli with probability p/3, then averaging over runs,
# reproduces that expression by definition of an average. This is the standard
# Monte Carlo wavefunction / quantum trajectory method.

_PAULI = {
    "X": (0.0 + 0j, 1.0 + 0j, 1.0 + 0j, 0.0 + 0j),
    "Y": (0.0 + 0j, -1j, 1j, 0.0 + 0j),
    "Z": (1.0 + 0j, 0.0 + 0j, 0.0 + 0j, -1.0 + 0j),
}


def _apply_pauli(sv: Any, n: int, t: int, which: str, xp: Any) -> None:
    m00, m01, m10, m11 = _PAULI[which]
    qaoa_core._apply_1q(sv, n, t, m00, m01, m10, m11, xp)


def qaoa_trajectory(
    n_qubits: int, diag: Any, gammas, betas, depolarizing: float,
    rng: np.random.Generator, xp: Any = np, custatevec_ctx=None,
) -> Any:
    """One noisy run: the QAOA circuit with randomly-sampled Pauli errors.

    Returns a statevector, not a density matrix. It is a single sample from the
    noisy distribution and is not meaningful alone — average many.
    """
    dim = 1 << n_qubits
    sv = xp.full(dim, 1.0 / np.sqrt(dim), dtype=xp.complex128)

    for gamma, beta in zip(gammas, betas, strict=True):
        qaoa_core.apply_cost_diagonal(sv, diag, float(gamma), xp)
        qaoa_core.apply_mixer(sv, n_qubits, float(beta), xp, custatevec_ctx)

        if depolarizing > 0:
            # One die roll per qubit per layer: nothing with probability 1-p,
            # otherwise one of X, Y, Z with probability p/3 each.
            hits = rng.random(n_qubits) < depolarizing
            for t in np.nonzero(hits)[0]:
                _apply_pauli(sv, n_qubits, int(t), "XYZ"[rng.integers(3)], xp)
    return sv


@dataclass
class TrajectoryResult:
    n_qubits: int
    trajectories: int
    depolarizing: float
    energy: float
    energy_stderr: float
    running_mean: list = field(default_factory=list)   # convergence trace
    running_stderr: list = field(default_factory=list)
    probs: Any = None
    seconds: float = 0.0
    memory_bytes: int = 0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "probs"}
        return d


def qaoa_trajectories(
    n_qubits: int, couplings, offset: float, gammas, betas,
    depolarizing: float = 0.02, trajectories: int = 200,
    xp: Any = np, seed: int = 17, custatevec_ctx=None,
    keep_probs: bool = True,
) -> TrajectoryResult:
    """Average many noisy runs. Memory is 2^n, not 2^(2n).

    Also records the running mean and standard error after each trajectory, so
    the convergence toward the exact answer can be shown rather than asserted.
    """
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    diag = qaoa_core.cost_diagonal(n_qubits, couplings, offset, xp=xp)

    acc = xp.zeros(1 << n_qubits, dtype=xp.float64) if keep_probs else None
    energies: list[float] = []
    run_mean, run_err = [], []

    for k in range(trajectories):
        sv = qaoa_trajectory(n_qubits, diag, gammas, betas, depolarizing,
                             rng, xp, custatevec_ctx)
        p = qaoa_core.probabilities(sv, xp)
        energies.append(float(xp.sum(p * diag)))
        if acc is not None:
            acc += p
        del sv, p

        e = np.asarray(energies)
        run_mean.append(float(e.mean()))
        run_err.append(float(e.std(ddof=1) / np.sqrt(k + 1)) if k else float("nan"))

    probs = (acc / trajectories) if acc is not None else None
    del acc, diag

    return TrajectoryResult(
        n_qubits=n_qubits, trajectories=trajectories, depolarizing=depolarizing,
        energy=run_mean[-1], energy_stderr=run_err[-1],
        running_mean=run_mean, running_stderr=run_err, probs=probs,
        seconds=time.perf_counter() - t0,
        memory_bytes=(1 << n_qubits) * 16,
    )
