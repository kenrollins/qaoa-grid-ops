# 03 — Architecture assessment

Fable review, 2026-07-30. Findings numbered A-NN. **Everything here is a plan —
no structural change was executed** (per MISSION). Line references are to the
branch after the Phase 1/2 commits.

---

## 1. Decomposing `qaoa_engine.py` (614 → ~630 LOC after fixes)

### What it currently owns (four change-reasons in one file)

| Concern | Symbols | LOC | Changes when… |
|---|---|---|---|
| Backend discovery & transport | `BackendInfo`, `_http_json`, `probe_gb10`, `probe_local`, `_max_qubits_for`, `select_backend` | ~105 | the service API or lab hardware changes |
| Run result model | `IslandingRun` + 7 derived properties | ~110 | the UI needs a new number |
| Physics post-selection | `_plan_score`, `_select_plan` | ~65 | operator policy changes |
| Orchestration & endpoints | `run_islanding_optimization`, `_run_local`, `scaling_probe`, `verify_fast_path`, `run_realism` | ~330 | the demo's flow changes |

The four concerns are already cleanly separated *within* the file (no tangled
state; module-level functions only), which makes the split low-risk and also
means it is not urgent. The real costs of the current shape: (a) the
gb10-try/except-fallback/local-xp dance is pasted four times (optimize,
evaluate in `scaling_probe`, `verify_fast_path`, `run_realism`) and the four
copies have already drifted (only `optimize` appends a fallback warning; only
`realism` returns error dicts instead of raising); (b) `_max_qubits_for` and
`WORKING_SET_FACTOR = 1.6` exist in two other places (server.py `_max_qubits`,
and the literal `1.6` in `scaling_probe`'s row dict) and can drift — the
memory-guard constant is the one number that must never disagree between the
UI's expectations and the service's refusals.

### Proposed split (facade preserved, zero UI churn)

```
src/simulation/
  capacity.py      _max_qubits_for, WORKING_SET_FACTOR, statevector-working-set
                   arithmetic. Imported by BOTH the engine and services/gb10_qsim
                   (the service already imports src.simulation.* from the rsynced
                   tree, so sharing is free). Kills the three-way drift risk.
  backends.py      BackendInfo, probes, select_backend, _http_json, and ONE
                   dispatch(endpoint, payload, local_fn, *, on_fallback) helper
                   that owns the try/fallback/xp-selection dance. ~150 LOC.
  post_selection.py  _plan_score, _select_plan (+ the security-before-shed
                   comment block, which is policy documentation). ~70 LOC.
  qaoa_engine.py   IslandingRun + the five public entry points, each now ~15
                   lines of orchestration over backends.dispatch(). Re-exports
                   select_backend etc. so app.py/command_center imports are
                   untouched. ~250 LOC.
```

Why this grouping and not others considered: splitting `IslandingRun` out was
rejected (it is the engine's public return type; separating it buys nothing but
an import hop); splitting each endpoint into its own module was rejected (they
share the dispatch pattern, which is the thing worth extracting). `capacity.py`
is the only piece with a correctness argument rather than a hygiene argument —
**if only one step lands, land that one.**

Sequencing (each step independently committable + AppTest-gated):
1. `capacity.py`, imported by engine + server (server change needs an rsync to
   the GB10 — coordinate with a deploy).
2. `backends.py` with `dispatch()`; port the four endpoints one commit each.
3. `post_selection.py` (pure move).
Effort: half a day total. Risk: step 1 touches the deployed service; 2-3 are
local-only.

### A-01 — Engine split as above — P2, REPORTED, effort M
### A-02 — Memory-guard arithmetic exists in three places — P1 (drift risk), REPORTED, effort S (subset of A-01 step 1)

---

## 2. The unused `custatevec_ctx` hook — close it or stop naming it

**Status:** `apply_mixer(..., custatevec_ctx=None)` threads through
`qaoa_statevector` and `optimize_qaoa`; nothing anywhere constructs a context.
The GPU path is **pure CuPy** — stride-reshape kernels in `qaoa_core`.

**This is quietly a claims problem, not just a performance one.** The
Architecture page's ASCII diagram says the GB10 side runs "cuStateVec
(cuQuantum)"; Layer 3 is titled "NVIDIA cuQuantum · cuStateVec" and credits it
with "dense statevector evolution"; the service's `/health` detail string says
"cuStateVec via cuquantum-python + CuPy"; sources.py says the compute service
"runs on cuquantum-python-cu12 plus CuPy". The library is installed and the
statement is *deployment-true but execution-false*: no cuStateVec kernel ever
runs. An evaluator who straces the service or reads `qaoa_core.py` (public
repo!) can see this. The project's own seed doc flags it as "the one place the
demo names cuQuantum without routing through it."

**Two honest exits:**

- **(a) Implement the context (recommended — it is already PLAN.md M3).**
  A ~70-line wrapper in the service: `custatevec.create()` handle,
  `apply_matrix` with `CUSTATEVEC_MATRIX_LAYOUT_ROW`, external workspace sized
  once per run, `apply_matrix_1q(sv, t, m)` matching the call-site signature
  qaoa_core already defined. Construct it in server.py's optimize/evaluate
  paths and pass through. The mixer is the only consumer (the cost unitary is
  an elementwise multiply — cuStateVec has nothing to add there; keep that
  fact in the Layer-3 text). Value: the architecture claims become
  execution-true, and M3's measured ~12× headroom at 30 qubits names the
  mixer's reshape path as prime suspect, so this is also the performance
  experiment M3 wants. **Constraint: cannot be validated off the GB10** —
  needs aarch64 + cuStateVec + the live service. Effort M (code S, validation
  is the cost: re-run the M3 bandwidth arithmetic and `GB10_MEASURED` after).
- **(b) Reword the claims to "CuPy today, cuStateVec at M3"** — 15 minutes,
  zero risk, and the honesty discipline is preserved. Do (b) immediately if
  (a) will not land before the next external demo.

### A-03 — cuStateVec named but never executed — P1, REPORTED (option b is S; option a is M and GB10-bound)

---

## 3. Performance leads (seed-doc items verified/updated)

- **`noise.py::depolarize` — RESOLVED this review** (F-16, commit c8a8a5c):
  closed-form channel, zero full-ρ copies, verified 1.1e-16 against the old
  implementation. The remaining noisy-path allocator is `_rho_apply_1q` (four
  half-ρ `.copy()`s per mixer gate on the density matrix). The same
  block-arithmetic trick applies (RX on row+column indices with one quarter
  temp), worth doing only if noisy demos at 13-14 qubits feel slow on the GB10.
- **`learn.py::_tradeoff_data` — CONFIRMED as written, worse than the seed
  says.** It runs `evaluate_partition` + a full `pf.solve` for **every** of the
  2ⁿ bitstrings, and because `st.tabs` executes all tab bodies, the first
  render of *any* tab pays it. At the default n=10 that is 1,024 solves
  (seconds); at the slider max n=12 it is 4,096 (tens of seconds, blocking).
  Fixes in preference order: (1) exploit the Z₂ symmetry the project already
  teaches — evaluate only bitstrings with bit n−1 = 0 and mirror the results:
  exact same figure, **half the cost, one line**; (2) keep exhaustive ≤10 and
  sample at 12 with the brute-force optimum and baseline always included;
  (3) the D-01 restructure (pages, not tabs) makes it lazy. (1) is a
  no-brainer commit for the next session; it was found too late in this one to
  gate and land safely. — **A-04, P2, effort S**
- **`app.py` recomputes `worst_contingency` (a full N-1 screen, |E| DC solves)
  on every widget interaction** while `fault_mode` is "Trip the most critical
  line" (the default). `n1_screen` is deterministic in `(spec, seed)`;
  `@st.cache_data` on a small wrapper keyed by the spec tuple removes ~15
  solves per rerun. Imperceptible at n=12, noticeable at n=24. — **A-05, P3,
  effort S**
- **M3's ~12× headroom at 30 qubits** — see A-03(a); the mixer ctx experiment
  is the designed probe for it. Nothing further to add from a machine without
  the hardware.

---

## 4. Smaller architectural observations

- **A-06 (P3)** — `probe_local()`'s CPU fallback hard-codes `max_qubits=24` and
  `free_memory_bytes=0`. F-06's UI gating removed the *claim* problem; probing
  real host memory (`os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_AVPHYS_PAGES')`,
  no new dependency) would remove the *data* problem and make the F-14 guard's
  8-GiB assumption unnecessary.
- **A-07 (P3)** — `run_islanding_optimization` checks `spec.n_nodes` against
  the ceiling but runs on `graph` when supplied; a caller passing a graph of
  different order than `spec.n_nodes` would dodge the warning. Today app.py
  always builds both from the same spec; assert `graph.number_of_nodes() ==
  spec.n_nodes` to keep it true.
- **A-08 (P3)** — `verify_fast_path` filters couplings to `i, j < 18` when
  truncating but keeps the full `offset`; harmless for the equivalence check
  (both paths share the model) — a one-line comment would stop the next reader
  re-deriving that.
- **Not a finding:** the UI-never-imports-CuPy boundary, the explicit backend
  reporting, the calibrate-once `_rated`/`_electrical` flags, and the
  post-selection policy ordering are all sound as designed. The BLE001 blind
  excepts in the probe path are deliberate and correctly scoped.
