---
id: note-09-who-owns-the-gb10
type: implementation
title: "Who owns the GB10 while a simulation runs?"
date: 2026-08-26
audience: [engineer, leader]
tags: [gb10, unified-memory, residency, orchestration, operations]
prerequisites: "None."
one_line: "An inference server and a statevector simulator cannot both hold a unified memory pool, and neither one is a client of the other; the integration point between them is residency — who holds the machine — rather than request routing, and getting that wrong costs qubits rather than throughput."
---

# Who owns the GB10 while a simulation runs?

A GB10 Grace Blackwell has **128 GB of unified memory**: one physical pool addressed
coherently by both the CPU and the GPU, rather than a separate GPU card with its own
VRAM. That property is why the machine can hold 30 qubits of dense statevector at all —
and it is also why two workloads on it are not merely slow neighbours. They are
competitors for a single resource, and the loser does not run at all.

Two workloads share this one:

| Workload | Interface | What it is |
|---|---|---|
| Inference server | OpenAI-compatible HTTP — chat completions against a named model | a **model lane**: requests are routed and metered by an LLM gateway |
| `gridops-qsim` | a typed HTTP API — `optimize`, `evaluate`, `realism`, `verify`, `health` | this project's simulator, which returns energies and convergence, not text |

## The simulator is not a model lane

The tempting integration is to register the simulator with the LLM gateway so that one
component routes everything on the machine. It does not work, for a reason worth stating
precisely rather than as a preference.

A gateway lane has exactly one verb: submit a prompt, receive a completion, and be metered
per token. The simulator's surface is six verbs with typed request bodies — Ising
couplings, layer counts, shot budgets, noise strengths — returning energy histories,
timings and the kernel path that actually executed. Flattening that into a completion
endpoint discards every one of those verbs, and buys metering semantics that mean nothing
for a workload whose cost is measured in memory-seconds rather than tokens.

!!! quote ""
    Two workloads on one accelerator do not necessarily share an interface. What they
    share is the memory, and that is the thing to arbitrate.

## The integration point is residency

Residency is the question of which workload is *loaded* — holding memory — at a given
moment, as distinct from which workload a given request is *routed* to. For workloads that
share an interface, routing is enough. For workloads that share only a memory pool, only
residency is meaningful, and it has to be arbitrated explicitly:

1. read the inference orchestrator's current state and **record exactly which models are
   loaded**, durably, before changing anything;
2. unload that recorded set;
3. start the simulator and confirm it is serving;
4. on release, stop the simulator and load back **exactly** the recorded set — no more,
   no less.

Steps 1 and 4 are a matched pair, and the ordering in step 1 is load-bearing: the record
must reach disk before the first unload, or a failure between the two leaves a model
unloaded with nothing anywhere saying it should come back. [Note 10](10-claiming-a-shared-accelerator.md)
covers what that costs to build correctly.

## What residency is worth, measured

Measured on this GB10 on 2026-08-26, with the inference orchestrator holding
`nemotron-120b` and `qwen35-a3b`:

| | Unified memory in use | Statevector ceiling |
|---|---|---|
| Two models resident | 117.7 GiB of a 121.6 GiB visible pool | ~27 qubits |
| Machine evacuated | ~4 GiB | **30 qubits** |

Three qubits is not a 10% difference. Each qubit doubles the statevector, so the evacuated
machine holds **eight times** the state — and the 30-qubit figure is the entire capability
claim this project makes about the hardware class. On a discrete-VRAM accelerator a
co-resident tenant costs throughput. On a unified pool it costs **problem size**, which is
the one thing that cannot be recovered by waiting longer.

## What follows

**For anyone sharing a unified-memory accelerator.** Ask what the co-tenant costs in
capability, not in latency. If the answer is "it lowers the largest problem that fits,"
the tenants need an arbitration mechanism, not a scheduler.

**Identify a neighbour by querying it, not by naming it.** A residency tool that detects
its co-tenant by looking for a specific process or container reports "the machine is idle"
the moment that co-tenant is replaced — the most dangerous possible failure, because it is
silent and it reads as good news. Asking the orchestrator what it currently has loaded is
both simpler and correct across changes to the model set. This is a general failure mode
for any tool that hardcodes the identity of something it does not own.

**Ceilings should be reported, not constant.** Because free memory moves, the simulator
computes its qubit ceiling from actual free memory at request time. A hardcoded 30 would
be wrong for most of the day.

## Limits of this note

The measurement is one machine on one date with one pair of models; the arithmetic
generalises, the specific figures do not. Nothing here addresses *concurrent* tenancy —
partitioning the pool so both workloads run at once, smaller. That is a real option this
project has not tested, and it trades the full 30-qubit ceiling away to get it.
