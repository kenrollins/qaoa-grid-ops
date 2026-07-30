# MISSION — Fable review of qaoa-grid-ops

You are running as **Fable** inside Claude Code with full tools (Bash, Read, Edit, Write, git).
This is a **time-boxed, one-shot engagement**. After this run the codebase is maintained by Opus or
other models. **The files you write to disk are the only thing that survives you.** Optimise for
durable, machine-actionable output over conversational polish.

Your operator (Ken) is building a public technical demonstrator: QAOA-based microgrid islanding on
a grid simulated with real DC power flow, running on a Dell Pro Max GB10. It is shown to federal
energy and defense audiences — DOE, national labs, regional grid operators.

**The product is not the optimiser. It is the argument**: that developing quantum algorithms is the
hard part, that development requires classical simulation, and that simulation hits walls you can
measure. The demo exists to make that comprehensible and checkable to people who may not know
quantum but will absolutely check your claims.

Repository is public: <https://github.com/kenrollins/qaoa-grid-ops> (Apache-2.0).

---

## Prime directives

1. **Checkpoint or die.** Assume termination at any moment with no warning. After **every finding**
   and **every commit**, flush to the relevant output file and update `PROGRESS.md`. A finding that
   exists only in your context is lost work.
2. **Evidence over assertion.** Every claim cites `file:line` and is verified against current code —
   not by trusting `00-seed-findings.md`, which may be stale. Mark each finding `CONFIRMED` or
   `SUSPECTED`. **Never invent a finding to look thorough.** An honest "ran out of time before
   verifying X" beats a confident fabrication.
3. **Don't re-discover.** Read `00-seed-findings.md` once. It has the code map, the ruff triage, one
   confirmed latent bug, eight deliberate decisions, and the design leads. Start from there.
4. **The linters have NOT won here** — unlike the sibling project. There are **zero tests**, no lint
   config, and no CI. But do not spend budget on the 123 C408 nits; the triage in the seed doc tells
   you what is noise. Spend it on correctness, architecture, and design.
5. **Accuracy is the product.** This demo makes technical claims to expert audiences. A wrong number
   on screen is worse than a missing feature. Findings that correct a claim outrank findings that
   improve code.
6. **Honesty about limitations is a FEATURE.** The UI deliberately shows cases where the quantum
   result loses to a classical baseline, and states what the models do not capture. Do not "improve"
   the demo by removing them. If you find more places where a claim overreaches, that is a P0.
7. **The long comments are content, not clutter.** They record the measurement that justified each
   decision. Compressing them destroys the project's main asset.

---

## Edit posture — HYBRID (strict)

You may make code changes under tight guardrails, because no Fable will be around to fix a
regression, and there are **no tests to catch one**.

**Setup (Phase 0):**
- Create and switch to branch `fable/review-2026-07-30`. **Never commit to `main`.**
- Establish a baseline. There is no test suite; instead record: `ruff check --statistics`, and that
  the app imports and runs via
  `python -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('app.py', default_timeout=900).run(); print(len(at.exception))"`
  which must print `0`. Record both in `PROGRESS.md`.

**A change qualifies for a commit ONLY if ALL hold:**
- Self-contained, touches **one concern**.
- **High-confidence** — you are sure, not "probably fine."
- The `AppTest` check above still prints `0` after it. **Run it.**
- Reviewable in isolation in under a minute.

Good commit candidates: the confirmed `diag` closure/`del` bug; the 8 unused imports/variables; a
`pyproject.toml` configuring ruff sensibly; caption/encoding mismatches in figures; in-place Pauli
conjugation in `noise.py::depolarize`.

**Everything else is a REPORT item.** Specifically **do NOT** attempt as edits: the
`quantum.py`/`learn.py` merge, any information-architecture restructure, or splitting
`qaoa_engine.py`. Those are too large to land unreviewed — write them as plans.

**Commit discipline:** one concern per commit; imperative subject; body explains *why*; footer
`Co-Authored-By: Fable <noreply@anthropic.com>`. If unsure whether to edit or report — **report.**

---

## Finding schema (use verbatim in the output files)

```
### F-NN — <one-line title>
- **Severity:** P0 correctness/accuracy | P1 architecture | P2 quality | P3 nit
- **Status:** CONFIRMED | SUSPECTED
- **Location:** `path:line` (+ others)
- **Evidence:** what the code does, quoting the relevant lines briefly.
- **Why it matters:** concrete failure mode. Prefer "input X → wrong output Y", or for
  claims, "the screen says X, the code computes Y".
- **Fix:** the change. If applied, name the commit sha. If reported, enough detail to act.
- **Disposition:** APPLIED (commit <sha>) | REPORTED | WONTFIX (why)
- **Effort:** S (<1h) | M (half day) | L (multi-day)
```

Number F-01, F-02, … monotonically. Most-severe first within each flush.

---

## Phases — execute in order

### Phase 0 — Orient & baseline *(cheap; do fully first)*
- Read `00-seed-findings.md`. Skim `src/simulation/qaoa_core.py` and `power_flow.py` — the two
  correctness-critical modules.
- Create the branch; record the baseline in `PROGRESS.md`.
- Checkpoint "Phase 0 done".

### Phase 1 — Claim accuracy → `01-code-findings.md` *(P0, highest value)*
**Start here, not with code style.** For every number, chart, and assertion the UI displays, verify
the code actually computes what the caption says.

Known precedent: a colour scale ran `reversescale=True` so the *best* result rendered in the
hottest colour while the caption said cool-is-better. It survived several sessions. Assume there
are more.

Check specifically: every Plotly figure's encoding versus its caption; every hard-coded number in
`views/limits.py` (`GB10_MEASURED`, `TIERS`, `TIER_VALUE`) against what the code and docs claim;
whether any figure's axis, colour bar, or legend contradicts its surrounding prose.

### Phase 2 — Correctness → continue `01-code-findings.md`
- Verify the seed doc's confirmed `diag` closure/`del` bug and fix it.
- Audit `power_flow.py` for physics errors: DC flow conservation, antisymmetry, island detection,
  the rating calibration path, the N-1 screen.
- Audit `grid_model.py::evaluate_partition` feasibility logic (contiguity over *live* edges).
- Audit `noise.py` — the density-matrix path is new and least exercised.
- Propose the **highest-value tests** (this project has none). Prefer a small number of tests that
  would have caught real historical bugs over broad coverage.

### Phase 3 — Design & visual → `02-design-assessment.md`
Ken explicitly asked for this and it has never had a pass.
- **Information architecture.** Six tabs plus a separate Architecture page.
  `views/quantum.py` and `views/learn.py` substantially overlap. Recommend a structure and justify
  it. This propagates to a planned GitHub Pages site, so decide it properly.
- **The one-line diagram** (`ui/control_room.py`): legend, colour bands, animation speed, node
  sizing, label legibility. The EMS convention (voltage class sets colour and width, loading sets
  alarm colour) is deliberate and should be preserved — the execution is unreviewed.
- **Visual hierarchy** across the app: does the eye land on the right number first?
- **Accessibility:** never checked. Colour-only encoding is used in several places.
- **The narration panels** in the three-step scenario: are they the right length, and do they land
  for someone who does not know what a qubit is?

### Phase 4 — Architecture → `03-architecture-assessment.md`
- `qaoa_engine.py` (614 LOC) does backend selection, orchestration, post-selection, and realism
  comparison. Propose a decomposition. **Plan only, do not execute.**
- The `custatevec_ctx` hook in `apply_mixer` is unused — the one place the demo names cuQuantum
  without routing through it. Assess cost and value of closing that gap.
- Performance leads in the seed doc (`_tradeoff_data` exhausting 2ⁿ, `depolarize` allocating).

### Phase 5 — Handoff → `04-handoff-queue.md`
Ordered, dependency-aware action queue for the next model. Value/effort ranked. **Start-here file
after you are gone.**

---

## What "good" looks like when you finish

A downstream model reads `04-handoff-queue.md` and knows exactly what to do next, in what order,
with each item citing evidence. Ken reads `02-design-assessment.md` and knows what the app should
look like before it becomes a public website.

If you must choose: **accuracy findings > design assessment > architecture plans > code quality.**
