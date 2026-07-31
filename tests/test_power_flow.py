"""DC power flow. Every number the operator sees derives from this module."""
import networkx as nx

from src.simulation import power_flow as pf
from src.simulation.grid_model import live_edges


def test_nodal_balance(grid):
    """Power in equals power out at every bus — Kirchhoff, to solver tolerance."""
    sol = pf.solve(grid)
    for nodes in sol.islands:
        gen = sum(grid.nodes[i]["generation_mw"] for i in nodes)
        load = sum(grid.nodes[i]["load_mw"] for i in nodes)
        served = min(gen, load)
        net_out = 0.0
        for (u, v), mw in sol.flows.items():
            if u in nodes and v not in nodes:
                net_out += mw
            elif v in nodes and u not in nodes:
                net_out -= mw
        # A single island exchanges nothing with the outside world.
        if len(sol.islands) == 1:
            assert abs(net_out) < 1e-6, f"island leaks {net_out} MW"
        assert served >= 0


def test_islands_match_networkx(faulted):
    """Our island detection must agree with a reference graph library."""
    opened = {tuple(sorted((u, v))) for u, v in list(faulted.edges())[:2]}
    sol = pf.solve(faulted, opened=opened)
    g = nx.Graph()
    g.add_nodes_from(faulted.nodes())
    g.add_edges_from(e for e in live_edges(faulted)
                     if tuple(sorted(e)) not in opened)
    assert sorted(sorted(c) for c in nx.connected_components(g)) == \
sorted(sorted(i) for i in sol.islands)


def test_intact_loading_is_realistic(grid):
    """Intact grid must sit comfortably inside ratings.

    Regression guard for the ratings-fiction bug: ratings were once sized from a
    synthetic attribute unrelated to solved flow, so the INTACT grid already sat
    at 80% and every contingency produced absurd overloads.
    """
    sol = pf.solve(grid)
    assert 0.40 < sol.worst_loading < 0.80, f"intact worst loading {sol.worst_loading:.2%}"
    assert not sol.overloads


def test_faulted_line_carries_nothing(faulted):
    sol = pf.solve(faulted)
    for u, v in faulted.edges():
        if faulted.edges[u, v].get("faulted"):
            assert (int(u), int(v)) not in sol.flows
            assert (int(v), int(u)) not in sol.flows


def test_n1_screen_ranks_by_consequence(grid):
    rows = pf.n1_screen(grid, limit=3)
    assert rows, "screen returned nothing"
    sev = [(-r["shed_mw"], -r["worst_loading"]) for r in rows]
    assert sev == sorted(sev), "N-1 screen not ordered by consequence"
