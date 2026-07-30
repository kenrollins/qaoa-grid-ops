# Fable review — 2026-07-30

A one-shot review of qaoa-grid-ops by the **Fable** model, covering **code and design**, producing
durable artifacts that Opus or other models consume afterwards.

## How to run it (Ken)

1. `cd /data/code/qaoa-grid-ops`
2. Switch Claude Code's model to **Fable** (`/model` → fable).
3. Paste this one line:

   > Read `docs/fable-review/MISSION.md` in full and execute it top to bottom. Begin with Phase 0.

That is it. The heavy context lives in version-controlled files, not in the paste, so the run is
robust to interruption and re-startable.

## What's here

| File | Role |
|---|---|
| `MISSION.md` | The prompt Fable executes: phases, finding schema, edit guardrails, checkpoints. |
| `00-seed-findings.md` | Pre-recon: code map, ruff triage, one confirmed latent bug, eight deliberate decisions, design leads. So Fable starts at judgment, not discovery. |
| `01-code-findings.md` | **Output.** Accuracy and correctness findings (P0→P3) with fixes. |
| `02-design-assessment.md` | **Output.** Information architecture, the one-line diagram, visual hierarchy, accessibility. |
| `03-architecture-assessment.md` | **Output.** `qaoa_engine.py` decomposition plan, cuStateVec gap, performance. |
| `04-handoff-queue.md` | **Output.** Ordered action queue for the next model. Start here afterwards. |
| `PROGRESS.md` | Checkpoint ledger. Read first to see where the run got to. |

## After Fable

1. Read `PROGRESS.md` for how far it got.
2. Work `04-handoff-queue.md` top to bottom.
3. Fable's code changes are atomic commits on `fable/review-2026-07-30` — review and merge
   deliberately. A departed model's edits deserve a human read, and this project has no tests to
   catch a regression.
4. Then build the GitHub Pages site, incorporating `02-design-assessment.md`.

## Design intent

- **Checkpoint-first** — artifacts hit disk as produced, so an unknown cutoff still leaves value.
- **Accuracy first** — this demo makes technical claims to expert audiences; a wrong number on
  screen outranks any code improvement. Phase 1 is claim verification, deliberately before code
  quality.
- **Design is in scope** — it has never had a pass, and the decisions propagate to a public website.
