# 01 — Code findings (claim accuracy + correctness)

Fable review, 2026-07-30, branch `fable/review-2026-07-30`, baseline `main` @ c6d58c8.
Phase 1 = claim accuracy (every number/figure vs what the code computes).
Phase 2 findings are appended below the Phase 1 block.

Verification artifacts: the numeric checks quoted here were produced by
`scratchpad/verify.py` (session-local); each finding quotes the measured output inline,
so the findings stand alone.

---

## Phase 1 — Claim accuracy

### F-01 — Power-flow arrows render mirrored east–west (direction of flow is wrong on screen)
- **Severity:** P0 correctness/accuracy
- **Status:** CONFIRMED
- **Location:** `src/ui/control_room.py:137` (static arrows), `src/ui/control_room.py:336` (animated track)
- **Evidence:** Both paths compute the marker angle as `ang - 90` where
  `ang = degrees(atan2(dy, dx))` in data space (y up). Plotly's `marker.angle` is
  measured **clockwise from screen-up** (`angleref: "up"`). The bundled
  `static/plotly.min.js` (v3.8.2) proves the convention in its own `angleref:
  "previous"` implementation: it computes the along-line rotation as
  `atan2(Δy_px, Δx_px)·180/π + 90` in **pixel** space, where `Δy_px = −dy`. So the
  correct pointing angle is `90 − ang`; the code's `ang − 90` is its negation — a
  reflection about the vertical axis. Arrows on vertical lines are correct; on
  horizontal lines they point exactly backwards; everything else is mirrored E–W.
  The animated arrows *march* in the correct direction (positions interpolate from
  the true source node) while *pointing* mirrored, so on many lines the arrowheads
  point against their own motion.
- **Why it matters:** "Arrows show where the power is going" is the diagram's core
  claim (module docstring, narration step ①: "Arrows are the electricity itself").
  A grid operator reads flow direction off the arrowhead instantly and will see
  power flowing *into* generators on east–west corridors.
- **Fix:** `angle=(90 - ang) if flow >= 0 else (270 - ang)` in `one_line_diagram`;
  `ang = 90 - degrees(atan2(y1-y0, x1-x0))` in `_line_arrow_track`. One-minute
  visual sanity check on a horizontal line recommended after deploy.
- **Disposition:** APPLIED (commit 6ffc8ae)
- **Effort:** S

### F-02 — Severed/faulted line MW shown to the operator comes from the synthetic `flow_mw`, not the solved flow
- **Severity:** P0 correctness/accuracy
- **Status:** CONFIRMED
- **Location:** `src/simulation/grid_model.py:372` (`evaluate_partition` severed lines),
  `src/simulation/grid_model.py:189` (`faulted_edges`); consumed by
  `src/ui/control_room.py:283-285` (event log "OPEN BREAKER … (N MW)"),
  `src/ui/components.py:311-313` + `:324-327` (JSON export), and `interrupted_mw`
  everywhere it appears.
- **Evidence:** `build_ising._cut_weight` (grid_model.py:287-289) deliberately uses
  `base_flow_mw` (the solved DC base-case flow), with a comment calling `flow_mw`
  "a synthetic generator attribute that has no relationship to where power really
  goes … minimising it optimised a fiction." Yet `evaluate_partition` reports
  `severed_lines`/`interrupted_mw` from `flow_mw`, and `faulted_edges` does the same.
  Measured (10-node default grid, worst contingency): severed line (8,9) is
  reported as **67.2 MW** while its solved base flow is **4.1 MW** — 16× off.
  Meanwhile `command_center.py:71-73` labels the *same faulted line* with
  `base_flow_mw`, so the narration header and the event log/JSON quote different MW
  for one line in one screen flow.
- **Why it matters:** The event log line "OPEN BREAKER GEN-08 ↔ SUB-09 (67 MW)" and
  the JSON export's `interrupted_mw` are operator-facing physical claims. The demo's
  own code comments call this basis a fiction. An audience member who sums severed
  MW against the displayed line flows (which come from the solve) will catch it.
- **Fix:** Use `e.get("base_flow_mw", e["flow_mw"])` in `evaluate_partition` and
  `faulted_edges` (same fallback pattern as `build_ising`). Note `_plan_score` uses
  `interrupted_mw` as its 5th tie-break, so ranking can shift — in the direction of
  physics.
- **Disposition:** APPLIED (commit 0b8a9b7)
- **Effort:** S

### F-03 — Architecture page: "a full 30-step optimization in ~0.1–0.7 s" contradicts the measured rate two rows above
- **Severity:** P0 correctness/accuracy
- **Status:** CONFIRMED
- **Location:** `src/ui/views/architecture.py:174`
- **Evidence:** The same table states 24 qubits = **0.67 s per energy evaluation**
  (matching `limits.py:GB10_MEASURED`). The "Interactive range" row then claims
  "6–24 qubits — a full 30-step optimization in ~0.1–0.7 s". 30 steps × 0.67 s ≈
  **20 s** at 24 qubits, ~30× the claimed upper bound.
- **Why it matters:** This is the page a technical evaluator reads, and the
  contradiction is checkable using only the numbers in the same card. Wrong number
  on screen for a federal audience = the exact failure mode the project's own
  claims discipline exists to prevent.
- **Fix:** Reword using only measured/arithmetic figures, e.g. "6–24 qubits —
  0.67 s or less per energy evaluation; a full 30-step optimization is ~20 s at
  24 qubits (arithmetic from the measured rate), sub-second per step below ~20."
- **Disposition:** APPLIED (commit 06d31bc)
- **Effort:** S

### F-04 — The debunked "overshoots by roughly √(term count)" claim survives in two places the Learn tab explicitly corrects
- **Severity:** P0 correctness/accuracy
- **Status:** CONFIRMED
- **Location:** `src/ui/views/limits.py:333-334` (Receipts callout), `src/simulation/qaoa_core.py:299-304` (comment)
- **Evidence:** `learn.py:359-363` (expander) says: "for a Hamiltonian of m
  *equal-magnitude* independent terms, σ(H) would grow as √m·|J|, and an earlier
  version of these notes quoted that. **It does not hold here** … measured ratio
  (2-4x) is far below √m (8-11x)." Yet `limits.py` still tells the audience the
  wrong scale "overshoots by roughly √(term count)", and the `qaoa_core.py` comment
  repeats it, with numbers (σ(H)≈3.5, max|J|≈2.5) that describe the
  **pre-normalisation** Hamiltonian, not today's. Measured on the current default
  objective (verify run, this session): n=12 → σ(H)=0.743, max|J|=0.314, σ/max|J|
  = 2.4; search-range overshoot g_maxJ/g_σ = **1.49×** (√66 ≈ 8.1). n=16 → σ=1.071,
  max|J|=0.306, overshoot 2.14× (√120 ≈ 11). The learn.py table numbers are the
  correct ones. The historical 1.26-vs-0.45 figures in the qaoa_core comment are
  internally consistent *for the old objective* (2.8× overshoot) — still nowhere
  near √66.
- **Why it matters:** limits.py is the thesis page ("Receipts — two real failures").
  Quoting a mechanism the project's own Learn tab measured and disavowed hands a
  knowledgeable visitor a contradiction between two tabs of the same app.
- **Fix:** In limits.py, replace "overshoots by roughly √(term count)" with the
  measured statement (~1.5–3× depending on objective normalisation, cross-reference
  the Learn tab's measured table). In qaoa_core.py, keep the historical numbers but
  date them to the pre-normalisation objective and delete the √(term-count) prose.
- **Disposition:** APPLIED (commit 6ec3a4e)
- **Effort:** S

### F-05 — "buys about nine more clean qubits, or four noisy ones" — the page's own table says five
- **Severity:** P0 correctness/accuracy
- **Status:** CONFIRMED
- **Location:** `src/ui/views/limits.py:253-254`
- **Evidence:** `TIER_VALUE` (limits.py:131-137) lists noisy ceilings 16 (GB10) →
  21 (multi-rack AI Factory): a difference of **5**. The callout under the metric
  row says "an 800× increase in memory — buys about nine more clean qubits, or
  **four** noisy ones." (Clean 33→42 = 9 is right.)
- **Why it matters:** The four adjacent metric tiles and the later table put 16 and
  21 on screen; a reader doing the subtraction the callout invites gets 5, not 4.
- **Fix:** "four" → "five".
- **Disposition:** APPLIED (commit fb3e72b)
- **Effort:** S

### F-06 — "Not arithmetic — the service reports both ceilings from its actual available memory" is false on the CPU fallback
- **Severity:** P1 architecture (conditional overclaim)
- **Status:** CONFIRMED
- **Location:** `src/ui/views/limits.py:390-399` (callout), `src/simulation/qaoa_engine.py:128-135` and `:613`
- **Evidence:** On the `local-cpu` path, `probe_local()` hard-codes
  `max_qubits=24` and reports `free_memory_bytes=0`; `run_realism` then computes
  the noisy ceiling from an **assumed** `2**33` (8 GiB). The limits.py callout
  renders whenever both numbers exist and asserts "Measured on this machine, right
  now … Not arithmetic — the service reports both ceilings from its actual
  available memory."
- **Why it matters:** Anyone running the public repo without a GPU (the common
  case for the GitHub audience) sees a "measured, right now" claim that is a
  hard-coded constant plus an assumption. This is the precise overclaim pattern
  the project's claims discipline forbids.
- **Fix:** Suppress the callout when `rz["backend"] == "local-cpu"` (GB10 and
  local-gpu ceilings are genuinely memory-derived), or make `probe_local()` report
  real host memory. Applied the former (smallest true change).
- **Disposition:** APPLIED (commit df4215a)
- **Effort:** S

### F-07 — Quantum tab says the plan "did NOT match the exact optimum" without the deliberate-trade framing the Grid tab already has
- **Severity:** P1 architecture (claim framing inconsistency)
- **Status:** CONFIRMED
- **Location:** `src/ui/views/quantum.py:157`; contrast `src/ui/views/command_center.py:196-207`
- **Evidence:** `IslandingRun.is_optimal` compares the energy of the plan
  **actually applied** — which post-selection may deliberately choose over the
  energy optimum for thermal security (`qaoa_engine.py:399-422`). command_center.py
  handles `is_optimal == False` with "deliberately differs … a different candidate
  from the quantum shortlist was applied instead". quantum.py renders the same flag
  as "The plan QAOA returned **did NOT match the exact optimum**" — reading as an
  algorithm failure when it is the documented security trade.
- **Why it matters:** Two tabs interpret one flag in opposite tones; the harsher
  one is the misleading one, in the tab whose stated rule is "No hand-waving. No
  overclaiming."
- **Fix:** Mirror the command_center framing (matched optimum / deliberately
  differs for thermal security).
- **Disposition:** APPLIED (commit 537e9e4)
- **Effort:** S

### F-08 — Spectral baseline partitions on the synthetic `flow_mw` weights the QUBO deliberately abandoned
- **Severity:** P1 architecture
- **Status:** CONFIRMED
- **Location:** `src/simulation/grid_model.py:442` (`spectral_baseline`)
- **Evidence:** The Laplacian is weighted by `g.edges[u, v]["flow_mw"]` — the
  attribute `build_ising` (grid_model.py:284-289) replaced with `base_flow_mw`
  because "minimising it optimised a fiction". So QAOA optimises severed *solved*
  flow while the classical baseline it is compared against optimises the fiction.
  `mw_better_than_baseline` is documented as "the fair comparison"
  (qaoa_engine.py:204-213) and exported in the JSON as `qaoa_advantage_mw`.
- **Why it matters:** The headline "QAOA keeps N MW on vs classical practice"
  is biased in QAOA's favour by handing the baseline worse inputs. An audience
  member who re-runs spectral bisection on the solved flows may report a smaller
  advantage.
- **Fix:** Weight the Laplacian with the same
  `e.get("base_flow_mw", e["flow_mw"])` basis. **Not applied here** deliberately:
  the recorded weight-sweep results in `settings.py:64-70` (+419 MW etc.) were
  measured against the current baseline; changing the baseline invalidates those
  recorded numbers, so the fix and the re-sweep should land together.
- **Disposition:** REPORTED
- **Effort:** M (fix is S; re-running and re-recording the 12-scenario sweep is the cost)

### F-09 — GB(10⁹) and GiB(2³⁰) are mixed on the same page under one label
- **Severity:** P2 quality
- **Status:** CONFIRMED
- **Location:** `src/ui/views/limits.py:229-230` (prose: "17 GB at 30 qubits — and
  34 GB at 31, 69 GB at 32" — decimal GB), vs `limits.py:63-69, 101` and the wall
  chart y-axis ("Memory (GB, log scale)" plotting `bytes / 2**30` = GiB, where 30
  qubits = 16). `components.py:203-221` gets it right ("GiB").
- **Why it matters:** The same page says 30 qubits costs 17 GB (prose) and plots
  it at 16 GB (chart). 7% is small but this audience checks; the fix is one label.
- **Fix:** Standardise on GiB in figure axis labels (or divide by 1e9 and keep GB).
- **Disposition:** REPORTED
- **Effort:** S

### F-10 — Noisy-ceiling marker plotted at 16.5 qubits, labelled "16 qubits noisy"
- **Severity:** P3 nit
- **Status:** CONFIRMED
- **Location:** `src/ui/views/limits.py:86-92` (`_qubits_for` returns n/2 = 16.5 for 128 GiB)
- **Evidence:** The diamond sits at the exact curve/capacity intersection (16.5);
  the label and every other statement of the number floor it to 16.
- **Fix:** Either plot at `floor(n)` or label "≈16.5 → 16 usable". Cosmetic.
- **Disposition:** REPORTED
- **Effort:** S

### F-11 — Two different "measured deviation" figures for the same equivalence check, neither dated or sized
- **Severity:** P3 nit
- **Status:** CONFIRMED
- **Location:** `src/ui/views/architecture.py:145-146` ("measured deviation
  8.0e-17"), `src/simulation/qaoa_core.py:26` ("3.4e-17")
- **Evidence:** Both are real-looking floats from different runs (deviation varies
  with n and p; this session's local run at n=8, p=2 gave 8.8e-17). Neither carries
  n/p or a date, unlike the project's other measured claims.
- **Fix:** Qualify both ("n=…, p=…, 2026-07-29") or state "float64 rounding scale,
  ~1e-16" instead of a specific run's value.
- **Disposition:** REPORTED
- **Effort:** S

### F-12 — "2ⁿ possible ways to split the grid into two groups" counts assignments, not splits
- **Severity:** P3 nit
- **Status:** CONFIRMED
- **Location:** `src/ui/views/quantum.py:50-53`, `command_center.py:143-144`, `learn.py:265-266`, others
- **Evidence:** 2ⁿ is the number of bit *assignments*: it counts each two-group
  split twice (Z₂ symmetry, which the project itself models —
  `learn.py:62` "the complement is the same physical partition") and includes the
  two degenerate all-in-one cases the objective explicitly forbids. Distinct
  nontrivial splits = 2ⁿ⁻¹ − 1.
- **Why it matters:** Only because this audience checks and the app itself teaches
  the Z₂ symmetry two tabs later. The search space the circuit holds genuinely is
  2ⁿ basis states, so the number is defensible — the phrase "ways to split … into
  two groups" is what's loose.
- **Fix:** Lowest-cost: say "2ⁿ candidate assignments" or "2ⁿ possible island
  labellings" where the count is quoted. WONTFIX is defensible too.
- **Disposition:** REPORTED
- **Effort:** S

---

## Phase 2 — Correctness

### F-13 — `diag` closure captured across a `del` (the seed doc's confirmed latent bug)
- **Severity:** P1 architecture (latent trap, not yet a live defect)
- **Status:** CONFIRMED
- **Location:** `src/simulation/qaoa_core.py` — `optimize_qaoa`: closure at
  (pre-fix) lines 276/280, `del sv, diag` at line 380
- **Evidence:** `energy_of` captured `diag` from the enclosing scope; the
  enclosing name is deleted near the end of `optimize_qaoa` to free the
  2ⁿ-element array on the GPU. All current calls precede the `del`, so it works
  today — but any future call after it raises `NameError`, and the `del` looks
  load-bearing enough that no reader would remove it. Ruff's two F821s were this.
- **Fix:** Bind `diag` as a default argument of `energy_of` — the function owns
  its reference, the outer `del` stays, F821s gone. Functional test: 8-qubit
  optimize runs, AppTest 0.
- **Disposition:** APPLIED (commit ab694ec)
- **Effort:** S

### F-14 — Local `run_realism` path had no memory guard: 15+ qubit request = 17 GiB+ in-process allocation
- **Severity:** P1 architecture (robustness; host-level failure mode)
- **Status:** CONFIRMED
- **Location:** `src/simulation/qaoa_engine.py:602-614` (pre-fix)
- **Evidence:** The GB10 service refuses `/qaoa/realism` above its live noisy
  ceiling (server.py:249-256, HTTP 507). The local fallback called
  `nz.compare_realism` directly with no check, so "⚗️ Run all three" on a grid
  ≥15 qubits without the GB10 attempted a 17 GiB (n=15) to 17 TiB (n=20)
  `np.full` in-process. On overcommitting Linux that is swap death or the OOM
  killer, not a clean MemoryError.
- **Fix:** Same ceiling arithmetic as the service, same error-dict shape the UI
  already renders. Verified: n=20 now returns the wall message; n=8 runs all
  three regimes.
- **Disposition:** APPLIED (commit 5f89811)
- **Effort:** S

### F-15 — server.py comment: "18 is 69 GB" — n=18 density matrix is 1 TiB
- **Severity:** P3 nit
- **Status:** CONFIRMED
- **Location:** `services/gb10_qsim/server.py:113`
- **Evidence:** 2^(2·18)·16 B = 1 TiB; 69 GiB is n=16. The `le=18` bound itself
  is fine (the live ceiling guard enforces memory), only the comment's arithmetic
  was wrong — in the service whose whole argument is this arithmetic.
- **Disposition:** APPLIED (commit 634043f)
- **Effort:** S

### F-16 — `depolarize` copied the full ρ four times per qubit per layer
- **Severity:** P2 quality (performance; the seed doc's flagged dominant cost)
- **Status:** CONFIRMED
- **Location:** `src/simulation/noise.py:122-140` (pre-fix)
- **Evidence:** Literal channel: `acc = (1-p)ρ` plus three `rho.copy()` Pauli
  conjugations per qubit per layer — 4 GB per copy at 14 qubits. The identity
  ρ + XρX + YρY + ZρZ = 2·(I ⊗ Tr_t ρ) collapses the channel to block arithmetic
  (populations mix by 2p/3, coherences damp by 1−4p/3): one pass over ρ, one
  quarter-size temp.
- **Fix:** Closed form, verified against the previous implementation on 20 random
  mixed states (n=2…7, p=0.001…0.75): max deviation 1.1e-16, trace preserved,
  pipeline purity/energy unchanged.
- **Disposition:** APPLIED (commit c8a8a5c)
- **Effort:** S

### Audited and found sound (evidence, so the next reviewer doesn't re-do it)

Verified numerically this session (verify.py output quoted in PROGRESS):

- **DC power flow (`power_flow.py::solve`)** — per-island nodal balance holds to
  1e-6 (net flow out of every node equals its scaled injection); islands returned
  by `solve` exactly match `networkx.connected_components` over live edges;
  intact-grid worst loading measured **59.2%**, matching `calibrate_ratings`'
  stated "near 59%" design point; dead islands produce zero flows and
  `blackout`/0 Hz handling behaves as documented.
- **N-1 screen** — ranks by (shed, worst loading) as documented; on the 12-node
  default the worst contingency yields 137% peak with no shed, matching the
  numbers quoted in learn.py's expander ("taking no action at all peaked at 137%").
- **Bit conventions** — `brute_force_ground_state` bitstring round-trips through
  `evaluate_partition` to the identical energy (little-endian convention is
  consistent end to end, including `top_bitstrings` and learn.py's index math).
- **`evaluate_partition` feasibility** — contiguity is judged over live edges
  only (grid_model.py:399-405); logic reads correctly and the degenerate/no-gen
  cases produce the documented notes.
- **`noise.py`** — the depolarising channel is trace-preserving (Tr=1 to 1e-9),
  Hermiticity preserved (2.8e-17), purity in range, and the noiseless density
  path matches statevector probabilities at 1.7e-17. `sample_expectation` and
  `purity` (Σ ρ∘ρᵀ) are correct as written.
- **`verify_equivalence`** — 8.8e-17 max amplitude deviation at n=8, p=2 locally.
- **Blind excepts (BLE001 ×9)** — audited; the probe/COBYLA-fallback ones are
  deliberate and documented in situ. None swallows an error the user needs.

### The tests this project should have (highest value first)

Zero tests exist. These are chosen because each would have caught a **real bug
from this project's history** (or from this review), not for coverage:

1. **`test_power_flow.py`** —
   (a) nodal balance: for every island, |net flow out − injection| < 1e-6;
   (b) `solve().islands` == networkx components over live edges;
   (c) intact default grid worst loading in (0.40, 0.80) — *catches any
   regression of the ratings-fiction bug that shipped 80%+ intact loadings*;
   (d) every faulted line carries no flow.
2. **`test_qaoa_core.py`** —
   (a) `verify_equivalence(n=8, p=2)` deviation < 1e-9 — *locks the demo's
   central "optimisation not approximation" claim*;
   (b) `optimize_qaoa` best energy < energy of the unevolved |+⟩ state (which
   equals the Hamiltonian offset) by a margin — *catches the
   converged-on-nothing failure (γ≈0) that shipped ratio 0.128*;
   (c) γ scan upper bound ≈ π/(2σ(H)) — *locks the F-04 fix*.
3. **`test_grid_model.py`** —
   (a) brute-force bitstring → `evaluate_partition` energy identity — *locks
   endianness*; (b) complement bitstring yields the same partition (Z₂);
   (c) island held together only by a faulted line ⇒ infeasible — *locks
   contiguity-over-live-edges*; (d) severed-line MW equals the solved base flow
   on a calibrated graph — *locks F-02*.
4. **`test_noise.py`** —
   (a) `depolarize` == explicit Pauli-conjugation reference on random ρ —
   *locks F-16's closed form forever*; (b) trace/Hermiticity preservation;
   (c) p=0 is the identity; (d) noiseless density path == statevector probs.
5. **`test_engine.py`** —
   (a) `_select_plan` never returns an infeasible plan when a feasible candidate
   exists; (b) a candidate with zero overloads beats one with lower shed and an
   overload — *locks deliberate decision #3 (security before shed) against a
   well-meaning "fix"*.

All five files run without a GPU and without the GB10 (NumPy path), so they can
gate CI on any host. Estimated: ~200 lines total, half a day including CI wiring.
