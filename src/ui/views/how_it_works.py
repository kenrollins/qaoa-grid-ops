"""Page: How it works — the merged quantum explainer.

Replaces the former "The Quantum Part" and "Learn QAOA" tabs, which had grown to
say the same things in two voices with nothing telling a visitor which to read.

The structure is `quantum.py`'s five steps — it had the discipline and the
honesty callout — with `learn.py`'s three figures moved to the step each one
actually illustrates. `learn.py` survives as the figure library; only its page
function retired.

Ordering principle: plain language, then the picture, then the mathematics —
and the mathematics is always inside an expander, because nothing on this page
should require opening one.
"""

from __future__ import annotations

import streamlit as st

from src.simulation.qaoa_engine import verify_fast_path
from src.ui import components as ui
from src.ui.views.learn import (
    interference_figure, landscape_figure, tradeoff_figure,
)


def _step(num: str, title: str, desc: str, math: str = "") -> str:
    m = f'<div class="math">{math}</div>' if math else ""
    return (f'<div class="qstep"><div class="num">{num}</div><div class="body">'
            f'<div class="t">{title}</div><div class="d">{desc}</div>{m}</div></div>')


def render(run=None, n_nodes: int = 12, layers: int = 2, seed: int = 7,
           pref: str = "gb10") -> None:
    n = run.model.n_qubits if run else n_nodes
    nc = run.model.n_terms if run else n * (n - 1) // 2
    p = run.result.get("layers", layers) if run else layers

    # ── The honesty callout. Verbatim from the old quantum tab: it is the best
    # paragraph in the app and it has to be the first thing read. ──────────────
    st.markdown("""
<div class="callout">
  <div class="h">Read this first — what this demonstration is</div>
  <p>This runs <strong>exact statevector simulation</strong> of a quantum algorithm on
  classical Dell hardware. There is <strong>no quantum processor</strong> in the loop, and
  none is being claimed.</p>
  <p>That is the point, not a limitation. QAOA is a <strong>hybrid</strong> algorithm: even
  with a perfect QPU attached, the overwhelming majority of the work — building the
  Hamiltonian, proposing parameters, converging the optimizer, decoding results into an
  islanding plan — runs on classical infrastructure. Simulating the quantum half today on
  the same hardware that will <em>drive</em> a real QPU tomorrow is how the algorithm,
  the encoding, and the operator tooling get developed and validated now.</p>
</div>""", unsafe_allow_html=True)

    cc = st.columns([1, 1, 3])
    fig_n = cc[0].select_slider("Figures: grid size", [8, 10, 12], value=10,
                                key="hiw_n",
                                help="Figures below are computed live. 10 nodes = 1,024 "
                                     "possible answers and renders in about a second; "
                                     "12 nodes is 4,096 and takes a few.")
    fig_p = cc[1].select_slider("Figures: circuit layers", [1, 2, 3, 4], value=2,
                                key="hiw_p")

    st.markdown("#### From a power grid to a quantum state, in five steps")

    # ── 1 ────────────────────────────────────────────────────────────────────
    st.markdown(_step(
        "1", "One qubit per substation",
        f"Each substation gets a single binary decision: <strong>which island does it "
        f"join?</strong> That is one qubit. With <strong>{n} substations</strong> there are "
        f"<strong>2<sup>{n}</sup> = {2**n:,}</strong> possible ways to split the grid — the "
        "search space that makes this hard classically.",
        "substation i  →  qubit i  →  bit b_i ∈ {0,1}  →  spin s_i = 1 − 2·b_i ∈ {+1,−1}"
    ), unsafe_allow_html=True)

    # ── 2, with the solution-space figure that shows what it is choosing between
    st.markdown(_step(
        "2", "The operating objective becomes an energy function",
        "Three competing requirements are encoded as one cost function whose <strong>lowest "
        "energy is the best islanding plan</strong>. Minimize the power severed by the cut; "
        "keep each island able to supply its own load; and forbid the degenerate 'put "
        "everything in one island' answer. This is a <strong>QUBO</strong> — quadratic "
        "unconstrained binary optimization — and it is exactly the form quantum optimization "
        "consumes.",
        "H(s) = A·Σ w_ij(1 − s_i s_j)/2  +  B·(Σ p_i s_i)²  +  C·(Σ s_i)²\\n"
        "        ↑ severed flow            ↑ island balance    ↑ non-degenerate"
    ), unsafe_allow_html=True)

    st.markdown("###### What the objective is choosing between")
    st.markdown("""
Every possible way to split this grid, evaluated with real power-flow physics.
Left-to-right is how much customer load a plan switches off; bottom-to-top is how hard
it pushes the most-loaded surviving line. **You want the bottom-left corner.**
""")
    with st.spinner("Evaluating every possible partition…"):
        st.plotly_chart(tradeoff_figure(fig_n, seed), width="stretch")
    st.markdown("""
The bottom-left corner is empty, and no amount of better optimization changes that — it is
a property of the grid. Safety is bought by switching off a block of customers. This is the
trade the cost function above is navigating, and it is why the weights are exposed as
sliders rather than baked in.
""")

    # ── 3, with the interference figure ──────────────────────────────────────
    st.markdown(_step(
        "3", "Superposition — every plan at once",
        f"A Hadamard gate on each qubit puts the register into a uniform superposition: all "
        f"<strong>{2**n:,}</strong> candidate partitions represented simultaneously, each with "
        "equal amplitude. Nothing has been decided yet; the algorithm's job is to move "
        "amplitude <em>toward</em> the good partitions and away from the bad ones.",
        f"|ψ₀⟩ = H^⊗{n} |0⟩^⊗{n} = (1/√{2**n}) · Σ_x |x⟩      every partition, equal weight"
    ), unsafe_allow_html=True)

    st.markdown("###### Watch the interference do it")
    st.markdown("""
Every bar is one possible answer; its height is how likely the machine is to hand you that
answer. Press play. It starts flat — the machine is guessing — then each layer marks the
good answers and makes the marks interfere, so probability drains out of bad answers and
piles into good ones. The green bars are the genuinely best answer and its mirror image.
""")
    st.plotly_chart(interference_figure(fig_n, seed, fig_p), width="stretch")
    st.markdown("""
Notice what does **not** happen: no bar reaches certainty. QAOA does not find the answer,
it *loads the dice* — which is why the real algorithm runs many times and takes the best
result, and why "how much better than guessing" is the number that matters.
""")

    # ── 4, with the landscape figure ─────────────────────────────────────────
    st.markdown(_step(
        "4", "QAOA — alternate 'judge' and 'mix'",
        f"The circuit alternates two operations for <strong>p = {p} layers</strong>. The "
        "<strong>cost unitary</strong> stamps each candidate partition with a phase "
        "proportional to how bad it is — good plans and bad plans now differ in phase, not "
        "yet in probability. The <strong>mixer</strong> then makes those phases interfere, "
        "converting the phase difference into an <em>amplitude</em> difference. Repeat, and "
        "probability concentrates on low-energy partitions. "
        f"Here that is <strong>{nc} ZZ couplings</strong> per layer "
        f"(<strong>{nc * p} total rotations</strong>) plus {n} mixer rotations per layer.",
        "|ψ⟩ = [ e^(−iβ_p H_M) · e^(−iγ_p H_C) ] … [ e^(−iβ₁ H_M) · e^(−iγ₁ H_C) ] |ψ₀⟩\\n"
        "        ↑ mixer (RX)        ↑ cost (RZZ)          γ, β tuned classically"
    ), unsafe_allow_html=True)

    st.markdown("###### The part that is actually hard: choosing the two dials")
    st.markdown("""
Each layer has two dials. **γ** sets how hard the cost step pushes; **β** sets how hard the
mixer stirs. Nobody knows the right values in advance, so a classical optimizer hunts for
them — and this is where most of the real work lives. Every point below is one setting of
the two dials; the colour is how good the result was. **Cool colours are better.**
""")
    with st.spinner("Evaluating the landscape…"):
        st.plotly_chart(landscape_figure(fig_n, seed), width="stretch")
    st.markdown("""
- **β matters more than you would guess.** There is a broad good band and a broad bad band,
  sharply separated. Choose β badly and no value of γ rescues the run.
- **There is a real basin here, and that is good news.** At this size the surface has
  structure an optimizer can follow. The flatness that makes optimization hard — the
  *barren plateau*, where gradients vanish exponentially with qubit count — emerges as
  systems grow. **You develop where you can still see the slope, then scale.**
- **The two vertical lines are a real bug from this project.** We sized the γ search range
  from the largest single coupling instead of the spread of the whole cost function, and
  searched ~1.5x wider than the informative region. Combined with a starved evaluation
  budget, deeper circuits scored *worse* than shallow ones until both were fixed.
""")
    with st.expander("Why the spread, and not the biggest coupling?"):
        st.markdown(r"""
The cost step separates two candidates by the phase difference $\gamma\,[H(x) - H(y)]$, so
what matters is the spread of $H$ across candidates — its standard deviation $\sigma(H)$ —
not the size of any individual coupling. Those come apart as a problem gets denser, because
many terms contribute to the total while $\max|J|$ describes only one.

Measured on this project's objective:

| nodes | coupling terms | $\sigma(H)$ | $\max|J|$ | ratio |
|---|---|---|---|---|
| 12 | 66 | 0.743 | 0.314 | 2.4x |
| 16 | 120 | 1.071 | 0.306 | 3.5x |

A tempting shortcut that does **not** hold here: for $m$ equal-magnitude independent terms
$\sigma(H)$ would grow as $\sqrt{m}\,|J|$, and an earlier version of this page said so. Our
objective sums three families with deliberately different scalings, so the measured ratio
(2–4x) is far below $\sqrt{m}$ (8–11x). Measure $\sigma(H)$; do not estimate it.

Setting $\gamma_{max} = \pi / (2\sigma(H))$ keeps the search where phase differences still
order candidates by quality.
""")

    # ── 5 ────────────────────────────────────────────────────────────────────
    st.markdown(_step(
        "5", "Measure — the bitstring IS the islanding plan",
        "Reading the register collapses it to one bitstring, and that bitstring is directly "
        "the operational answer: bit <em>i</em> says which island substation <em>i</em> "
        "belongs to. Because amplitude was concentrated on low-energy states, the outcome is "
        "very likely a good plan.",
        "measure |ψ⟩  →  b = 0110100…  →  island A = {i : b_i = 0},  island B = {i : b_i = 1}"
    ), unsafe_allow_html=True)

    st.markdown(ui.card_html("What comes back is a shortlist, not an answer", """
<p>The circuit does not test the options one at a time. It puts all of them into
superposition at once, then uses interference to make good splits more likely to be
measured and bad ones cancel out. So what comes back is a <strong>ranked shortlist</strong>
of the most probable partitions.</p>
<p>Each candidate on that shortlist is then checked against real power-flow physics, and the
electrically securest is the one applied. That matters because the cost function has
<strong>no notion of thermal line ratings</strong> — the power flowing on a line after a cut
depends on the whole surviving network, which a QUBO cannot express. The quantum stage
proposes; classical physics disposes. Every candidate came off the circuit.</p>"""),
        unsafe_allow_html=True)

    # ── Who does what ────────────────────────────────────────────────────────
    st.markdown("#### Who does what — the hybrid split")
    st.markdown("""
<div class="split">
  <div class="col q">
    <h5>Quantum layer (simulated here)</h5>
    <ul>
      <li>Hold a superposition over all 2<sup>n</sup> partitions</li>
      <li>Apply the cost unitary — phase-separate by solution quality</li>
      <li>Apply the mixer — interfere phases into amplitudes</li>
      <li>Return the cost expectation ⟨H⟩ for the current parameters</li>
    </ul>
  </div>
  <div class="col c">
    <h5>Classical layer (Dell hardware, always)</h5>
    <ul>
      <li>Build the grid model and derive the Ising couplings</li>
      <li>Propose and refine the (γ, β) parameters — the outer optimizer</li>
      <li>Evolve and store the statevector — the memory-bound work</li>
      <li>Decode bitstrings, verify feasibility, produce the operator schedule</li>
    </ul>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown(ui.card_html("Why the classical side dominates — and why that is the story", """
<p>In the NISQ era the quantum processor is a <strong>subroutine inside a classical loop</strong>,
not a replacement for it. Every optimizer iteration is a fresh circuit with new parameters,
so the outer loop runs hundreds of times; between iterations, all the work is classical.</p>
<p>Which means the practical bottleneck for hybrid quantum computing today is
<strong>classical infrastructure</strong> — memory capacity, memory bandwidth, and the ability to
keep sensitive infrastructure data on-premise.</p>"""), unsafe_allow_html=True)

    # ── Live figures from the last run ───────────────────────────────────────
    if run is not None:
        conc = run.concentration or 0.0
        cols = st.columns(3)
        cols[0].markdown(ui.metric_html(
            "Search space", f"{2 ** run.model.n_qubits:,}", "partitions",
            f"{run.model.n_qubits} substations = {run.model.n_qubits} qubits"),
            unsafe_allow_html=True)
        cols[1].markdown(ui.metric_html(
            "Amplitude concentration", f"{conc:.1f}", "x uniform",
            "1.0x would mean the circuit did nothing",
            kind="ok" if conc > 2 else "warn"), unsafe_allow_html=True)
        cols[2].markdown(ui.metric_html(
            "Two-qubit rotations",
            f"{run.model.n_terms * run.result.get('layers', p):,}", "",
            f"{run.model.n_terms} couplings x {run.result.get('layers', p)} layers"),
            unsafe_allow_html=True)

        if run.exact:
            st.markdown(f"""
<div class="callout" style="border-left-color:var(--ok);
     background:rgba(61,220,151,.06);border-color:rgba(61,220,151,.32)">
  <div class="h" style="color:var(--ok)">Verified against ground truth</div>
  <p>Every one of the <strong>{2 ** run.model.n_qubits:,}</strong> possible partitions was
  also evaluated by brute force, and the plan applied
  {'<strong>matches the exact optimum</strong> of the objective'
   if run.is_optimal else
   '<strong>deliberately differs</strong> from the objective&rsquo;s optimum — the '
   'energy-minimising split ran a line past its thermal rating, so a different candidate '
   'from the quantum shortlist was applied'}.</p>
  <p>This check is only affordable below ~20 qubits, which is why it matters that it runs
  <em>here</em>. Algorithm correctness gets established in the regime where truth is still
  computable, before scaling to sizes where it is not.</p>
</div>""", unsafe_allow_html=True)
    else:
        st.info("Run the scenario on the **Command Center** page to populate live figures "
                "for this grid.")

    st.markdown("---")
    st.markdown("#### The circuit itself, gate by gate")
    st.caption("For readers who want the gate-level detail. Nothing above depends on it.")

    n = run.model.n_qubits if run else n_nodes
    nc = run.model.n_terms if run else n * (n - 1) // 2
    st.markdown(f'<div class="circuit">{ui.circuit_ascii(n, layers, nc)}</div>',
                unsafe_allow_html=True)
    st.markdown("")

    if run:
        st.plotly_chart(ui.probability_figure(run.result.get("top_states", []), n),
                        width="stretch")
        params = run.result.get("best_params", [])
        p = run.result.get("layers", layers)
        cols = st.columns(2)
        cols[0].markdown(ui.card_html("Optimized cost angles γ", "".join(
            f"<p>γ<sub>{i+1}</sub> = <strong>{v:.4f}</strong></p>"
            for i, v in enumerate(params[:p]))), unsafe_allow_html=True)
        cols[1].markdown(ui.card_html("Optimized mixer angles β", "".join(
            f"<p>β<sub>{i+1}</sub> = <strong>{v:.4f}</strong></p>"
            for i, v in enumerate(params[p:]))), unsafe_allow_html=True)
        st.markdown(ui.card_html("Simulation note", """
<p>The cost Hamiltonian is diagonal in the computational basis, so exp(-iγH<sub>C</sub>) is
applied as a single elementwise phase multiply rather than as thousands of individual RZZ
gates. This is an <strong>optimization, not an approximation</strong> — and you can check that
here rather than take it on faith.</p>"""), unsafe_allow_html=True)

        if st.button("🔍  Verify: apply every RZZ gate individually and compare"):
            with st.spinner("Running both paths on the live backend…"):
                st.session_state["verify"] = verify_fast_path(
                    run.model, layers=run.result.get("layers", layers),
                    backend_preference=pref)

        v = st.session_state.get("verify")
        if v:
            if v.get("error"):
                st.error(f"Verification failed: {v['error']}")
            else:
                dev = v.get("max_amplitude_deviation", 0.0)
                ok = v.get("equivalent")
                st.markdown(f"""
<div class="callout" style="border-left-color:var(--{'ok' if ok else 'crit'});
 background:rgba(61,220,151,.06);border-color:rgba(61,220,151,.32)">
  <div class="h" style="color:var(--{'ok' if ok else 'crit'})">
{'Verified equivalent' if ok else 'NOT equivalent'} — {v.get('n_qubits')} qubits,
p={v.get('layers')}, on {v.get('backend')}</div>
  <p>Maximum amplitude deviation between the diagonal fast path and gate-by-gate RZZ
  application: <strong>{dev:.3e}</strong>
  {'— floating-point noise, i.e. the two are the same unitary.' if ok
   else '— above tolerance, the fast path is NOT reproducing the gate sequence.'}</p>
</div>""", unsafe_allow_html=True)
    else:
        st.info("Run an optimization to populate the measured statevector distribution.")

