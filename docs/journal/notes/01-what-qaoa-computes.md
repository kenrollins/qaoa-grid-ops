---
id: note-01-what-qaoa-computes
type: note
title: "What QAOA actually computes, and what simulating it leaves out"
date: 2026-07-30
audience: [scientist, engineer, leader]
tags: [qaoa, noise, memory-wall, simulation]
prerequisites: "None. Linear algebra helps but is not assumed."
one_line: "QAOA prepares a superposition over all candidate solutions and uses interference to concentrate probability on good ones. Simulating it faithfully requires modelling finite measurement statistics and device noise; each addition changes the classical cost, and noise changes it from 2^n to 2^(2n). On a 128 GB machine we measured the consequence directly: 30 qubits clean, 14 qubits noisy."
---

# What QAOA actually computes, and what simulating it leaves out

The Quantum Approximate Optimization Algorithm (QAOA) is the most widely
attempted near-term quantum algorithm for combinatorial optimization. Evaluating
whether it is useful — and what infrastructure its development requires — means
being precise about what it computes and, equally, what a classical simulation
of it silently omits.

## The problem it takes

QAOA operates on problems expressible as **QUBO** (Quadratic Unconstrained
Binary Optimization): choose a value of 0 or 1 for each of n variables so as to
minimise a cost that depends on individual choices and on pairs of choices.

Substituting spin variables s_i = 1 - 2x_i, mapping {0,1} to {+1,-1}, gives the
equivalent **Ising form**:

```
H(s) = offset + Σ_(i<j) J_ij · s_i · s_j
```

where J_ij is the coupling between variables i and j. In the demonstrator this
project is built around, each variable is a substation and its value names which
of two electrical islands the substation joins.

The key property: H is **diagonal** in the computational basis. Every candidate
solution corresponds to one basis state, and H assigns it a number. There are 2^n
candidates.

## The mechanism

One qubit is assigned per variable. A qubit is a two-state quantum system whose
state is described by two complex amplitudes rather than a single bit; n qubits
require 2^n amplitudes, one per possible bitstring.

QAOA runs three stages.

**1. Superposition.** A Hadamard gate on each qubit produces a state in which
every one of the 2^n candidate solutions carries equal amplitude:

```
|ψ₀⟩ = (1/√2^n) Σ_x |x⟩
```

Nothing has been decided; measuring here returns a uniformly random candidate.

**2. p alternating layers.** Each layer applies two operators.

The **cost operator** exp(-i·γ·H) multiplies each candidate's amplitude by a
phase proportional to its cost. Because H is diagonal, this changes no
probabilities — only relative phases. Good and bad solutions are now
distinguishable in phase but not yet in likelihood.

The **mixer operator** exp(-i·β·Σ X_i) rotates each qubit about the X axis,
which couples neighbouring bitstrings and causes the phases set by the cost
operator to interfere. Constructive interference on low-cost states and
destructive interference on high-cost states converts phase structure into
probability structure.

Repeating for p layers, with distinct angles (γ_k, β_k) per layer, deepens the
concentration.

**3. Measurement and classical optimization.** Measuring returns one bitstring,
sampled with the probability the circuit has arranged. The expectation
⟨ψ|H|ψ⟩ is fed to a classical optimizer that adjusts the 2p angles and the
circuit is rerun. QAOA is therefore a **hybrid** algorithm: a quantum
subroutine inside a classical optimization loop.

The physical intuition is a Trotterised adiabatic sweep — γ should generally
rise across layers while β falls, tracing an approximate path from an easy
starting Hamiltonian to the problem Hamiltonian. That structure has practical
consequences for parameter search (note 02).

## What a simulation leaves out

Simulating QAOA on classical hardware means storing and evolving the 2^n
amplitudes explicitly. Done that way, three things become available that no
physical quantum computer offers, and each omission matters.

**Exact expectation values.** From a stored statevector, ⟨H⟩ = Σ_x |ψ(x)|²·H(x)
is computed exactly. A physical device returns one bitstring per execution; the
expectation must be estimated from many runs, with statistical error scaling as
σ(H)/√N for N measurements. That error enters the classical optimizer's
objective, which is then minimising a surface that moves each time it is
sampled.

**Noiseless evolution.** Physical gates misfire and qubits decohere. Representing
a system subject to noise requires a **density matrix** ρ — a 2^n × 2^n matrix
rather than a 2^n vector — because the system is in a statistical mixture of
states rather than a single pure state. This is the dominant cost change:
storage goes from 2^n to **2^(2n)**.

**Arbitrary connectivity.** A simulated circuit may couple any qubit to any
other. Physical devices connect each qubit to a few neighbours, so an
all-to-all Hamiltonian must be compiled onto the hardware graph using SWAP
operations, typically multiplying circuit depth by one to two orders of
magnitude.

## Worked example: the cost of admitting reality

Measured on a Dell Pro Max with GB10 Grace Blackwell (128 GB unified memory),
2026-07-30, 12-qubit dense problem, p=2, at optimized angles. Noise model is
per-qubit depolarizing after each layer.

| Regime | ⟨H⟩ | State size | Purity |
|---|---|---|---|
| Ideal statevector | 1.343 | 64 KB | 1.000 |
| 1,024 measurements | 1.319 | 64 KB | 1.000 |
| Depolarizing, 2% per qubit per layer | 1.388 | 256 MB | 0.500 |

Purity, Tr(ρ²), is 1.0 for a pure state and 1/2^n for a maximally mixed one; it
is the most legible single measure of how much noise has degraded the
computation. At 2% error per qubit per layer, half the state's coherence is gone.

The device-reported ceilings on the same machine, queried live from free memory:

```
GET /noise/ceiling
{"max_qubits_clean": 30, "max_qubits_noisy": 14}
```

!!! quote ""
    The same machine simulates 30 qubits of ideal quantum mechanics, or
    14 qubits of the quantum mechanics that actually happens.

A caution that follows directly from the mechanism: **under depolarizing noise
⟨H⟩ moves toward the mean of H**, because the state approaches maximally mixed.
Sweeping error from 0% to 12% on a 10-qubit instance, we measured ⟨H⟩ falling
monotonically from 2.888 to 2.620 while purity collapsed from 1.000 to 0.050. If
the Hamiltonian's mean happens to lie below the value QAOA achieves, energy
therefore *improves* as the computation is destroyed. Energy alone is not a
sufficient metric under noise; purity, or the probability assigned to known-good
solutions, must be reported alongside it.

## What follows

For **algorithm design**: results obtained in ideal simulation are an upper
bound, not a prediction. Error-mitigation strategies cannot be calibrated
without a noiseless reference to calibrate against, which means noisy and ideal
simulation are needed together, not as alternatives.

For **infrastructure**: the binding constraint is memory, and which curve you
are on depends on whether noise is modelled. Clean simulation doubles per qubit;
noisy simulation quadruples. A machine sized for 30 clean qubits is a machine
sized for roughly 14 noisy ones.

For **evaluating claims**: a stated qubit count is meaningless without stating
the simulation method and whether noise was included. The same hardware supports
very different numbers.

## Limits of this note

The noise model is per-qubit depolarizing, the standard first-order model. It is
not device-calibrated: no T1/T2 relaxation times, no gate-specific error rates,
no crosstalk, no readout error. Real devices deviate from depolarizing behaviour
in ways that matter for mitigation strategy design.

Full-density-matrix simulation is also not the only option. Tensor-network
methods represent states in a compressed form and reach far larger systems when
entanglement is limited; noisy QAOA circuits have been sampled at 476 qubits by
such methods. The 2^(2n) figure here is the cost of *exact, general* density
matrix simulation, which is what validating an algorithm against ground truth
requires.

## References

- Farhi, Goldstone, Gutmann, *A Quantum Approximate Optimization Algorithm*, arXiv:1411.4028 — the original construction described above.
- Zhou et al., *QAOA: Performance, Mechanism, and Implementation on Near-Term Devices*, arXiv:1812.01041 — the adiabatic framing and its parameter consequences.
- *Pilot-Wave Simulator*, Quantum 10, 2173 (2026) — tensor-network sampling of noisy QAOA to 476 qubits; the boundary on this note's memory claim.
