"""Transparent first-order routing estimates for hardware-preview experiments.

This is deliberately not presented as transpilation.  It holds the logical to
physical placement fixed and sums shortest-path movement for each ZZ interaction,
which is useful for showing why a dense logical Hamiltonian becomes expensive on
sparse hardware.  A target-specific compiler remains the authority for a named QPU.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import networkx as nx


@dataclass(frozen=True)
class RoutingEstimate:
    topology: str
    physical_edges: int
    logical_interactions: int
    adjacent_interactions: int
    estimated_swaps: int
    estimated_two_qubit_gates: int
    expansion: float
    max_distance: int

    def to_dict(self) -> dict:
        return asdict(self)


def topology_graph(n_qubits: int, topology: str) -> nx.Graph:
    if topology == "All-to-all emulator":
        return nx.complete_graph(n_qubits)
    if topology == "Linear device":
        return nx.path_graph(n_qubits)
    if topology == "Ring device":
        return nx.cycle_graph(n_qubits)
    if topology == "Square-grid device":
        width = math.ceil(math.sqrt(n_qubits))
        graph = nx.Graph()
        graph.add_nodes_from(range(n_qubits))
        for node in range(n_qubits):
            row, col = divmod(node, width)
            if col and node - 1 < n_qubits:
                graph.add_edge(node, node - 1)
            if row and node - width < n_qubits:
                graph.add_edge(node, node - width)
        return graph
    raise ValueError(f"Unknown topology: {topology}")


def estimate_routing(n_qubits: int, couplings, topology: str,
                     layers: int = 1) -> RoutingEstimate:
    """Estimate routing with fixed identity placement and restore-after-use SWAPs.

    Each non-adjacent interaction at distance d uses 2(d-1) SWAPs so the original
    placement is restored.  One SWAP is counted as three generic two-qubit gates.
    This is conservative and intentionally simple enough to audit.
    """
    graph = topology_graph(n_qubits, topology)
    distances = dict(nx.all_pairs_shortest_path_length(graph))
    pairs = [(int(i), int(j)) for item in couplings
             for i, j in [(item[0], item[1])]]
    adjacent = 0
    swaps = 0
    max_distance = 0
    for i, j in pairs:
        distance = distances[i][j]
        max_distance = max(max_distance, distance)
        adjacent += int(distance == 1)
        swaps += 2 * max(0, distance - 1)
    logical = len(pairs) * layers
    swaps *= layers
    gates = logical + 3 * swaps
    return RoutingEstimate(
        topology=topology, physical_edges=graph.number_of_edges(),
        logical_interactions=logical, adjacent_interactions=adjacent * layers,
        estimated_swaps=swaps, estimated_two_qubit_gates=gates,
        expansion=(gates / logical if logical else 1.0), max_distance=max_distance,
    )

