"""Shared fixtures. Everything here runs on CPU with no GB10 — CI must not
depend on hardware that only exists in one lab."""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from src.config.settings import GridSpec
from src.simulation.grid_model import apply_fault, build_grid, build_ising
from src.simulation import power_flow as pf


@pytest.fixture(scope="session")
def spec():
    return GridSpec(n_nodes=10, seed=7)


@pytest.fixture(scope="session")
def grid(spec):
    """Intact, rating-calibrated network."""
    return pf.calibrate_ratings(build_grid(spec))


@pytest.fixture(scope="session")
def faulted(grid):
    line = pf.worst_contingency(grid)
    return apply_fault(grid, [line] if line else [])


@pytest.fixture(scope="session")
def model(faulted, spec):
    return build_ising(faulted, spec.weights)
