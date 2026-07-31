---
id: note-04-noise-without-the-density-matrix
type: note
title: "How do you simulate noise without paying 2^(2n)?"
date: 2026-07-31
audience: [scientist, engineer, leader]
tags: [noise, trajectories, memory-wall, simulation]
prerequisites: "Note 01 for the density-matrix cost."
one_line: "Modelling noise exactly needs a density matrix, which squares the memory and caps a 128 GB machine at 14 qubits. Quantum trajectories replace one exact object with many random pure-state runs averaged together, cost 2^n instead of 2^(2n), reaching 30 qubits on the same hardware. Measured: at 30 qubits the exact method needs 16 exabytes and the trajectory method needs 16 GB, for about 0.2% statistical error."
---

# How do you simulate noise without paying 2^(2n)?

Note 01 gave the uncomfortable number: on a 128 GB machine, exact noisy simulation
reaches **14 qubits** where clean simulation reaches 30. Squaring the memory is
what a density matrix costs, and it arrives early enough to stop most useful work.

That number is the limit of the **exact** method, not of noisy simulation. Production
noise studies mostly do not use density matrices.

## The alternative: run it wrong, many times

A density matrix tracks every possible thing the noise could have done, simultaneously,
along with how likely each is. A **trajectory** does the opposite. Run the circuit once
as an ordinary state vector and, wherever noise would act, roll dice and apply one
specific randomly-chosen error. That single run is wrong — it is one arbitrary way the
noise could have landed. Run it many times with different dice, average the results, and
you converge on exactly what the density matrix would have told you.

Each run is a state vector, so each costs **2^n**, not 2^(2n).

## Why it converges, exactly

This is not an approximation of the physics. The depolarising channel is *already*
written as a probabilistic mixture:

```
ρ  →  (1−p)·ρ  +  (p/3)·(XρX + YρY + ZρZ)
```

Read that as instructions: with probability (1−p) do nothing, and with probability p/3
apply each of X, Y, or Z. Sampling those choices and averaging over runs reproduces the
right-hand side *by the definition of an average*. The technique is the Monte Carlo
wavefunction, or quantum trajectory, method.

What you give up is exactness. The estimate carries statistical error that falls as
**1/√N**, so halving the uncertainty costs four times the runs.

## Verified before it was believed

Against an exact density matrix on an 8-qubit instance, depolarising 3% per qubit per
layer:

| trajectories | estimate | error vs exact |
|---|---|---|
| 25 | 1.35250 | 0.017 |
| 100 | 1.38454 | 0.015 |
| 400 | 1.37773 | 0.008 |
| 1,600 | 1.37007 | **0.0003** |
| *exact* | *1.36978* | — |

The error halves each time the run count quadruples, which is the 1/√N it should be.

## Measured at scale

Dell Pro Max GB10, 128 GB unified, 2026-07-30. Same noise model, same machine, 40
trajectories:

| qubits | exact (density matrix) | 40 trajectories |
|---|---|---|
| 14 | 4.0 GB · 17.6 s · ⟨H⟩ = 3.3964 | 0.004 GB · 0.02 s · ⟨H⟩ = 3.4080 ± 0.0107 |
| 20 | 16 TB — will not fit | 0.02 GB · 0.30 s |
| 26 | 64 PB — will not fit | 1.0 GB · 34.8 s |
| 30 | **16 exabytes** — will not fit | **16 GB** · 643 s |

Density-matrix sizes are exact arithmetic — 2<sup>2n</sup> complex amplitudes at 16 bytes
each. Sizes throughout this project are binary, as memory is always sold and addressed:
1 GB = 2<sup>30</sup> bytes. The trajectory column is measured allocation, which is why it
does not divide out to the same clean powers.

The 14-qubit row is the one that licenses the rest. It is the largest problem where
*both* methods run, and they agree inside one standard error. Every row below it has
only one method available, so the agreement above is the evidence that the cheap method
is measuring the same thing.

At 30 qubits the exact approach would need sixteen **exabytes** of memory. The dice approach
needs sixteen gigabytes and eleven minutes, and is wrong by about 0.2%.

## What follows

For **algorithm design**: choose the method by what the question needs. Validating an
error-mitigation strategy wants exactness, because a statistical wobble can hide the
effect being measured. Asking whether an algorithm survives realistic noise at realistic
size wants trajectories, because 1% is fine and 14 qubits is not.

For **infrastructure**, this is the sharper point. The two methods stress different
resources:

- Density matrix — bound by the **size of one coherent memory domain**. It is a single
  object; it cannot be split across a slow link.
- Trajectories — bound by **GPU count**. The runs are independent, so the workload
  parallelises perfectly and never needs the GPUs to talk to each other.

A machine that is poor at one can be excellent at the other. Note 05 works that through
against real hardware.

## Limits of this note

The unravelling here covers **depolarising** noise, which is separable into Pauli
channels and therefore trivially samplable. Amplitude damping and other non-unital
channels need a different unravelling (jump operators with a non-Hermitian effective
Hamiltonian); the principle carries, the implementation does not.

The trajectory count needed for a target error depends on the variance of the observable,
which is problem-specific. The 1/√N scaling is general; the constant is not.

Nothing here says trajectories are always preferable. They are cheaper in memory and more
expensive in time, and they answer a slightly different question — an estimate with error
bars rather than a number.
