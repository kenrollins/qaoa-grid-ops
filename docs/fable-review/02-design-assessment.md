# 02 — Design & visual assessment

Fable review, 2026-07-30. First design pass this project has had. Everything here
cites the code as it stands on `fable/review-2026-07-30` after the Phase 1/2 fix
commits. Design findings are numbered D-NN (code findings are F-NN in
`01-code-findings.md`). Items marked **APPLIED** were safe one-concern commits;
everything structural is a recommendation for Ken to decide before the GitHub
Pages port — these choices propagate there.

---

## 1. Information architecture — the six-tab problem

### What exists
One `st.navigation` page ("Command Center") holding **six tabs** —
Grid Topology & Islanding · The Quantum Part · Learn QAOA · Under the Hood
(itself two **nested** tabs: "Why this is hard" and "Circuit, gate by gate") ·
Simulation Capability · Sources — plus a second page, Architecture.

### The four structural problems

**(a) The thesis is buried two levels deep.** The project's own docs say the
argument lives in `limits.py` ("The demo's actual thesis lives on this page").
It renders inside tab 4, inside sub-tab 1. The audience most likely to be
persuaded by it — an evaluator who reads rather than drives — has to find it
behind a tab labelled "🔬 Under the Hood: Circuit & Qubit Operations", a label
that promises gate diagrams, not a procurement argument.

**(b) `quantum.py` and `learn.py` say the same things in different voices.**
Substantive overlap, measured by topic: superposition (quantum step 3 ≈ learn §1
prose), cost/mixer alternation (quantum step 4 ≈ learn §1-2), the hybrid loop
(quantum "Who does what" ≈ learn's framing ≈ limits' architecture section), the
"checked against ground truth" callout (quantum ≈ command_center step ③). The
two tabs were written for the same reader at the same level; nothing in the tab
names tells a visitor which to read. This is the redundancy the seed doc called
out, and it should be resolved *before* the Pages port doubles it.

**(c) Streamlit tabs are the wrong container for this content.**
`st.tabs` executes **every** tab body on **every** rerun — all six tabs' figure
code runs when the user drags a slider on tab 1 (the heavy learn.py figures are
`st.cache_data`-ed after first computation, but first render pays for all tabs,
and every rerun still rebuilds every Plotly figure object). Tabs also have no
URLs: you cannot link a DOE contact to "the wall" directly. `st.Page`/`st.navigation`
(already used for Architecture) gives lazy execution *and* URL paths — both of
which the GitHub Pages port will want as literal page URLs.

**(d) Tab 4 ("Simulation Capability") duplicates the wall.** Its
`memory_figure` is the same exponential-memory chart as limits' `memory_wall_figure`
minus the density-matrix curve; its capability-claim card restates limits'
argument. One of them should own the claim.

### Recommendation — four URL-addressable pages, "operate" then "understand"

```
⚡ Command Center      — the 3-step scenario ONLY (tab 1 as-is)
⚛️ How it works        — quantum.py MERGED with learn.py (below) + circuit sub-tab
🧱 The Wall            — limits.py promoted to top level + capability sweep folded in
🏗️ Architecture & Sources — existing architecture page + sources tab
```

Rationale: it matches the two real audience journeys (drive the demo → ask "was
that real?" → ask "why does this need this hardware?"; or read-only: wall →
architecture → sources). It promotes the thesis to a named destination. It cuts
six tabs + nested tabs + a page (8 destinations, 2 hidden) to 4 destinations,
zero hidden. And each becomes a URL the Pages site mirrors one-to-one.

**The merge, concretely** (quantum.py is the spine — it has the discipline;
learn.py contributes the three figures, which are the best teaching material in
the app):

| Merged section | Takes from |
|---|---|
| "Read this first" honesty callout | quantum (verbatim — it is the best paragraph in the app) |
| Steps 1-2: qubit per substation, objective | quantum steps 1-2, + learn §3's tradeoff figure moved here (it visualises exactly what step 2's objective is choosing between) |
| Step 3: superposition | quantum step 3 + learn §1 interference figure with its play button |
| Step 4: judge and mix | quantum step 4 + learn §2 landscape figure + the two math expanders |
| Step 5: measure → plan | quantum step 5 + the post-selection explanation currently only in learn §3's expander |
| Who does what / why classical dominates | quantum (verbatim), drop learn's duplicate framing |
| Live metrics + ground-truth callout | quantum (as fixed in F-07) |
| Circuit, gate by gate | current sub-tab, unchanged, as a section or expander at the bottom |

Learn's grid-size/seed/layers controls survive as controls on the embedded
figures. Nothing is deleted from the repo in step one — `learn.py` becomes the
figure library (`interference_figure`, `landscape_figure`, `tradeoff_figure`
imported by the merged page), its `render()` retired. **Do not attempt this as a
live edit in this review** (per MISSION); it is a half-day of careful copy work.

### D-01 — Restructure to four pages, merge quantum+learn — **P1, REPORTED, effort M**
### D-02 — Sidebar is global but only Command Center consumes it — **P2, REPORTED**
The contingency/weights/backend sidebar renders on the Architecture page too,
where none of it does anything visible. With the 4-page structure, scope the
sidebar to Command Center (`with st.sidebar:` inside the page function) or add
a one-line "these controls drive the Command Center" caption on other pages.

### D-03 — Two run buttons, two different behaviours — **P2, REPORTED**
Sidebar "🚀 Run Hybrid Optimization" stores a run but does not advance
`demo_step`, so on tab 1 nothing visibly changes (the result is only visible if
the user separately presses ③ — which *re-runs* the optimization from scratch,
discarding the sidebar run). A live demo driver will press the big primary
button and see nothing happen. Fix: sidebar run sets `demo_step = 2` when a
fault is armed, and ③ reuses `st.session_state["run"]` if its parameters match
rather than recomputing. (Kept as REPORT: touches session-state flow across two
files; needs a manual click-through I cannot do headless.)

---

## 2. The one-line diagram (`control_room.py`)

The EMS conventions (voltage class = colour+width, loading = alarm colour,
damage ≠ plan) are the right call and are preserved. Findings are about
execution:

### D-04 — The loading bands have no legend anywhere — **P1, REPORTED**
The legend explains voltage classes (345/230/138/115 kV), FAULTED, and opened
breakers — but the alarm colours (green <80% / amber <95% / orange <100% /
pink ≥100%), which are *the* operational signal, are explained nowhere on or
near the diagram. An operator knows the convention; a DOE program manager does
not, and the narration only says "running hot". Fix: a one-line HTML key strip
under the diagram (swatch + range + word), reusing `LOAD_BANDS` so it can never
drift from the code. ~15 lines in `control_room.py`, but it is pure additive UI
so I left it for the next session rather than risk layout on a screen I cannot
see. It belongs in the same commit as a bands-legend for the Pages port.

### D-05 — Node index labels are unreadable on de-energised nodes — **P2, REPORTED**
Labels render at 9 px in near-black `#04121a` on the node fill. On island
colours (cyan `#00c8ff`, orange `#ff9f1c`) contrast is fine; on the
de-energised fill `#3a3f4b` it is ~1.6:1 — invisible, on exactly the nodes the
step-③ story is about (dark island = lights out). Fix: per-node `textfont.color`
list — light text on dark fills (the lists are already built per-node; one more
list).

### D-06 — Animation loop pops at the wrap point — **P3, REPORTED**
`speed = 0.6 + min(2.2, loading·1.9)` is continuous, so at frame 24→0 the phase
`(k·speed/n_steps) % 1` jumps unless speed is an integer. Every non-integer-speed
line's arrows visibly teleport once per 2.2 s loop. Fix: quantise speed to
1/2/3 (matching the existing 1/2/3 arrow-count convention — nice coherence for
free) or set `n_steps` per line so each speed completes whole cycles.

### D-07 — Loading overlay obscures the voltage colour it rides on — **P3, REPORTED**
The band-colour core is drawn at `max(1.6, kv_width·0.55)` on top of the base
conductor. For 115 kV (width 1.8) the 1.6-wide core covers ~90% of the line, so
a hot thin line reads as *only* alarm-coloured — the "both facts at once" intent
(docstring) holds for the backbone but not the periphery. Fix: cap overlay at
`kv_width·0.5` with no absolute floor, or halo the overlay.

### The good, so it survives future redesigns
Faulted-X vs open-square markers are instantly distinguishable and non-colour-
dependent; arrow count (1/2/3) redundantly encodes loading — this is genuinely
good accessibility design; hover text is complete (name, kV, rating, flow,
loading, band word); the instrument strip above the diagram is the correct
hierarchy — numbers first, picture second; frequency alarm thresholds (±0.05 /
±0.2 Hz) match real operating bands.

---

## 3. Visual hierarchy

**Where the eye lands first, per screen, as built:**
- Step ① and ②: narration → instrument strip → diagram. Correct order, and the
  crit-styled narration on step ② does the emotional work. Good.
- Step ③: narration → strip → diagram → **state cards** → verdict callout →
  event log/convergence. The state cards are the payoff of the whole demo (three
  states side by side) and they sit below the fold under a 640 px diagram.
  **D-08 (P2, REPORTED):** move the three state cards directly under the ③
  narration, above the diagram — the "before/nothing/after" comparison is the
  argument; the diagram is the illustration. Also: ① and ② end with a `cue`
  line; ③ ends without one. Add "▶ Compare the three states below, then open
  the Quantum tab to see how the answer was found." — it hands the audience to
  the next surface.
- limits.py: the two-sentence thesis callout at the top is exactly right. But
  the page ends with three consecutive heading+callout blocks ("Why do this
  now" → "What this means for the architecture" → "The uncomfortable part")
  totalling ~600 words of dense callout after the last chart. **D-09 (P2,
  REPORTED):** fold "What this means for the architecture" split-panel into the
  crossover-chart section it explains, and let "The uncomfortable part" be the
  page's single closer. Nothing needs rewriting — it is a reorder.

### D-10 — The wall chart wastes 80% of its vertical range — **P2, REPORTED**
`memory_wall_figure` plots the density-matrix curve to n=55 → y spans ~27
decades on log scale, while all five hardware reference lines live within 2.1–5
decades — the entire hardware story (the reason the chart exists) is compressed
into the bottom ~15% of the plot, and the two GB10 diamond markers nearly
overlap the tier labels. `crossover_figure` already solves this with
`range=[-9, 11]`. Fix: same treatment here (e.g. `range=[0, 9]` in log-GB, dm
curve exiting the top is itself the message). One line.

### D-11 — "Exceeds available memory" bars are invisible — **P2, REPORTED**
`components.scaling_figure` draws blocked sizes as **zero-height** bars; the
legend entry appears but nothing is visible in the plot — the most important
data point of the capability story (where the machine stops) is a legend ghost.
Fix: render blocked sizes as full-height hatched/dim bars clipped at the y-max
with a "does not fit" hover, or annotate at the ceiling line. (The `ceiling`
vline partially covers this when set; the bars should still not silently vanish.)

---

## 4. Accessibility (never checked before; checked now)

**What is already right (keep):** island A/B = cyan/orange is a genuinely
colour-blind-robust pair; arrow count redundantly encodes loading class; band
*words* ("watch/alarm/OVERLOAD") appear in hover text; faulted/open lines get
shape markers, not just colour; body text `#8fa3c0` on `#131a29` is ~6.8:1 —
comfortably AA.

- **D-12 (P1, REPORTED) — red/green loading axis with no non-colour fallback on
  the lines themselves.** normal `#3ddc97` vs OVERLOAD `#ff2d55` is the classic
  protanopia collision, and watch `#ffc857` vs alarm `#ff9f1c` are near-identical
  for *everyone* at 2 px width. Arrow count helps but arrows only render when
  |flow| > 0.5 MW. Cheapest strong fix: OVERLOAD lines also get `dash="dash"`
  and +1 width — pattern is the standard colour-independent alarm channel; plus
  the D-04 legend giving the band words.
- **D-13 (P2, REPORTED) — infinite autoplay with no pause.** The diagram
  animation now autostarts and loops forever (by design, and it does read as
  "operating"). WCAG 2.2.2 wants a pause/stop for auto-moving content that
  lasts >5 s; a small "⏸ freeze diagram" toggle that re-renders the static
  figure satisfies it without resurrecting the play-button friction (the static
  path still exists in `one_line_diagram`). Also relevant for projector demos —
  presenters freeze screens.
- **D-14 (P3, REPORTED) — Turbo for the landscape.** Perceptually ordered but
  not CVD-safe at the red end. The chart's argument survives (the annotated
  vlines and star carry it), so this is low priority; Viridis with reversed
  sense ("dark = better" + saying so in the colourbar label) would be the safe
  swap if the Pages port revisits it.
- **Charts generally:** hover-only information (statevector MiB, band words) is
  keyboard/screen-reader-inaccessible in Plotly by default. For the *app* this
  is acceptable (operator tool idiom); for the public **Pages port**, put the
  key numbers in visible captions/tables too — which `limits.py` already mostly
  does.

---

## 5. The narration panels (three-step scenario)

Judged against "does it land for someone who does not know what a qubit is":

- **Step ① (fixed cue in e98f5a3):** Right length (3 short paragraphs). "Squares
  are power stations, circles are substations" earns its place; "that is the
  point of looking at it now, so the next screen means something" is excellent
  stagecraft. **Keep.**
- **Step ②:** The strongest panel. Concrete mechanism (reroute → overheat → trip
  → chain), one historical anchor (2003), one number (2ⁿ splits), one cue. A
  non-quantum reader follows every sentence. **Keep verbatim.**
- **Step ③:** The first paragraph is right. The second ("It does not test the
  options one at a time…") is the single best plain-language QAOA sentence in
  the app — better than anything in quantum.py or learn.py; in the D-01 merge it
  should be *promoted* to the explainer, not duplicated. Two mechanical gaps:
  the island list truncates at two (`isl[:2]`) with no "and N more", and the
  panel is the only one of the three without a closing `cue` (see D-08).
- **Panel voice consistency:** ① speaks to "you", ② narrates the grid, ③
  narrates the algorithm. That progression works; do not flatten it.
- **Length calibration:** all three fit on one screen with the instrument strip
  at 1080p. At 768p (federal laptop + projector), step ② narration + strip push
  the diagram fully below the fold. Acceptable — the narration *is* the content
  at that moment — but keep the panels from growing further.

---

## 6. Misc UI paper-cuts (all P3, REPORTED)

- **D-15** — Sidebar "Island power balance" slider: `max=2.0, default=2.0` — the
  chosen sweep value sits at the top of its own range; you can only detune it
  downward. Raise max to 4.0 (settings.py's sweep table itself measured 4.0).
- **D-16** — Interference figure: the two green "best answer" bars only exist in
  animation frames; before pressing play (and the caption's "the two green bars"
  promise) all bars are cyan. Colour the initial trace's best/complement bars too.
- **D-17** — `st.dataframe` in the capability sweep renders Streamlit-default
  light chrome inside a dark instrument panel; `hide_index` is set but the
  header row still breaks the theme. A `.spec`-styled HTML table would match.
- **D-18** — Tab labels carry emoji + long titles ("🔬 Under the Hood: Circuit &
  Qubit Operations" = 44 chars); at 1280 px the six tabs wrap to two rows. The
  D-01 restructure obsoletes this; if tabs stay, shorten to ≤20 chars each.
- **D-19** — Architecture page shows "live ceiling: 0 qubits" in the ASCII
  diagram when the backend is down (the bottom warning explains, but the number
  reads as a live measurement of zero). Render "—" when `available` is false.

---

## Priority order for a design sprint (one line each)

1. D-01 restructure + merge (decides the Pages site's shape — do first).
2. D-04 loading-band legend + D-12 overload dash (one commit, the diagram's
   biggest legibility + accessibility win).
3. D-08 state cards above the diagram + ③ closing cue.
4. D-10 wall-chart y-range + D-11 visible blocked bars (the two thesis charts).
5. D-03 unify the two run buttons.
6. D-05 node-label contrast, D-13 pause control, then the P3 paper-cuts.
