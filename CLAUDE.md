# qaoa-grid-ops

**Grid Ops — Hybrid Quantum-Classical Grid Optimization.** A federal-audience
demo (DOE / ORNL / grid operators) proving that a desktop-class **Dell Pro Max
GB10 Grace Blackwell** carries **30 qubits of dense all-to-all QAOA** on-premise
and air-gapped — the floor of the hardware class, not the ceiling.

Read `BRIEF.md` for the design, the claim, and the alternatives rejected (with
reasons and measurements); `PLAN.md` for build order — **M0 is done and demoable**;
`README.md` to run it.

## Layout
`app.py` owns page config, the shared sidebar, and the backend probe, then
dispatches via `st.navigation` to two pages in `src/ui/views/`:
**Command Center** (`command_center.py` — 4 tabs, incl. `quantum.py`, the
audience explainer) and **Architecture** (`architecture.py`).

This app is a lab tenant-in-waiting — it is **not yet registered**. Platform
contract: `/data/code/dmz/ONBOARDING.md` — follow it, don't copy it. See PLAN.md M4.

## Stack

- **UI** — Streamlit + Plotly on xr7620, port 8501. Dark "command center" theme.
- **Compute** — `gridops-qsim`, a FastAPI service **on the GB10** at
  `10.0.13.200:8600`, running cuStateVec via `cuquantum-python-cu12` + CuPy.
- **Math** — `src/simulation/qaoa_core.py` is array-agnostic: the *same code*
  runs under NumPy locally and CuPy on the GB10.
- Local venv is **Python 3.12** (`qiskit-aer-gpu` has no 3.13 wheel).

## Three things that will bite you

1. **`qiskit-aer-gpu` is x86_64-only.** No aarch64 wheel exists, so it *cannot*
   run on the GB10. That is why compute is a separate service and why the GPU
   path is cuStateVec, not Aer. The x86 Aer install on xr7620 is a local-dev
   convenience only — it is **not** the product path.
2. **The GB10's memory is UNIFIED and shared with inference.** `nim-llama8b`
   holds ~59 GB when running, dropping the ceiling from 30 qubits to ~27. An
   over-allocation here does not just fail the request — it can evict a
   neighbour's model. `MEMORY_SAFETY` in the service guards this; don't raise it
   casually. Use `tools/gb10-gpu {claim|release|status}` — same residency
   discipline as the lab's `l4-fleet`. ⚠ `claim` takes **`nim/*` off the LiteLLM
   gateway** until `release`.
3. **Never report one "approximation ratio."** ⟨H⟩ averages the whole
   measurement distribution (~0.25); the plan actually returned is the **exact
   optimum** (1.000). Conflating them made the algorithm look broken during
   bring-up. `solution_ratio`, `expectation_ratio`, and `concentration` are
   separate properties on purpose.

## Claims discipline

This is shown to people who will check. Every number in the UI is measured live
or verified against brute force. **Do not** add speed comparisons against other
hardware — that framing was tested, measured at a genuine 1.2–2.2×, and cut
(BRIEF.md). The claim is *capability*, which is a fact about the machine.
