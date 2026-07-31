---
title: Grid Ops
hide:
  - navigation
  - toc
---

# Grid Ops

!!! quote ""
    **Hybrid quantum-classical grid optimization — QAOA microgrid islanding on a Dell Pro
    Max GB10, and where classical simulation of quantum algorithms actually runs out.**

    By **Ken Rollins**, Federal Field CTO — Emerging Technologies at Dell.

---

A working demonstrator that solves controlled microgrid islanding with QAOA on a Dell Pro
Max GB10, built to find where classical simulation of quantum algorithms actually runs
out — and what that means for the hardware you need to develop them.

!!! quote ""
    A desktop-class GB10 Grace Blackwell carries **30 qubits** of dense, all-to-all QAOA
    on-premise and air-gapped. That is the **floor** of the hardware class, not the ceiling.

## What the demonstration does

A transmission grid loses a line. There are tens of thousands of ways to split what
remains into two self-sufficient microgrids so the failure cannot cascade, and one of them
is best. QAOA searches all of them at once; real DC power flow decides which answer is
electrically survivable.

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
| the scenario, start to finish | [The demonstration](demo.md) |
| what QAOA actually does | [How it works](how-it-works.md) |
| the hardware argument | [Why it needs this hardware](hardware.md) |
| depth, with provenance | [Technical notes](notes/index.md) |
| how it is built | [Architecture](architecture.md) |

Source: [github.com/kenrollins/qaoa-grid-ops](https://github.com/kenrollins/qaoa-grid-ops) · Apache-2.0
