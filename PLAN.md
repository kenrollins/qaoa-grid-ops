# Grid Ops — build plan

Milestones in build order. **M0 is done and demoable today.** Everything after it
is improvement, not scaffolding.

---

## M0 — Working vertical slice ✅ DONE (2026-07-29)

End to end and verified on real hardware:

- [x] Grid domain model → three-term islanding QUBO → Ising couplings
- [x] `qaoa_core` — array-agnostic (NumPy **and** CuPy), tiled for memory
- [x] `gridops-qsim` FastAPI service live on the GB10, `setsid`-detached,
      permanent venv at `~/gridops/.venv`
- [x] Engine facade with live backend probing + honest fallback reporting
- [x] Streamlit Command Center, 4 tabs, Dell federal dark theme
- [x] JSON islanding schedule export
- [x] Verified: QAOA returns the **exact optimum** (`MATCH=True`, p=1/2/4)
- [x] Verified: diagonal fast path ≡ gate-by-gate RZZ (deviation **8.0e-17**)
- [x] Measured capability curve to **30 qubits**

**Demo it at 12–16 nodes, p=2, 30 steps.** Sub-second, verified optimal against
brute force.

---

## M1 — Make the 60 seconds land

The physics is right; the theater is not yet.

- [ ] **Live convergence.** The curve currently appears after the run completes.
      Stream it — the GB10 service already accepts a `progress` callback; add
      SSE or chunked streaming and animate. *This is the single highest-value
      visual change.*
- [x] **Contingency framing.** Line-fault selector (none / most-critical /
      choose), faulted lines drawn distinctly from deliberately opened breakers,
      contingency banner above the result.
- [x] **MW accounting.** Load served / shed, per island, plus a spectral-bisection
      baseline to compare against. Operators judge plans in MW, not Hamiltonians.
- [ ] Node hover → substation detail card.

## M2 — Credibility surface

- [x] ⚛️ Quantum explainer tab — audience-facing, states plainly this is simulation not a QPU
- [x] Architecture promoted to its own page (system diagram, request path, deployment, security)
- [x] `tools/gb10-gpu` claim/release/status — GB10 residency, mirrors `l4-fleet`
- [x] `POST /qaoa/verify` wired into Tab 3 as a live button (measures ~3.4e-17).
- [ ] Show the exact-optimum comparison as a first-class panel, not a text card.
      Brute force is affordable to ~20 qubits; make optimality *visible*.
- [ ] Surface `expectation_ratio` vs `solution_ratio` vs `concentration` as three
      labelled instruments with a sentence each. Do not collapse them into one
      "approximation ratio" — that ambiguity is what made the algorithm look
      broken during bring-up.
- [ ] Persist runs to `data/` so a demo can be replayed without a live GB10.

## M2.5 — Objective alignment ← **the top algorithm task now**

QAOA reliably finds the true optimum of the stated objective, and still loses to
spectral bisection on MW served in ~2 of 12 scenarios. The objective is a proxy
and it is misaligned in a specific, fixable way:

- [ ] **The balance term is symmetric.** `(Σpᵢsᵢ)²` penalises surplus generation
      as hard as a deficit, but only deficits shed load. Explore a one-sided
      penalty, or a per-island deficit term, that stays quadratic in the spins.
- [ ] Score directly on MW served, not on the Hamiltonian, when comparing runs.
- [ ] Sweep weights per grid size — the best weights may not be size-invariant.

## M3 — Performance headroom (real, and quantified)

At 30 qubits, one energy evaluation takes 50 s. Rough bandwidth math says it
should be closer to **4 s**: p=2 gives 2·(1+30) = 62 passes over a 16 GB
statevector ≈ 1 TB of traffic, and the GB10's unified memory does ~270 GB/s.
**~12× is being left on the floor.** Suspects, in order:

- [ ] `_apply_1q` materializes two half-size temporaries per qubit per layer.
      Fuse into a single in-place kernel (`cupy.ElementwiseKernel` or RawKernel).
- [ ] Use **cuStateVec's own `apply_matrix`** for the mixer instead of the CuPy
      reshape path. The hook (`custatevec_ctx`) exists in `apply_mixer` and is
      currently unused — this is the one place the demo names cuQuantum but does
      not yet route through it. Closing that gap is both a perf win and a
      narrative fix.
- [ ] complex64 option (halves memory → **+1 qubit**, roughly doubles bandwidth).
      Expose as a precision toggle; validate against complex128 first.
- [ ] Cache the cost diagonal across optimizer steps — it is already built once
      per `optimize_qaoa`, but the capability sweep rebuilds it per size.

## M4 — Lab tenant onboarding ✅ MOSTLY DONE (2026-07-29)

- [x] Registered via `new-tenant qaoa-grid-ops --band work` → **10.0.13.103**
- [x] Containerized on `dmz13` (`/data/docker/qaoa-grid-ops/`). Caddy is
      macvlan-only and **cannot reach the host's port** — measured, not assumed —
      so a host-side process could never have been fronted.
- [x] Caddy route + Authentik passkey app; external path verified **302 + real
      Let's Encrypt cert** through the lighthouse.
- [x] Linked from the portal Demo Floor, with live GB10 state via `/api/gridops`.
- [ ] ⚠ **OPERATOR STEP OUTSTANDING** — Unbound override
      `qaoa-grid-ops.lab.kenrollins.dev` → `10.0.13.3` (**specific host, never a
      wildcard** — OPNsense #8051 breaks Unbound LAN-wide). Until then the name
      resolves internally to the *public* lighthouse address and LAN traffic
      hairpins out and back instead of going straight to Caddy.
- [ ] Expose `/metrics` for Prometheus (`10.0.13.203`).
- [ ] The minted gateway key in `/data/docker/qaoa-grid-ops/.env` is **unused** —
      this demo makes no inference calls. Harmless, but don't let it imply one.

## M4.5 — Dependency cleanup

- [ ] `qiskit`, `qiskit-aer-gpu`, `cuquantum-python-cu12` are in the top-level
      `requirements.txt` and are **imported nowhere**. The architecture moved to
      cuStateVec-on-the-GB10 and left them vestigial: ~1 GB of wheels that also
      pin the interpreter to 3.12. The deployed image uses `requirements-ui.txt`
      and excludes them. Decide whether to drop them outright.

## M5 — GB10 service hardening

- [ ] **systemd unit** for `gridops-qsim` so it survives reboot. Needs **one
      interactive `sudo`** to install into `/opt/gridops` + `/etc/systemd/system`.
      **Do not add passwordless sudo** — nothing here needs root at runtime, and
      a standing grant weakens the host to save one password prompt.
- [ ] Move `~/gridops` → `/opt/gridops` as part of that same sudo step.
- [ ] Decide GB10 memory policy vs `nim-llama8b`. Today they contend for the same
      unified pool: NIM resident ⇒ ~27 qubit ceiling; NIM stopped ⇒ 30. Either
      accept 27 as the demo number, or script claim/release around a run.
- [ ] Health/readiness endpoint already exists — add it to the portal catalog.

## M6 — Depth and range

- [ ] Raise the node ceiling above 24 now that 30 is proven. Gate on the live
      `max_qubits` the service reports rather than a constant.
- [ ] Real IEEE test-case topologies (14/30/57-bus) alongside the synthetic grid.
      Recognizable to a DOE/ORNL audience in a way a random graph is not.
- [ ] 3+ islands (one-hot / multi-way partition). Currently strictly bipartite.
- [ ] Warm-start QAOA from a classical heuristic (spectral partition) and show
      the improvement — strong "algorithm development" content.

---

## Deliberately deferred

- **CPU-vs-GPU benchmarking.** Cut on purpose — see BRIEF.md. Do not reintroduce.
- **Real QPU integration.** The claim is about classical backbone for HQCC. A
  cloud QPU call would contradict the air-gap story.
- **Multi-user / auth.** Comes free with Authentik at M4.
- **Noise modeling.** Interesting, and orthogonal to the hardware claim.
