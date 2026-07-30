"""Tab: Under the Hood — what makes this hard, and where the walls are.

The demo's actual thesis lives on this page. The grid optimization is a vehicle;
the argument is that **developing** a quantum algorithm is the hard part, that
developing it requires simulating it classically, and that simulation runs into
walls you can compute exactly.

Written in layers on purpose. The top of every section is plain language that a
systems person can act on; the detail underneath is there for whoever wants it.
Nobody should need calculus to leave understanding why the memory matters.

Measured figures carry their date and the machine they came from. Extrapolated
figures are labelled as arithmetic, because 2^n needs no measurement.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.config.settings import COLORS
from src.ui import components as ui

# Measured on this lab's hardware. Dated because hardware claims rot.
GB10_MEASURED = [  # (qubits, seconds per energy evaluation, p=2, dense all-to-all)
    (24, 0.67), (26, 2.6), (28, 11.6), (30, 50.0),
]
MEASURED_NOTE = "measured on the Dell Pro Max GB10, 2026-07-29, p=2 dense all-to-all"

# Reference points for the wall chart.
#
# Capacities are aggregate high-bandwidth memory for the configuration; the qubit
# numbers are ARITHMETIC from those capacities (2^n·16 B), not vendor performance
# claims. VERIFY THE CONFIGURATIONS before this is shown to a customer — the
# curve is exact, the hardware line-up is the part that dates.
TIERS = [
    ("Dell Pro Max · GB10 · 128 GB unified", 128 * 2**30, COLORS["accent"]),
    ("Dell PowerEdge XE9680 · 8× H200 · 1.1 TB", 1.1 * 2**40, COLORS["island_b"]),
    ("Dell PowerEdge XE9680 · 8× B200 · 1.5 TB", 1.5 * 2**40, COLORS["ok"]),
    ("GB200 NVL72 · 13.4 TB · one NVLink domain", 13.4 * 2**40, COLORS["warn"]),
    ("Multi-rack AI Factory · ~100 TB", 100 * 2**40, COLORS["crit"]),
]


def _qubits_for(capacity_bytes: float, noisy: bool) -> float:
    """Largest n whose state fits. Statevector 2^n·16 B; density matrix 2^2n·16 B."""
    import math
    n = math.log2(capacity_bytes / 16.0)
    return n / 2.0 if noisy else n


def memory_wall_figure() -> go.Figure:
    """The two curves that define the whole problem."""
    import math

    ns = list(range(10, 56))
    sv = [(2 ** n) * 16 for n in ns]
    dm = [(2 ** (2 * n)) * 16 for n in ns]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ns, y=[b / 2**30 for b in sv], mode="lines", name="Clean simulation (statevector)",
        line=dict(color=COLORS["accent"], width=3),
        hovertemplate="%{x} qubits<br>%{y:,.3g} GB<extra>statevector</extra>"))
    fig.add_trace(go.Scatter(
        x=ns, y=[b / 2**30 for b in dm], mode="lines", name="With noise (density matrix)",
        line=dict(color=COLORS["crit"], width=3, dash="dash"),
        hovertemplate="%{x} qubits<br>%{y:,.3g} GB<extra>density matrix</extra>"))

    for label, cap, color in TIERS:
        gb = cap / 2**30
        fig.add_hline(y=gb, line=dict(color=color, width=1.2, dash="dot"),
                      annotation_text=f"  {label}", annotation_position="top left",
                      annotation_font=dict(color=color, size=10))

    # Where the GB10 actually lands on each curve.
    gb10 = 128 * 2**30
    fig.add_trace(go.Scatter(
        x=[_qubits_for(gb10, False)], y=[gb10 / 2**30], mode="markers+text",
        marker=dict(size=14, color=COLORS["accent"], symbol="diamond",
                    line=dict(color=COLORS["bg"], width=2)),
        text=["  33 qubits clean"], textposition="middle right",
        textfont=dict(color=COLORS["accent"], size=11), showlegend=False,
        hovertemplate="GB10 clean ceiling<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=[_qubits_for(gb10, True)], y=[gb10 / 2**30], mode="markers+text",
        marker=dict(size=14, color=COLORS["crit"], symbol="diamond",
                    line=dict(color=COLORS["bg"], width=2)),
        text=["16 qubits noisy  "], textposition="middle left",
        textfont=dict(color=COLORS["crit"], size=11), showlegend=False,
        hovertemplate="GB10 noisy ceiling<extra></extra>"))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor="#070b12",
        font=dict(color=COLORS["text"], size=12), height=470,
        margin=dict(l=60, r=30, t=50, b=50),
        title=dict(text="The wall — memory required to simulate n qubits", font=dict(size=14)),
        legend=dict(bgcolor="rgba(7,11,18,.8)", x=0.02, y=0.98, font=dict(size=11)))
    fig.update_xaxes(title="Qubits", gridcolor=COLORS["line"], dtick=5)
    fig.update_yaxes(title="Memory (GB, log scale)", type="log",
                     gridcolor=COLORS["line"])
    return fig


def scaling_measured_figure() -> go.Figure:
    """What it actually costs in time on real hardware."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[n for n, _ in GB10_MEASURED], y=[s for _, s in GB10_MEASURED],
        marker=dict(color=COLORS["accent"]), name="seconds per evaluation",
        text=[f"{s:.2f}s" for _, s in GB10_MEASURED], textposition="outside",
        hovertemplate="%{x} qubits<br>%{y:.2f} s per energy evaluation<extra></extra>"))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor="#070b12",
        font=dict(color=COLORS["text"], size=12), height=330,
        margin=dict(l=60, r=30, t=50, b=45), showlegend=False,
        title=dict(text=f"Time per evaluation — {MEASURED_NOTE}", font=dict(size=13)))
    fig.update_xaxes(title="Qubits", gridcolor=COLORS["line"], dtick=2)
    fig.update_yaxes(title="Seconds (log)", type="log", gridcolor=COLORS["line"])
    return fig


def _hard(num: str, title: str, plain: str, detail: str, cost: str) -> str:
    return (f'<div class="qstep"><div class="num">{num}</div><div class="body">'
            f'<div class="t">{title}</div>'
            f'<div class="d">{plain}</div>'
            f'<div class="d" style="margin-top:.45rem;opacity:.85">{detail}</div>'
            f'<div class="math">COST: {cost}</div></div></div>')


def render(run=None) -> None:
    st.markdown("""
<div class="callout" style="border-left-color:var(--accent);
     background:rgba(0,200,255,.05);border-color:rgba(0,200,255,.3)">
  <div class="h" style="color:var(--accent)">The whole argument, in two sentences</div>
  <p><strong>Every qubit you add doubles the memory needed to simulate it. Turn on noise —
  which you must, to design anything that works on real hardware — and it squares instead.</strong></p>
  <p>Running a quantum algorithm is not the hard part. <em>Designing</em> one that survives a
  real, noisy, sparsely-connected device is the hard part, and that design work happens in
  classical simulation. Which means the ceiling on quantum algorithm development is a
  classical infrastructure problem — and it arrives much sooner than people expect.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("### The wall")
    st.markdown("""
A quantum state of n qubits is a list of 2ⁿ numbers. At 16 bytes each, that is
**17 GB at 30 qubits** — and 34 GB at 31, 69 GB at 32. The line is not steep; it is
*exponential*, which is worse than steep.

Noise changes the shape of the problem entirely. Modelling a noisy system needs a
**density matrix** — 2ⁿ × 2ⁿ instead of 2ⁿ — so it costs **the square**. On the same box,
noisy simulation reaches roughly **half** the qubits of clean simulation.
""")
    st.plotly_chart(memory_wall_figure(), width="stretch")

    c = st.columns(4)
    for col, (lbl, val, note) in zip(c, [
        ("Developer workstation", "33", "GB10 · 128 GB unified · clean"),
        ("Same box, with noise", "16", "density matrix squares the cost"),
        ("GB200 NVL72", "~39", "13.4 TB in one NVLink domain · clean"),
        ("Multi-rack AI Factory", "~42", "~100 TB · clean"),
    ]):
        col.markdown(ui.metric_html(lbl, val, "", note), unsafe_allow_html=True)

    st.markdown("""
<div class="callout">
  <div class="h">Read those four numbers together</div>
  <p>Going from a <strong>developer workstation</strong> to a <strong>multi-rack AI
  Factory</strong> — an 800× increase in memory — buys about <strong>nine more clean qubits,
  or four noisy ones</strong>. That is what exponential means, and it is the honest reason
  quantum matters: a real 30-qubit noisy device does for free what no classical machine we
  can build will do.</p>
  <p>It is also the reason simulation capacity is the binding constraint on algorithm
  development. You are not trying to out-compute the quantum computer. You are trying to get
  far enough to design something worth running on one.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("### It is not only capacity — it is bandwidth")
    st.markdown("""
Every gate touches **the entire state**. A 30-qubit statevector is 16 GB, and one QAOA
energy evaluation at p=2 makes ~62 passes over it — roughly **a terabyte of memory traffic
for a single number**. That is why this workload is memory-bandwidth-bound rather than
FLOP-bound, and why unified memory on the GB10 matters more than raw compute.
""")
    st.plotly_chart(scaling_measured_figure(), width="stretch")
    st.caption("Measured, not modelled. 24 qubits is interactive at 0.67 s; 30 qubits takes "
               "50 s per evaluation — and a full optimisation needs 30+ of them.")

    st.markdown("### The four things that make this genuinely hard")
    st.markdown(_hard(
        "1", "Noise — and why it squares the memory",
        "Real quantum hardware is <strong>wrong a lot</strong>. Every gate has an error rate, "
        "qubits forget their state within microseconds, and reading them out misreports. An "
        "algorithm designed as if none of that existed does not survive contact with a device.",
        "Modelling noise means tracking not just the state but the <em>uncertainty</em> about "
        "it — a density matrix ρ of 2ⁿ×2ⁿ entries rather than a vector of 2ⁿ. Error-mitigation "
        "techniques (zero-noise extrapolation, readout correction) are themselves algorithms "
        "that need designing and testing against simulated noise.",
        "squares the memory · 33 clean qubits → 16 noisy on identical hardware"),
        unsafe_allow_html=True)

    st.markdown(_hard(
        "2", "Shots — you never actually see the answer",
        "A real quantum computer does not hand you a number. It hands you a <strong>coin "
        "flip</strong>, and you run the circuit thousands of times to estimate what it meant. "
        "This demo cheats: it reads the exact answer straight out of the simulated state, "
        "which no physical device can do.",
        "Estimating ⟨H⟩ from finite samples carries statistical noise ~1/√shots. That noise "
        "goes directly into the classical optimiser, which is now trying to find a minimum "
        "while the landscape jitters under it. Shot budget becomes a first-class design "
        "parameter, traded against accuracy.",
        "1,000–10,000 circuit executions per single optimiser step"),
        unsafe_allow_html=True)

    st.markdown(_hard(
        "3", "Connectivity — the chip is not shaped like your problem",
        "This grid problem couples <strong>every substation to every other</strong>. Real "
        "quantum chips connect each qubit to two or three neighbours. Getting two distant "
        "qubits to interact means physically shuffling states along a chain of intermediate "
        "ones — and every shuffle is another chance to be wrong.",
        "Compiling an all-to-all Hamiltonian onto a heavy-hex or linear topology inserts SWAP "
        "networks that multiply circuit depth by 10–100×. Since decoherence is a wall-clock "
        "budget, deeper circuits mean more decay — so the compilation strategy determines "
        "whether the algorithm works at all. This is a large, active research area.",
        "10–100× circuit depth · deeper circuit = more noise = worse answer"),
        unsafe_allow_html=True)

    st.markdown(_hard(
        "4", "The parameter landscape — where optimisers go to die",
        "QAOA has knobs (γ and β) that a classical optimiser tunes. The surface it is "
        "searching is <strong>mostly flat</strong>, with the good regions rare and narrow. "
        "Start in the wrong place and the optimiser sits still, reporting success, having "
        "found nothing.",
        "This is the barren-plateau problem: for many ansätze the gradient vanishes "
        "exponentially with qubit count, so the search space becomes featureless exactly as "
        "the problem becomes interesting. Mitigations — layer-wise growth, annealing-inspired "
        "initialisation, parameter transfer between problem sizes — are the substance of "
        "current QAOA research.",
        "thousands of evaluations to map · and this project hit it twice, below"),
        unsafe_allow_html=True)

    st.markdown("### What actually broke while building this demo")
    st.markdown("""
<div class="callout">
  <div class="h">Receipts — two real failures from this project</div>
  <p><strong>1. Deeper circuits scored worse.</strong> QAOA at p=4 returned an approximation
  ratio of <strong>0.135</strong> against p=2's <strong>0.255</strong> — backwards from how the
  algorithm is supposed to behave, on the single slider a knowledgeable visitor reaches for
  first. Cause: γ was scaled by the largest coupling instead of by <strong>σ(H)</strong>, the
  spread of the cost function. On a dense problem that overshoots by roughly √(term count),
  so the entire search budget was spent in an over-rotated regime that looks like noise.</p>
  <p><strong>2. The optimiser reported convergence on the unevolved state.</strong> Runs
  finished, drew a clean curve, and returned an energy exactly equal to the Hamiltonian's
  constant offset — the signature of γ≈0, meaning the cost unitary had done
  <em>nothing at all</em>. Cause: a layer-wise schedule split a 30-step budget across p
  levels, leaving ~3 optimiser iterations in up to 8 dimensions. It never moved off its
  starting point, and nothing in the output said so.</p>
  <p>Both were found by checking against brute force, which is only affordable below ~20
  qubits. Above that, an algorithm can be quietly, confidently wrong — which is precisely why
  the development regime, where truth is still computable, is the regime that matters.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("### What this means for the architecture")
    st.markdown("""
<div class="split">
  <div class="col c">
    <h5>One bigger problem</h5>
    <ul>
      <li>Bound by <strong>memory capacity</strong> — the state must fit</li>
      <li>Then by <strong>memory bandwidth</strong> — every gate reads all of it</li>
      <li>Past one box, by <strong>interconnect</strong>: gates spanning devices need
          all-to-all exchange every time, so NVLink domain size is decisive — PCIe is not
          in the running</li>
      <li>This is why GB200 NVL72 matters here: 13.4 TB inside <em>one</em> NVLink domain
          behaves like one machine, where the same capacity split across InfiniBand-linked
          nodes does not</li>
    </ul>
  </div>
  <div class="col q">
    <h5>Many problems at once</h5>
    <ul>
      <li>Parameter sweeps, noise ensembles, shot studies, ansatz comparisons</li>
      <li>Embarrassingly parallel — bound simply by <strong>GPU count</strong></li>
      <li>Scales near-linearly with GPU count — measured at <strong>4× on four GPUs with
          zero contention</strong></li>
      <li>This is where most development hours actually go</li>
    </ul>
  </div>
</div>""", unsafe_allow_html=True)
    st.markdown("""
<div class="callout">
  <div class="h">The uncomfortable part</div>
  <p>No single machine gives you all three of capacity, bandwidth, and interconnect. A
  desktop-class GB10 takes you to 33 clean qubits — genuinely useful, and enough to develop
  and validate against exact answers. Past that the requirement is not a bigger server, it is
  <strong>a different class of system</strong>: many nodes, high-speed fabric, and the
  operational apparatus to run them.</p>
  <p>The workstation is where an algorithm gets designed and validated against exact answers.
  The AI Factory is where it gets pushed past the size at which anyone can check it by hand.
  Both are needed, and they are not the same purchase.</p>
  <p>That is the honest shape of the problem, and it is why this demo is built to find limits
  rather than to hide them.</p>
</div>""", unsafe_allow_html=True)
