# Grid Ops — Hybrid Quantum-Classical Grid Optimization

Interactive demonstration of **QAOA-based microgrid islanding** running on Dell
classical infrastructure — specifically the **Dell Pro Max with GB10 Grace
Blackwell**, which carries **30 qubits of dense all-to-all QAOA** on-premise,
air-gapped, with no cloud QPU.

> Networked microgrid islanding under emergency interruption — line drop, cyber
> incident, disaster — formulated as a QUBO and solved with the Quantum
> Approximate Optimization Algorithm. In NISQ-era hybrid algorithms, the
> overwhelming majority of compute is **classical**: parameter optimization,
> circuit evolution, and expectation evaluation. That is the work Dell hardware
> absorbs, today and when real QPUs arrive.

---

## Quick start

```bash
# 1. Claim the GB10 for the demo. Stops the resident NIM and starts gridops-qsim.
cd /data/code/qaoa-grid-ops
./tools/gb10-gpu claim                          # → CLAIMED, ceiling 30 qubits

# 2. The dashboard, on xr7620
.venv/bin/python -m streamlit run app.py        # → http://<host>:8501

# 3. When finished — give the GPU back to inference
./tools/gb10-gpu release
```

Set **Substation nodes** to 12–16, **layers p** to 2, then press
**🚀 Run Hybrid Optimization**. Sub-second, and at ≤16 nodes the result is
verified against brute-force optimum.

### If the GB10 is unavailable

Switch **Backend → This host** in the sidebar. The app runs the identical
`qaoa_core` routines locally. Correct results; the hardware claim does not apply.

---

## Architecture

```
  ┌─ xr7620 ──────────────────┐        ┌─ Dell Pro Max GB10 ─────────────┐
  │  Streamlit Command Center │  VLAN  │  gridops-qsim (FastAPI :8600)   │
  │  grid model · QUBO build  │◄──13──►│  cuStateVec / CuPy              │
  │  topology · convergence   │  HTTP  │  aarch64 · Blackwell sm_121     │
  │  export · capability      │        │  128 GiB unified memory         │
  └───────────────────────────┘        └─────────────────────────────────┘
```

The split is **required**, not stylistic: `qiskit-aer-gpu` ships x86_64 wheels
only and cannot be installed on the GB10's aarch64 silicon. cuQuantum does ship
aarch64, so the GPU path is cuStateVec. See `BRIEF.md`.

```
app.py                        Streamlit entrypoint, 4 tabs
src/config/settings.py        palette, bounds, objective weights, backend URL
src/simulation/
  grid_model.py               topology → 3-term islanding QUBO → Ising
  qaoa_core.py                statevector math, NumPy *and* CuPy, tiled
  qaoa_engine.py              backend selection, run orchestration, metrics
src/ui/
  style.css                   Dell federal command-center theme
  components.py               Plotly instruments + HTML fragments
services/gb10_qsim/
  server.py                   FastAPI compute service (deploy to GB10)
  start.sh                    setsid-detached launcher
```

## Pages

### ⚡ Command Center — four tabs

1. **🗺️ Grid Topology & Microgrid Islanding** — transmission network colored by
   island assignment, severed lines dashed red, QAOA convergence, MW accounting,
   and JSON schedule export.
2. **⚛️ The Quantum Part** — what is actually quantum here, in five steps from
   substation to measured bitstring, plus the quantum/classical responsibility
   split. Opens by stating plainly that this is exact simulation and **not a
   QPU** — the audience will ask, and answering first is what keeps it credible.
3. **🔬 Under the Hood** — the QAOA ansatz, optimized (γ, β), and the measured
   probability distribution against the uniform baseline.
4. **📊 Simulation Capability** — how large a problem this machine holds, and the
   exponential memory wall. *Not* a speed comparison — see BRIEF.md.

### 🏗️ Architecture — its own page

Full system diagram, the forced x86_64/aarch64 constraint, the four-layer stack,
the request path for one optimization, deployment specifics on both hosts, the
API surface, GPU claim/release policy, measured performance, and security posture.

## GPU residency — claim before you demo

The GB10's 128 GiB is **unified** memory shared between CPU and GPU, so the
resident NIM (`nim-llama8b`, ~59 GiB) does not merely slow a run — it lowers the
**qubit ceiling from 30 to ~27**, because the ceiling *is* free memory. Same
discipline as the lab's `l4-fleet`:

```bash
./tools/gb10-gpu claim     # stop NIM → start gridops-qsim → 30-qubit ceiling
./tools/gb10-gpu status    # what is resident, VRAM used, live ceiling
./tools/gb10-gpu release   # stop gridops-qsim → restart NIM → nim/* restored
```

⚠ `claim` takes **`nim/*` off the LiteLLM gateway** until you `release`.

## Deploying the compute service

```bash
rsync -a --exclude __pycache__ src/ gb10:gridops/src/
rsync -a services/gb10_qsim/ gb10:gridops/services/gb10_qsim/
ssh gb10 '~/gridops/services/gb10_qsim/start.sh'
```

| endpoint | purpose |
|---|---|
| `GET /health` | device, free memory, **live** qubit ceiling |
| `POST /qaoa/optimize` | full QAOA run — history, best bitstring, timings |
| `POST /qaoa/evaluate` | one timed energy evaluation (capability sweep) |
| `POST /qaoa/verify` | proves the diagonal fast path ≡ gate-by-gate RZZ |

## Measured performance (GB10, 2026-07-29)

| qubits | statevector | 1 energy eval |
|---|---|---|
| 24 | 0.25 GB | **0.67 s** |
| 26 | 1.0 GB | 2.6 s |
| 28 | 4.0 GB | 11.6 s |
| 30 | 16 GB | 50 s |

6–24 qubits is interactive. 30 qubits runs and is the capability statement.
Correctness: QAOA returns the **exact optimum** at p=1/2/4 on 12 nodes; the
diagonal fast path matches gate-by-gate RZZ to **8.0e-17**.

## Requirements

Python **3.12** (`qiskit-aer-gpu` has no 3.13 wheel; `qiskit` pinned `<2` for
Aer 0.15.1 compatibility). GB10 side needs `cuquantum-python-cu12`, `cupy-cuda12x`,
`fastapi`, `uvicorn` — all with aarch64 wheels.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Chosen over MIT for its explicit
patent grant, which matters more in corporate and government evaluation
contexts.

## A note on what this is

A technical demonstrator and a set of measured findings, not a production grid
tool. The power-flow model is a DC approximation, the noise model is generic
depolarizing rather than device-calibrated, and the grid topologies are
synthetic. Every claim carries its provenance — measured, computed, or cited —
and the limits are stated where the results are presented.
