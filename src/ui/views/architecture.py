"""Page: Architecture — the full system, not the marketing version.

Deliberately includes the constraints and the forced decisions, because this is
the page a technical evaluator reads, and the fastest way to lose that reader is
a diagram that implies everything was a free choice.
"""

from __future__ import annotations

import streamlit as st

from src.config.settings import GB10_QSIM_URL
from src.ui import components as ui


def _spec(rows: list[tuple[str, str]]) -> str:
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f'<table class="spec">{body}</table>'


def render(backend: dict) -> None:
    total_gb = backend.get("total_memory_bytes", 0) / 2**30
    live = backend.get("available", False)
    # An unreachable backend has no ceiling; printing 0 reads as a live
    # measurement of zero rather than an absence of measurement.
    ceiling = backend.get("max_qubits", 0) if live else "—"

    st.markdown("### System architecture")
    st.markdown(f"""
<div class="flow">┌─ xr7620 ──────────────────────────┐         ┌─ Dell Pro Max GB10 ───────────────┐
│  QAOA Grid Ops Command Center     │         │  gridops-qsim  (FastAPI :8600)    │
│                                   │         │                                   │
│  Streamlit + Plotly       :8501   │  VLAN13 │  cuStateVec mixer kernels         │
│  grid model → QUBO → Ising        │◄──HTTP─►│  CuPy tiled diagonal · CUDA 12    │
│  backend probe · run orchestration│  JSON   │  aarch64 · Blackwell sm_121       │
│  topology · convergence · export  │         │  {total_gb:>5.0f} GiB unified memory        │
│                                   │         │  live ceiling: {ceiling!s:>2} qubits          │
│  NO quantum state held here       │         │  OWNS the statevector             │
└───────────────────────────────────┘         └───────────────────────────────────┘
        classical orchestration                    memory-bound quantum simulation</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="callout">
  <div class="h">The split is forced, not stylistic</div>
  <p><strong>qiskit-aer-gpu publishes x86_64 wheels only.</strong> There is no aarch64 build,
  so Qiskit's GPU simulator <strong>cannot be installed on the GB10 at all</strong>.
  cuQuantum and CuPy <em>do</em> ship aarch64 wheels, so the GPU path on Grace Blackwell
  uses cuStateVec for the mixer and tiled CuPy kernels for the diagonal cost operation.</p>
  <p>Running the quantum simulation on the GB10 therefore <em>requires</em> separating it
  from a UI that runs elsewhere. This diagram is what the hardware permits, not a preference.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("### The four layers")
    st.markdown(f"""
<div class="layer"><div class="tier">Layer 1 — Interface &amp; Orchestration</div>
<div class="name">Operations Command Center</div>
<div class="desc">Contingency parameters, topology visualization, convergence telemetry, and
the exportable islanding schedule. Also owns the domain model: transmission topology,
generation and load profiles, and the QUBO construction. Holds <strong>no quantum state</strong>
— it sends couplings and receives energies.</div>
<div class="tech">Streamlit · Plotly · NetworkX · xr7620</div></div>

<div class="layer"><div class="tier">Layer 2 — Quantum Formulation</div>
<div class="name">QUBO / Ising Model + QAOA Ansatz</div>
<div class="desc">The analytic formulation reduces three objectives to a pure-quadratic
Ising Hamiltonian. The alternative formulation labels partitions with DC power flow and fits
those outcomes onto the same pairwise basis, retaining held-out error. Both are
<strong>dense all-to-all</strong>. The classical outer loop (SciPy COBYLA) tunes the
(γ, β) schedule.</div>
<div class="tech">NumPy · SciPy · shared NumPy/CuPy kernel code</div></div>

<div class="layer"><div class="tier">Layer 3 — Hardware Acceleration</div>
<div class="name">NVIDIA cuQuantum cuStateVec · CuPy · CUDA 12</div>
<div class="desc">Dense statevector evolution over 2<sup>n</sup> complex amplitudes, executed
as CUDA kernels on the GPU — the state lives in GPU memory and never returns to the host
during a run. Because the cost Hamiltonian is diagonal, the cost unitary is applied as a single
elementwise phase multiply rather than thousands of individual RZZ gates, and ⟨H⟩ is computed
<strong>exactly</strong>. The mixer executes in place through NVIDIA's specialised
<strong>cuStateVec applyMatrix</strong> primitive. The diagonal cost unitary remains tiled in
<strong>CuPy</strong>: moving it to cuStateVec measured no material gain and required another
full-width complex array. The reported kernel path names what actually initialized.</div>
<div class="tech">cuquantum-python-cu12 · cupy-cuda12x · CUDA 12</div></div>

<div class="layer hw"><div class="tier">Layer 4 — Dell Infrastructure Backbone</div>
<div class="name">Dell Pro Max with GB10 — Grace Blackwell</div>
<div class="desc">{total_gb:.0f} GiB of <strong>unified</strong> memory, compute capability
{backend.get('compute_capability', '12.1')}. Unified memory is the binding resource for
statevector simulation — which is why a desktop-class system carries
<strong>{ceiling}{" qubits" if live else ""}</strong> of dense all-to-all QAOA. Entirely on-premise: grid topology,
generation profiles, and contingency plans never leave the building. No public cloud QPU,
no third-party API, no egress.</div>
<div class="tech">TAA-compliant · air-gappable · {backend.get('device', 'NVIDIA GB10')}</div></div>
""", unsafe_allow_html=True)

    st.markdown("### NVIDIA software and package stack")
    st.markdown("""
| NVIDIA software or package | What it does here |
|---|---|
| **NVIDIA CUDA 12** | Device runtime, memory allocation, contexts, and kernel execution |
| **NVIDIA cuQuantum — cuStateVec** | Purpose-built state-vector primitives; `applyMatrix` executes every one-qubit mixer rotation in place |
| **`cuquantum-python-cu12`** | Python bindings used to create the cuStateVec handle, declare CUDA data types, and call cuStateVec |
| **CuPy — `cupy-cuda12x`** | CUDA-backed arrays for initialization, tiled cost phases, probabilities, expectations, and the correct accelerator fallback |
| **NVIDIA driver tooling** | `nvidia-smi` supplies live process-memory observations for residency status and diagnosis |

The split is measured rather than decorative: the mixer was **4.0–4.2× faster** through
cuStateVec than through the generic CuPy reshape path. The diagonal measured effectively the
same either way, so it stays on the lower-memory tiled CuPy path. Qiskit Aer GPU is not in the
product path because its GPU wheels are x86_64-only and cannot run on the GB10's aarch64 host.
""")

    st.markdown("### Request path — one optimization")
    st.markdown("""
<div class="flow">operator sets nodes / layers / steps, presses Run
   │
   ├─ 1. build_grid()          synthesize substations, generation, load, line ratings
   ├─ 2. build_ising()         analytic or fitted objective → J_ij + offset    [xr7620]
   ├─ 3. select_backend()      GET /health → device, free memory, LIVE ceiling
   │
   ├─ 4. POST /qaoa/optimize ──────────────────────────────────────────────►  [GB10]
   │        { n_qubits, couplings, offset, layers, steps }
   │                                            │
   │                             cost_diagonal()│ tiled, n·2^tile scratch
   │                          ramp init + scan  │ 1-D scale search
   │                          COBYLA outer loop │ each step: evolve + ⟨H⟩ exact
   │                            top_bitstrings()│ argpartition, not a full sort
   │                                            ▼
   │   ◄──────── { energy_history, best_bitstring, top_states, timings } ────
   │
   ├─ 5. evaluate_partition()  bitstring → MW severed, island balance, FEASIBILITY
   ├─ 6. brute_force()         exact optimum, if ≤ 16 qubits (verification)
   └─ 7. render + JSON export  operator-legible schedule</div>
""", unsafe_allow_html=True)

    st.markdown("### Deployment")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(ui.card_html("Command Center — xr7620", _spec([
            ("Process", "streamlit run app.py"),
            ("Port", "8501"),
            ("Python", "3.12 (aer-gpu has no 3.13 wheel)"),
            ("Holds", "grid model, QUBO build, UI state"),
            ("GPU", "none required"),
            ("Lab status", "not yet a registered tenant — no VLAN-13 "
                           "address, Caddy route, or Authentik app (PLAN.md M4)"),
        ])), unsafe_allow_html=True)
    with c2:
        st.markdown(ui.card_html("gridops-qsim — GB10", _spec([
            ("Endpoint", GB10_QSIM_URL),
            ("Service", "FastAPI + uvicorn, setsid-detached"),
            ("Root", "~/gridops  (→ /opt/gridops at M5)"),
            ("Launcher", "services/gb10_qsim/start.sh"),
            ("Persistence", "no systemd unit yet — will not "
                            "survive a GB10 reboot (PLAN.md M5)"),
            ("Memory guard", "MEMORY_SAFETY=0.55 of free VRAM"),
        ])), unsafe_allow_html=True)

    st.markdown("### API surface")
    st.markdown(ui.card_html("gridops-qsim endpoints", _spec([
        ("GET /health", "device, free/total memory, <strong>live</strong> qubit ceiling — "
                        "the ceiling is queried, never hard-coded"),
        ("POST /qaoa/optimize", "full QAOA run — convergence history, best bitstring, "
                                "top measured states, timings"),
        ("POST /qaoa/evaluate", "one timed energy evaluation — the unit of the capability sweep"),
        ("POST /qaoa/verify", "applies every RZZ individually and compares against the "
                              "diagonal fast path — measured deviation 8.0e-17"),
    ])), unsafe_allow_html=True)

    st.markdown("### GPU residency — claim / release")
    st.markdown("""
<div class="callout">
  <div class="h">The GB10 is claimed, not shared</div>
  <p>Same discipline as the lab's L4 fleet: a demo <strong>claims</strong> the GPU, gets the
  whole machine, and <strong>releases</strong> it so the default inference tenant returns.</p>
  <p>On the GB10 this matters more than on a discrete GPU, because its memory is
  <strong>unified</strong> and shared between CPU and GPU. Models loaded by the GB10 vLLM
  orchestrator consume nearly the whole pool, which lowers the qubit ceiling because the
  ceiling <em>is</em> free memory.
  An over-allocation on a unified pool can also evict the neighbour's model outright.</p>
</div>""", unsafe_allow_html=True)
    st.markdown(ui.card_html("tools/gb10-gpu", _spec([
        ("gb10-gpu claim", "record and unload resident orchestrator models → start gridops-qsim. "
                           "<strong>GB10 LiteLLM lanes are unavailable</strong> until release."),
        ("gb10-gpu release", "stop gridops-qsim → restore exactly the evacuated models"),
        ("gb10-gpu status", "what is resident, VRAM in use, and the live qubit ceiling"),
    ])), unsafe_allow_html=True)

    st.markdown("### Measured performance")
    st.markdown(ui.card_html("GB10 — dense all-to-all QAOA, p=2, cuStateVec (2026-07-30)",
                             _spec([
        ("24 qubits", "0.25 GB statevector · <strong>0.16 s</strong> per energy evaluation"),
        ("26 qubits", "1.0 GB · 0.65 s"),
        ("28 qubits", "4.0 GB · 2.78 s"),
        ("30 qubits", "<strong>16 GB</strong> · 12 s — capability ceiling, not interactive"),
        ("Interactive range", "6–24 qubits — 0.16 s or less per energy evaluation; "
                              "a full 30-step optimization is ~5 s at 24 qubits "
                              "(arithmetic from the measured rate), well under a second "
                              "per step below ~20 qubits"),
        ("Correctness", "QAOA returns the <strong>exact optimum</strong> at p=1/2/4, "
                        "verified by brute force"),
        ("Kernel path", "the mixer runs on <strong>cuStateVec</strong> — 4.0-4.2x measured "
                        "against the general-purpose CuPy path, agreeing to ~1e-18. The "
                        "diagonal cost unitary stays tiled on CuPy: same speed, and it "
                        "keeps the full 30-qubit ceiling"),
        ("Known headroom", "~3x remains against a bandwidth-bound estimate at 30 qubits, "
                           "unattributed — it would need profiling to explain, and is "
                           "reported rather than guessed at"),
    ])), unsafe_allow_html=True)

    st.markdown("### Security posture")
    st.markdown(ui.card_html("On-premise by construction", _spec([
        ("Data egress", "none — grid topology, generation profiles and contingency plans "
                        "never leave the building"),
        ("Inference dependency", "none — this application makes no LLM or external API calls"),
        ("Quantum dependency", "none — no cloud QPU, no vendor queue, no scheduling delay"),
        ("Hardware", "TAA-compliant Dell infrastructure, air-gappable"),
        ("Network", "GB10 reached over VLAN 13; the lab's DMZ→LAN path is blocked by policy"),
        ("Front door (planned)", "Caddy + Authentik passkey at "
                                 "qaoa-grid-ops.lab.kenrollins.dev — PLAN.md M4"),
    ])), unsafe_allow_html=True)

    if not live:
        st.warning(f"gridops-qsim is not answering at {GB10_QSIM_URL} — "
                   "figures above describe the intended deployment. "
                   "Run `tools/gb10-gpu claim` to bring it up.")
