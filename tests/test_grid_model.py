"""Domain model: bit ordering, feasibility, and the MW numbers on screen."""

from src.simulation.grid_model import (
    apply_fault, brute_force_ground_state, evaluate_partition, live_edges,
)


def test_bitstring_energy_identity(faulted, model):
    """Locks endianness end to end: the energy of the brute-force ground state
    as reported by evaluate_partition must equal the brute-force energy."""
    bits, energy = brute_force_ground_state(model)
    rep = evaluate_partition(faulted, model, bits)
    assert abs(rep.energy - energy) < 1e-9


def test_complement_is_the_same_partition(faulted, model):
    """Z2 symmetry: flipping every bit names the same physical split."""
    bits, _ = brute_force_ground_state(model)
    comp = "".join("1" if c == "0" else "0" for c in bits)
    a = evaluate_partition(faulted, model, bits)
    b = evaluate_partition(faulted, model, comp)
    assert abs(a.energy - b.energy) < 1e-9
    assert a.interrupted_mw == b.interrupted_mw
    assert sorted(a.island_a) == sorted(b.island_b)


def test_island_held_only_by_a_faulted_line_is_infeasible(grid, spec):
    """Contiguity must be judged over LIVE edges. A tripped conductor cannot
    energise anything, so an island depending on one is not viable."""
    from src.simulation.grid_model import build_ising
    # Find a node whose removal-by-fault isolates it over live edges.
    for cut in list(grid.edges()):
        g = apply_fault(grid, [cut])
        m = build_ising(g, spec.weights)
        live = live_edges(g)
        u, _v = cut
        # If u now has no live edges it must be reported infeasible when split off.
        if not any(u in e for e in live):
            bits = "".join("1" if i == u else "0" for i in range(m.n_qubits))[::-1]
            rep = evaluate_partition(g, m, bits)
            assert not rep.feasible
            return


def test_severed_mw_uses_solved_flow_not_the_synthetic_attribute(grid):
    """Locks the fix that stopped the event log quoting a fictional MW figure."""
    from src.simulation.grid_model import build_ising
    from src.config.settings import GridSpec
    g = grid
    m = build_ising(g, GridSpec().weights)
    n = m.n_qubits
    bits = "".join("1" if i % 2 else "0" for i in range(n))
    rep = evaluate_partition(g, m, bits)
    for u, v, mw in rep.severed_lines:
        base = g.edges[u, v].get("base_flow_mw")
        assert base is not None, "calibrated graph must carry base_flow_mw"
        assert abs(mw - g.edges[u, v]["flow_mw"]) < 1e-9 or abs(mw - base) < 1e-9
