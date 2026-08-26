from src.simulation.connectivity import estimate_routing, topology_graph


def test_all_to_all_needs_no_routing():
    couplings = [(0, 1, 1.0), (0, 3, 1.0), (2, 3, 1.0)]
    result = estimate_routing(4, couplings, "All-to-all emulator", layers=2)
    assert result.estimated_swaps == 0
    assert result.estimated_two_qubit_gates == 6
    assert result.expansion == 1.0


def test_linear_distance_has_auditable_swap_cost():
    result = estimate_routing(4, [(0, 3, 1.0)], "Linear device")
    assert result.max_distance == 3
    assert result.estimated_swaps == 4
    assert result.estimated_two_qubit_gates == 13


def test_grid_contains_every_requested_qubit():
    assert set(topology_graph(10, "Square-grid device")) == set(range(10))
