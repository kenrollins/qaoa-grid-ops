"""Transmission grid → Ising Hamiltonian.

This module is the physics-to-math bridge and is deliberately free of any
quantum-backend dependency: it turns a substation topology into couplings, and
turns a measured bitstring back into operator-legible numbers (MW interrupted,
MW of imbalance). It runs identically on the GB10, on xr7620, or on a laptop.

── The formulation ──────────────────────────────────────────────────────────
Controlled islanding is a *constrained* graph partition, not a plain Max-Cut.
Splitting a network into two electrically viable microgrids means trading three
objectives that genuinely fight each other:

  1. FLOW   — cut as little live power transfer as possible. Every severed line
              is real energy that stops moving.
  2. BALANCE— each island must supply its own load. An island holding all the
              generation and none of the demand is a partition, not a microgrid.
  3. SIZE   — forbid the degenerate answer. Minimising (1) and (2) alone is
              solved perfectly by "put everything in one island, cut nothing",
              which is not an islanding plan.

With spin s_i = +1/-1 naming node i's island, and net injection
p_i = generation_mw - load_mw:

    H(s) = A · Σ_(i,j)∈E  w_ij (1 - s_i s_j)/2      flow severed by the cut
         + B · ( Σ_i p_i s_i )²                     per-island power balance
         + C · ( Σ_i s_i )²                         island size balance

The balance term is what makes this interesting. Σ_i p_i s_i is the *difference*
in net injection between the islands, so squaring it drives both islands toward
self-sufficiency at once — and because it couples every node to every other
node, the resulting Hamiltonian is DENSE (all-to-all ZZ), not just the sparse
transmission graph. That density is the honest reason this needs real hardware:
a p-layer circuit on n nodes carries p·n(n-1)/2 two-qubit rotations.

Expanding the squares gives a pure-quadratic Ising model (no local fields):

    H(s) = offset + Σ_(i<j) J_ij s_i s_j

    J_ij   = -A·w_ij/2 · [edge (i,j) exists]  +  2B·p_i·p_j  +  2C
    offset =  A·Σ_E w_ij/2  +  B·Σ_i p_i²  +  C·n
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import networkx as nx
import numpy as np

from src.config.settings import GridSpec, ObjectiveWeights

# Total generation as a multiple of total load. Real systems carry a modest
# operating reserve, not a 3x surplus.
RESERVE_MARGIN = 1.08


@dataclass(frozen=True)
class IsingModel:
    """A pure-quadratic Ising problem: H(s) = offset + Σ_(i<j) J_ij s_i s_j."""

    n_qubits: int
    couplings: dict[tuple[int, int], float]
    offset: float

    @property
    def n_terms(self) -> int:
        return len(self.couplings)

    def energy(self, spins: np.ndarray) -> float:
        """Exact energy of one spin configuration (±1 vector)."""
        e = self.offset
        for (i, j), jij in self.couplings.items():
            e += jij * spins[i] * spins[j]
        return float(e)

    def scale(self) -> float:
        """Largest |J|, used to keep QAOA's γ range physically sensible."""
        return max((abs(v) for v in self.couplings.values()), default=1.0)


# ── Building the network ─────────────────────────────────────────────────────

def build_grid(spec: GridSpec) -> nx.Graph:
    """Synthesize a plausible transmission network.

    Structure: a ring backbone (so the grid is always connected and always has
    at least two disjoint paths — a real transmission characteristic) plus a
    fraction of random chords standing in for interties.

    Every node carries generation_mw and load_mw; every line carries a
    flow_mw rating that becomes its cut weight.
    """
    rng = np.random.default_rng(spec.seed)
    n = spec.n_nodes
    g = nx.cycle_graph(n)

    # Interties beyond the ring backbone.
    extra = int(spec.extra_edge_fraction * n)
    attempts = 0
    while g.number_of_edges() < n + extra and attempts < 20 * n:
        attempts += 1
        u, v = (int(x) for x in rng.choice(n, size=2, replace=False))
        if u != v and not g.has_edge(u, v):
            g.add_edge(u, v)

    n_gen = max(1, int(round(spec.generator_fraction * n)))
    gen_nodes = set(int(x) for x in rng.choice(n, size=n_gen, replace=False))

    # Generation sites are lumpy; load buses are comparatively uniform.
    raw_gen = {i: (float(rng.uniform(60, 240)) if i in gen_nodes else 0.0) for i in range(n)}
    loads = {i: float(rng.uniform(8, 45)) for i in range(n)}

    # Scale generation to sit just above total load. Without this the synthetic
    # grid carries ~3x more generation than demand, every possible fragment is
    # trivially self-sufficient, and islanding can NEVER shed load — which makes
    # the balance term of the objective decorative and the whole contingency
    # story unfalsifiable. Real systems are dispatched close to demand.
    total_load = sum(loads.values())
    total_raw = sum(raw_gen.values()) or 1.0
    scale = (total_load * RESERVE_MARGIN) / total_raw

    for i in range(n):
        is_gen = i in gen_nodes
        gen = raw_gen[i] * scale
        load = loads[i]
        g.nodes[i].update(
            name=f"{'GEN' if is_gen else 'SUB'}-{i:02d}",
            kind="generation" if is_gen else "load",
            generation_mw=round(gen, 1),
            load_mw=round(load, 1),
            net_mw=round(gen - load, 1),
        )

    for u, v in g.edges():
        g.edges[u, v]["flow_mw"] = round(float(rng.uniform(15, 120)), 1)

    # Lay the grid out once, deterministically, so the topology does not
    # reshuffle between reruns and the operator can build a mental map.
    pos = nx.spring_layout(g, seed=spec.seed, iterations=200)
    for i, (x, y) in pos.items():
        g.nodes[i]["x"], g.nodes[i]["y"] = float(x), float(y)

    return g


def normalized_injections(g: nx.Graph) -> np.ndarray:
    """Net injection per node, scaled so the balance term is O(1).

    Without normalisation p_i·p_j runs to ~10⁴ and swamps the flow term; the
    weights in ObjectiveWeights would then be uninterpretable.
    """
    p = np.array([g.nodes[i]["net_mw"] for i in g.nodes()], dtype=float)
    denom = float(np.abs(p).max()) or 1.0
    return p / denom


# ── Contingency: tripping lines ──────────────────────────────────────────────

def apply_fault(g: nx.Graph, edges: Iterable[tuple[int, int]]) -> nx.Graph:
    """Mark lines as tripped by a fault (line drop, cyber event, storm).

    A faulted line is NOT removed from the graph — the operator still needs to
    see it on the one-line diagram, drawn as failed. It is instead marked
    `faulted=True`, and every downstream calculation treats it as carrying no
    power: it contributes nothing to the cut objective, it cannot hold an island
    together for contiguity purposes, and severing it costs nothing because it
    is already out.

    Returns a copy — the caller's pristine grid stays intact so the same
    topology can be re-faulted differently without rebuilding it.
    """
    h = g.copy()
    for u, v in h.edges():
        h.edges[u, v].setdefault("faulted", False)
    for u, v in edges:
        if h.has_edge(u, v):
            h.edges[u, v]["faulted"] = True
    return h


def live_edges(g: nx.Graph) -> list[tuple[int, int]]:
    """Edges still carrying power — everything not tripped."""
    return [(int(u), int(v)) for u, v in g.edges() if not g.edges[u, v].get("faulted")]


def faulted_edges(g: nx.Graph) -> list[tuple[int, int, float]]:
    return [(int(u), int(v), float(g.edges[u, v]["flow_mw"]))
            for u, v in g.edges() if g.edges[u, v].get("faulted")]


def most_critical_line(g: nx.Graph) -> tuple[int, int] | None:
    """The line whose loss hurts most — highest flow among those that would
    disconnect the grid, else simply the highest flow still in service.

    A fault that merely removes a redundant tie is not a contingency worth
    demonstrating; one that splits the network is.
    """
    live = live_edges(g)
    if not live:
        return None
    h = nx.Graph(live)
    h.add_nodes_from(g.nodes())

    def flow(e: tuple[int, int]) -> float:
        return float(g.edges[e[0], e[1]]["flow_mw"])

    splitting = []
    for u, v in live:
        h.remove_edge(u, v)
        if not nx.is_connected(h):
            splitting.append((u, v))
        h.add_edge(u, v)
    pool = splitting or live
    return max(pool, key=flow)


# ── Load accounting — how operators actually score a plan ────────────────────

@dataclass(frozen=True)
class LoadReport:
    """MW served vs shed. The number a grid operator judges the plan by."""

    total_load_mw: float
    total_generation_mw: float
    served_mw: float
    shed_mw: float
    per_island: list[dict]

    @property
    def served_fraction(self) -> float:
        return self.served_mw / self.total_load_mw if self.total_load_mw else 1.0


def load_report(g: nx.Graph, islands: list[list[int]]) -> LoadReport:
    """Score a partition by load served.

    Each island can serve at most its own generation — that is the entire point
    of islanding. Load beyond an island's generation is shed. An island with no
    generation sheds everything in it.
    """
    total_load = sum(g.nodes[i]["load_mw"] for i in g.nodes())
    total_gen = sum(g.nodes[i]["generation_mw"] for i in g.nodes())

    served, per = 0.0, []
    for idx, nodes in enumerate(islands):
        if not nodes:
            continue
        gen = sum(g.nodes[i]["generation_mw"] for i in nodes)
        load = sum(g.nodes[i]["load_mw"] for i in nodes)
        s = min(gen, load)
        served += s
        per.append({
            "island": chr(ord("A") + idx),
            "nodes": len(nodes),
            "generation_mw": round(gen, 1),
            "load_mw": round(load, 1),
            "served_mw": round(s, 1),
            "shed_mw": round(load - s, 1),
        })

    return LoadReport(
        total_load_mw=round(total_load, 1),
        total_generation_mw=round(total_gen, 1),
        served_mw=round(served, 1),
        shed_mw=round(total_load - served, 1),
        per_island=per,
    )


def build_ising(g: nx.Graph, weights: ObjectiveWeights) -> IsingModel:
    """Assemble the islanding Hamiltonian described in this module's docstring.

    Faulted lines are excluded from the flow term: a tripped line carries no
    power, so cutting it costs nothing and the optimizer must not be paid to
    avoid it.
    """
    n = g.number_of_nodes()
    p = normalized_injections(g)

    live = live_edges(g)
    # Weight the cut by the ACTUAL solved base-case flow when power_flow has
    # calibrated the network. `flow_mw` is a synthetic generator attribute that
    # has no relationship to where power really goes, so minimising it optimised
    # a fiction. `base_flow_mw` is the DC power flow result.
    def _cut_weight(u, v) -> float:
        e = g.edges[u, v]
        return float(e.get("base_flow_mw", e["flow_mw"]))

    flows = np.array([_cut_weight(u, v) for u, v in live], dtype=float) \
        if live else np.array([1.0])
    flow_denom = float(flows.max()) or 1.0

    couplings: dict[tuple[int, int], float] = {}

    def add(i: int, j: int, value: float) -> None:
        if i > j:
            i, j = j, i
        couplings[(i, j)] = couplings.get((i, j), 0.0) + value

    # 1. Flow severed by the cut — live lines only.
    for u, v in live:
        w = _cut_weight(u, v) / flow_denom
        add(int(u), int(v), -weights.flow * w / 2.0)

    # 2. + 3. Balance and size — both dense, both all-to-all.
    #
    # Divided by n. This is not cosmetic: the flow term touches only |E| ≈ n
    # edges, while these touch all n(n-1)/2 pairs. Left unnormalised the dense
    # terms outweigh flow by ~n, and the optimiser buys island balance at ANY
    # cut cost — measured at n=14, it severed 144.7 MW against a 57.2 MW
    # spectral bisection and returned an infeasible plan, while faithfully
    # finding the true ground state of that lopsided objective. The weights in
    # ObjectiveWeights are only interpretable once the three terms are on
    # comparable footing.
    dense_scale = 1.0 / max(1, n)
    for i in range(n):
        for j in range(i + 1, n):
            add(i, j, dense_scale * (2.0 * weights.balance * p[i] * p[j]
                                     + 2.0 * weights.size))

    offset = (
        (weights.flow * float((flows / flow_denom).sum()) / 2.0 if live else 0.0)
        + dense_scale * weights.balance * float((p ** 2).sum())
        + dense_scale * weights.size * n
    )

    # Drop couplings that rounded to nothing — they cost a two-qubit gate each.
    couplings = {k: v for k, v in couplings.items() if abs(v) > 1e-12}
    return IsingModel(n_qubits=n, couplings=couplings, offset=offset)


# ── Reading an answer back out ───────────────────────────────────────────────

@dataclass(frozen=True)
class PartitionReport:
    """Operator-legible evaluation of one candidate islanding plan."""

    bitstring: str
    assignment: list[int]
    energy: float
    severed_lines: list[tuple[int, int, float]]
    interrupted_mw: float
    island_a: list[int]
    island_b: list[int]
    imbalance_a_mw: float
    imbalance_b_mw: float
    feasible: bool
    notes: list[str]

    @property
    def max_imbalance_mw(self) -> float:
        return max(abs(self.imbalance_a_mw), abs(self.imbalance_b_mw))


def evaluate_partition(g: nx.Graph, model: IsingModel, bitstring: str) -> PartitionReport:
    """Turn a measured bitstring into MW, not just an energy number.

    `bitstring` is little-endian (qubit 0 is the rightmost character), matching
    both Qiskit's convention and the GB10 service's index ordering.
    """
    n = g.number_of_nodes()
    bits = [int(c) for c in bitstring[::-1][:n]]
    bits += [0] * (n - len(bits))
    spins = np.array([1 - 2 * b for b in bits], dtype=float)

    # A faulted line is already out: cutting it interrupts nothing further, so
    # counting it as "severed by the plan" would inflate the headline MW figure
    # with damage the fault already did.
    severed = [
        (int(u), int(v), float(g.edges[u, v]["flow_mw"]))
        for u, v in g.edges()
        if bits[u] != bits[v] and not g.edges[u, v].get("faulted")
    ]
    interrupted = sum(f for _, _, f in severed)

    island_a = [i for i in range(n) if bits[i] == 0]
    island_b = [i for i in range(n) if bits[i] == 1]

    def imbalance(nodes: list[int]) -> float:
        return sum(g.nodes[i]["net_mw"] for i in nodes)

    imb_a, imb_b = imbalance(island_a), imbalance(island_b)

    notes: list[str] = []
    feasible = True
    if not island_a or not island_b:
        feasible = False
        notes.append("Degenerate: one island is empty — no separation performed.")
    else:
        for label, nodes in (("A", island_a), ("B", island_b)):
            if not any(g.nodes[i]["kind"] == "generation" for i in nodes):
                feasible = False
                notes.append(f"Island {label} contains no generation — it cannot be energised.")
        # Contiguity must be judged over LIVE lines only — a tripped line cannot
        # energise anything, so an island held together only by a faulted
        # conductor is not actually connected.
        live_graph = nx.Graph(live_edges(g))
        live_graph.add_nodes_from(g.nodes())
        for label, nodes in (("A", island_a), ("B", island_b)):
            sub = live_graph.subgraph(nodes)
            if len(nodes) > 1 and not nx.is_connected(sub):
                feasible = False
                notes.append(f"Island {label} is not electrically contiguous.")

    return PartitionReport(
        bitstring=bitstring,
        assignment=bits,
        energy=model.energy(spins),
        severed_lines=severed,
        interrupted_mw=round(interrupted, 1),
        island_a=island_a,
        island_b=island_b,
        imbalance_a_mw=round(imb_a, 1),
        imbalance_b_mw=round(imb_b, 1),
        feasible=feasible,
        notes=notes,
    )


def spectral_baseline(g: nx.Graph) -> str:
    """Classical spectral bisection — the method an engineer reaches for first.

    Partitions on the sign of the Fiedler vector (second-smallest eigenvector of
    the flow-weighted Laplacian over live lines). This is a genuinely good
    minimum-cut heuristic, and including it keeps the demo honest: QAOA should be
    compared against competent classical practice, not against nothing.

    Note what it optimises — cut weight alone. It has no notion of generation
    adequacy, which is exactly where the QUBO's balance term earns its place.

    Returned little-endian to match every other bitstring in this project.
    """
    n = g.number_of_nodes()
    live = live_edges(g)
    if n < 2 or not live:
        return "0" * n

    lap = np.zeros((n, n), dtype=float)
    for u, v in live:
        w = float(g.edges[u, v]["flow_mw"])
        lap[u, u] += w
        lap[v, v] += w
        lap[u, v] -= w
        lap[v, u] -= w

    vals, vecs = np.linalg.eigh(lap)
    order = np.argsort(vals)
    fiedler = vecs[:, order[1]] if n > 1 else vecs[:, 0]

    bits = [1 if fiedler[i] > 0 else 0 for i in range(n)]
    if all(b == bits[0] for b in bits):  # degenerate — split at the median
        med = float(np.median(fiedler))
        bits = [1 if fiedler[i] > med else 0 for i in range(n)]
    return "".join(str(b) for b in reversed(bits))


def brute_force_ground_state(model: IsingModel) -> tuple[str, float]:
    """Exact optimum by exhaustive search. Only sane below ~20 qubits.

    Present so the demo can state QAOA's approximation ratio honestly instead of
    asserting optimality it has not checked.
    """
    n = model.n_qubits
    if n > 20:
        raise ValueError(f"refusing to brute-force {n} qubits ({1 << n} states)")

    best_e, best_s = math.inf, 0
    for state in range(1 << n):
        spins = np.array([1 - 2 * ((state >> k) & 1) for k in range(n)], dtype=float)
        e = model.energy(spins)
        if e < best_e:
            best_e, best_s = e, state
    return format(best_s, f"0{n}b"), float(best_e)
