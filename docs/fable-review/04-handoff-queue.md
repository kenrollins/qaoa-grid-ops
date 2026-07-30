# 04 — Handoff queue

**Start here.** Fable review completed 2026-07-30 on branch
`fable/review-2026-07-30` (baseline `main` @ c6d58c8). This file is the ordered
action queue; evidence lives in `01-code-findings.md` (F-NN),
`02-design-assessment.md` (D-NN), `03-architecture-assessment.md` (A-NN).

## State of the branch you are picking up

- **17 commits**: 15 code fixes/improvements + 2 doc batches, every code commit
  gated on `AppTest` printing 0 exceptions (the check command is in MISSION.md
  and PROGRESS.md). Nothing on `main` has been touched.
- **Everything applied was P0/P1 claim-accuracy, one confirmed latent bug, two
  memory-safety guards, one verified perf rewrite, plus lint hygiene.** All
  structural work was deliberately left as plans (below).
- **First action for a human: merge or review the branch.** The fixes correct
  operator-facing numbers (arrows, MW figures, four claims); the demo should
  not be shown externally from `main` while the branch sits unmerged.
- **Second action (2 min, needs eyeballs):** load the app, look at one
  east-west line on the diagram — confirm arrowheads now point with their
  motion (F-01 was verified against plotly.js source, not a rendered screen).

## The queue (value ÷ effort, dependencies noted)

### Tier 1 — before the next external demo

1. **Add the five test files** from `01-code-findings.md` §"The tests this
   project should have". Each test is mapped to a real historical bug; all run
   CPU-only. Also add a GitHub Actions workflow: `ruff check` (config now in
   pyproject.toml, signal is 28) + `pytest` + the AppTest smoke line. **Effort:
   half a day. Do this first — it converts every fix on this branch into a
   regression net, and this project has shipped multi-session visual/claims
   bugs precisely because nothing gated.** (No dependencies.)
2. **F-08 — rebase the spectral baseline onto `base_flow_mw` and re-run the
   weight sweep.** The one applied-adjacent accuracy item too entangled to fix
   here: the classical baseline currently optimises the synthetic weights, which
   flatters `qaoa_advantage_mw`, the demo's headline comparison. Change the one
   line in `spectral_baseline`, re-run the 12-scenario sweep, update the numbers
   in `settings.py`'s ObjectiveWeights comment (and the +419 MW anywhere it is
   quoted). **Effort: S code + an hour of sweep. Depends on: nothing, but do it
   after (1) so the round-trip tests are watching.**
3. **A-03(b) — reword the cuStateVec claims** (Architecture page Layer 3, ASCII
   diagram, `/health` detail, sources.py "Built on") to "CuPy today, cuStateVec
   at M3", **unless** you are about to do Tier 2 item 6, in which case skip the
   reword. The public repo currently claims an execution path that never runs.
   **Effort: 15 min.**
4. **D-04 + D-12 — loading-band legend under the one-line diagram + dashed
   OVERLOAD lines.** One commit, reuses `LOAD_BANDS`, biggest legibility and
   accessibility win on the flagship screen. **Effort: S.**

### Tier 2 — shape decisions (Ken's call, then execute)

5. **D-01 — the four-page restructure and the quantum/learn merge.** The full
   merge table is in `02-design-assessment.md` §1. Decide this BEFORE building
   the GitHub Pages site — the page boundaries become the site's URLs.
   **Effort: M (half day). Blocks: Pages site. After it lands, A-04's tab-
   eagerness cost disappears too.**
6. **A-03(a) — implement the cuStateVec context for the mixer** (~70 lines in
   the service + wiring; plan in `03-architecture-assessment.md` §2). This is
   PLAN.md M3's own experiment for the measured ~12× headroom. **Must be done
   on the GB10; re-measure `GB10_MEASURED` and the architecture page's measured-
   performance card afterwards.** **Effort: M.**
7. **A-01/A-02 — engine split, `capacity.py` first.** The memory-guard
   arithmetic (0.55 safety × 1.6 working set) lives in three files; unify it
   before it drifts — the service's refusals and the UI's expectations must
   agree. Facade preserved, sequencing in the assessment. **Effort: M. The
   capacity.py step needs an rsync/deploy to the GB10.**

### Tier 3 — quick wins in any idle session (all S, no dependencies)

8. **A-04** — Z₂ trick in `_tradeoff_data`: evaluate half the bitstrings,
   mirror the rest. Same figure, half the cost, one line.
9. **D-08** — state cards above the diagram in step ③, plus a closing cue line.
10. **D-10 + D-11** — wall-chart y-range clamp; visible "does not fit" bars.
11. **F-09** — pick GB or GiB and make prose + axes agree (charts labelled GB
    currently plot GiB).
12. **D-03** — unify the sidebar Run button with step ③ (needs a manual
    click-through; do not land headless).
13. **D-05, D-13, A-05, A-06, A-07, A-08, F-10, F-11, F-12, D-06, D-07, D-14
    through D-19** — paper-cuts; each is one commit; evidence in their files.

### Explicitly not queued (decided against; do not resurrect)

- Rewriting the long comments, the C408 `dict()` style, the RFC1918 addresses,
  the plotly.js vendoring, the shed-vs-security post-selection order, or the
  honest-limitation panels. See "Deliberate decisions" in `00-seed-findings.md`
  — several of this review's findings were about *protecting* those (F-07
  aligned copy TO the deliberate trade; the test plan's engine tests lock
  decision #3 against future "fixes").

## Verification ritual for future changes (no test suite until item 1 lands)

```
.venv/bin/python -m ruff check .        # 28 findings is the clean baseline
.venv/bin/python -c "from streamlit.testing.v1 import AppTest; \
  at=AppTest.from_file('app.py', default_timeout=900).run(); print(len(at.exception))"
# must print 0
```

## Commit index (branch, oldest first)

| SHA | What | Finding |
|---|---|---|
| 6ffc8ae | Flow arrows mirrored east–west | F-01 |
| 0b8a9b7 | Severed/faulted MW from solved flow | F-02 |
| ab694ec | diag closure/del trap | F-13 |
| 6ec3a4e | γ-overshoot claim → measured ratio | F-04 |
| fb3e72b | four noisy qubits → five | F-05 |
| 06d31bc | interactive-range self-contradiction | F-03 |
| 537e9e4 | quantum tab optimum framing | F-07 |
| df4215a | CPU-fallback "measured" callout gated | F-06 |
| 1c4cfe2 | unused imports/locals (11) | — |
| 30ed0cd | pyproject ruff config (180→28) | — |
| 5f89811 | local realism memory guard | F-14 |
| 634043f | server density-matrix comment | F-15 |
| c8a8a5c | depolarize closed form (1.1e-16 verified) | F-16 |
| d57e0b9 | findings ledger F-01..F-16 | — |
| e98f5a3 | dead ENERGISE cue | F-17 |
| (docs)  | 02-design, 03-architecture, this file | D-*, A-* |
