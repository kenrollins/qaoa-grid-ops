---
id: note-06-why-emulation-needs-an-experiment-loop
type: implementation
title: "What makes quantum emulation an algorithm-development tool?"
date: 2026-08-26
audience: [scientist, engineer, leader]
tags: [qaoa, emulation, experiments, noise, shots, objective-design]
prerequisites: "Note 01."
one_line: "A simulator becomes an algorithm-development instrument only when it preserves controlled experiments: the formulation, circuit, optimizer, measurement model, hardware assumptions, and operational outcome must be comparable across runs. A single polished solve demonstrates an application; an experiment loop demonstrates how the algorithm was developed."
---

# What makes quantum emulation an algorithm-development tool?

An exact state-vector simulator can expose every amplitude, evaluate an expectation without
sampling error, and compare a result with ground truth while the problem remains small enough
to enumerate. Those capabilities are more than a substitute for unavailable quantum hardware.
They are observability tools for developing the algorithm that will eventually run on it.

The distinction matters in this demonstrator. A transmission-grid contingency followed by a
credible islanding plan proves that the software stack works. It does not, by itself, show how
simulation helped choose the objective, circuit depth, parameter initialization, optimizer,
shot budget, or noise tolerance. Those decisions become visible only when runs are retained as
controlled experiments and compared on the same problem.

!!! quote ""
    A single solve demonstrates an application. A controlled comparison demonstrates algorithm development.

## The experiment is the unit of work

An algorithm-development result is not only a bit string. It is a record containing:

- the grid, fault, and QUBO formulation;
- the ansatz, depth, initialization, and classical optimizer budget;
- whether evaluation used exact probabilities or finite measurement shots;
- the noise and connectivity assumptions;
- the complete convergence history and final probability distribution available to the method;
- the operational result after power-flow screening;
- the backend, kernel, elapsed time, source revision, and random seed.

Without that record, changing two sliders creates two anecdotes. With it, the same action creates
an experiment that can be reproduced, compared, exported, and challenged.

## Four answers must not be collapsed into one

The hybrid workflow can produce four different candidates:

1. the exact minimum-energy state, when enumeration is affordable;
2. the most probable state in the simulated QAOA distribution;
3. the best state actually observed in a finite set of shots;
4. the operational plan selected after classical power-flow and security checks.

They answer different questions. The first validates the mathematical objective. The second
measures ideal circuit concentration. The third predicts what a real execution may return. The
fourth asks whether the proposal is usable by the grid. Displaying the transitions between them
is the hybrid algorithm; hiding them behind one label makes the result look simpler than it is.

## Two failures are more informative than a perfect run

This project already contains two useful development findings.

First, sizing the QAOA cost angle from the largest individual coupling searched too wide a
parameter range on a dense Hamiltonian. Sizing it from the standard deviation of the complete
cost distribution exposed the informative basin and restored the expected benefit of depth.
Exact simulation made the landscape observable.

Second, the current squared balance term penalizes generation surplus as strongly as generation
deficit, although only deficit sheds customer load. QAOA can therefore find the exact optimum of
the stated objective while producing a worse operational outcome than a classical baseline. That
is not a solver failure. It is evidence that the proxy objective is misaligned with the intended
decision.

These cases define the customer demonstration we want: reproduce a failure, inspect information
available from emulation, change one design choice, and measure the improvement.

## Implementation programme

The demonstrator will be extended in dependency order:

1. introduce a versioned experiment record, persistent run history, replay, and JSON/CSV export;
2. add a comparison workspace with exact, sampled, and operational metrics side by side;
3. promote finite-shot and noisy execution into the primary workflow;
4. add guided baseline, failure, and improved presets rather than requiring a customer to invent
   a useful slider configuration;
5. stream the classical optimization so the hybrid loop is visible while it runs;
6. compare objective formulations, including a deficit-aware candidate;
7. add warm-start and parameter-transfer experiments;
8. estimate connectivity-aware routing cost for representative QPU topologies;
9. add a recognized IEEE grid case and robustness sweeps across faults and random seeds;
10. refactor backend dispatch and capacity policy where those additions create pressure.

Each stage must preserve the current one-click Command Center and remain executable without the
GB10 through the NumPy fallback. Hardware-specific measurements remain explicitly labelled.

## What will be measured

Comparison will not be reduced to one approximation ratio. Each experiment will report:

- final expectation and exact-objective gap where ground truth is available;
- probability mass assigned to acceptable candidates;
- best sampled energy and probability of observing an acceptable plan in a shot batch;
- MW served and shed, overload count, and worst line loading;
- circuit depth, two-qubit interactions, and routing overhead where applicable;
- elapsed time, evaluation count, memory model, backend, and kernel.

The operational and mathematical metrics remain separate. An objective can be optimized well and
still encode the wrong preference.

## Limits of this programme

The initial noise model is generic depolarizing noise, not calibration from a named device. A
connectivity estimate is not a transpiler-verified compiled circuit until a target gate set and
routing implementation are selected. Warm-start and deficit-aware objectives are algorithm
variants to evaluate, not assumed improvements. The experiment framework exists precisely so
those claims must be earned by measurements rather than presentation.

