# Seed findings — recon handover for the Fable review (2026-07-30)

**Purpose.** Pre-computed reconnaissance so the review starts at *judgment*, not
discovery. Everything below was measured against the code at commit `e06d0f7`.
Items marked `CONFIRMED` were checked this session; `SUSPECTED` needs verifying.

Do not spend cycles re-deriving what is here. Spend them on what this pass missed.

Scope requested: **code and design/visual**, both.

---

## Quality baseline (CONFIRMED)

- **5,281 lines** of Python across **21 files**.
- **Zero tests.** No test files, no pytest config, no CI. This is the single
  largest gap in the project.
- **No lint or type configuration** — no `pyproject.toml`, `ruff.toml`, or
  `mypy.ini`. `ruff` was installed ad hoc for this recon and is not a dependency.
- **No TODO/FIXME/HACK markers** anywhere.
- `ruff check` (default rules): **180 findings**, but see the triage below — the
  overwhelming majority are noise, not defects.

### Ruff triage — do not burn budget on the top line

| Rule | Count | Verdict |
|---|---|---|
| C408 unnecessary-collection-call | 123 | **Ignore.** `dict(...)` inside Plotly figure specs. Idiomatic for Plotly, and rewriting to literals would hurt readability. Configure the rule off. |
| ISC004 implicit-str-concat | 12 | Cosmetic. |
| BLE001 blind-except | 9 | **Worth a look.** Several are deliberate (backend probing must not raise), but confirm each. |
| F401 unused-import | 6 | Real, trivial. |
| F821 undefined-name | 2 | **Not a false positive — see below.** |
| F841 unused-variable | 2 | Real, trivial. |
| S110 try-except-pass | 2 | Deliberate in `probe_local()`; confirm the other. |

**Recommendation:** add a `pyproject.toml` with ruff configured (ignore C408,
ISC004), then the signal is roughly 25 findings rather than 180.

---

## The one latent bug found in recon (CONFIRMED)

`src/simulation/qaoa_core.py` — `optimize_qaoa()`:

- `diag` is created at **line 265**
- the `energy_of` closure captures it at **lines 276 and 280**
- `diag` is **deleted at line 380** (`del sv, diag`), for GPU memory reasons

This works today because every `energy_of` call happens before line 380. It is
nonetheless a trap: any future code that invokes the closure after the `del`
raises `NameError`, and the `del` looks load-bearing (it frees a
2ⁿ-element array on the GPU), so a reader is unlikely to remove it.

Ruff flags this as F821. It is the only ruff finding that represents a real
defect. Suggested fix: pass `diag` explicitly or restructure so the lifetime is
obvious.

---

## Code map

| Module | LOC | Role | Risk |
|---|---|---|---|
| `simulation/qaoa_engine.py` | 614 | Backend selection, run orchestration, post-selection | **Highest.** Largest file, most responsibilities. Candidate for a split. |
| `ui/views/limits.py` | 530 | The "why this is hard" argument + charts | Prose-heavy; mixes content with figure code. |
| `simulation/grid_model.py` | 475 | Topology → QUBO, feasibility, load accounting | Dense but cohesive. |
| `ui/control_room.py` | 442 | One-line diagram, animation, alarm log | Figure construction is long and linear. |
| `simulation/qaoa_core.py` | 426 | The quantum math (NumPy/CuPy agnostic) | **Most correctness-critical.** Also the best-commented. |
| `ui/views/learn.py` | 416 | Visual QAOA explainer | Recomputes heavy figures; see performance below. |
| `simulation/power_flow.py` | 383 | DC power flow, ratings, N-1 screen | Correctness-critical, no tests. |

---

## Deliberate decisions — do NOT "fix" these

Each of these looks like a defect and is not. Reversing any of them undoes
something that was measured.

1. **The diagonal fast path in `qaoa_core`.** The cost unitary is applied as an
   elementwise phase multiply rather than gate-by-gate RZZ. This is an
   optimisation, **not** an approximation — `verify_equivalence()` measures
   agreement at 3.4e-17, and the demo exposes that check as a live button.
2. **Tiled kernels** in `cost_diagonal` and `apply_cost_diagonal`. They look
   like premature optimisation. They are not: the untiled versions need 30 GB
   and 34 GB respectively at 30 qubits. Comments explain this in situ.
3. **Post-selection ranks thermal security above load shed.** Ranking shed-first
   reads as more operator-friendly and is wrong — it accepts a cascade to avoid
   shedding, and a cascade sheds everything.
4. **The objective has no thermal term, and the UI says so.** This is a known,
   documented limitation (PLAN.md M2.5), not an oversight. The demo displays the
   case where a classical spectral baseline beats QAOA rather than hiding it.
5. **No CPU-vs-GPU benchmark.** Deliberately cut. Measured honestly it was
   1.2–2.2x, not the 20–30x the original spec assumed, and the framing invites a
   methodology argument the demo would lose. Do not reintroduce it.
6. **plotly.js is served from `static/`, not a CDN.** A CDN is 40x lighter and
   breaks air-gapped — which is the deployment this demo argues for.
7. **RFC1918 addresses remain in the architecture docs.** Audited and kept
   deliberately; they describe the real deployment and are meaningless off that
   network.
8. **`st.iframe`, not `st.components.v1.html`.** The latter is past its removal
   date (2026-06-01).

---

## Leads worth verifying

**Performance**
- `ui/views/learn.py::_tradeoff_data` runs a full DC power flow for **every one
  of 2ⁿ partitions** — 4,096 solves at 12 nodes. Cached via `st.cache_data`, but
  first render is slow and it is the default figure on a tab. SUSPECTED: worth
  sampling or capping rather than exhausting.
- `simulation/noise.py::depolarize` copies the full density matrix three times
  per qubit per layer (one per Pauli). At 14 qubits ρ is 4 GB, so this is the
  dominant cost of noisy runs. SUSPECTED: in-place Pauli conjugation is possible
  for X and Z (permutation and sign flip respectively) and would cut allocations
  substantially.
- `M3` in PLAN.md documents ~12x of measured headroom at 30 qubits, with the
  mixer's CuPy reshape path as the prime suspect. The `custatevec_ctx` hook in
  `apply_mixer` exists and is **unused** — this is the one place the demo names
  cuQuantum without routing through it.

**Correctness**
- `power_flow.py` has no tests and is load-bearing for every number on screen.
  Highest-value place to add them: DC flow conservation (sum of injections ≈ 0),
  flows antisymmetric, island detection matching `networkx` components.
- `grid_model.py::evaluate_partition` feasibility logic (contiguity over *live*
  edges only) is subtle and untested.

**Design / visual — Ken explicitly wants this reviewed**
- **Tab redundancy.** There are now six tabs plus a separate Architecture page.
  `views/quantum.py` ("The Quantum Part") and `views/learn.py` ("Learn QAOA —
  visually") **substantially overlap** — both explain superposition, the cost and
  mixer operators, and the hybrid loop. This redundancy was introduced
  incrementally and has not been reconciled. Strong candidate for a merge.
- Information architecture generally: is six tabs plus a page the right shape,
  or should the demo split into "operate" and "understand" surfaces?
- The one-line diagram legend, colour bands, and animation speed have not had a
  design pass. The colour scheme follows EMS convention (voltage class sets
  colour/width, loading sets alarm colour), which should be preserved — but the
  execution is unreviewed.
- A colour-scale bug survived several sessions here (`reversescale=True` put the
  *best* result in the hottest colour while the caption said cool-is-better).
  Worth checking every figure for caption/encoding agreement.
- Accessibility: nothing has been checked. Colour-only encoding is used in
  several places.

---

## Context that changes what "good" means here

This is a **demonstrator and a teaching artifact**, not a production tool. Two
consequences for the review:

- **Comments are unusually long and are load-bearing.** They record *why* a
  decision was made and frequently cite a measurement that justified it. They are
  content, not clutter. Compressing them loses the project's main asset.
- **Honesty about limitations is a feature.** The UI deliberately surfaces cases
  where the quantum result is worse than a classical baseline, and states what
  the models do not capture. Do not "improve" the demo by removing those.

Public repository: <https://github.com/kenrollins/qaoa-grid-ops> (Apache-2.0).
The next planned step after this review is a GitHub Pages site mirroring the
app's tabs, so **design decisions made here will propagate to the public site.**
