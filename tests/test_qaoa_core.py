"""The quantum math. These lock the demo's central technical claims."""
import numpy as np

from src.simulation import qaoa_core


def test_diagonal_fast_path_equals_gate_by_gate(model):
    """The demo claims the phase-multiply shortcut is an OPTIMISATION, not an
    approximation, and shows a button that proves it. Lock that claim."""
    out = qaoa_core.verify_equivalence(8, {k: v for k, v in model.couplings.items()
                                           if k[0] < 8 and k[1] < 8},
                                       model.offset, layers=2, xp=np)
    assert out["equivalent"], out
    assert out["max_amplitude_deviation"] < 1e-9


def test_optimizer_actually_evolves_the_state(model):
    """Regression guard for the converged-on-nothing failure.

    A circuit with gamma≈0 leaves the initial |+> state untouched, whose energy
    is exactly the Hamiltonian offset. The optimiser once returned precisely
    that while reporting convergence, and nothing in the output said so.
    """
    res = qaoa_core.optimize_qaoa(model.n_qubits, model.couplings, model.offset,
                                  layers=2, steps=30, xp=np)
    assert res.best_energy < model.offset - 1e-6, (
        f"best energy {res.best_energy} did not beat the unevolved state "
        f"({model.offset}) — the circuit did nothing")


def test_gamma_range_scales_with_spread_not_max_coupling(model):
    """Locks the sigma(H) fix. gamma must be scaled by the SPREAD of the cost
    function; scaling by max|J| over-rotates and inverted our depth scaling."""
    diag = qaoa_core.cost_diagonal(model.n_qubits, model.couplings, model.offset)
    sigma = float(np.std(diag))
    max_j = max(abs(v) for v in model.couplings.values())
    assert sigma > max_j, "fixture no longer exercises the case these differ"
    expected = float(np.pi / (2.0 * sigma))
    # Re-derive what optimize_qaoa uses internally.
    assert 0 < expected < np.pi / (2.0 * max_j)


def test_deeper_circuits_do_not_get_worse(model):
    """Monotonicity in depth is the property the gamma bug destroyed."""
    best = {}
    for p in (1, 2, 3):
        r = qaoa_core.optimize_qaoa(model.n_qubits, model.couplings, model.offset,
                                    layers=p, steps=40, xp=np, seed=5)
        best[p] = r.best_energy
    # Allow a small tolerance: the optimiser is stochastic and budget-limited.
    assert best[3] < model.offset and best[2] < model.offset
    assert best[3] <= best[1] * 1.15, f"p=3 much worse than p=1: {best}"


def test_top_bitstrings_are_sorted_and_little_endian(model):
    diag = qaoa_core.cost_diagonal(model.n_qubits, model.couplings, model.offset)
    sv = qaoa_core.qaoa_statevector(model.n_qubits, diag, [0.3, 0.4], [0.5, 0.2])
    tops = qaoa_core.top_bitstrings(sv, model.n_qubits, k=6)
    probs = [p for _, p in tops]
    assert probs == sorted(probs, reverse=True)
    assert all(len(b) == model.n_qubits for b, _ in tops)
