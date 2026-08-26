# Grid Ops — design brief

**Hybrid Quantum-Classical Grid Optimization.** An interactive technical
demonstration for a federal energy/defense audience (DOE, ORNL, regional grid
operators), showing Dell classical infrastructure as the backbone that makes
hybrid quantum computing (HQCC) usable today.

---

## The claim

> **A desktop-class Dell Pro Max with GB10 Grace Blackwell carries 30 qubits of
> dense, all-to-all QAOA — on-premise, air-gapped, with no cloud QPU — and that
> is the FLOOR of the hardware class, not the ceiling.**

Falsifiable, and it has been measured on the real machine (see *Measured facts*).

Two framings were deliberately **rejected**:

- ❌ *"GPU is 20–30× faster than CPU."* The original spec called for a CPU-vs-GPU
  benchmark tab. Measured honestly on this lab's hardware, the speedup over a
  96-core host was **1.2–2.2×** across the demo's qubit range, with one unstable
  20-qubit outlier at 25×. Any figure like "25×" would have been cherry-picked
  from noise, and a national-lab audience contains people who know that
  statevector simulation is memory-bandwidth-bound. A demo that loses its
  central argument to one informed question is worse than no demo.
- ❌ *"Faster than the lab's L4s."* Comparing against an older GPU in the same
  rack makes the claim about *that* GPU. The point is the capability floor of a
  current desktop-class system, which only rises with larger configurations.

**Capability, not speed.** "How large a problem does this machine hold" is a fact
about hardware. "How fast is it versus X" is an argument about benchmarking
methodology, and you lose control of it the moment someone asks how you measured.

---

## What someone SEES — first 60 seconds

1. A dark operations-room dashboard. Header reads **GRID OPS**, Dell
   Technologies Federal, and a live status pill: *Dell Pro Max GB10 · 30 qubit
   ceiling · 66 GiB free*. The ceiling is **queried live**, not hard-coded.
2. A transmission network — substations, generation (squares), transmission
   lines, all labelled in MW.
3. They set **Substation nodes** to 14 and press **🚀 Run Hybrid Optimization**.
4. Under a second later the grid **splits into two colored microgrid islands**,
   with severed lines drawn dashed red, and four readouts appear: interrupted
   flow in MW, island sizes and net power, solve time, and **FEASIBLE**.
5. Below, the QAOA convergence curve, and a verification card stating that brute
   force over all 16,384 partitions was computed and **QAOA matched the exact
   optimum**.
6. They download the islanding schedule as JSON — an auditable artifact.

The moment that lands: *the answer is verified optimal, and the box that produced
it is a desktop that never phoned home.*

---

## Why this problem

**Networked microgrid islanding under emergency interruption** (line drop, cyber
incident, disaster). Controlled islanding is a genuine, hard, combinatorial grid
problem, and it is a QUBO — not a QUBO-shaped toy.

It is **not** plain Max-Cut. Three objectives genuinely fight:

| Term | Meaning | Why it must be there |
|---|---|---|
| **Flow** | minimize MW severed by the cut | every cut line is real energy stopping |
| **Balance** | each island supplies its own load | an island with all generation and no load is a partition, not a microgrid |
| **Size** | islands comparable | without it, the optimum is "one island, cut nothing" — degenerate |

With spin `s_i = ±1` and net injection `p_i = gen − load`:

```
H(s) = A·Σ_(i,j)∈E w_ij (1 − s_i s_j)/2   +   B·(Σ_i p_i s_i)²   +   C·(Σ_i s_i)²
```

The balance term couples **every node to every other node**, so the Hamiltonian is
**dense all-to-all**, not the sparse transmission graph. That density is the
honest reason this needs real hardware: at 24 nodes it is 276 ZZ couplings per
layer. It also makes the demo's sliders meaningful — the weights are the knobs an
algorithm developer actually turns.

---

## Architecture

```
  ┌─ xr7620 ──────────────────┐        ┌─ Dell Pro Max GB10 ─────────────┐
  │  Streamlit Command Center │  VLAN  │  gridops-qsim (FastAPI :8600)   │
  │  topology · convergence   │◄──13──►│  cuStateVec / CuPy              │
  │  export · capability tab  │  HTTP  │  aarch64 · Blackwell sm_121     │
  │  grid model + QUBO build  │        │  128 GiB unified memory         │
  └───────────────────────────┘        └─────────────────────────────────┘
```

**Why split at all — this is not a preference, it is forced.**
`qiskit-aer-gpu` publishes **x86_64 wheels only**. There is no aarch64 build, so
it **cannot be installed on the GB10**. The GPU path on Grace Blackwell runs
through CuPy + cuQuantum's own cuStateVec bindings, which *do* ship aarch64
wheels. Putting the compute on the GB10 therefore requires separating it from a
UI that runs elsewhere.

Rejected alternatives:
- **Everything on xr7620 with qiskit-aer-gpu.** Works, installs cleanly, and was
  verified running — but then the demo's hardware story is about 4× L4, not the
  GB10. The claim would be about the wrong machine.
- **Build qiskit-aer from source on aarch64.** Days of work, and Aer 0.15.1
  predates `sm_121`. cuStateVec reaches the same place today.
- **Streamlit on the GB10 too.** Puts a web surface on the inference host and
  couples the demo's uptime to it. The UI is stateless and cheap; keep it on
  xr7620 with the rest of the lab's tenant apps.

### Key implementation decision: the diagonal fast path

`H_C` is diagonal in the computational basis, so:
- `exp(-iγH_C)` is **one elementwise phase multiply**, not `p·n(n−1)/2` RZZ gate
  applications. At 24 nodes, p=4, that collapses 1104 gate passes into 4.
- `⟨H⟩ = Σ|ψ(x)|²H(x)` is **exact** — no shot sampling, so the convergence curve
  is the true expectation rather than a noisy estimate of it.

This is an optimization, **not an approximation**. `POST /qaoa/verify` applies
every RZZ individually and compares: measured deviation **8.0e-17**. The demo
exposes that check rather than asking anyone to trust it.

---

## Measured facts (2026-07-29, on the real hardware)

GB10: aarch64, compute capability **12.1**, 130.6 GiB unified, inference evacuated.

| qubits | statevector | working set | diag build | 1 energy eval |
|---|---|---|---|---|
| 24 | 0.25 GB | 0.38 GB | 1.3 s | **0.67 s** |
| 26 | 1.0 GB | 1.5 GB | 5.9 s | 2.6 s |
| 28 | 4.0 GB | 6.0 GB | 27 s | 11.6 s |
| 30 | **16 GB** | 24 GB | 126 s | 50 s |

- **6–24 qubits is interactive** — a full 30-step optimization in ~0.1–0.7 s.
  This is the demo range.
- **30 qubits runs** but ~50 s/eval makes it a capability statement, not a live
  driver. Real optimization headroom remains (see PLAN.md M3).
- **Solution quality: QAOA returns the exact optimum** at p=1,2,4 on 12 nodes
  (`MATCH=True`), sometimes as the Z₂-symmetric complement — an identical plan.

### Two ratios, and why both are shown

| metric | value (12 nodes) | what it means |
|---|---|---|
| `solution_ratio` | **1.000** | the returned plan IS the optimum |
| `expectation_ratio` | ~0.25 | ⟨H⟩ averages the whole distribution, most of which is still junk at low depth |
| `concentration` | 6–9× uniform, rises with p | the honest live signal that depth buys something |

Reporting only the expectation ratio understates the result ~4×; reporting only
the solution ratio overstates how well the optimizer converged. **Show both.**

---

## Bugs found and fixed during bring-up

Recorded because they will otherwise be reintroduced:

1. **Deeper circuits scored *worse*.** p=4 (ratio 0.135) below p=2 (0.255) — the
   opposite of how QAOA behaves, on the one slider a knowledgeable visitor will
   reach for. Root cause: γ was scaled by `max|J|`, but the relevant scale is
   **σ(H)**, the spread of the cost function. On a dense 12-node problem that
   overshot by ~3×, so the search spent its budget in the over-rotated regime.
   Fixed: `gamma_hi = π / (2σ(H))`.
2. **Runs that "converged" to the unevolved state.** A layer-growing INTERP
   schedule split a 10–50 step budget across p levels, leaving ~3 COBYLA
   iterations in up to 8 dimensions. The optimizer never moved, returned γ≈0,
   and reported the energy of |+⟩ — which is exactly the Hamiltonian offset.
   Fixed: annealing-inspired linear-ramp init + 1-D scale scan, then joint
   refinement.
3. **`cost_diagonal` allocated n·2ⁿ bytes** of spin arrays — fine at 24 qubits
   (400 MB), **30 GB at 30 qubits**. Fixed: tiled.
4. **The phase multiply allocated two full-width temporaries** — 34 GB of scratch
   at 30 qubits on top of a 17 GB statevector. Fixed: tiled.
5. **Generation was ~3x load.** The synthetic grid dispatched far more
   generation than demand, so every possible fragment was trivially
   self-sufficient, islanding could never shed load, and the balance term of the
   objective was decorative — the contingency story was unfalsifiable. Fixed:
   generation scaled to a 1.08 reserve margin, as real systems are dispatched.
6. **The objective was scaled wrong by a factor of ~n.** The flow term touches
   |E| ≈ n edges; balance and size touch all n(n−1)/2 pairs. Unnormalised, the
   dense terms outweighed flow by ~n and the optimizer bought island balance at
   any cut cost — at n=14 it severed 144.7 MW against a 57.2 MW spectral
   bisection and returned an **infeasible** plan, while faithfully finding that
   objective's true ground state. Fixed: dense terms divided by n. The weights
   are only interpretable once the three terms are on comparable footing.
7. **The service died on SSH disconnect.** `nohup … &` inside `ssh host 'cmd'` is
   not enough; the process group is signalled on close. Fixed: `setsid` in
   `start.sh`.

---

## The classical baseline, and an honest loss

QAOA is compared against **spectral bisection** (Fiedler vector of the
flow-weighted Laplacian) — competent classical practice, not a straw man. Both
partition the same faulted grid, so any difference is attributable to the
objective rather than to hardware.

Default weights were chosen by sweep over 12 scenarios (4 seeds x 3 sizes),
scored on MW served:

| weights (flow / balance / size) | W/T/L | net MW | infeasible |
|---|---|---|---|
| 1.0 / 1.0 / 0.35 | 2/2/8 | −187 | 0/12 |
| **0.5 / 2.0 / 0.20** | **5/3/4** | **+260** | 1/12 ← chosen |
| 1.0 / 3.0 / 0.15 | 4/1/7 | +95 | 0/12 |
| 1.0 / 4.0 / 0.10 | 4/4/4 | +242 | 0/12 |

**These figures were re-measured on 2026-07-31 and are roughly half what this
document previously reported.** The spectral baseline was building its Laplacian
from the synthetic `flow_mw` attribute while QAOA optimised solved flows — so the
classical method was minimising a cut through a fiction. Corrected, the chosen row
fell from 7W/3T/2L and +419 MW to 5W/3T/4L and +260 MW. The ranking of weight
choices survived; the size of the advantage did not.

Pushing balance higher wins more load but returns electrically non-viable plans.
**An infeasible plan is not a better plan.**

QAOA still loses 2 of 12. When it does, it has returned the *true optimum of the
stated objective* (brute-force verified) while serving less load — which is a
statement about the objective, not the solver: the balance term `(Σpᵢsᵢ)²` is
symmetric, penalising an island with surplus generation exactly as hard as one
with a deficit, though only deficits shed load. **The UI says so on screen when
it happens.** Objective alignment is the open algorithm problem, and surfacing it
is more valuable to this audience than hiding it.

## Lab integration status

**Registered and live.** This paragraph said "not yet a registered tenant — no
VLAN-13 address, no Caddy route, no Authentik app, no public DNS" long after all
four existed; corrected 2026-08-26. It runs as a container on VLAN 13 behind the
lab's identity proxy, and reaches the GB10 at the compute service endpoint.

**Owner-only since 2026-08-26** (it was guest-visible). The demo gained controls
that mutate GB10 residency, and a demo that can take shared silicon away from
the rest of the lab does not belong one click from a visitor — however good it
looks on a demo floor.

The GB10 uses the vLLM orchestrator; the NIM container it once stopped is
retired. `claim` records and unloads the resident model set before starting qsim;
`release` restores that exact set. Both go through `gridops-residency`, an
owner-only control plane on the GB10 with a durable evacuation record and a
lease. GB10-backed inference lanes are unavailable while the simulator holds the
machine — the gateway itself stays up.
