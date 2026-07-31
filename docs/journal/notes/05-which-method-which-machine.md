---
id: note-05-which-method-which-machine
type: note
title: "Which simulation method needs which machine?"
date: 2026-07-31
audience: [scientist, engineer, leader]
tags: [memory-wall, hardware, simulation, procurement]
prerequisites: "Notes 01 and 04."
one_line: "For state-vector simulation the sizing figure is the largest COHERENT memory domain, not a system's total GPU memory — a state vector cannot straddle a slow link. Which method you run decides which machine wins, and the ranking inverts: the platform with the smallest coherent domain in a portfolio can be the best one for noisy work, because trajectories are bound by GPU count rather than domain size."
---

# Which simulation method needs which machine?

There is no single best platform for quantum circuit simulation, because there is no
single method. Each way of simulating stresses a different part of a machine, and the
ranking of platforms **inverts** depending on which one you are running. Sizing this
workload by "total GPU memory" produces the wrong answer roughly half the time.

## The figure that matters is the coherent domain

A state vector of n qubits is one object of 2ⁿ amplitudes, and **every gate touches all
of it**. A gate acting on a high-order qubit requires an all-to-all exchange across
whatever holds the state. So the simulation runs at the speed of the *worst* link inside
the memory domain, and a state vector that has to straddle a slow link does not merely
run slower — it stops being worth running.

The consequence is that a machine's honest capacity is **the largest tightly-coupled
memory domain it can form**, not the sum of its accelerators.

Concretely, from the Dell PowerEdge sourcebooks and GPU Qualification Matrix:

- Inside an NVLink domain: **900 GB/s** (4th gen)
- Across PCIe Gen5 x16 between domains: **128 GB/s**

A **7x** cliff. Which produces this, which is the single most useful line in the whole
analysis:

> An 8× RTX PRO 6000 node holds **768 GB** of GPU memory and simulates **32 qubits**.
> A 4-GPU H200 NVL island holds **564 GB** and simulates **35**.
> Less total memory, three more qubits, because the memory is coherent.

## The methods, and what each one is bound by

| Method | What it computes | Binding constraint | Wants |
|---|---|---|---|
| **Exact state vector** | the ideal circuit, every amplitude | largest coherent domain, 2ⁿ | one big NVLink domain |
| **Density matrix** | noise, exactly | same domain, but **2^(2n)** | the biggest domain available |
| **Trajectories** | noise, approximately | **GPU count** — one run per GPU | many independent GPUs |
| **Tensor networks** | structured, low-entanglement circuits | entanglement, not qubit count | circuit-dependent |

## The inversion, worked

Take an XE7745 with 8× RTX PRO 6000 Blackwell. Dell documents **no NVLink** for that GPU
on that platform: eight separate PCIe Gen5 devices. On the coherent-domain metric it is
the weakest configuration in the portfolio — 96 GB, about **32 qubits**, no better than a
single card.

Now run trajectory-based noise instead (note 04). Each run is an independent state vector
that fits on one GPU, so the same box becomes **eight simultaneous 32-qubit noisy
workers** — and noisy simulation at scale is precisely the study that consumes thousands
of independent runs. For that job it beats a single 4-GPU NVLink island outright.

The worst platform for one method is among the best for another.

## The portfolio, by coherent domain

| Platform | Largest coherent domain | Domain memory | Clean qubits | Noisy (exact) | Independent domains |
|---|---|---|---|---|---|
| Dell Pro Max GB10 | unified memory | 128 GB | 33* | 16* | 1 |
| XE7745/7740 · 8× RTX PRO 6000 | 1 GPU (no NVLink) | 96 GB | 32 | 16 | **8** |
| XE7740 · 8× H100 NVL | 2-GPU NVL2 | 188 GB | 33 | 16 | 4 |
| XE7745 · 8× H200 NVL | 4-GPU NVL4 | 564 GB | 35 | 17 | 2 |
| XE9780 · 8× HGX B200 | 8-GPU NVSwitch | 1.44 TB | 36 | 18 | 1 |
| XE9780/9785 · 8× HGX B300 NVL8 | 8-GPU NVSwitch | 2.16 TB | 37 | 18 | 1 |
| XE9785 · 8× AMD MI355X | 8-GPU Infinity Fabric | 2.30 TB | 37 | 18 | 1 |
| XE9712 · GB300 NVL72 | 72-GPU unified pool | 20.7 TB | 40 | 20 | 1 |

\* The GB10 row is arithmetic; **measured** on our unit it is 30 clean and 14 noisy,
because free memory is shared with whatever else is resident. Every other row is
arithmetic from published domain capacity and has not been measured here.

The practical breakpoints are 2 GPUs (H100 NVL), 4 (H200 NVL), 8 (HGX B300 NVL8), then
72 (GB300 NVL72).

## What follows

**Ask what question you are answering before asking what to buy.** Developing and
validating an algorithm against exact answers is a coherent-domain problem and lives
comfortably on a workstation. Mapping parameter landscapes, running noise ensembles, and
comparing ansätze are throughput problems and want device count. Most programmes need
both, and they are not the same purchase.

**The qubit column is brutal and should be shown as such.** Going from a 128 GB
workstation to a 20.7 TB rack — 160× the memory — buys **seven** clean qubits. If the
goal is qubit count, the mathematics does not support the spend. The defensible
justifications are noisy validation, which is otherwise impossible at useful sizes, and
iteration velocity.

**Interrogate any quoted qubit number.** It is meaningless without the method, the
precision, and whether noise was modelled. The same hardware honestly supports very
different figures.

## Limits of this note

Capacities are nameplate figures from vendor documentation; only the GB10 row was
measured by us. Two discrepancies are unresolved in Dell's own materials: HGX B300 NVL8
is listed at 270 GB per GPU where Blackwell Ultra is commonly quoted at 288, and a GPU
qualification source shows 279 GB for GB300 NVL72 against the XE9712 spec sheet's 288.

The qubit figures assume complex128 and a single state vector with no working-set
overhead. Real simulators need scratch; our own measured ceilings sit 2–3 qubits below
the arithmetic for exactly that reason.

Nothing here evaluates cost, power, availability, or software maturity, all of which move
a real decision.
