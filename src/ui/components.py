"""Plotly instruments and HTML fragments for the Command Center.

Every figure here shares one palette (src.config.settings.COLORS) and one dark
template so the dashboard reads as a single instrument rather than a pile of
charts. Charts state units and say when a number is unverified — an operator
audience treats an unlabelled axis as a missing fact.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import plotly.graph_objects as go

from src.config.settings import COLORS, statevector_bytes

_CSS_PATH = Path(__file__).with_name("style.css")


def load_css() -> str:
    return f"<style>{_CSS_PATH.read_text()}</style>"


def _base_layout(fig: go.Figure, height: int = 460, **kw) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        font=dict(color=COLORS["text"], size=12),
        margin=dict(l=48, r=24, t=44, b=44),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        **kw,
    )
    fig.update_xaxes(gridcolor=COLORS["line"], zerolinecolor=COLORS["line"])
    fig.update_yaxes(gridcolor=COLORS["line"], zerolinecolor=COLORS["line"])
    return fig


# ── Header ───────────────────────────────────────────────────────────────────

def header_html(backend_label: str, backend_state: str, detail: str) -> str:
    cls = {"live": "live", "warn": "warn", "down": "down"}.get(backend_state, "warn")
    return f"""
<div class="gridops-header">
  <div>
    <div class="title">GRID <span class="accent">OPS</span></div>
    <div class="sub">Hybrid Quantum-Classical Contingency Optimization</div>
  </div>
  <div style="flex:1"></div>
  <div><span class="pill {cls}"><span class="dot"></span>{backend_label}</span>
       <div class="sub" style="margin-top:.4rem">{detail}</div></div>
  <div class="brand"><strong>DELL TECHNOLOGIES</strong><br>Federal / On-Premise<br>TAA-Compliant Infrastructure</div>
</div>"""


def metric_html(label: str, value: str, unit: str = "", note: str = "", kind: str = "") -> str:
    k = f" {kind}" if kind else ""
    u = f'<span class="unit">{unit}</span>' if unit else ""
    n = f'<div class="note">{note}</div>' if note else ""
    return (f'<div class="metric{k}"><div class="label">{label}</div>'
            f'<div class="value">{value}{u}</div>{n}</div>')


def card_html(title: str, body: str) -> str:
    return f'<div class="card"><h4>{title}</h4>{body}</div>'


# ── Tab 1 — topology ─────────────────────────────────────────────────────────

def topology_figure(g: nx.Graph, report=None) -> go.Figure:
    """Transmission network, coloured by island assignment once solved.

    Severed lines are drawn dashed and red on top of the intact network, so the
    islanding decision is legible at a glance instead of requiring the viewer to
    diff two colours of node.
    """
    assign = report.assignment if report is not None else None
    severed = {tuple(sorted((u, v))) for u, v, _ in (report.severed_lines if report else [])}

    intact_x, intact_y, cut_x, cut_y = [], [], [], []
    for u, v in g.edges():
        xs = [g.nodes[u]["x"], g.nodes[v]["x"], None]
        ys = [g.nodes[u]["y"], g.nodes[v]["y"], None]
        if tuple(sorted((u, v))) in severed:
            cut_x += xs; cut_y += ys
        else:
            intact_x += xs; intact_y += ys

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=intact_x, y=intact_y, mode="lines", name="Transmission line",
        line=dict(color=COLORS["line"], width=1.6), hoverinfo="skip",
    ))
    if cut_x:
        fig.add_trace(go.Scatter(
            x=cut_x, y=cut_y, mode="lines", name="Severed (islanding cut)",
            line=dict(color=COLORS["crit"], width=2.4, dash="dot"), hoverinfo="skip",
        ))

    xs = [g.nodes[i]["x"] for i in g.nodes()]
    ys = [g.nodes[i]["y"] for i in g.nodes()]
    if assign is None:
        colors = [COLORS["accent"] if g.nodes[i]["kind"] == "generation"
                  else COLORS["text_dim"] for i in g.nodes()]
        legend = "Substation / generation"
    else:
        colors = [COLORS["island_a"] if assign[i] == 0 else COLORS["island_b"] for i in g.nodes()]
        legend = "Microgrid island A / B"

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", name=legend,
        text=[str(i) for i in g.nodes()], textposition="middle center",
        textfont=dict(size=9, color="#04121a"),
        marker=dict(
            size=[26 if g.nodes[i]["kind"] == "generation" else 19 for i in g.nodes()],
            color=colors,
            symbol=["square" if g.nodes[i]["kind"] == "generation" else "circle" for i in g.nodes()],
            line=dict(color=COLORS["bg"], width=1.6),
        ),
        customdata=[[g.nodes[i]["name"], g.nodes[i]["generation_mw"],
                     g.nodes[i]["load_mw"], g.nodes[i]["net_mw"]] for i in g.nodes()],
        hovertemplate=("<b>%{customdata[0]}</b><br>Generation %{customdata[1]} MW"
                       "<br>Load %{customdata[2]} MW<br>Net %{customdata[3]} MW<extra></extra>"),
    ))

    _base_layout(fig, height=520, title="Transmission topology — squares are generation")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return fig


def convergence_figure(history: list[float], exact: float | None = None) -> go.Figure:
    """QAOA energy expectation per optimizer step (best-so-far)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=history, x=list(range(1, len(history) + 1)), mode="lines+markers",
        name="⟨H⟩ best-so-far", line=dict(color=COLORS["accent"], width=2.4),
        marker=dict(size=5, color=COLORS["accent"]),
    ))
    if exact is not None:
        fig.add_hline(
            y=exact, line=dict(color=COLORS["ok"], width=1.6, dash="dash"),
            annotation_text="exact ground state (brute force)",
            annotation_font_color=COLORS["ok"], annotation_position="bottom right",
        )
    _base_layout(fig, height=300, title="QAOA convergence — classical parameter optimization")
    fig.update_xaxes(title="Optimizer step")
    fig.update_yaxes(title="⟨H⟩  (cost expectation)")
    return fig


# ── Tab 2 — capability / scaling ─────────────────────────────────────────────

def scaling_figure(rows: list[dict], ceiling: int | None = None) -> go.Figure:
    """Time per energy evaluation vs problem size, with the memory ceiling.

    Deliberately NOT a speedup chart. The claim is capability — how large a
    problem this machine holds — so the y-axis is seconds and the annotation
    that matters is where the working set stops fitting.
    """
    ok = [r for r in rows if r.get("seconds")]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[r["n_qubits"] for r in ok],
        y=[r["seconds"] for r in ok],
        name="Time per energy evaluation",
        marker=dict(color=COLORS["accent"], line=dict(color=COLORS["accent_dim"], width=1)),
        customdata=[[r["statevector_bytes"] / 2**20] for r in ok],
        hovertemplate="%{x} qubits<br>%{y:.3f} s<br>statevector %{customdata[0]:.1f} MiB<extra></extra>",
    ))
    blocked = [r for r in rows if not r.get("seconds")]
    if blocked:
        fig.add_trace(go.Bar(
            x=[r["n_qubits"] for r in blocked],
            y=[0] * len(blocked), name="Exceeds available memory",
            marker=dict(color=COLORS["crit"]),
        ))
    if ceiling:
        fig.add_vline(
            x=ceiling + 0.5, line=dict(color=COLORS["warn"], width=1.6, dash="dash"),
            annotation_text=f"live ceiling {ceiling} qubits",
            annotation_font_color=COLORS["warn"],
        )
    _base_layout(fig, height=380, title="Simulation capability — time per energy evaluation")
    fig.update_xaxes(title="Substation nodes (qubits)")
    fig.update_yaxes(title="Seconds", type="log")
    return fig


def memory_figure(max_n: int = 34, ceiling_bytes: int = 0) -> go.Figure:
    """Statevector memory vs qubit count — the exponential wall, drawn."""
    ns = list(range(10, max_n + 1))
    gb = [statevector_bytes(n) / 2**30 for n in ns]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ns, y=gb, mode="lines+markers", name="Statevector (complex128)",
        line=dict(color=COLORS["accent"], width=2.4), marker=dict(size=5),
    ))
    if ceiling_bytes:
        fig.add_hline(
            y=ceiling_bytes / 2**30, line=dict(color=COLORS["ok"], width=1.6, dash="dash"),
            annotation_text=f"GB10 available now: {ceiling_bytes / 2**30:.0f} GiB",
            annotation_font_color=COLORS["ok"],
        )
    _base_layout(fig, height=340, title="Why memory is the binding constraint")
    fig.update_xaxes(title="Qubits")
    fig.update_yaxes(title="GiB", type="log")
    return fig


# ── Tab 3 — under the hood ───────────────────────────────────────────────────

def circuit_ascii(n_qubits: int, layers: int, n_couplings: int, show: int = 8) -> str:
    """ASCII sketch of the QAOA ansatz actually being simulated."""
    shown = min(show, n_qubits)
    lines = [
        f"QAOA ansatz   n={n_qubits} qubits   p={layers} layers   "
        f"{n_couplings} ZZ couplings/layer   {layers * n_couplings} RZZ total",
        "",
    ]
    for q in range(shown):
        seg = "".join(f"─[RZZ]──[RX({chr(946)}{l+1})]─" for l in range(layers))
        lines.append(f"q{q:<2}|0⟩ ──[H]──{seg}─── M")
    if n_qubits > shown:
        lines.append(f"      ⋮   ({n_qubits - shown} further qubits omitted)")
    lines += [
        "",
        f"  [H]     Hadamard — prepare uniform superposition over 2^{n_qubits} "
        f"= {2**n_qubits:,} grid partitions",
        f"  [RZZ]   Cost unitary exp(-i{chr(947)}H_C) — one rotation per coupling J_ij",
        f"  [RX]    Mixer unitary exp(-i{chr(946)}{chr(931)}X_i) — drives transitions between partitions",
        "  M       Measure — the bitstring IS the island assignment",
    ]
    return "\n".join(lines)


def probability_figure(top_states: list, n_qubits: int, k: int = 12) -> go.Figure:
    """Most probable measurement outcomes vs the uniform baseline.

    The uniform line is the whole point: it shows the circuit has concentrated
    amplitude on good partitions rather than returning noise.
    """
    items = []
    for s in top_states[:k]:
        if isinstance(s, (list, tuple)):
            items.append((s[0], float(s[1])))
        else:
            items.append((s["bitstring"], float(s["probability"])))

    uniform = 1.0 / (1 << n_qubits)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[b for b, _ in items], y=[p for _, p in items],
        marker=dict(color=COLORS["accent"]), name="P(outcome)",
        hovertemplate="%{x}<br>P = %{y:.5f}<extra></extra>",
    ))
    fig.add_hline(
        y=uniform, line=dict(color=COLORS["warn"], width=1.6, dash="dash"),
        annotation_text=f"uniform baseline 1/2^{n_qubits}",
        annotation_font_color=COLORS["warn"],
    )
    _base_layout(fig, height=360, title="Measurement distribution — amplitude concentration")
    fig.update_xaxes(title="Partition bitstring", tickangle=-60)
    fig.update_yaxes(title="Probability")
    return fig


# ── Export ───────────────────────────────────────────────────────────────────

def partition_report_json(run) -> str:
    """The islanding schedule, as an auditable operator artifact."""
    g, r = run.graph, run.report
    doc = {
        "schema": "gridops.islanding-schedule/v1",
        "problem": {
            "substations": g.number_of_nodes(),
            "transmission_lines": g.number_of_edges(),
            "qubits": run.model.n_qubits,
            "zz_couplings": run.model.n_terms,
            "search_space": 2 ** run.model.n_qubits,
        },
        "execution": {
            "backend": run.result.get("backend"),
            "device": run.result.get("device"),
            "layers": run.result.get("layers"),
            "optimizer_steps": run.result.get("steps_run"),
            "seconds": round(run.result.get("seconds", 0.0), 4),
            "statevector_bytes": run.result.get("statevector_bytes"),
            "notes": run.result.get("notes", []),
        },
        "solution": {
            "bitstring": r.bitstring,
            "energy_of_solution": r.energy,
            "expectation_H": run.result.get("best_energy"),
            "feasible": r.feasible,
            "feasibility_notes": r.notes,
            "interrupted_mw": r.interrupted_mw,
            "severed_lines": [
                {"from": u, "to": v, "flow_mw": f} for u, v, f in r.severed_lines
            ],
            "island_a": {
                "nodes": [g.nodes[i]["name"] for i in r.island_a],
                "net_mw": r.imbalance_a_mw,
            },
            "island_b": {
                "nodes": [g.nodes[i]["name"] for i in r.island_b],
                "net_mw": r.imbalance_b_mw,
            },
        },
        "verification": {
            "exact_optimum_computed": run.exact is not None,
            "matches_exact_optimum": run.is_optimal,
            "solution_ratio": run.solution_ratio,
            "expectation_ratio": run.expectation_ratio,
            "concentration_vs_uniform": run.concentration,
        },
        "warnings": run.warnings,
    }
    return json.dumps(doc, indent=2)
