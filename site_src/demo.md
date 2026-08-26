# The demonstration

The live demonstration is a controlled algorithm-development experiment. The grid contingency
stays fixed while the objective supplied to QAOA changes.

## ① Establish the operating problem

A transmission network begins inside its ratings.

<div class="figure-wrap" markdown>

--8<-- "figures/grid-normal.html"

</div>

A 345 kV corridor then fails.

<div class="figure-wrap" markdown>

--8<-- "figures/grid-faulted.html"

</div>
<div class="figure-wrap" markdown>

--8<-- "figures/loading-key.html"

</div>

The power that line carried reroutes onto the surviving network. In the default scenario, peak
loading rises from **54% to 137%**, with two lines beyond their ratings. The operator must decide
where to separate the grid before another protection trip starts a cascade.

With 12 substations there are **4,096** possible two-island assignments. At eight substations—the
size used for the narrated development experiment—all **256** assignments can be scored with
power flow and checked against ground truth.

## ② Run the baseline algorithm

The baseline converts three engineer-selected preferences into an analytic QUBO: minimize flow
severed by the cut, balance net injection between islands, and prevent the trivial “put everything
in one island” answer. QAOA concentrates probability on low-energy assignments, then classical
power flow screens its ranked shortlist for feasibility and thermal security.

This run answers two different questions:

- **Did QAOA optimize the Hamiltonian it was given?** Exact enumeration answers this while the
  problem remains small.
- **Did that Hamiltonian describe the operational decision?** MW served, overloads, and power-flow
  feasibility answer this.

Those answers can disagree. A solver can be correct while its objective is wrong.

## ③ Let emulation teach the objective

The second experiment holds the grid, fault, depth, and optimizer budget fixed. The emulator
scores partitions using quantities the analytic QUBO cannot calculate during execution:

```
operational loss = overload count + overload severity + load shed
                 + interrupted flow + infeasibility penalty
```

It then fits the best pairwise Ising approximation to those labels. The result is still a QUBO
that the same QAOA implementation can consume, but its coefficients were learned from operational
outcomes rather than written down term by term.

!!! warning "A surrogate, not power flow inside a quantum circuit"
    Thermal thresholds and network redistribution are not exactly quadratic in the original
    island-assignment bits. The application reports held-out fit error instead of implying the
    surrogate reproduces the power-flow solver exactly.

## ④ Compare the experiments

The Algorithm Lab retains both runs and keeps four answers separate:

1. the exact ground state of the selected QUBO, where enumeration is affordable;
2. the most probable state in the ideal QAOA distribution;
3. the best state observed with a finite shot budget;
4. the plan applied after classical security screening.

The first exhaustive study used four eight-node contingencies:

| Grid seed | True minimum loss | Analytic-QUBO plan | Surrogate-QUBO plan | Held-out NRMSE |
|---:|---:|---:|---:|---:|
| 3 | 0.044 | 2.220 | **0.044** | 0.790 |
| 7 | 0.211 | 8.867 | **0.405** | 0.924 |
| 11 | 0.145 | 4.020 | **2.323** | 0.873 |
| 19 | 0.076 | 4.078 | **2.582** | 0.868 |

The surrogate selected a lower-loss operational plan in all four cases and the true operational
optimum in one. This is a measured small-instance result, **not** a claim of general advantage.
The high fit error is equally important: it marks a representational limit that coefficient tuning
alone cannot remove.

## ⑤ Preview physical execution

The same optimized circuit can then be evaluated three ways:

- exact ideal expectation from the complete state vector;
- finite-shot sampling from that ideal state;
- density-matrix evolution with generic depolarizing noise.

A connectivity preview also estimates how the dense logical Hamiltonian expands on square-grid,
ring, and linear device layouts. It is explicitly a planning estimate—not target-device
transpilation.

## What the customer should leave understanding

The simulator did not merely run a quantum algorithm. It exposed a mismatch between the stated
objective and the real decision, supplied exact labels while ground truth was affordable, helped
construct an alternative, and measured what improved and what still could not be represented.

That is the value of quantum emulation before useful quantum hardware is available.

## Access

The live application is owner-operated and passkey-protected because it includes controls that
temporarily reassign a shared GB10 from inference to simulation. This public site contains the
reproducible explanation and engine-generated figures without exposing lab controls.
