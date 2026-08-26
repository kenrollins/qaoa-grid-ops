---
id: note-07-first-algorithm-lab-slice
type: implementation
title: "What does the first Algorithm Lab slice prove?"
date: 2026-08-26
audience: [scientist, engineer, leader]
tags: [qaoa, experiments, noise, shots, connectivity, reproducibility]
prerequisites: "Note 06."
one_line: "The first implementation slice changes the unit of interaction from one disposable solve to a versioned experiment. Runs can now be compared, exported, and explicitly persisted; the same optimized circuit can be evaluated ideally, with finite shots, and with depolarizing noise; and dense logical interactions can be contrasted with an auditable sparse-connectivity routing estimate."
---

# What does the first Algorithm Lab slice prove?

The initial implementation of the Algorithm Lab establishes the experimental substrate before
adding more algorithm variants. This order matters: a new objective or ansatz is not useful as a
demonstration if the application cannot retain what changed and compare the outcome fairly.

## A completed solve is now a versioned record

Each Command Center solve produces a schema-versioned `ExperimentRecord`. It separates the
mathematical result from the operational result and records the grid seed, fault, objective
weights, depth, optimizer budget, backend, kernel, elapsed time, convergence history, exact
energy where available, probability concentration, shortlist selection, MW accounting, and
security result.

The record is deliberately flat. Live runs contain NetworkX graphs and solver objects that are
useful in memory but fragile as durable files. The portable record exports to JSON and CSV,
round-trips through a schema check, and is written beneath `data/experiments/` only when the
operator explicitly asks for a snapshot.

## The four answers are visible

The comparison page distinguishes the exact QUBO optimum, the QAOA argmax, and the plan applied
after security screening. It also reports whether screening replaced the argmax and how many
candidates were examined. Finite-shot execution is displayed separately because the best state
observed in a batch need not be the ideal argmax.

This closes an important ambiguity: “the quantum answer” is not a single object in a hybrid
workflow.

## Physical realism changes one factor at a time

For the current optimized angles, the Algorithm Lab can run three evaluations:

1. exact ideal expectation from the complete state vector;
2. a finite-shot estimate from the same ideal state;
3. exact depolarizing-noise evolution from a density matrix.

The table reports expectation, best retained state where the method provides one, shot error,
purity, memory, and time. The comparison does not re-optimize between modes, so measurement and
noise are the controlled variables.

The noise remains generic per-qubit depolarizing noise. It is not described as a calibration of
a named device.

## Connectivity is an estimate, not compilation

The first routing preview compares all-to-all, square-grid, ring, and linear connectivity. It
uses identity placement, shortest paths, restores placement after each interaction, and counts
each SWAP as three generic two-qubit gates. Those rules are visible beside the result.

This is intentionally a planning estimate. It demonstrates why a dense QAOA Hamiltonian acquires
routing cost on sparse hardware, but it does not replace target-specific transpilation against a
device gate set and calibration.

## Guided experiments replace unexplained knobs

The primary controls now open in Guided mode with three hypotheses: baseline, under-trained, and
improved. Advanced mode preserves the original depth, optimizer, and objective sliders. The
guided presets make a defensible comparison available without requiring a customer to know which
combination of parameters will teach something.

## Verification

The implementation was verified on the local NumPy path on 2026-08-26:

- the complete pytest suite passed, with one hardware-dependent test skipped;
- Ruff reported no findings;
- the Streamlit initial-render smoke test reported zero exceptions;
- the full normal-operation, fault, and solve AppTest sequence reported zero exceptions.

No new GB10 performance claim was measured in this slice. The existing remote noise and
cuStateVec paths were reused without changing their kernels.

## What remains

The next algorithm slice is not a cosmetic extension. It must earn three comparisons: an
alternative objective that improves alignment with served MW, warm-start or parameter-transfer
initialization that reduces optimizer work, and target-specific compilation that replaces the
current routing estimate. Streaming remote optimizer progress requires a transport change, such
as server-sent events or a job/event endpoint, because the current HTTP optimize request returns
one complete JSON response.

