# PROGRESS — Fable review checkpoint ledger

Read this first to see where the run got to. **All five phases completed.**
Next reader: start at `04-handoff-queue.md`.

| Phase | Status | Notes |
|---|---|---|
| 0 — Orient & baseline | DONE | Branch created; ruff + AppTest baselines recorded below |

| 1 — Claim accuracy | DONE | F-01…F-12; 8 fixes committed (SHAs in findings file) |
| 2 — Correctness | DONE | F-13…F-16 applied; physics audited sound; test plan written |
| 3 — Design & visual | DONE | 02-design-assessment.md, D-01…D-19 + sprint order; F-17 (dead ENERGISE cue) committed e98f5a3 |
| 4 — Architecture | DONE | 03-architecture-assessment.md, A-01…A-08 (engine split plan, cuStateVec gap, perf leads) |
| 5 — Handoff | DONE | 04-handoff-queue.md — start there; 3 tiers, commit index, verification ritual |

## Baseline (fill in Phase 0)
- Branch: `fable/review-2026-07-30` (from `main` @ c6d58c8)
- `ruff check --statistics` (ruff via `.venv/bin/python -m ruff`): **180 findings** —
  123 C408, 12 ISC004, 9 BLE001, 6 F401, 5 F541, 4 I001, 4 RUF100, 3 RUF059,
  3 UP037, 2 F821, 2 F841, 2 S110, 2 UP035, 1 C401, 1 DTZ001, 1 RUF046.
  Matches the seed doc's triage (majority C408/ISC004 noise).
- AppTest exception count (must be 0): **0** (via `.venv/bin/python`, Python 3.12.3;
  command exactly as MISSION.md specifies; only a benign bare-mode ScriptRunContext warning).

## Checkpoints
_(append one line per finding flushed or commit landed)_
- 2026-07-30: Phase 0 done — branch `fable/review-2026-07-30`, ruff 180 (matches seed), AppTest 0 exceptions. Seed doc read; `qaoa_core.py` + `power_flow.py` skimmed.
- 2026-07-30: Phase 1 findings F-01…F-12 flushed to 01-code-findings.md. Headliners: arrows mirrored E–W (F-01, via bundled plotly.js source), severed-MW uses synthetic flow_mw (F-02, 67.2 vs 4.1 MW measured), architecture "30-step in 0.7 s" contradiction (F-03), √(term-count) claim debunked-but-still-shown (F-04). Numeric verification in scratchpad/verify.py output, quoted in findings.
- 2026-07-30: 14 commits on the branch, every one AppTest-gated at 0 exceptions:
  6ffc8ae F-01 arrows · 0b8a9b7 F-02 severed MW · ab694ec F-13 diag/del ·
  6ec3a4e F-04 overshoot claim · fb3e72b F-05 four→five · 06d31bc F-03 interactive
  row · 537e9e4 F-07 optimum framing · df4215a F-06 CPU-fallback callout ·
  1c4cfe2 unused code · 30ed0cd pyproject/ruff (180→28) · 5f89811 F-14 realism
  guard · 634043f F-15 server comment · c8a8a5c F-16 depolarize closed form
  (verified 1.1e-16 vs old).
- 2026-07-30: Phase 3 done — 02-design-assessment.md written (IA restructure to 4 URL pages, quantum/learn merge table, one-line-diagram execution findings, accessibility pass, narration review). One more code commit found during the pass: e98f5a3 removes the step-① cue for the ENERGISE button deleted in 087789d (F-17).
- 2026-07-30: Phase 2 done — power_flow physics verified numerically (nodal balance ≤1e-6, islands==components, intact 59.2% matches the 59% design claim), bit conventions round-trip, noise module verified (trace, Hermiticity, purity, noiseless≡statevector). Five-file test plan written into 01-code-findings.md, each test mapped to a real historical bug. REPORTED (not applied): F-08 spectral-baseline weight basis (invalidates recorded sweep), F-09 GB/GiB, F-10/F-11/F-12 nits.
