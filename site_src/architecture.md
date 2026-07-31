# Architecture

Deliberately includes the constraints and the forced decisions, because a diagram that
implies everything was a free choice is the fastest way to lose a technical reader.

```
┌─ Application host ────────────────┐         ┌─ Dell Pro Max GB10 ───────────────┐
│  Grid Ops Command Center          │         │  gridops-qsim  (FastAPI :8600)    │
│                                   │         │                                   │
│  Streamlit + Plotly               │  VLAN   │  cuStateVec kernels               │
│  grid model → QUBO → Ising        │◄──HTTP─►│  CuPy / CUDA 12                   │
│  backend probe · orchestration    │  JSON   │  aarch64 · Blackwell sm_121       │
│  topology · convergence · export  │         │  128 GiB unified memory           │
│  NO quantum state held here       │         │  OWNS the state vector            │
└───────────────────────────────────┘         └───────────────────────────────────┘
        classical orchestration                    memory-bound quantum simulation
```

!!! warning "The split is forced, not stylistic"
    **`qiskit-aer-gpu` publishes x86_64 wheels only.** There is no aarch64 build, so
    Qiskit's GPU simulator **cannot be installed on the GB10 at all**. cuQuantum *does*
    ship aarch64, so the GPU path on Grace Blackwell is CuPy plus cuStateVec.

    Running the simulation on the GB10 therefore *requires* separating it from a UI that
    runs elsewhere. This diagram is what the hardware permits, not a preference.

## The four layers

**1 — Interface and orchestration.** Contingency parameters, topology visualization,
convergence telemetry, the exportable islanding schedule, and the domain model itself:
transmission topology, generation and load, and the QUBO construction. Holds **no quantum
state** — it sends couplings and receives energies.

**2 — Quantum formulation.** Three competing objectives reduced to a pure-quadratic Ising
Hamiltonian, dense all-to-all because the balance term couples every node to every other.
SciPy COBYLA tunes the (γ, β) schedule.

**3 — Hardware acceleration.** Dense state-vector evolution over 2ⁿ complex amplitudes as
CUDA kernels; the state lives in GPU memory and never returns to the host during a run.
Because the cost Hamiltonian is diagonal, the cost unitary is a single elementwise phase
multiply rather than thousands of RZZ gates, and ⟨H⟩ is computed **exactly**.

The QAOA mixer runs through **cuStateVec**, NVIDIA's purpose-built statevector kernels:
**4.0–4.2× measured** against the general-purpose CuPy path, agreeing to ~1e-18. The cost
unitary deliberately stays on the tiled CuPy path — routing it through cuStateVec measured
4.18× against 4.17× while requiring the full 2ⁿ phase array in device memory, 16 GB at 30
qubits. Mixer accelerated, diagonal tiled: full speed, full ceiling.

**4 — Dell infrastructure.** 128 GiB of unified memory, compute capability 12.1. Unified
memory is the binding resource for state-vector simulation, which is why a desktop-class
system carries 30 qubits of dense all-to-all QAOA. Entirely on-premise: grid topology,
generation profiles and contingency plans never leave the building.

## Request path — one optimization

```
operator sets nodes / layers / steps, presses Run
   ├─ 1. build_grid()          synthesize substations, generation, load, ratings
   ├─ 2. build_ising()         3-term objective → J_ij couplings + offset
   ├─ 3. select_backend()      GET /health → device, free memory, LIVE ceiling
   ├─ 4. POST /qaoa/optimize ──────────────────────────────────────────►  [GB10]
   │        cost_diagonal()    tiled, bounded scratch
   │        ramp init + scan   1-D scale search
   │        COBYLA outer loop  each step: evolve + ⟨H⟩ exact
   │   ◄──── { energy_history, top_states, timings, kernels } ──────────
   ├─ 5. evaluate_partition()  bitstring → MW severed, balance, FEASIBILITY
   ├─ 6. brute_force()         exact optimum, if ≤ 16 qubits (verification)
   └─ 7. render + JSON export  operator-legible schedule
```

## API surface

| Endpoint | Purpose |
|---|---|
| `GET /health` | device, free/total memory, **live** qubit ceiling — queried, never hard-coded |
| `GET /noise/ceiling` | clean and noisy ceilings from actual free memory |
| `POST /qaoa/optimize` | full run — convergence history, shortlist, timings, kernel path |
| `POST /qaoa/evaluate` | one timed energy evaluation |
| `POST /qaoa/realism` | the same circuit ideal / finite-shot / noisy |
| `POST /qaoa/verify` | proves the diagonal fast path ≡ gate-by-gate RZZ |

## Honest reporting

The result always names the path that **actually executed**, never the one requested. A
local fallback labels itself `local-*` with an explicit warning naming what the result does
not support — because a run that silently executes elsewhere while the interface reports
GB10 hardware is exactly the unearned claim this project exists to avoid.

## Security posture

| | |
|---|---|
| Data egress | none — grid topology and contingency plans never leave the building |
| Inference dependency | none — this application makes no LLM or external API calls |
| Quantum dependency | none — no cloud QPU, no vendor queue |
| Hardware | TAA-compliant, air-gappable |
| Front door | identity-proxy with passkey authentication |

## What is not done

No systemd unit for the simulation service, so it does not survive a host reboot.
The objective has no thermal term (see [note 03](notes/03-what-a-qubo-cannot-express.md)).
Roughly 3× of theoretical memory-bandwidth headroom at 30 qubits is unexplained and would
need profiling to attribute.
