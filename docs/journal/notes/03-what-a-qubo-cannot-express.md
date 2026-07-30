---
id: note-03-what-a-qubo-cannot-express
type: note
title: "What a QUBO can and cannot express: a worked constrained problem"
date: 2026-07-30
audience: [scientist, engineer, leader]
tags: [qubo, objective-design, power-flow]
prerequisites: "Note 01 for the QUBO/Ising form."
one_line: "Mapping a real problem onto a QUBO forces every requirement into a sum of pairwise terms. Constraints that depend on the global consequences of a choice do not fit. We measured the result: the provably optimal solution to a correctly-solved islanding objective loaded a transmission line to 202 percent of its rating, because thermal limits cannot be written as a pairwise cost."
---

# What a QUBO can and cannot express: a worked constrained problem

Quantum optimization requires the problem in QUBO form: a cost that is a sum of
terms involving at most two binary variables. That format is not a notational
preference — it is what maps onto a two-local Hamiltonian and therefore onto the
gates a device can apply.

The encoding step is where most of the engineering difficulty in applied quantum
optimization actually sits, and it is the step most likely to be glossed over.
This note works one real example through and shows what fell off the edge.

## The problem

**Controlled islanding**: after a transmission line fails, deliberately open
selected circuit breakers to split a power grid into self-sufficient sections,
so that a developing failure cannot propagate. One binary variable per
substation names which of two islands it joins.

Three requirements, all genuine:

1. **Minimise interrupted flow.** Every line cut stops real power transfer.
2. **Balance each island.** An island must generate approximately what it
   consumes; one holding all the generation and none of the load is not a
   microgrid.
3. **Avoid the degenerate answer.** Requirements 1 and 2 are both perfectly
   satisfied by "put everything in one island and cut nothing", which is not an
   islanding plan.

## The encoding

With spin s_i = ±1 naming node i's island, w_ij the power flowing on line (i,j),
and p_i = generation_i − load_i the net injection at node i:

```
H(s) = A · Σ_(i,j)∈E  w_ij (1 − s_i s_j)/2      interrupted flow
     + B · ( Σ_i p_i s_i )²                     island power balance
     + C · ( Σ_i s_i )²                         non-degeneracy
```

Two features are worth drawing out.

**The balance term is why this is not Max-Cut.** Σ_i p_i s_i is the difference
in net injection between the two islands; squaring it drives both toward
self-sufficiency simultaneously. Expanding the square produces a term p_i·p_j
for *every* pair of nodes — so the Hamiltonian is **dense and all-to-all**, not
merely the sparse transmission graph. At 24 nodes that is 276 two-qubit
rotations per layer. Problem structure and circuit cost are not the same thing.

**Term scaling is not free.** The flow term touches |E| ≈ n edges; balance and
non-degeneracy touch all n(n−1)/2 pairs. Left unnormalised the dense terms
dominate by a factor of order n, and the weights A, B, C become uninterpretable.
Dividing the dense terms by n restores comparability. Before that correction the
optimizer purchased island balance at any cut cost, severing 144.7 MW where a
classical spectral bisection cut 57.2 MW.

## What does not fit

Transmission lines have thermal ratings. Exceeding one causes the conductor to
heat and sag, and its protection to trip it out — which transfers its power to
the next line, which may then also trip. That cascade is the mechanism of
large-scale blackouts.

This constraint cannot be written as a sum of pairwise terms in s, because the
power flowing on a line *after* a proposed cut is a global, nonlinear function
of the entire partition. It depends on the topology that remains and on
Kirchhoff's laws across the whole surviving network. There is no pair (i,j)
whose product carries the information.

So it was not in the objective. The consequence, measured:

| Case | Peak line loading | Lines over rating |
|---|---|---|
| Intact network | 54% | 0 |
| After the fault, no action | 137% | 2 |
| Energy-optimal islanding plan | **202%** | 2 |

The optimization made the thermal situation substantially worse while achieving
a better objective value. The solver was correct throughout — brute-force
enumeration confirms the returned plan minimises H. The objective was
incomplete.

!!! quote ""
    A solver that finds the true optimum of an incomplete objective is
    externally indistinguishable from a solver that is broken.

## The trade-off the encoding was hiding

Enumerating all 4,096 partitions of the 12-node faulted network, and evaluating
each with a DC power flow:

- **64** are electrically feasible — both islands contiguous, both containing generation
- **10** are thermally secure, with every line inside its rating
- all 10 shed between **128 and 163 MW** of a 325 MW system

There is no solution that both keeps all load energised and respects thermal
limits on this contingency. Security costs roughly 40 percent of demand.

That is a substantive finding about the power system, and the QUBO could not
express it because the quantity being traded — post-contingency line loading —
was not among the terms.

## Two responses, and what each is worth

**Reorder the selection criteria.** Candidate plans were originally ranked with
load-shed above overload count. That ordering is intuitive and wrong: it accepts
a cascade to avoid shedding, and a cascade sheds everything. Security-constrained
ranking is standard practice in operations and stopped the 202 percent plan from
being selected.

**Screen the distribution rather than the argmax.** QAOA returns a probability
distribution over solutions, not a single answer. Taking only the most probable
bitstring discards the rest of what the circuit computed. Taking the top 64
measured states and evaluating each with a real power flow selects on the
constraint the Hamiltonian could not express. On the default scenario the most
probable candidate peaked at 202 percent and the selected one at 143 percent —
every candidate produced by the circuit, the choice made by physics.

This second response is a legitimate hybrid pattern and also a patch. The
distribution is drawn from a landscape that has no thermal information, so
sampling it more heavily does not create any. Of 4,096 partitions only 10 are
secure, and the shortlist has not yet contained one.

The principled fix is an objective incorporating post-contingency flow, which
requires either an iterative scheme — solve, evaluate flows, penalise the
observed overloads, re-solve — or auxiliary variables encoding flow explicitly,
at significant qubit cost. Both are open work rather than implementation tasks.

## What follows

For **problem selection**: a problem is a good quantum optimization candidate
when its important constraints are naturally pairwise. Constraints that are
global, nonlinear, or emergent either require auxiliary variables — which
consume the qubits that are scarce — or must be handled outside the quantum
step. Assess this before assessing hardware.

For **algorithm design**: report what the objective omits, explicitly. The
approximation ratio measures fidelity to the objective, and says nothing about
fidelity to the problem.

For **evaluating claims**: "the quantum algorithm found the optimal solution" is
a claim about a Hamiltonian, not about the world. The useful question is what
was left out of the encoding, and it is rarely answered unprompted.

## Limits of this note

The power flow used here is a **DC approximation** — linearised, lossless, flat
voltage. It is the standard tool for contingency screening and is appropriate
for "where does power go when this line opens", but it is not an AC solution
and models neither reactive power nor voltage collapse.

The thermal cascade screen is first-order: lines above rating are assumed to
trip, without re-solving iteratively as each trip redistributes flow again. Real
cascade analysis iterates.

The enumeration result — 10 secure partitions of 4,096, all shedding 128–163 MW
— is specific to this synthetic 12-node network with a 1.08 reserve margin. The
qualitative finding that security and load service trade against each other is
general; the numbers are not.
