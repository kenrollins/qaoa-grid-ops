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

from src.config.settings import COLORS, GridSpec
from src.simulation import power_flow as pf
from src.simulation import noise as nz
from src.simulation import qaoa_core
from src.simulation.grid_model import (
    apply_fault, build_grid, build_ising, brute_force_ground_state, evaluate_partition,
)


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

    best_bits, _ = brute_force_ground_state(m)
    best_idx = int(best_bits, 2)
    # Z2 symmetry: the complement is the same physical partition.
    comp_idx = (~best_idx) & (dim - 1)
    order = np.argsort(diag)            # sort candidates best-to-worst by cost
    return ([f[order] for f in frames], diag[order],
            int(np.where(order == best_idx)[0][0]),
            int(np.where(order == comp_idx)[0][0]), dim)


def interference_figure(n_nodes: int, seed: int, layers: int) -> go.Figure:
    frames, _, best_pos, comp_pos, dim = _interference_data(
        n_nodes, seed, layers)
    x = np.arange(dim)
    uniform = 1.0 / dim

    # Colour the best answer and its Z2 partner in the INITIAL trace too, not
    # only inside the animation frames. The caption points at "the two green
    # bars", and before pressing play there were none.
    bar_colors = [COLORS["ok"] if i in (best_pos, comp_pos) else COLORS["accent"]
                  for i in range(dim)]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=frames[0], marker=dict(color=bar_colors),
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
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["plot_bg"],
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
    gammas, betas, z, g_sigma, g_maxj, sigma, _ = _landscape_data(n_nodes, seed)
    fig = go.Figure(go.Heatmap(
        # Viridis, not Turbo: Turbo is perceptually ordered but collides at the
        # red end under common colour-vision deficiencies. Viridis is CVD-safe
        # and monotonic in lightness, so the ordering survives in greyscale and
        # on a bad projector. Low <H> (better) is the DARK end, and the colourbar
        # says so rather than relying on the reader inferring it.
        x=gammas, y=betas, z=z, colorscale="Viridis",
        colorbar=dict(title="⟨H⟩<br>darker<br>is better", tickfont=dict(size=10)),
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
                  annotation_text=" old range searched out to here ",
                  annotation_position="bottom",
                  annotation_font=dict(color=COLORS["crit"], size=10))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["plot_bg"],
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
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["plot_bg"],
        font=dict(color=COLORS["text"], size=12), height=430,
        margin=dict(l=60, r=25, t=52, b=50),
        title=dict(text=f"Every one of the {len(rows):,} possible answers, "
                        f"and what each one costs", font=dict(size=13)),
        legend=dict(bgcolor="rgba(5,5,5,.85)", x=0.55, y=0.98, font=dict(size=10)))
    fig.update_xaxes(title=f"customer load switched off (MW, of {total_load:,.0f} total)",
                     gridcolor=COLORS["line"])
    fig.update_yaxes(title="worst line loading (% of rating)", gridcolor=COLORS["line"])
    return fig


# ── Figure 4: trajectories converging on the exact answer ────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _trajectory_data(n_nodes: int, seed: int, noise_pct: float, n_traj: int):
    """Run BOTH methods on the same problem so convergence is demonstrable.

    Deliberately small: the density matrix has to be affordable for the exact
    line to exist at all. That constraint is itself the point being made.
    """
    spec = GridSpec(n_nodes=n_nodes, seed=seed)
    g = build_grid(spec)
    m = build_ising(g, spec.weights)
    res = qaoa_core.optimize_qaoa(n_nodes, m.couplings, m.offset, layers=2, steps=40)
    gam, bet = res.best_params[:2], res.best_params[2:]
    p = noise_pct / 100.0

    diag = qaoa_core.cost_diagonal(n_nodes, m.couplings, m.offset)
    rho = nz.qaoa_density_matrix(n_nodes, diag, gam, bet, depolarizing=p)
    exact = nz.density_expectation(rho, diag)
    del rho

    tr = nz.qaoa_trajectories(n_nodes, m.couplings, m.offset, gam, bet,
                              depolarizing=p, trajectories=n_traj, seed=seed + 1,
                              keep_probs=False)
    return exact, tr.running_mean, tr.running_stderr, nz.density_matrix_bytes(n_nodes), tr.memory_bytes


def trajectory_convergence_figure(n_nodes: int, seed: int, noise_pct: float,
                                  n_traj: int) -> go.Figure:
    exact, mean, err, _dm_bytes, _tr_bytes = _trajectory_data(n_nodes, seed, noise_pct, n_traj)
    xs = list(range(1, len(mean) + 1))
    hi = [m + (e if e == e else 0) for m, e in zip(mean, err, strict=True)]
    lo = [m - (e if e == e else 0) for m, e in zip(mean, err, strict=True)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs + xs[::-1], y=hi + lo[::-1], fill="toself",
                             fillcolor="rgba(0,200,255,.15)", line=dict(width=0),
                             name="uncertainty (±1 standard error)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=xs, y=mean, mode="lines", name="running average of the dice rolls",
                             line=dict(color=COLORS["accent"], width=2.4),
                             hovertemplate="after %{x} runs<br>estimate %{y:.4f}<extra></extra>"))
    fig.add_hline(y=exact, line=dict(color=COLORS["ok"], width=2.5, dash="dash"),
                  annotation_text="  the exact answer (density matrix)",
                  annotation_position="top right",
                  annotation_font=dict(color=COLORS["ok"], size=11))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["plot_bg"],
        font=dict(color=COLORS["text"], size=12), height=400,
        margin=dict(l=60, r=25, t=52, b=48),
        title=dict(text="Many cheap random runs, averaged, land on the expensive exact answer",
                   font=dict(size=13)),
        legend=dict(bgcolor="rgba(5,5,5,.85)", x=0.4, y=0.02, font=dict(size=10)))
    fig.update_xaxes(title="number of noisy runs averaged", gridcolor=COLORS["line"])
    fig.update_yaxes(title="estimated ⟨H⟩", gridcolor=COLORS["line"])
    return fig


def noise_memory_figure() -> go.Figure:
    """The two noise methods against the machine that has to hold them."""
    ns = list(range(8, 33))
    dm = [(2 ** (2 * n)) * 16 / 2**30 for n in ns]
    tr = [(2 ** n) * 16 / 2**30 for n in ns]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ns, y=dm, mode="lines", name="Density matrix (exact)",
                             line=dict(color=COLORS["crit"], width=3),
                             hovertemplate="%{x} qubits<br>%{y:,.3g} GB<extra></extra>"))
    fig.add_trace(go.Scatter(x=ns, y=tr, mode="lines", name="One trajectory (approximate)",
                             line=dict(color=COLORS["ok"], width=3),
                             hovertemplate="%{x} qubits<br>%{y:,.3g} GB<extra></extra>"))
    fig.add_hline(y=66, line=dict(color=COLORS["accent"], width=2, dash="dot"),
                  annotation_text="  what a 128 GB GB10 can actually use",
                  annotation_position="top left",
                  annotation_font=dict(color=COLORS["accent"], size=10))
    fig.add_vline(x=14, line=dict(color=COLORS["crit"], width=1.5, dash="dash"),
                  annotation_text="exact stops here", annotation_position="top",
                  annotation_font=dict(color=COLORS["crit"], size=10))
    fig.add_vline(x=30, line=dict(color=COLORS["ok"], width=1.5, dash="dash"),
                  annotation_text="trajectories reach here", annotation_position="top",
                  annotation_font=dict(color=COLORS["ok"], size=10))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["plot_bg"],
        font=dict(color=COLORS["text"], size=12), height=400,
        margin=dict(l=62, r=25, t=52, b=48),
        title=dict(text="Same noise, same machine, two ways of paying for it",
                   font=dict(size=13)),
        legend=dict(bgcolor="rgba(5,5,5,.85)", x=0.02, y=0.98, font=dict(size=11)))
    fig.update_xaxes(title="Qubits", gridcolor=COLORS["line"], dtick=2)
    fig.update_yaxes(title="Memory (GB, log scale)", type="log", gridcolor=COLORS["line"])
    return fig


# ── The page function is retired ─────────────────────────────────────────────
#
# This module was a standalone "Learn QAOA" tab until the six-tab structure was
# flattened. It said the same things as the quantum explainer in a second voice,
# with nothing telling a visitor which to read. The explainer won on discipline;
# these three figures won on teaching value, so they moved there and this file
# became the figure library it always should have been.
#
# Kept as importable functions: interference_figure, landscape_figure,
# tradeoff_figure, and their cached data loaders.
