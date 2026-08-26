"""Central configuration for QAOA Grid Ops.

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
# THE palette. tools/gen_theme.py derives the custom properties for both
# src/ui/style.css and the published site's extra.css from this dict, and
# tests/test_theme.py fails the build if either drifts from it.
#
# Not pure black, and not white text. Near-white on #000 at paragraph length
# causes halation -- the glyph edges bloom and the eye cannot settle -- which
# made the site's prose genuinely hard to read. The background is lifted off
# black with a slight blue cast and the body text is stepped back from white
# twice: #e6edf7 -> #dbe4f0 -> #c4cfdd, which is 12.2:1 here, still comfortably
# past WCAG AAA (7:1). Softer is only worth doing while it stays legible, so
# the value was measured rather than eyeballed. The application matches, so the
# two surfaces stay one product.
#
# Kept in step with the :root block in src/ui/style.css. The theme pass
# restyled the application chrome there but left this dict on the previous
# palette, so every Plotly figure rendered as a lighter panel floating on the
# new black background -- in the application AND on the published site, which
# generates its figures from this same dict.
COLORS: dict[str, str] = {
    "bg": "#0b0f17",
    "surface": "#141b26",
    "surface_alt": "#1b2433",
    "border": "#1b2433",
    "accent": "#0099CC",       # darkened blue — primary accent
    "accent_dim": "#006699",
    "text": "#c4cfdd",
    "text_dim": "#6a8fa3",
    "island_a": "#0099CC",     # microgrid island A
    "island_b": "#ff9f1c",     # microgrid island B
    "ok": "#3ddc97",
    "warn": "#ffc857",
    "crit": "#ff5c5c",
    # Gridlines are deliberately NOT the border token: on pure black, #0d1a26
    # is invisible, and a chart with no gridlines cannot be read off.
    "line": "#243044",
    # Plot area, one step below surface. Was hardcoded as "#070b12" in nine
    # places, which is why it survived the theme pass unchanged.
    "plot_bg": "#070b12",
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
    formulation: str = "analytic"  # analytic | operational-surrogate
