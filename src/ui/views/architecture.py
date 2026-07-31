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
│  Streamlit + Plotly       :8501   │  VLAN13 │  CuPy / CUDA statevector kernels  │
│  grid model → QUBO → Ising        │◄──HTTP─►│  CuPy / CUDA 12                   │
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
  cuQuantum <em>does</em> ship aarch64 wheels, so the GPU path on Grace Blackwell is
  CuPy on CUDA.</p>
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
<div class="desc">Three competing objectives — minimize severed flow, hold each island
power-balanced, forbid the degenerate partition — reduced to a pure-quadratic Ising
Hamiltonian. The balance term couples <strong>every node to every other node</strong>, so the
problem is <strong>dense all-to-all</strong>, not the sparse transmission graph. The classical
outer loop (SciPy COBYLA) tunes the (γ, β) schedule.</div>
<div class="tech">NumPy · SciPy · shared NumPy/CuPy kernel code</div></div>

<div class="layer"><div class="tier">Layer 3 — Hardware Acceleration</div>
<div class="name">NVIDIA CUDA · CuPy statevector kernels</div>
<div class="desc">Dense statevector evolution over 2<sup>n</sup> complex amplitudes, executed
as CUDA kernels on the GPU — the state lives in GPU memory and never returns to the host
during a run. Because the cost Hamiltonian is diagonal, the cost unitary is applied as a single
elementwise phase multiply rather than thousands of individual RZZ gates, and ⟨H⟩ is computed
<strong>exactly</strong>. Memory-tiled throughout so scratch stays bounded as the statevector grows.
<br><br><strong>Honest note:</strong> these are <strong>CuPy</strong> kernels — general-purpose GPU
array operations — not NVIDIA's specialised <strong>cuStateVec</strong> quantum kernels. cuQuantum
is installed and the integration hook exists, but it is not yet on the execution path. Measured
headroom from closing that gap is roughly 12x at 30 qubits (PLAN.md M3).</div>
<div class="tech">cupy-cuda12x · CUDA 12 · cuQuantum installed, not yet on the execution path</div></div>

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

    st.markdown("### Request path — one optimization")
    st.markdown("""
<div class="flow">operator sets nodes / layers / steps, presses Run
   │
   ├─ 1. build_grid()          synthesize substations, generation, load, line ratings
   ├─ 2. build_ising()         3-term objective → J_ij couplings + offset      [xr7620]
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
  <strong>unified</strong> and shared between CPU and GPU. The resident NIM
  (<code>nim-llama8b</code>) holds ~59 GiB, which does not merely slow a run — it lowers the
  <strong>qubit ceiling from 30 to ~27</strong>, because the ceiling <em>is</em> free memory.
  An over-allocation on a unified pool can also evict the neighbour's model outright.</p>
</div>""", unsafe_allow_html=True)
    st.markdown(ui.card_html("tools/gb10-gpu", _spec([
        ("gb10-gpu claim", "stop nim-llama8b → start gridops-qsim → full 30-qubit ceiling. "
                           "<strong>nim/* goes off the LiteLLM gateway</strong> until release."),
        ("gb10-gpu release", "stop gridops-qsim → restart nim-llama8b → inference restored"),
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
