"""Central configuration for Grid Ops.

Every tunable the demo needs lives here so the UI, the engine, and the GB10
service agree on one set of numbers. Environment variables win over defaults so
the same code runs on a laptop, on xr7620, and against the GB10 unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ── Brand / theme ────────────────────────────────────────────────────────────
# Dell Technologies federal palette, used by both the CSS and the Plotly charts
# so the two never drift apart.
COLORS: dict[str, str] = {
    "bg": "#0a0e17",
    "surface": "#131a29",
    "surface_alt": "#1a2438",
    "border": "#243149",
    "accent": "#00c8ff",       # Dell cyan — primary accent
    "accent_dim": "#0a7ea4",
    "text": "#e6edf7",
    "text_dim": "#8fa3c0",
    "island_a": "#00c8ff",     # microgrid island A
    "island_b": "#ff9f1c",     # microgrid island B
    "ok": "#3ddc97",
    "warn": "#ffc857",
    "crit": "#ff5c5c",
    "line": "#2c3a54",
}

# ── Compute backend ──────────────────────────────────────────────────────────
# The GB10 is the product. `local` exists only so the UI still functions while
# the GB10 is busy serving inference — it is NOT the story.
GB10_QSIM_URL: str = os.getenv("GB10_QSIM_URL", "http://127.0.0.1:8600")
GB10_REQUEST_TIMEOUT: int = int(os.getenv("GB10_REQUEST_TIMEOUT", "600"))
DEFAULT_BACKEND: str = os.getenv("GRIDOPS_BACKEND", "gb10")  # gb10 | local

# Complex128 statevector: 16 bytes per amplitude.
BYTES_PER_AMPLITUDE: int = 16


def statevector_bytes(n_qubits: int) -> int:
    """Memory a dense complex128 statevector of `n_qubits` occupies."""
    return (1 << n_qubits) * BYTES_PER_AMPLITUDE


# ── Demo bounds ──────────────────────────────────────────────────────────────
QUBIT_MIN, QUBIT_MAX, QUBIT_DEFAULT = 6, 24, 12
LAYERS_MIN, LAYERS_MAX, LAYERS_DEFAULT = 1, 4, 2
STEPS_MIN, STEPS_MAX, STEPS_DEFAULT = 10, 50, 30


@dataclass(frozen=True)
class ObjectiveWeights:
    """Weights on the three competing terms of the islanding QUBO.

    These are the knobs an algorithm developer actually turns — the whole point
    of the demo is that changing them changes the Hamiltonian, and you can watch
    the optimizer respond in real time.
    """

    # Defaults chosen by sweep over 12 scenarios (4 seeds x 3 grid sizes),
    # scored on MW served against a classical spectral bisection baseline.
    # Re-measured 2026-07-31 after the baseline was corrected to weight its cut
    # by SOLVED flow rather than the synthetic attribute — it had been optimising
    # a fiction, which flattered every figure below:
    #   flow=1.0 bal=1.0 size=0.35 →  2W/2T/8L, -187 MW,  0/12 infeasible
    #   flow=0.5 bal=2.0 size=0.20 →  5W/3T/4L, +260 MW,  1/12 infeasible  ← chosen
    #   flow=1.0 bal=3.0 size=0.15 →  4W/1T/7L,  +95 MW,  0/12 infeasible
    #   flow=1.0 bal=4.0 size=0.10 →  4W/4T/4L, +242 MW,  0/12 infeasible
    # Prior figures against the flattered baseline were roughly double these
    # (the chosen row read 7W/3T/2L, +419 MW). The ordering survived; the margin
    # did not. Against a baseline given the same information, QAOA wins about
    # half the time on this problem — which is the honest result.
    flow: float = 0.5       # minimise power interrupted by the cut
    balance: float = 2.0    # each island generation/load self-sufficient
    size: float = 0.2       # keep islands comparable — forbids the trivial cut


@dataclass(frozen=True)
class GridSpec:
    """Shape of the synthetic transmission network."""

    n_nodes: int = QUBIT_DEFAULT
    seed: int = 7
    generator_fraction: float = 0.3
    extra_edge_fraction: float = 0.25   # beyond the spanning ring
    weights: ObjectiveWeights = field(default_factory=ObjectiveWeights)
