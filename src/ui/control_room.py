"""The control-room view — a one-line diagram that behaves like an EMS display.

Built to the conventions a transmission operator already reads, so the picture
carries meaning before anyone explains it:

  * **Voltage class sets colour and thickness.** 345 kV is light blue and heavy,
    115 kV is thin and grey — the standard EMS scheme. You can see the backbone.
  * **Loading sets the alarm colour.** Green below 80%, amber to 95%, orange to
    100%, hot pink past it. A red line is not "a line that broke", it is a line
    carrying more than it is rated for, which is how cascades start.
  * **Arrows show where the power is going**, sized and spaced by MW. Power
    moving is the thing a static graph never conveys.
  * **A faulted line and an opened breaker look nothing alike.** One is damage,
    one is the plan.

Every number rendered here comes from the DC power flow in `power_flow.py`.
Nothing on this screen is decorative.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import networkx as nx
import plotly.graph_objects as go

from src.config.settings import COLORS
from src.simulation import power_flow as pf

# Substations are drawn as breaker-and-a-half style boxes: generation is a
# square (a "source"), load buses are circles. Matches one-line convention.
GEN_SYMBOL, LOAD_SYMBOL = "square", "circle"


def _arrow_points(x0, y0, x1, y1, n_arrows, offset=0.0):
    """Evenly spaced points along a segment, with the segment's bearing."""
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    pts = []
    for k in range(n_arrows):
        t = (k + 0.5) / n_arrows
        pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, ang))
    return pts


def one_line_diagram(
    g: nx.Graph,
    sol: pf.FlowSolution,
    report=None,
    opened: set[tuple[int, int]] | None = None,
    title: str = "",
    height: int = 820,
) -> go.Figure:
    """Render the network in its solved state."""
    opened = opened or set()
    assign = report.assignment if report is not None else None
    fig = go.Figure()

    # ── Lines, grouped by state so the legend stays readable ────────────────
    # Iterate highest voltage first so the legend reads as a monotonic ladder
    # (345 / 230 / 138 / 115). Insertion order otherwise follows the edge list,
    # which produced "115 / 230 / 138 / 345" — a voltage ladder out of order.
    seen_kv: set[int] = set()
    ordered_edges = sorted(g.edges(), key=lambda e: -g.edges[e].get("kv", 0))
    for u, v in ordered_edges:
        e = g.edges[u, v]
        x0, y0 = g.nodes[u]["x"], g.nodes[u]["y"]
        x1, y1 = g.nodes[v]["x"], g.nodes[v]["y"]
        key = tuple(sorted((int(u), int(v))))
        kv = e.get("kv", 115)
        rating = e.get("rating_mva", 100.0)

        faulted = e.get("faulted")
        is_open = key in opened
        flow = sol.flows.get((int(u), int(v)), sol.flows.get((int(v), int(u)), 0.0))
        if (int(u), int(v)) not in sol.flows and (int(v), int(u)) in sol.flows:
            flow = -sol.flows[(int(v), int(u))]
        loading = sol.loading.get((int(u), int(v)), sol.loading.get((int(v), int(u)), 0.0))

        hover = (f"<b>{g.nodes[u]['name']} ↔ {g.nodes[v]['name']}</b><br>"
                 f"{kv} kV · rated {rating:.0f} MVA<br>")

        if faulted:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color=COLORS["crit"], width=e.get("kv_width", 2) + 2.4),
                name="⚡ FAULTED", legendgroup="fault",
                showlegend="fault" not in seen_kv, hoverinfo="text",
                text=hover + "<b>FAULTED — line out of service</b>"))
            seen_kv.add("fault")
            # Break marker at the midpoint: unmistakable, reads at a distance.
            fig.add_trace(go.Scatter(
                x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], mode="markers",
                marker=dict(symbol="x-thin", size=17,
                            line=dict(color=COLORS["crit"], width=3.5)),
                showlegend=False, hoverinfo="skip"))
            continue

        if is_open:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color=COLORS["warn"], width=2.0, dash="dot"),
                name="Breaker opened (islanding plan)", legendgroup="open",
                showlegend="open" not in seen_kv, hoverinfo="text",
                text=hover + "<b>BREAKER OPEN — islanding plan</b>"))
            seen_kv.add("open")
            fig.add_trace(go.Scatter(
                x=[(x0 + x1) / 2], y=[(y0 + y1) / 2], mode="markers",
                marker=dict(symbol="square-open", size=11,
                            line=dict(color=COLORS["warn"], width=2.4)),
                showlegend=False, hoverinfo="skip"))
            continue

        band_color, band_label = pf.loading_band(loading)
        # Base conductor drawn in its voltage colour; the loading colour rides on
        # top as a thinner core, so BOTH facts are visible at once.
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines",
            line=dict(color=e.get("kv_color", "#8a99ad"), width=e.get("kv_width", 2)),
            name=f"{kv} kV", legendgroup=f"kv{kv}", showlegend=kv not in seen_kv,
            hoverinfo="text",
            text=(hover + f"Flow <b>{abs(flow):.1f} MW</b><br>"
                          f"Loading <b>{loading * 100:.0f}%</b> · {band_label}")))
        seen_kv.add(kv)

        if loading >= 0.80:
            # The loading colour rides ON TOP of the voltage-class conductor as a
            # thinner core, so both facts stay visible. Capped at half the base
            # width with no absolute floor: a 1.6 floor covered ~90% of a 115 kV
            # line, so hot thin lines read as alarm-coloured only and lost their
            # voltage class.
            #
            # Past 100% the line is also DASHED and widened. Pattern is the
            # standard colour-independent alarm channel — green-vs-red is the
            # classic protanopia collision, and this diagram is the surface most
            # likely to be projected in a room.
            over = loading >= 1.0
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color=band_color,
                          width=e.get("kv_width", 2) * (0.75 if over else 0.5),
                          dash="dash" if over else "solid"),
                showlegend=False, hoverinfo="skip"))

        # ── Flow arrows: count and size track MW ────────────────────────────
        if abs(flow) > 0.5:
            n_arrows = 1 if loading < 0.35 else (2 if loading < 0.75 else 3)
            ang = 0.0
            for ax, ay, ang in _arrow_points(x0, y0, x1, y1, n_arrows):
                fig.add_trace(go.Scatter(
                    x=[ax], y=[ay], mode="markers",
                    marker=dict(
                        symbol="arrow", size=8 + min(9, abs(flow) / 14.0),
                        # Plotly marker.angle is CLOCKWISE from screen-up, so a
                        # data-space bearing θ (counter-clockwise from east, y up)
                        # renders correctly at 90−θ, not θ−90 — the latter mirrors
                        # every arrow east–west.
                        angle=(90 - ang) if flow >= 0 else (270 - ang),
                        color=band_color if loading >= 0.80 else e.get("kv_color", "#8a99ad"),
                        line=dict(color=COLORS["bg"], width=0.6)),
                    showlegend=False, hoverinfo="text",
                    text=f"{abs(flow):.1f} MW → {loading * 100:.0f}% of rating"))

    # ── Substations ─────────────────────────────────────────────────────────
    de_energised = {n for st in sol.island_state if not st["energised"] for n in st["nodes"]}

    xs, ys, sizes, colors, symbols, texts, labels, lines = [], [], [], [], [], [], [], []
    label_colors: list[str] = []
    for i in g.nodes():
        nd = g.nodes[i]
        is_gen = nd["kind"] == "generation"
        xs.append(nd["x"])
        ys.append(nd["y"])
        sizes.append(26 + (nd["generation_mw"] / 11 if is_gen else nd["load_mw"] / 3))
        symbols.append(GEN_SYMBOL if is_gen else LOAD_SYMBOL)

        if i in de_energised:
            colors.append("#3a3f4b")           # dark = de-energised, lights out
        elif assign is not None:
            colors.append(COLORS["island_a"] if assign[i] == 0 else COLORS["island_b"])
        else:
            colors.append(COLORS["accent"] if is_gen else COLORS["text_dim"])

        lines.append(COLORS["crit"] if i in de_energised else COLORS["bg"])
        labels.append(str(i))
        # Label colour follows the fill: dark text on the bright island colours,
        # light text on the dark de-energised fill. A single near-black label
        # colour was ~1.6:1 against #3a3f4b — unreadable precisely on the nodes
        # whose whole point is that their lights are out.
        label_colors.append("#e6edf7" if i in de_energised else "#04121a")
        texts.append(
            f"<b>{nd['name']}</b> · {nd.get('kv', 115)} kV<br>"
            f"Generation {nd['generation_mw']:.1f} MW<br>"
            f"Load {nd['load_mw']:.1f} MW<br>"
            f"Net {nd['net_mw']:+.1f} MW"
            + ("<br><b>DE-ENERGISED</b>" if i in de_energised else ""))

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=labels, textposition="middle center",
        textfont=dict(size=11, color=label_colors),
        marker=dict(size=sizes, color=colors, symbol=symbols,
                    line=dict(color=lines, width=1.8)),
        name="Substation", customdata=texts,
        hovertemplate="%{customdata}<extra></extra>"))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["plot_bg"], font=dict(color=COLORS["text"], size=11),
        margin=dict(l=10, r=10, t=38 if title else 10, b=10), height=height,
        title=dict(text=title, font=dict(size=13)) if title else None,
        legend=dict(bgcolor="rgba(5,5,5,.75)", bordercolor=COLORS["border"],
                    borderwidth=1, font=dict(size=10), orientation="v",
                    x=1.0, xanchor="right", y=1.0),
        showlegend=True)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return fig


def loading_key(sol: pf.FlowSolution | None = None) -> str:
    """Key strip for the loading bands, generated from LOAD_BANDS itself.

    These colours are the diagram's primary operational signal and were
    previously explained nowhere on screen — an operator knows the convention,
    a programme manager does not, and the narration only says "running hot".

    Built from the band table so the key can never drift from the rendering.
    Shows a live count per band when a solution is supplied.
    """
    counts: dict[str, int] = {}
    if sol is not None:
        for ld in sol.loading.values():
            counts[pf.loading_band(ld)[1]] = counts.get(pf.loading_band(ld)[1], 0) + 1

    lo = 0.0
    cells = []
    for limit, color, label in pf.LOAD_BANDS:
        if limit == float("inf"):
            rng = f"&ge; {lo * 100:.0f}%"
        elif lo == 0.0:
            rng = f"&lt; {limit * 100:.0f}%"
        else:
            rng = f"{lo * 100:.0f}–{limit * 100:.0f}%"
        n = counts.get(label)
        tally = f'<span class="ct">{n}</span>' if n else ""
        dash = ' style="border-bottom:2px dashed ' + color + ';background:none;height:0"' \
            if label == "OVERLOAD" else f' style="background:{color}"'
        cells.append(f'<div class="lk"><span class="sw"{dash}></span>'
                     f'<span class="rg">{rng}</span>'
                     f'<span class="lb" style="color:{color}">{label}</span>{tally}</div>')
        lo = limit
    return ('<div class="loadkey"><span class="hdr">Line loading, % of rating</span>'
            + "".join(cells) + '</div>')


# ── Instruments ──────────────────────────────────────────────────────────────

def instrument_strip(sol: pf.FlowSolution, risk: dict, label: str) -> str:
    """The numbers an operator's eye goes to first."""
    f = sol.frequency_hz
    dev = f - pf.NOMINAL_HZ
    # Real operating band is tight: ±0.05 Hz is routine, ±0.2 Hz is an event.
    f_kind = "ok" if abs(dev) < 0.05 else ("warn" if abs(dev) < 0.2 else "crit")
    if sol.blackout:
        f_kind = "crit"

    worst = sol.worst_loading * 100
    w_kind = "ok" if worst < 80 else ("warn" if worst < 100 else "crit")
    shed_kind = "ok" if sol.shed_mw <= 0.05 else "crit"
    risk_kind = {"secure": "ok", "elevated": "warn", "cascade": "crit"}.get(risk["level"], "")

    def cell(lbl, val, unit, note, kind):
        k = f" {kind}" if kind else ""
        return (f'<div class="metric{k}"><div class="label">{lbl}</div>'
                f'<div class="value">{val}<span class="unit">{unit}</span></div>'
                f'<div class="note">{note}</div></div>')

    return (
        '<div class="instrument-row">'
        + cell("System frequency", f"{f:.2f}" if f else "—", " Hz",
               f"{dev:+.3f} Hz from nominal" if f else "SYSTEM BLACK", f_kind)
        + cell("Load served", f"{sol.served_mw:,.0f}", " MW",
               f"of {sol.total_load_mw:,.0f} MW demand · {sol.served_fraction * 100:.1f}%",
               "ok" if sol.served_fraction > 0.999 else "warn")
        + cell("Load shed", f"{sol.shed_mw:,.0f}", " MW",
               "none" if sol.shed_mw <= 0.05 else "customers off supply", shed_kind)
        + cell("Highest line loading", f"{worst:.0f}", " %",
               f"{len(sol.overloads)} line(s) beyond rating", w_kind)
        + cell("Islands", f"{len(sol.islands)}", "",
               " · ".join(f"{len(s['nodes'])}n @ {s['frequency_hz']:.2f}Hz"
                          for s in sol.island_state[:3]) or "one system", "")
        + cell("Security", risk["level"].upper(), "", label, risk_kind)
        + "</div>")


# ── Alarm / event log ────────────────────────────────────────────────────────

def build_events(run, t0: datetime | None = None) -> list[dict]:
    """A SCADA-style event feed for the contingency and the response.

    Timestamps are synthesised for presentation — the ordering and the content
    are real, derived from the solved states. Labelled as such in the UI.
    """
    t0 = t0 or datetime(2026, 7, 30, 14, 32, 8)
    g = run.graph
    ev: list[dict] = []

    def add(dt_ms, sev, src, msg):
        ev.append({"t": (t0 + timedelta(milliseconds=dt_ms)).strftime("%H:%M:%S.%f")[:-3],
                   "sev": sev, "src": src, "msg": msg})

    intact, post, isl = run.flow_intact, run.flow_post_fault, run.flow_islanded
    add(0, "info", "SCADA", f"System normal · {intact.total_load_mw:,.0f} MW load · "
                            f"{intact.frequency_hz:.2f} Hz · peak line {intact.worst_loading*100:.0f}%")

    for u, v, mw in run.fault:
        kv = g.edges[u, v].get("kv", 115)
        add(1200, "crit", "PROT",
            f"LINE TRIP — {g.nodes[u]['name']} ↔ {g.nodes[v]['name']} "
            f"({kv} kV, was carrying {mw:.0f} MW)")
        add(1260, "crit", "PROT", "Breaker operation confirmed both terminals")

    if post:
        add(1800, "warn", "STATE", f"Flow redistributed · peak line loading now "
                                   f"{post.worst_loading*100:.0f}%")
        for u, v, ld in post.overloads[:4]:
            add(1900, "crit", "ALARM",
                f"OVERLOAD {g.nodes[u]['name']}↔{g.nodes[v]['name']} at {ld*100:.0f}% "
                f"of {g.edges[u,v]['rating_mva']:.0f} MVA rating")
        r = pf.cascade_risk(post)
        if r["level"] != "secure":
            add(2000, "crit", "RAS", r["note"])

    n = run.model.n_qubits
    add(2400, "info", "QAOA", f"Islanding search dispatched — {2**n:,} candidate "
                              f"partitions · {run.backend.label}")
    add(2400 + int(run.result.get("seconds", 0) * 1000), "info", "QAOA",
        f"Solution returned in {run.result.get('seconds', 0):.2f} s · "
        f"{run.result.get('steps_run')} optimizer steps")

    sel = run.result.get("selection") or {}
    if sel:
        add(2500, "info", "QAOA",
            f"{sel.get('candidates_screened', 0)} candidate plans screened by DC power flow; "
            f"{'argmax retained' if sel.get('chosen_was_argmax') else 'a lower-probability plan was electrically superior'}")

    for u, v, mw in run.report.severed_lines:
        add(2700, "warn", "CTRL",
            f"OPEN BREAKER {g.nodes[u]['name']} ↔ {g.nodes[v]['name']} ({mw:.0f} MW)")

    if isl:
        for s in isl.island_state:
            add(3000, "info" if s["shed_mw"] <= 0.05 else "warn", "ISL",
                f"Island formed · {len(s['nodes'])} substations · "
                f"{s['generation_mw']:.0f} MW gen / {s['load_mw']:.0f} MW load · "
                f"{s['frequency_hz']:.2f} Hz"
                + (f" · {s['shed_mw']:.0f} MW SHED" if s["shed_mw"] > 0.05 else ""))
        r2 = pf.cascade_risk(isl)
        add(3200, {"secure": "ok", "elevated": "warn", "cascade": "crit"}[r2["level"]],
            "STATE", f"Post-islanding security: {r2['level'].upper()} · "
                     f"peak line {isl.worst_loading*100:.0f}% · {r2['overloads']} overload(s)")
    return ev


def alarm_log(events: list[dict], limit: int = 22) -> str:
    rows = "".join(
        f'<div class="alarm {e["sev"]}"><span class="ts">{e["t"]}</span>'
        f'<span class="src">{e["src"]}</span><span class="msg">{e["msg"]}</span></div>'
        for e in events[:limit])
    return f'<div class="alarmlog">{rows}</div>'


# ── Animation ────────────────────────────────────────────────────────────────

def _line_arrow_track(g, sol, opened, n_steps: int, per_line: int = 3):
    """Precompute arrow positions for every animation step.

    Arrows march along each line in the direction power is flowing, at a speed
    proportional to loading — so a heavily loaded corridor visibly runs faster
    than a lightly loaded one. All arrows live in ONE trace per frame so the
    animation updates a couple of arrays rather than hundreds of traces.
    """
    segs = []
    for u, v in g.edges():
        e = g.edges[u, v]
        key = tuple(sorted((int(u), int(v))))
        if e.get("faulted") or key in opened:
            continue
        f = sol.flows.get((int(u), int(v)))
        if f is None:
            f = -sol.flows.get((int(v), int(u)), 0.0)
        if abs(f) < 0.5:
            continue
        loading = sol.loading.get((int(u), int(v)),
                                  sol.loading.get((int(v), int(u)), 0.0))
        x0, y0 = g.nodes[u]["x"], g.nodes[u]["y"]
        x1, y1 = g.nodes[v]["x"], g.nodes[v]["y"]
        if f < 0:                      # draw in the direction power actually goes
            x0, y0, x1, y1 = x1, y1, x0, y0
        # 90−θ, not θ−90: marker.angle is clockwise from screen-up (see
        # one_line_diagram). θ−90 mirrors the arrowheads east–west, so they
        # point against their own direction of travel on horizontal lines.
        ang = 90 - math.degrees(math.atan2(y1 - y0, x1 - x0))
        color, _ = pf.loading_band(loading)
        if loading < 0.80:
            color = e.get("kv_color", "#8a99ad")
        # Faster march when the line is working harder.
        speed = 0.6 + min(2.2, loading * 1.9)
        segs.append((x0, y0, x1, y1, ang, color, 8 + min(9, abs(f) / 14.0), speed))

    frames_xy = []
    for k in range(n_steps):
        xs, ys, angs, cols, sizes = [], [], [], [], []
        for x0, y0, x1, y1, ang, color, size, speed in segs:
            base = (k * speed / n_steps) % 1.0
            for a in range(per_line):
                t = (base + a / per_line) % 1.0
                xs.append(x0 + (x1 - x0) * t)
                ys.append(y0 + (y1 - y0) * t)
                angs.append(ang)
                cols.append(color)
                sizes.append(size)
        frames_xy.append((xs, ys, angs, cols, sizes))
    return frames_xy


def animate(fig, g, sol, opened=None, n_steps: int = 24, duration: int = 90):
    """Add marching power-flow arrows to an existing one-line diagram.

    The static figure already carries the arrows; this replaces them with an
    animated trace and attaches Plotly frames plus a play control. A grid that
    moves reads as *operating* rather than as a diagram of a grid.
    """
    opened = opened or set()
    track = _line_arrow_track(g, sol, opened, n_steps)
    if not track or not track[0][0]:
        return fig

    # Drop the static arrow markers; the animated trace supersedes them.
    keep = [tr for tr in fig.data
            if not (tr.mode == "markers" and getattr(tr.marker, "symbol", None) == "arrow")]
    fig.data = tuple(keep)

    xs, ys, angs, cols, sizes = track[0]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", name="power flow",
        marker=dict(symbol="arrow", size=sizes, angle=angs, color=cols,
                    line=dict(color=COLORS["bg"], width=0.6)),
        showlegend=False, hoverinfo="skip"))
    flow_idx = len(fig.data) - 1

    fig.frames = [
        go.Frame(name=str(k),
                 data=[go.Scatter(x=x, y=y,
                                  marker=dict(symbol="arrow", size=s, angle=a, color=c,
                                              line=dict(color=COLORS["bg"], width=0.6)))],
                 traces=[flow_idx])
        for k, (x, y, a, c, s) in enumerate(track)]

    # No play button. The frames are PRECOMPUTED -- animating costs the browser a
    # couple of array swaps per frame and costs the server nothing at all, so
    # making an operator press start to see a grid that is already running was
    # only ever a Plotly default we failed to override. render_animated() starts
    # it automatically and loops it.
    fig._gridops_frame_ms = duration
    return fig


def render_animated(fig, height: int = 840, key: str = "flow") -> None:
    """Render a figure whose animation starts on load and loops forever.

    Streamlit's st.plotly_chart cannot autostart a Plotly animation, so this
    emits the figure as standalone HTML in a component iframe with
    auto_play=True and a loop handler.

    plotly.js is referenced from /app/static/ -- our own copy, served by this
    container. Inlining it instead would add ~4.6 MB to every render; pulling it
    from a CDN would be light but would break air-gapped, which is precisely the
    deployment this demo argues for.
    """
    import streamlit as st

    # WCAG 2.2.2 wants a way to stop auto-moving content that runs beyond five
    # seconds, and this loops indefinitely. It is also plain demo hygiene:
    # presenters freeze a screen while they talk over it.
    frozen = st.toggle("Freeze diagram", value=False, key=f"freeze_{key}",
                       help="Stop the power-flow animation. The diagram and every "
                            "number stay exactly as they are.")
    if frozen:
        st.plotly_chart(fig, width="stretch",
                        config={"displayModeBar": False})
        return

    ms = getattr(fig, "_gridops_frame_ms", 90)
    html = fig.to_html(
        include_plotlyjs="/app/static/plotly.min.js",
        full_html=False, auto_play=True, div_id=f"gridops-{key}",
        config={"displayModeBar": False, "responsive": True})

    # Restart on completion. Plotly emits plotly_animated when a run finishes.
    loop = f"""
<script>
(function() {{
  var tries = 0;
  function arm() {{
    var el = document.getElementById("gridops-{key}");
    if (!el || !el.on) {{ if (tries++ < 80) setTimeout(arm, 100); return; }}
    el.on("plotly_animated", function() {{
      Plotly.animate(el, null, {{
        frame: {{duration: {ms}, redraw: true}},
        transition: {{duration: 0}},
        mode: "immediate"
      }});
    }});
  }}
  arm();
}})();
</script>"""
    # st.iframe, not st.components.v1.html -- the latter's removal date
    # (2026-06-01) has already passed.
    st.iframe(f'<div style="background:{COLORS["surface"]};margin:0">{html}{loop}</div>',
              height=height)
