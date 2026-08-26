# Technical notes

Applied notes on quantum optimization, written from a working QAOA
demonstrator that solves controlled islanding on a simulated transmission
grid. Intended for scientists, engineers, and technical leaders evaluating
the field.

Every figure is measured, computed from first principles, or cited. Where a
claim is contested in the literature, the note says so. Where an earlier claim
here was wrong, the correction is explained rather than silently edited.

See `../STYLE.md` for the standards these are written to.

## The notes

| # | Question it answers | Prerequisites |
|---|---|---|
| [01](01-what-qaoa-computes.md) | What does QAOA actually compute, and what does simulating it leave out? | None |
| [02](02-why-depth-can-hurt.md) | Why can adding circuit depth make QAOA *worse*? | Note 01 |
| [03](03-what-a-qubo-cannot-express.md) | What can a QUBO encoding express, and what falls off the edge? | Note 01 |
| [04](04-noise-without-the-density-matrix.md) | How do you simulate noise without paying 2^(2n)? | Note 01 |
| [05](05-which-method-which-machine.md) | Which simulation method needs which machine? | Notes 01, 04 |
| [06](06-why-emulation-needs-an-experiment-loop.md) | What makes quantum emulation an algorithm-development tool? | Note 01 |
| [07](07-what-the-first-algorithm-lab-slice-proves.md) | What does the first Algorithm Lab slice prove? | Note 06 |
| [08](08-can-emulation-train-a-better-qubo.md) | Can emulation train a better operational QUBO? | Notes 03, 06 |
| [09](09-who-owns-the-gb10.md) | Who owns the GB10 while a simulation runs? *(implementation superseded by 10)* | None |
| [10](10-an-owner-only-hand-on-the-gb10.md) | What changes when the demo can take the machine itself? | Note 09 |

## Planned

- Hardware connectivity and compilation cost: what mapping an all-to-all
  Hamiltonian onto a real device topology does to circuit depth.
- Shot budgets: how measurement statistics interact with the classical
  optimizer, and how to choose N.
- Tensor networks in detail: where they beat state vectors and where their cost
  explodes, since they are the standing caveat on every memory claim here.

## Measurement environment

Unless stated otherwise, figures come from a Dell Pro Max with GB10 Grace
Blackwell — 128 GB unified memory, compute capability 12.1 — running
cuStateVec via cuquantum-python and CuPy. Qubit ceilings are reported live by
the simulation service from actual free memory, not derived.
