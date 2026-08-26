---
title: QAOA Grid Ops
hide:
  - navigation
  - toc
---

# QAOA Grid Ops

!!! quote ""
    **Quantum emulation as an algorithm-development instrument — diagnose, improve, and
    validate QAOA microgrid islanding on a Dell Pro Max GB10.**

    By **Ken Rollins**, Federal Field CTO — Emerging Technologies at Dell.

---

A working demonstrator that uses exact emulation to expose when QAOA correctly optimizes
the wrong operational objective, construct an alternative quadratic surrogate, and measure
what improves before physical quantum hardware enters the loop.

!!! quote ""
    A desktop-class GB10 Grace Blackwell carries **30 qubits** of dense, all-to-all QAOA
    on-premise and air-gapped. That is the **floor** of the hardware class, not the ceiling.

## What the demonstration does

A transmission grid loses a line. The baseline QUBO and an emulator-fitted operational
surrogate solve the same contingency. The Algorithm Lab retains both runs and compares
objective quality, quantum probability concentration, MW served, overloads, finite-shot
behavior, and noise. Real DC power flow decides which proposals are electrically survivable.

<div class="figure-wrap" markdown>

--8<-- "figures/grid-faulted.html"

</div>
<div class="figure-wrap" markdown>

--8<-- "figures/loading-key.html"

</div>
<p class="figure-note">The network after losing its most critical line, solved with a DC
power flow. Line colour and width encode voltage class; the overlay and dash pattern
encode loading against rating. Interactive — hover any line.</p>

## What it is actually about

The grid problem is the vehicle. The argument is that **developing** a quantum algorithm
is the hard part, that development happens in classical simulation, and that simulation
hits walls you can compute exactly.

- **A correct solver can optimize the wrong objective.** Exact emulation separates
  algorithm failure from formulation failure while ground truth is still affordable.
- **The emulator can supply training labels.** Power-flow-scored partitions fit an
  operational QUBO surrogate, with held-out error kept visible.
- **Ideal, finite-shot, and noisy results are different experiments**, not one number.
- **Every qubit doubles the memory.** Turn on noise and it squares instead.
- **Measured on our GB10:** 30 qubits clean, 14 noisy, same machine, same second.
- **The sizing figure is the largest *coherent* memory domain**, not total GPU memory —
  a state vector cannot straddle a slow link.
- **Which method you run decides which machine wins**, and the ranking inverts.

## What this deliberately does not claim

- **Not that quantum beats classical here.** QAOA has no demonstrated advantage over good
  classical heuristics on problems like this. Against a spectral-bisection baseline given
  the same information, our implementation wins about half the time.
- **Not that classical simulation stops at 50 qubits.** That is the limit of *exact state
  vector* simulation. Tensor-network methods reach far beyond it on structured circuits —
  including QAOA.
- **Not a production grid tool.** The power flow is a DC approximation, the noise model is
  generic depolarising rather than device-calibrated, and the topologies are synthetic.

Every figure here is measured, computed from first principles, or cited, and says which.

## Start here

| If you want | Read |
|---|---|
| the baseline → diagnosis → improved-objective story | [The demonstration](demo.md) |
| how both formulations and the hybrid pipeline work | [How it works](how-it-works.md) |
| the hardware argument | [Why it needs this hardware](hardware.md) |
| depth, with provenance | [Technical notes](notes/index.md) |
| how it is built | [Architecture](architecture.md) |

Source: [github.com/kenrollins/qaoa-grid-ops](https://github.com/kenrollins/qaoa-grid-ops) · Apache-2.0
