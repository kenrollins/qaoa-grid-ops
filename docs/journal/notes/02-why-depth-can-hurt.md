---
id: note-02-why-depth-can-hurt
type: note
title: "Why adding circuit depth can make QAOA worse in practice"
date: 2026-07-30
audience: [scientist, engineer, leader]
tags: [qaoa, parameter-landscape, optimization]
prerequisites: "Note 01, or familiarity with the QAOA ansatz."
one_line: "QAOA at depth p+1 can express everything depth p can, so performance should be monotone in depth. In practice it frequently is not, because the classical optimizer must find good angles in a 2p-dimensional landscape that is mostly flat. We measured p=4 scoring 0.135 against p=2's 0.255 from a parameter-scaling error, and separately measured an optimizer reporting convergence on a circuit that had performed no computation at all."
---

# Why adding circuit depth can make QAOA worse in practice

QAOA has a guarantee that sounds decisive: a depth-(p+1) circuit contains the
depth-p circuit as a special case, by setting the extra layer's angles to zero.
Optimal performance is therefore non-decreasing in p, and in the limit of large
p QAOA approaches the adiabatic algorithm and the exact optimum.

Practitioners nonetheless routinely observe performance *degrading* with depth.
The gap between the guarantee and the observation is entirely in the word
*optimal*: the guarantee is about the best achievable angles, and finding them
is a classical optimization problem that becomes harder in exactly the regime
where the extra depth would help.

This note explains the two mechanisms behind that gap, with measurements from a
12-node grid-partitioning instance.

## The landscape being searched

A depth-p QAOA circuit has 2p free parameters: angles γ_1..γ_p controlling the
cost operator and β_1..β_p controlling the mixer. The classical optimizer
searches this 2p-dimensional space to minimise ⟨H⟩.

Two properties of that space cause trouble.

**It is largely flat.** For many ansätze, the gradient of the objective vanishes
exponentially with qubit count — the **barren plateau** phenomenon (McClean et
al., 2018). A randomly initialised optimizer in a high-dimensional flat region
receives almost no signal about which direction improves. The problem worsens as
both qubit count and parameter count grow, which is to say exactly as the
problem becomes interesting.

**It is periodic and easy to over-rotate.** The cost operator applies a phase
exp(-i·γ·H(x)) to each candidate x. Phase is defined modulo 2π, so once γ is
large enough that γ·[range of H] substantially exceeds 2π, the phases assigned
to different candidates wrap repeatedly and lose their ordered relationship to
cost. The landscape in that regime is oscillatory and structureless.

## Mechanism 1: the useful range of γ is set by the spread of H, not by any single coupling

Choosing a search range for γ requires knowing the scale of H. The intuitive
choice — the largest coupling magnitude, max|J| — is wrong, and wrong by an
amount that grows with problem density.

What determines whether two candidates receive usefully different phases is the
difference in their *total* cost. The relevant scale is therefore the standard
deviation of H across candidate solutions, σ(H), not the size of any individual
term. The two diverge as a problem gets denser, because many terms contribute to
the total while max|J| describes only one of them.

Measured on the current objective, which normalises its dense terms by n:

| nodes | coupling terms | σ(H) | max\|J\| | ratio |
|---|---|---|---|---|
| 12 | 66 | 0.743 | 0.314 | 2.4x |
| 14 | 91 | 0.767 | 0.258 | 3.0x |
| 16 | 120 | 1.071 | 0.306 | 3.5x |

The ratio grows with problem size, which is what makes max|J| unsafe as a proxy.
In the implementation the error was compounded by a floor — the range was
π / max(1, max|J|) — so once normalisation pushed max|J| below 1 the search ran
out to π regardless, about 1.5x wider than the informative region.

**A correction to an earlier version of this note.** It stated that σ(H) grows as
√m·|J| for m coupling terms, and quoted σ(H) ≈ 3.5 against max|J| ≈ 2.5 at 12
nodes. Both need qualifying. The √m relation holds for m *equal-magnitude,
independent* terms; this objective sums three families with deliberately
different scalings, and the measured ratio (2–4x) is well below √m (8–11x). The
quoted figures were also measured before the dense terms were normalised by n,
so they are not reproducible against current code. The mechanism is unchanged —
σ(H) is the right scale, max|J| is not — but the magnitude should be measured
per problem, not estimated.

The measured consequence, approximation ratio by depth:

| Depth p | Approximation ratio, γ scaled by max\|J\| |
|---|---|
| 1 | 0.129 |
| 2 | 0.255 |
| 3 | 0.137 |
| 4 | 0.135 |

Non-monotone, with the deepest circuits performing worst. Correcting the scale
to γ_max = π / (2σ(H)) removed the inversion.

```python
# src/simulation/qaoa_core.py
sigma = float(xp.std(diag))          # spread of H across all 2^n candidates
gamma_hi = float(np.pi / (2.0 * sigma))
```

## Mechanism 2: parameter budget divided by depth can starve the search entirely

A common and well-motivated strategy is **layer-wise initialization**: optimize
at depth 1, use the result to seed depth 2, and continue. Zhou et al. show
QAOA's optimal angles vary smoothly with depth, so interpolating a good depth-p
schedule onto a finer grid lands near the depth-(p+1) optimum.

The strategy has a failure mode when the total evaluation budget is small. With
a budget of 30 evaluations split across p+1 levels, each level receives roughly
three iterations of a derivative-free optimizer operating in up to eight
dimensions. That is not enough to move off the starting point.

The observable signature is specific and worth recognising. Several runs
returned ⟨H⟩ values equal to the Hamiltonian's constant offset — 10.67 on this
instance. That value is the expectation of the *initial* uniform superposition,
which is what the circuit produces when γ ≈ 0 and the cost operator is the
identity. The optimizer had never left its initialization, and reported
convergence.

!!! quote ""
    An energy exactly equal to the Hamiltonian's offset is not a
    result; it is the signature of a circuit that performed no
    computation.

The replacement used here is a single-parameter annealing-inspired schedule:
γ rising linearly across layers, β falling, with one scanned scale factor. This
follows from the adiabatic interpretation of QAOA — the circuit approximates a
sweep from mixer-dominated to cost-dominated evolution — and reduces the
effective search to roughly one dimension, which a 10-to-50 evaluation budget
can explore.

## What follows

For **algorithm design**: non-monotonicity in p is a diagnostic, not a property
of QAOA. Observing it should prompt examination of the parameter search before
any conclusion about the algorithm. Report the initialization strategy and
evaluation budget alongside any depth-scaling result; without them the result is
not interpretable.

For **infrastructure**: parameter landscapes are mapped by brute force —
thousands of independent circuit evaluations, each an independent simulation.
This work is embarrassingly parallel and scales with device count rather than
with memory capacity, making it a different procurement question from the
single-large-circuit case.

For **evaluating claims**: a reported approximation ratio is a statement about a
particular parameter search as much as about QAOA. Two implementations of the
same algorithm on the same problem can differ by a factor of two purely through
initialization.

## Limits of this note

Both mechanisms were measured on one problem family — dense, all-to-all Ising
instances derived from grid partitioning — at 10 to 14 qubits. The γ-scaling
argument should generalise to any dense Hamiltonian, since it depends only on
σ(H) growing with term count, but we have not verified it on sparse or
structured instances where max|J| and σ(H) are closer.

We did not encounter a true barren plateau. Our second failure was budget
starvation, which is a distinct phenomenon that happens to present similarly
— an optimizer that does not move. Distinguishing them requires measuring
gradient magnitude directly, which we did not do.

## References

- McClean, Boixo, Smelyanskiy, Babbush, Neven, *Barren plateaus in quantum neural network training landscapes*, arXiv:1803.11173 — exponentially vanishing gradients.
- Zhou, Wang, Choi, Pichler, Lukin, *QAOA: Performance, Mechanism, and Implementation on Near-Term Devices*, arXiv:1812.01041 — smooth parameter variation with depth, INTERP and FOURIER heuristics, adiabatic framing.
- Farhi, Goldstone, Gutmann, arXiv:1411.4028 — the monotonicity guarantee referenced above.
