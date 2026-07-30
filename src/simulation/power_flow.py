"""DC power flow, line ratings, and system state — the operator-facing physics.

Everything the control-room view displays is COMPUTED here, not decorated in.
When a line trips, flow genuinely redistributes onto the remaining network, some
lines genuinely exceed their ratings, and island frequency genuinely sags in
proportion to the generation deficit. The drama on screen is physics.

── What model this is, and what it is not ───────────────────────────────────
This is a **DC power flow**: the standard linearised approximation used for
contingency screening across the industry. It assumes flat voltage (1.0 pu),
lossless lines, and small angle differences, which reduces the power flow to a
linear system:

    B·θ = P          flow_ij = (θ_i − θ_j) / x_ij

It is NOT a full AC solution — no reactive power, no voltage collapse, no
transient stability. For "where does the power go when this line opens", which
is exactly what an islanding demo needs, DC power flow is the right tool and is
what planners actually use for N-1 screening. Anything derived from a rougher
heuristic than this (frequency, cascade propagation) is labelled as such at the
point it is computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np

# ── Voltage classes ──────────────────────────────────────────────────────────
# Real transmission colour convention: higher voltage = lighter/cooler + thicker.
# (345 kV light blue, 115 kV grey is the widely used EMS scheme.)
# `min_mva` is the floor a line of that class can be built to. Conductor size
# follows voltage class in the real world -- you do not string a 345 kV corridor
# on a 25 MVA conductor. Without these floors, a lightly-loaded line got a rating
# proportional to its small base flow, and post-contingency power landing on it
# produced absurd 369% loadings that said more about the rating model than the
# contingency.
VOLTAGE_CLASSES = [
    {"kv": 345, "color": "#7fd4ff", "width": 4.2, "label": "345 kV", "min_mva": 320.0},
    {"kv": 230, "color": "#4aa8d8", "width": 3.2, "label": "230 kV", "min_mva": 180.0},
    {"kv": 138, "color": "#6b8fae", "width": 2.4, "label": "138 kV", "min_mva": 95.0},
    {"kv": 115, "color": "#8a99ad", "width": 1.8, "label": "115 kV", "min_mva": 70.0},
]
KV_MIN_MVA = {c["kv"]: c["min_mva"] for c in VOLTAGE_CLASSES}

# Loading thresholds against the line's normal rating. These mirror typical
# operator alarm bands: watch at 80%, alarm at 95%, emergency past 100%.
LOAD_BANDS = [
    (0.80, "#3ddc97", "normal"),
    (0.95, "#ffc857", "watch"),
    (1.00, "#ff9f1c", "alarm"),
    (float("inf"), "#ff2d55", "OVERLOAD"),
]

NOMINAL_HZ = 60.0


def loading_band(loading: float) -> tuple[str, str]:
    """(colour, label) for a per-unit loading value."""
    for limit, color, label in LOAD_BANDS:
        if loading < limit:
            return color, label
    return LOAD_BANDS[-1][1], LOAD_BANDS[-1][2]


# ── Electrical properties ────────────────────────────────────────────────────

def assign_electrical_properties(g: nx.Graph) -> nx.Graph:
    """Give every line a voltage class, reactance, and MVA rating.

    Voltage class follows importance: the backbone (highest-flow, best-connected
    corridors) is built at higher voltage, exactly as a real network is planned.
    Reactance scales with geographic length taken from the layout, so electrically
    long paths really do carry less flow — that is what makes redistribution after
    an outage look like a grid instead of a random reshuffle.
    """
    if g.graph.get("_electrical"):
        return g

    flows = {(u, v): g.edges[u, v]["flow_mw"] for u, v in g.edges()}
    if not flows:
        return g
    ranked = sorted(flows.items(), key=lambda kv: -kv[1])
    n_edges = len(ranked)

    for rank, ((u, v), mw) in enumerate(ranked):
        frac = rank / max(1, n_edges - 1)
        if frac < 0.20:
            cls = VOLTAGE_CLASSES[0]
        elif frac < 0.45:
            cls = VOLTAGE_CLASSES[1]
        elif frac < 0.75:
            cls = VOLTAGE_CLASSES[2]
        else:
            cls = VOLTAGE_CLASSES[3]

        dx = g.nodes[u]["x"] - g.nodes[v]["x"]
        dy = g.nodes[u]["y"] - g.nodes[v]["y"]
        length = float(np.hypot(dx, dy)) or 0.05

        e = g.edges[u, v]
        e["kv"] = cls["kv"]
        e["kv_color"] = cls["color"]
        e["kv_width"] = cls["width"]
        # Higher voltage lines are electrically "stronger" (lower reactance per
        # unit length) — the reason bulk power rides the 345 kV backbone.
        e["reactance"] = length * (345.0 / cls["kv"]) ** 1.6 * 0.10
        # Provisional only — calibrate_ratings() replaces this with a rating
        # sized against the ACTUAL solved base-case flow. See that function for
        # why the synthetic flow_mw attribute is the wrong basis.
        e["rating_mva"] = round(max(45.0, mw * 1.55), 0)
        e.setdefault("faulted", False)

    # Substation nomenclature follows the highest voltage it terminates.
    for i in g.nodes():
        kvs = [g.edges[i, j]["kv"] for j in g.neighbors(i)]
        g.nodes[i]["kv"] = max(kvs) if kvs else 115

    g.graph["_electrical"] = True
    return g


def calibrate_ratings(g: nx.Graph, headroom: float = 1.7) -> nx.Graph:
    """Size every line's rating against its ACTUAL intact-network flow.

    Transmission is built for the load it normally carries plus a contingency
    margin — so a line's rating must derive from the flow the network really
    puts on it, which only a power-flow solve knows.

    The first version of this sized ratings from the generator's synthetic
    `flow_mw` attribute, a number unrelated to the solved DC flows. The result
    was an intact grid already sitting at 80% loading with no contingency at all,
    so every fault produced instant absurd overloads (174%, then 257% after
    islanding). The physics was right; the ratings were fiction.

    `headroom` 1.7 puts the intact case near 59% loading — comfortably green,
    with genuine room before the alarm bands, so an overload on screen means
    something happened rather than that the model was born broken.
    """
    g = assign_electrical_properties(g)
    if g.graph.get("_rated"):
        return g

    base = solve(g, _skip_calibration=True)
    for u, v in g.edges():
        key = (int(u), int(v))
        mw = abs(base.flows.get(key, base.flows.get((key[1], key[0]), 0.0)))
        floor = KV_MIN_MVA.get(g.edges[u, v]["kv"], 70.0)
        g.edges[u, v]["rating_mva"] = round(max(floor, mw * headroom), 0)
        g.edges[u, v]["base_flow_mw"] = round(mw, 1)

    g.graph["_rated"] = True
    return g


# ── DC power flow ────────────────────────────────────────────────────────────

@dataclass
class FlowSolution:
    """Solved network state for one configuration (intact, faulted, or islanded)."""

    flows: dict[tuple[int, int], float] = field(default_factory=dict)   # signed MW, u→v
    loading: dict[tuple[int, int], float] = field(default_factory=dict)  # per-unit of rating
    islands: list[list[int]] = field(default_factory=list)
    island_state: list[dict] = field(default_factory=list)
    served_mw: float = 0.0
    shed_mw: float = 0.0
    total_load_mw: float = 0.0
    frequency_hz: float = NOMINAL_HZ
    overloads: list[tuple[int, int, float]] = field(default_factory=list)
    blackout: bool = False

    @property
    def worst_loading(self) -> float:
        return max(self.loading.values(), default=0.0)

    @property
    def served_fraction(self) -> float:
        return self.served_mw / self.total_load_mw if self.total_load_mw else 1.0


def _open_edges(g: nx.Graph, extra_open: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """Lines actually in service: not faulted and not opened by the plan."""
    out = []
    for u, v in g.edges():
        key = tuple(sorted((int(u), int(v))))
        if g.edges[u, v].get("faulted") or key in extra_open:
            continue
        out.append((int(u), int(v)))
    return out


def solve(
    g: nx.Graph,
    opened: set[tuple[int, int]] | None = None,
    _skip_calibration: bool = False,
) -> FlowSolution:
    """Solve DC power flow for the network as currently configured.

    Each electrical island is solved independently — which is the whole point of
    islanding. Within an island, generation is redispatched to follow load; if
    generation is short, load is shed and frequency sags.
    """
    opened = opened or set()
    # calibrate_ratings() calls back into solve(); the flag breaks that cycle.
    g = assign_electrical_properties(g) if _skip_calibration else calibrate_ratings(g)
    live = _open_edges(g, opened)

    live_graph = nx.Graph()
    live_graph.add_nodes_from(g.nodes())
    live_graph.add_edges_from(live)

    sol = FlowSolution()
    sol.total_load_mw = round(sum(g.nodes[i]["load_mw"] for i in g.nodes()), 1)

    freq_terms: list[tuple[float, float]] = []  # (island capacity, island freq)

    for comp in nx.connected_components(live_graph):
        nodes = sorted(comp)
        sol.islands.append(nodes)

        cap = sum(g.nodes[i]["generation_mw"] for i in nodes)
        load = sum(g.nodes[i]["load_mw"] for i in nodes)
        served = min(cap, load)
        shed = load - served
        sol.served_mw += served
        sol.shed_mw += shed

        # Frequency from the power imbalance. SIMPLIFIED: real frequency response
        # depends on inertia and governor droop; here a deficit of the island's
        # full capacity is taken to pull frequency down by ~2 Hz, which puts a
        # realistic 0.05-0.5 Hz sag on a partial shortfall. Directionally correct
        # and honestly labelled — it is not a dynamic stability simulation.
        if cap <= 0:
            f = 0.0                       # dead island — no generation at all
        elif load <= 0:
            f = NOMINAL_HZ
        else:
            deficit_pu = (load - cap) / max(cap, 1e-6)
            f = NOMINAL_HZ - 2.0 * max(0.0, deficit_pu)
            if cap > load:                # surplus: governors pull back, slight rise
                f = NOMINAL_HZ + min(0.05, (cap - load) / max(load, 1e-6) * 0.15)
            f = max(0.0, min(f, NOMINAL_HZ + 0.5))
        freq_terms.append((cap, f))

        sol.island_state.append({
            "nodes": nodes,
            "generation_mw": round(cap, 1),
            "load_mw": round(load, 1),
            "served_mw": round(served, 1),
            "shed_mw": round(shed, 1),
            "frequency_hz": round(f, 3),
            "energised": cap > 0,
        })

        # ── DC power flow within this island ──────────────────────────────────
        sub = live_graph.subgraph(nodes)
        if len(nodes) < 2 or sub.number_of_edges() == 0:
            continue

        idx = {n: k for k, n in enumerate(nodes)}
        m = len(nodes)

        # Net injection, with generation scaled to follow served load exactly so
        # the island balances (an unbalanced injection vector has no solution).
        gen_total = cap or 1.0
        p = np.zeros(m)
        for n in nodes:
            gen = g.nodes[n]["generation_mw"] * (served / gen_total if gen_total else 0.0)
            served_here = g.nodes[n]["load_mw"] * (served / load if load else 0.0)
            p[idx[n]] = gen - served_here

        b = np.zeros((m, m))
        for u, v in sub.edges():
            x = max(g.edges[u, v]["reactance"], 1e-4)
            i, j = idx[u], idx[v]
            b[i, i] += 1.0 / x
            b[j, j] += 1.0 / x
            b[i, j] -= 1.0 / x
            b[j, i] -= 1.0 / x

        # Slack bus = biggest generator in the island; drop its row/column.
        slack = max(nodes, key=lambda n: g.nodes[n]["generation_mw"])
        s = idx[slack]
        keep = [k for k in range(m) if k != s]
        try:
            theta_r = np.linalg.solve(b[np.ix_(keep, keep)], p[keep])
        except np.linalg.LinAlgError:
            theta_r = np.linalg.lstsq(b[np.ix_(keep, keep)], p[keep], rcond=None)[0]
        theta = np.zeros(m)
        theta[keep] = theta_r

        for u, v in sub.edges():
            x = max(g.edges[u, v]["reactance"], 1e-4)
            mw = float((theta[idx[u]] - theta[idx[v]]) / x)
            key = (int(u), int(v))
            sol.flows[key] = mw
            rating = g.edges[u, v]["rating_mva"]
            sol.loading[key] = abs(mw) / rating if rating else 0.0

    # System frequency shown to the operator = capacity-weighted island average.
    live_terms = [(c, f) for c, f in freq_terms if c > 0]
    if live_terms:
        tot = sum(c for c, _ in live_terms)
        sol.frequency_hz = round(sum(c * f for c, f in live_terms) / tot, 3)
    else:
        sol.frequency_hz = 0.0
        sol.blackout = True

    sol.overloads = sorted(
        ((u, v, ld) for (u, v), ld in sol.loading.items() if ld >= 1.0),
        key=lambda t: -t[2],
    )
    sol.served_mw = round(sol.served_mw, 1)
    sol.shed_mw = round(sol.shed_mw, 1)
    return sol


# ── Cascade screening ────────────────────────────────────────────────────────

def cascade_risk(sol: FlowSolution) -> dict:
    """Would this state propagate? Overloaded lines trip on protection.

    SIMPLIFIED cascade screen: any line at or above its rating is assumed to be
    tripped by protection, which is how real cascades start (Aug 2003 began with
    exactly this). A rigorous study would re-solve iteratively after each trip;
    this reports the first round, which is what an operator sees on the alarm
    screen in the seconds that matter.
    """
    n = len(sol.overloads)
    if n == 0:
        risk, note = "secure", "All lines within rating. System is N-1 secure."
    elif n <= 2:
        risk, note = "elevated", (
            f"{n} line(s) beyond rating — protection will trip them, "
            "shifting flow onto neighbours.")
    else:
        risk, note = "cascade", (
            f"{n} lines beyond rating simultaneously. This is the signature of "
            "a cascading outage: each trip loads the next.")
    return {"level": risk, "overloads": n, "note": note,
            "worst": round(sol.worst_loading * 100, 1)}


# ── N-1 contingency screening ────────────────────────────────────────────────

def n1_screen(g: nx.Graph, limit: int | None = None) -> list[dict]:
    """Open each line in turn and rank by how badly the system responds.

    This is the real operator workflow: an N-1 screen asks "which single loss
    hurts most", and the answer is the contingency worth demonstrating. Ranking
    by a line's own MW rating would only find the biggest line — not the one the
    network cannot survive losing, which is a property of the whole topology.

    Ranked by load shed first (an island going dark beats any overload), then by
    the worst resulting line loading.
    """
    g = calibrate_ratings(g)
    rows: list[dict] = []
    for u, v in list(g.edges()):
        if g.edges[u, v].get("faulted"):
            continue
        sol = solve(g, opened={tuple(sorted((int(u), int(v))))})
        rows.append({
            "line": (int(u), int(v)),
            "kv": g.edges[u, v]["kv"],
            "base_flow_mw": g.edges[u, v].get("base_flow_mw", 0.0),
            "shed_mw": sol.shed_mw,
            "worst_loading": sol.worst_loading,
            "overloads": len(sol.overloads),
            "islands": len(sol.islands),
            "frequency_hz": sol.frequency_hz,
        })
    rows.sort(key=lambda r: (-r["shed_mw"], -r["worst_loading"]))
    return rows[:limit] if limit else rows


def worst_contingency(g: nx.Graph) -> tuple[int, int] | None:
    """The single line whose loss the system handles worst."""
    rows = n1_screen(g, limit=1)
    return rows[0]["line"] if rows else None
