"""Noise: the closed-form depolarizing channel and the trajectory method."""
import numpy as np

from src.simulation import noise as nz, qaoa_core


def _reference_depolarize(rho, n, p):
    """Literal Kraus form — the definition the closed form must reproduce."""
    X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
    Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
    Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)
    for t in range(n):
        acc = (1.0 - p) * rho
        for pa in (X, Y, Z):
            acc += (p / 3.0) * nz._rho_apply_1q(rho.copy(), n, t, pa, np)
        rho = acc
    return rho


def _random_rho(n, seed=0):
    rng = np.random.default_rng(seed)
    dim = 1 << n
    a = rng.normal(size=(dim, dim)) + 1j * rng.normal(size=(dim, dim))
    rho = a @ a.conj().T
    return rho / np.trace(rho).real


def test_closed_form_matches_kraus_reference():
    """Locks the closed-form rewrite that removed four full-rho copies per qubit."""
    n, p = 4, 0.07
    rho = _random_rho(n)
    fast = nz.depolarize(rho.copy(), n, p, np)
    ref = _reference_depolarize(rho.copy(), n, p)
    assert np.max(np.abs(fast - ref)) < 1e-12


def test_channel_preserves_trace_and_hermiticity():
    n, p = 4, 0.15
    rho = _random_rho(n, seed=3)
    out = nz.depolarize(rho.copy(), n, p, np)
    assert abs(np.trace(out).real - 1.0) < 1e-10
    assert np.max(np.abs(out - out.conj().T)) < 1e-10


def test_zero_noise_is_the_identity():
    n = 4
    rho = _random_rho(n, seed=5)
    assert np.max(np.abs(nz.depolarize(rho.copy(), n, 0.0, np) - rho)) == 0.0


def test_noiseless_density_matrix_matches_statevector(model):
    """With p=0 the density path must reproduce the pure-state probabilities."""
    n = 8
    coup = {k: v for k, v in model.couplings.items() if k[0] < n and k[1] < n}
    diag = qaoa_core.cost_diagonal(n, coup, model.offset)
    gam, bet = [0.31, 0.52], [0.6, 0.25]
    rho = nz.qaoa_density_matrix(n, diag, gam, bet, depolarizing=0.0)
    sv = qaoa_core.qaoa_statevector(n, diag, gam, bet)
    assert np.max(np.abs(nz.density_probabilities(rho) -
                         qaoa_core.probabilities(sv))) < 1e-10


def test_trajectories_converge_on_the_density_matrix(model):
    """The whole justification for the trajectory method.

    Averaging many randomly-perturbed pure-state runs must reproduce the exact
    density-matrix answer, because the depolarizing channel IS a probabilistic
    mixture. Tolerance is set from the method's own reported standard error.
    """
    n, p = 6, 0.05
    coup = {k: v for k, v in model.couplings.items() if k[0] < n and k[1] < n}
    diag = qaoa_core.cost_diagonal(n, coup, model.offset)
    gam, bet = [0.3, 0.5], [0.6, 0.2]

    rho = nz.qaoa_density_matrix(n, diag, gam, bet, depolarizing=p)
    exact = nz.density_expectation(rho, diag)

    tr = nz.qaoa_trajectories(n, coup, model.offset, gam, bet,
                              depolarizing=p, trajectories=600, seed=11,
                              keep_probs=False)
    # Within 4 standard errors is a very loose bound; a broken unravelling
    # misses by far more than that.
    assert abs(tr.energy - exact) < 4 * tr.energy_stderr + 1e-9, (
        f"trajectories {tr.energy:.5f} +/- {tr.energy_stderr:.5f} "
        f"vs exact {exact:.5f}")


def test_noisy_ceiling_is_about_half_the_clean_one():
    """The headline memory claim: a density matrix is 2^(2n), not 2^n."""
    free = 64 * 2**30
    clean = 0
    while (1 << (clean + 1)) * 16 * 1.6 <= free * 0.55:
        clean += 1
    noisy = nz.max_noisy_qubits(free)
    assert noisy < clean, (noisy, clean)
    assert abs(noisy - clean / 2) <= 2, f"noisy {noisy} not ~half of clean {clean}"
