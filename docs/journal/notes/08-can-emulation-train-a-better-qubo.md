---
id: note-08-can-emulation-train-a-better-qubo
type: implementation
title: "Can emulation train a better operational QUBO?"
date: 2026-08-26
audience: [scientist, engineer, leader]
tags: [qubo, power-flow, objective-design, emulation, surrogate-model]
prerequisites: "Notes 03 and 06."
one_line: "Power-flow-scored partitions can train a quadratic Ising surrogate that selects materially better operational plans than the hand-authored three-term QUBO on the four exhaustive eight-node contingencies tested. The surrogate is still an approximation: held-out normalized RMSE was 0.79–0.92, evidence that thresholded security behavior cannot be represented exactly by an unconstrained quadratic model over the original decision bits."
---

# Can emulation train a better operational QUBO?

The analytic islanding Hamiltonian minimizes severed flow, net-injection imbalance, and island
size imbalance. Those quantities are quadratic in binary island assignments and therefore fit
QAOA directly. The operator's actual decision also depends on load shed and thermal overloads
after the network is separated. Those quantities require a power-flow solution and include
threshold behavior that is not naturally quadratic.

The question is whether exact emulation can bridge part of that gap: score partitions using the
expensive operational calculation while the problem is small, then project those scores onto a
quadratic Ising model the quantum algorithm can consume.

!!! quote ""
    The emulator can teach the Hamiltonian what the operator values, but a quadratic projection cannot preserve every power-flow threshold.

## The target

For each partition x, the implementation computes a dimensionless operational loss:

```
L(x) = 4 · overload_count
     + 8 · sum(max(0, line_loading - 1)^2)
     + shed_MW / total_load_MW
     + 0.15 · interrupted_MW / total_live_flow_MW
     + 2 · infeasible_partition
```

Security is deliberately dominant, followed by overload severity, customer load, and disruption.
The coefficients are policy choices exposed in code, not physical constants.

The surrogate uses the ordinary pairwise Ising basis:

```
L_hat(s) = c + sum_(i<j) J_ij s_i s_j
```

Least squares with a small ridge penalty fits c and J. Complementary bit strings are included in
pairs because exchanging the names of island A and B must not change the physical plan. For up to
12 nodes all partitions can be labeled; above that, the current implementation samples at most
4,096 configurations.

## Exhaustive eight-node result

Computed locally on 2026-08-26 using the NumPy path. Each row uses the most-critical-line
contingency and evaluates all 256 partitions. “Analytic” and “surrogate” report the true
operational loss L of the exact ground state of the corresponding QUBO.

| Grid seed | True minimum L | Analytic-QUBO plan L | Surrogate-QUBO plan L | Held-out NRMSE |
|---:|---:|---:|---:|---:|
| 3 | 0.044 | 2.220 | **0.044** | 0.790 |
| 7 | 0.211 | 8.867 | **0.405** | 0.924 |
| 11 | 0.145 | 4.020 | **2.323** | 0.873 |
| 19 | 0.076 | 4.078 | **2.582** | 0.868 |

The surrogate selected a lower-loss operational plan in all four cases and the true optimum in
one. This is a measured improvement on this small study, not evidence of general advantage.

## Why the fit error remains high

The held-out normalized root-mean-square error is 0.79–0.92. The main target terms contain sharp
changes: crossing a thermal rating changes overload count, and disconnecting a generator can
change load shed nonlinearly across an entire island. A quadratic polynomial over the original
assignment bits has no auxiliary state with which to represent those transitions exactly.

This is the useful algorithm-development result. Better coefficient tuning cannot remove a
representational limit. The next formulation decision is whether to accept the approximate
surrogate, introduce auxiliary variables and constraints, or retain power-flow screening as a
classical post-processing stage.

## Demonstration sequence

The application now includes a Presenter Guide on the Algorithm Lab page. The shortest controlled
comparison uses eight substations and seed 7:

1. run the Baseline algorithm;
2. run the Operational surrogate experiment without changing grid or fault;
3. compare served MW, overloads, selected versus argmax state, and fit NRMSE;
4. state explicitly that QAOA optimizes either Hamiltonian, while emulation evaluates whether the
   Hamiltonian represents the operational decision.

## Limits

The four-case study is too small to select a production formulation. The power-flow labels come
from the project's DC approximation, not an AC security analysis. Target coefficients encode one
operator policy and have not been elicited from a utility. The fitted model uses the same grid
instance it is asked to optimize; transfer to unseen topologies and contingencies has not yet been
measured. Those are the next validation requirements.

