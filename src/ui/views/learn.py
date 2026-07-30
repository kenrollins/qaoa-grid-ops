"""Tab: Learn — QAOA explained visually, with figures computed from the real engine.

Written for people who think in pictures. Every concept here has a plain-language
statement, a diagram you can watch move, and only then the equation — and the
equation is always optional. Nothing on this page is an illustration drawn to
look right: every figure is produced by the same code that runs the demo, so
what you are looking at is the actual computation.

The three figures that do the heavy lifting:

  * **Interference** — the probability of every candidate answer, layer by layer.
    This is the one that makes superposition and interference click: 4,096 bars
    start identical, and you watch the good ones grow while the rest shrink.
  * **The parameter landscape** — a contour map of the energy surface the
    classical optimiser is searching. Shows immediately why the search range
    matters and what "mostly flat" means in practice.
  * **The solution space** — every possible answer plotted by what it costs,
    which turns an abstract trade-off into a shape you can point at.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import COLORS, GridSpec, ObjectiveWeights
from src.simulation import power_flow as pf
from src.simulation import qaoa_core
from src.simulation.grid_model import (
    apply_fault, build_grid, build_ising, brute_force_ground_state, evaluate_partition,
)
from src.ui import components as ui


# ── Figure 1: interference, layer by layer ───────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _interference_data(n_nodes: int, seed: int, layers: int):
    """Probability of every candidate after each stage of the circuit."""
    spec = GridSpec(n_nodes=n_nodes, seed=seed)
    g = build_grid(spec)
    m = build_ising(g, spec.weights)
    diag = qaoa_core.cost_diagonal(n_nodes, m.couplings, m.offset)

    res = qaoa_core.optimize_qaoa(n_nodes, m.couplings, m.offset,
                                  layers=layers, steps=40)
    params = np.array(res.best_params)
    gammas, betas = params[:layers], params[layers:]

    dim = 1 << n_nodes
    sv = np.full(dim, 1.0 / np.sqrt(dim), dtype=np.complex128)
    frames = [np.abs(sv) ** 2]
    for k in range(layers):
        qaoa_core.apply_cost_diagonal(sv, diag, float(gammas[k]), np)
        qaoa_core.apply_mixer(sv, n_nodes, float(betas[k]), np)
        frames.append(np.abs(sv) ** 2)

    best_bits, best_e = brute_force_ground_state(m)
    best_idx = int(best_bits, 2)
    # Z2 symmetry: the complement is the same physical partition.
    comp_idx = (~best_idx) & (dim - 1)
    order = np.argsort(diag)            # sort candidates best-to-worst by cost
    return ([f[order] for f in frames], diag[order],
            int(np.where(order == best_idx)[0][0]),
            int(np.where(order == comp_idx)[0][0]), dim)


def interference_figure(n_nodes: int, seed: int, layers: int) -> go.Figure:
    frames, sorted_diag, best_pos, comp_pos, dim = _interference_data(
        n_nodes, seed, layers)
    x = np.arange(dim)
    uniform = 1.0 / dim

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=frames[0], marker=dict(color=COLORS["accent"]),
        name="probability", hovertemplate="candidate %{x}<br>P = %{y:.5f}<extra></extra>"))
    fig.add_hline(y=uniform, line=dict(color=COLORS["text_dim"], width=1, dash="dot"),
                  annotation_text="pure guessing", annotation_position="top right",
                  annotation_font=dict(color=COLORS["text_dim"], size=10))

    steps = ["Start — every answer equally likely"] + [
        f"After layer {k + 1} of {layers}" for k in range(layers)]
    fig.frames = [
        go.Frame(name=str(k),
                 data=[go.Bar(x=x, y=f, marker=dict(
                     color=[COLORS["ok"] if i in (best_pos, comp_pos)
                            else COLORS["accent"] for i in range(dim)]))])
        for k, f in enumerate(frames)]

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor="#070b12",
        font=dict(color=COLORS["text"], size=12), height=390, bargap=0,
        margin=dict(l=60, r=25, t=60, b=45),
        title=dict(text="Every possible answer, and how likely the circuit makes it",
                   font=dict(size=13)),
        showlegend=False,
        updatemenus=[dict(
            type="buttons", direction="left", x=0.01, y=1.16, xanchor="left",
            bgcolor="rgba(19,26,41,.9)", bordercolor=COLORS["border"], borderwidth=1,
            font=dict(color=COLORS["accent"], size=11), showactive=False,
            buttons=[dict(label="▶  WATCH THE INTERFERENCE", method="animate",
                          args=[None, dict(frame=dict(duration=900, redraw=True),
                                           transition=dict(duration=400),
                                           fromcurrent=True, mode="immediate")])])],
        sliders=[dict(active=0, y=-0.02, x=0.02, len=0.95,
                      currentvalue=dict(prefix="", font=dict(color=COLORS["accent"], size=12)),
                      steps=[dict(method="animate", label=steps[k],
                                  args=[[str(k)], dict(mode="immediate",
                                                       frame=dict(duration=0, redraw=True))])
                             for k in range(len(frames))])])
    fig.update_xaxes(title="the 2ⁿ possible answers, sorted best on the left",
                     showticklabels=False, gridcolor=COLORS["line"])
    fig.update_yaxes(title="probability", gridcolor=COLORS["line"])
    return fig


# ── Figure 2: the parameter landscape ────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _landscape_data(n_nodes: int, seed: int, res: int = 60):
    """⟨H⟩ over a grid of (gamma, beta) for a single-layer circuit."""
    spec = GridSpec(n_nodes=n_nodes, seed=seed)
    g = build_grid(spec)
    m = build_ising(g, spec.weights)
    diag = qaoa_core.cost_diagonal(n_nodes, m.couplings, m.offset)

    sigma = float(np.std(diag))
    max_j = max(abs(v) for v in m.couplings.values())
    g_sigma = float(np.pi / (2.0 * sigma))       # the correct scale
    g_maxj = float(np.pi / max(1.0, max_j))      # the intuitive, wrong scale

    g_hi = max(g_sigma, g_maxj) * 1.25
    gammas = np.linspace(0.0, g_hi, res)
    betas = np.linspace(0.0, np.pi / 2, res)

    z = np.empty((res, res))
    for i, b in enumerate(betas):
        for j, gm in enumerate(gammas):
            sv = qaoa_core.qaoa_statevector(n_nodes, diag, [gm], [b], xp=np)
            z[i, j] = qaoa_core.expectation(sv, diag, np)
    return gammas, betas, z, g_sigma, g_maxj, sigma, max_j


def landscape_figure(n_nodes: int, seed: int) -> go.Figure:
    gammas, betas, z, g_sigma, g_maxj, sigma, max_j = _landscape_data(n_nodes, seed)
    fig = go.Figure(go.Heatmap(
        x=gammas, y=betas, z=z, colorscale="Turbo", reversescale=True,
        colorbar=dict(title="⟨H⟩<br>lower<br>is better", tickfont=dict(size=10)),
        hovertemplate="γ = %{x:.3f}<br>β = %{y:.3f}<br>⟨H⟩ = %{z:.3f}<extra></extra>"))

    lo = float(z.min())
    yi, xi = np.unravel_index(np.argmin(z), z.shape)
    fig.add_trace(go.Scatter(
        x=[gammas[xi]], y=[betas[yi]], mode="markers+text",
        marker=dict(symbol="star", size=17, color="white",
                    line=dict(color=COLORS["bg"], width=1.5)),
        text=[f"  best found: ⟨H⟩ {lo:.2f}"], textposition="middle right",
        textfont=dict(color="white", size=11), showlegend=False, hoverinfo="skip"))

    fig.add_vline(x=g_sigma, line=dict(color=COLORS["ok"], width=2.5),
                  annotation_text=f" correct range ends here (σ(H)={sigma:.1f})",
                  annotation_position="top", annotation_font=dict(color=COLORS["ok"], size=10))
    fig.add_vline(x=g_maxj, line=dict(color=COLORS["crit"], width=2.5, dash="dash"),
                  annotation_text=f" where max|J|={max_j:.1f} sent the search ",
                  annotation_position="bottom",
                  annotation_font=dict(color=COLORS["crit"], size=10))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor="#070b12",
        font=dict(color=COLORS["text"], size=12), height=430,
        margin=dict(l=60, r=25, t=52, b=50),
        title=dict(text="The surface the classical optimizer has to search",
                   font=dict(size=13)))
    fig.update_xaxes(title="γ  —  how hard the cost step pushes")
    fig.update_yaxes(title="β  —  how hard the mixer stirs")
    return fig


# ── Figure 3: the whole solution space ───────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _tradeoff_data(n_nodes: int, seed: int):
    """Evaluate every possible partition with a real power flow."""
    spec = GridSpec(n_nodes=n_nodes, seed=seed)
    base = pf.calibrate_ratings(build_grid(spec))
    line = pf.worst_contingency(base)
    g = apply_fault(base, [line] if line else [])
    m = build_ising(g, spec.weights)

    rows = []
    for s in range(1 << n_nodes):
        bits = format(s, f"0{n_nodes}b")
        rep = evaluate_partition(g, m, bits)
        opened = {tuple(sorted((u, v))) for u, v, _ in rep.severed_lines}
        sol = pf.solve(g, opened=opened)
        rows.append((sol.shed_mw, sol.worst_loading * 100.0,
                     rep.feasible, len(sol.overloads), rep.energy))
    return rows, sol.total_load_mw


def tradeoff_figure(n_nodes: int, seed: int) -> go.Figure:
    rows, total_load = _tradeoff_data(n_nodes, seed)
    infeas = [r for r in rows if not r[2]]
    feas_bad = [r for r in rows if r[2] and r[3] > 0]
    feas_ok = [r for r in rows if r[2] and r[3] == 0]

    fig = go.Figure()
    for data, name, color, size in [
        (infeas, "Not electrically viable", "#39404f", 4),
        (feas_bad, "Viable, but a line is over its rating", COLORS["warn"], 6),
        (feas_ok, "Viable AND thermally secure", COLORS["ok"], 11),
    ]:
        if not data:
            continue
        fig.add_trace(go.Scatter(
            x=[d[0] for d in data], y=[d[1] for d in data], mode="markers", name=name,
            marker=dict(color=color, size=size, opacity=0.75,
                        line=dict(color=COLORS["bg"], width=0.4)),
            hovertemplate="shed %{x:.0f} MW<br>peak line %{y:.0f}%<extra></extra>"))

    fig.add_hline(y=100, line=dict(color=COLORS["crit"], width=2, dash="dash"),
                  annotation_text="  100% — above this line, conductors trip",
                  annotation_position="top right",
                  annotation_font=dict(color=COLORS["crit"], size=10))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor="#070b12",
        font=dict(color=COLORS["text"], size=12), height=430,
        margin=dict(l=60, r=25, t=52, b=50),
        title=dict(text=f"Every one of the {len(rows):,} possible answers, "
                        f"and what each one costs", font=dict(size=13)),
        legend=dict(bgcolor="rgba(7,11,18,.85)", x=0.55, y=0.98, font=dict(size=10)))
    fig.update_xaxes(title=f"customer load switched off (MW, of {total_load:,.0f} total)",
                     gridcolor=COLORS["line"])
    fig.update_yaxes(title="worst line loading (% of rating)", gridcolor=COLORS["line"])
    return fig


# ── The page ─────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown("""
<div class="callout" style="border-left-color:var(--accent);
     background:rgba(0,200,255,.05);border-color:rgba(0,200,255,.3)">
  <div class="h" style="color:var(--accent)">How to read this page</div>
  <p>Every picture here is produced by the same code that runs the demo — none of
  them are drawn to illustrate a point. Plain-language explanation first, the picture
  second, and the mathematics only if you want it (it is folded away, and nothing
  depends on opening it).</p>
</div>""", unsafe_allow_html=True)

    cols = st.columns([1, 1, 2])
    n_nodes = cols[0].select_slider("Grid size", [8, 10, 12], value=10,
                                    help="Smaller renders faster. 10 nodes = 1,024 answers.")
    seed = cols[1].number_input("Grid seed", 1, 999, 7)
    layers = cols[2].select_slider("Circuit layers (p)", [1, 2, 3, 4], value=2)

    # ── 1. Interference ─────────────────────────────────────────────────────
    st.markdown("## 1. How a quantum computer looks at every answer at once")
    st.markdown(f"""
Start with the honest version of the problem. Splitting {n_nodes} substations into
two groups has **2^{n_nodes} = {2 ** n_nodes:,} possible answers**. A classical computer
must examine them more or less one at a time.

A quantum computer holds **one qubit per substation**, and n qubits can represent
all 2ⁿ combinations simultaneously — a *superposition*. Every bar in the chart below
is one possible answer, and the height of the bar is how likely the machine is to
give you that answer if you look at it right now.

**Press play.** At the start every bar is the same height: the machine is guessing.
Each circuit layer does two things — it marks the good answers, then it makes the
marks interfere, so probability drains out of bad answers and piles into good ones.
The two green bars are the genuinely best answer and its mirror image.
""")
    st.plotly_chart(interference_figure(n_nodes, int(seed), layers), width="stretch")
    st.markdown("""
Notice what does **not** happen: no single bar shoots up to certainty. QAOA does not
find the answer, it *loads the dice* — and with a low-depth circuit it loads them
only somewhat. That is why the real algorithm runs the circuit many times and takes
the best result, and why "how much better than guessing" is the number that matters.
""")
    with st.expander("The mathematics, if you want it"):
        st.markdown(r"""
The starting state is an equal superposition over all $2^n$ basis states:

$$|\psi_0\rangle = \frac{1}{\sqrt{2^n}}\sum_x |x\rangle$$

Each layer applies two operators. The **cost** operator multiplies each candidate
by a phase set by its cost — it changes no probabilities, only phases:

$$e^{-i\gamma H_C}|x\rangle = e^{-i\gamma H(x)}|x\rangle$$

The **mixer** rotates every qubit about the X axis, which mixes neighbouring
bitstrings and turns those phase differences into amplitude differences:

$$e^{-i\beta \sum_j X_j}$$

After $p$ layers the probability of measuring $x$ is $|\langle x|\psi\rangle|^2$ —
the bar heights above. Phase is invisible until interference converts it into
probability, which is the entire trick.
""")

    # ── 2. The landscape ────────────────────────────────────────────────────
    st.markdown("## 2. The part that is actually hard: choosing the two dials")
    st.markdown("""
Each layer has two dials. **γ (gamma)** sets how hard the cost step pushes;
**β (beta)** sets how hard the mixer stirs. Get them right and probability piles onto
good answers. Get them wrong and the circuit does nothing useful.

Nobody knows the right values in advance, so a classical optimizer hunts for them —
and this is where most of the real work lives. The map below is that search surface
for a single layer: **every point is one setting of the two dials, and the colour is
how good the result was.** Cool colours are better.
""")
    with st.spinner("Evaluating the landscape…"):
        st.plotly_chart(landscape_figure(n_nodes, int(seed)), width="stretch")
    st.markdown("""
Three things are visible at a glance, and they are the whole difficulty:

- **The good region is small.** Most of the map is one flat colour. An optimizer
  dropped at random has no gradient to follow — it is standing in a field with no
  slope, and this gets exponentially worse with more qubits. That is the
  *barren plateau* problem.
- **Too much γ is as bad as too little.** Past a certain point the colours become
  stripes. Phase wraps around, and the ordering between good and bad answers is
  scrambled — the circuit is running hard and achieving noise.
- **The two vertical lines are a real bug from this project.** We originally sized
  the search range by the largest single coupling in the problem (red dashed) rather
  than the spread of the whole cost function (green). On a densely connected problem
  those differ by roughly the square root of the number of terms, so most of the
  search budget was spent out in the striped region. Deeper circuits scored *worse*
  than shallow ones until it was fixed.
""")
    with st.expander("Why the spread, and not the biggest coupling?"):
        st.markdown(r"""
The cost step separates two candidates by the phase difference
$\gamma\,[H(x) - H(y)]$. What matters is therefore the spread of $H$ across
candidates — its standard deviation $\sigma(H)$ — not the size of any single term.

For a Hamiltonian built from $m$ comparable coupling terms, $\sigma(H)$ grows
roughly as $\sqrt{m}\,|J|$, while $\max|J|$ does not grow at all. Our 12-node
problem has 66 terms: measured $\sigma(H) \approx 3.5$ against $\max|J| \approx 2.5$.

Setting $\gamma_{max} = \pi / (2\sigma(H))$ keeps the search inside the region where
phases still order candidates by quality.
""")

    # ── 3. The solution space ───────────────────────────────────────────────
    st.markdown("## 3. What we were actually asking for — and what it costs")
    st.markdown(f"""
Here is every one of the **{2 ** n_nodes:,} possible ways** to split this grid after a
line has failed, each one evaluated with real power-flow physics. Left-to-right is
how much customer load the plan switches off. Bottom-to-top is how hard the plan
pushes the most-loaded surviving line.

**You want the bottom-left corner** — nobody loses power, no line is overloaded.
""")
    with st.spinner("Evaluating every possible partition with a power flow…"):
        st.plotly_chart(tradeoff_figure(n_nodes, int(seed)), width="stretch")
    st.markdown("""
The bottom-left corner is empty. That is the finding, and no amount of better
optimization changes it — it is a property of the grid, not of the algorithm.

Grey points are not electrically viable at all (an island with no power station, or
one split into disconnected pieces). Amber points keep the lights on but run a
conductor past its rating, which is how cascading blackouts start. The few green
points are genuinely safe — and every one of them sits well to the right, meaning
**safety is bought by switching off a large block of customers**.

This is the picture a control-room operator carries in their head, and it is the
reason the problem is worth solving well: you are not looking for a free answer,
you are looking for the least-bad one under time pressure.
""")
    with st.expander("Why the optimizer could not see the vertical axis"):
        st.markdown("""
The cost function we hand the quantum computer contains three things: interrupted
power flow, island power balance, and a term forbidding the do-nothing answer.

It contains **nothing about line ratings** — because the power flowing on a line
*after* a cut depends on the whole surviving network at once, and a QUBO can only
express costs involving one or two variables at a time.

So the optimizer honestly minimised what it was given, and the answer it returned
sat high on the vertical axis: it loaded a line to 202% of rating, where taking no
action at all peaked at 137%. The fix in the demo is to take the top candidates the
quantum circuit produces and run a real power flow on each, choosing on the axis the
Hamiltonian cannot see. See note 03 for the full treatment.
""")

    st.markdown("---")
    st.markdown("""
##### Going deeper
The written notes carry the full detail, the measured numbers with their provenance,
and the references: `docs/journal/notes/` in the project repository.
""")
