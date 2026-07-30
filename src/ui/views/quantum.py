"""Tab: The Quantum Part — what is actually quantum here, and what is not.

Written for a federal energy/defense audience that knows power systems cold and
may know QAOA not at all. Two rules govern this page:

  1. No hand-waving. Every claim maps to something the code actually does.
  2. No overclaiming. This is EXACT SIMULATION of a quantum algorithm on
     classical Dell hardware — not a QPU. That is stated plainly and early,
     because the audience will ask, and answering it before they ask is the
     difference between a credible demo and a sales pitch.
"""

from __future__ import annotations

import streamlit as st

from src.ui import components as ui


def _step(num: str, title: str, desc: str, math: str = "") -> str:
    m = f'<div class="math">{math}</div>' if math else ""
    return (f'<div class="qstep"><div class="num">{num}</div><div class="body">'
            f'<div class="t">{title}</div><div class="d">{desc}</div>{m}</div></div>')


def render(run=None, n_nodes: int = 12, layers: int = 2) -> None:
    n = run.model.n_qubits if run else n_nodes
    nc = run.model.n_terms if run else n * (n - 1) // 2
    p = run.result.get("layers", layers) if run else layers

    st.markdown(f"""
<div class="callout">
  <div class="h">Read this first — what this demonstration is</div>
  <p>This runs <strong>exact statevector simulation</strong> of a quantum algorithm on
  classical Dell hardware. There is <strong>no quantum processor</strong> in the loop, and
  none is being claimed.</p>
  <p>That is the point, not a limitation. QAOA is a <strong>hybrid</strong> algorithm: even
  with a perfect QPU attached, the overwhelming majority of the work — building the
  Hamiltonian, proposing parameters, converging the optimizer, decoding results into an
  islanding plan — runs on classical infrastructure. Simulating the quantum half today on
  the same hardware that will <em>drive</em> a real QPU tomorrow is how the algorithm,
  the encoding, and the operator tooling get developed and validated now.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("#### From a power grid to a quantum state, in five steps")

    st.markdown(_step(
        "1", "One qubit per substation",
        f"Each substation gets a single binary decision: <strong>which island does it "
        f"join?</strong> That is one qubit. With <strong>{n} substations</strong> there are "
        f"<strong>2<sup>{n}</sup> = {2**n:,}</strong> possible ways to split the grid — the "
        "search space that makes this hard classically.",
        f"substation i  →  qubit i  →  bit b_i ∈ {{0,1}}  →  spin s_i = 1 − 2·b_i ∈ {{+1,−1}}"
    ), unsafe_allow_html=True)

    st.markdown(_step(
        "2", "The operating objective becomes an energy function",
        "Three competing requirements are encoded as one cost function whose <strong>lowest "
        "energy is the best islanding plan</strong>. Minimize the power severed by the cut; "
        "keep each island able to supply its own load; and forbid the degenerate 'put "
        "everything in one island' answer. This is a <strong>QUBO</strong> — quadratic "
        "unconstrained binary optimization — and it is exactly the form quantum optimization "
        "consumes.",
        "H(s) = A·Σ w_ij(1 − s_i s_j)/2  +  B·(Σ p_i s_i)²  +  C·(Σ s_i)²\n"
        "        ↑ severed flow            ↑ island balance    ↑ non-degenerate"
    ), unsafe_allow_html=True)

    st.markdown(_step(
        "3", "Superposition — every plan at once",
        f"A Hadamard gate on each qubit puts the register into a uniform superposition: all "
        f"<strong>{2**n:,}</strong> candidate partitions represented simultaneously, each with "
        "equal amplitude. Nothing has been decided yet; the algorithm's job is to move "
        "amplitude <em>toward</em> the good partitions and away from the bad ones.",
        f"|ψ₀⟩ = H^⊗{n} |0⟩^⊗{n} = (1/√{2**n}) · Σ_x |x⟩      every partition, equal weight"
    ), unsafe_allow_html=True)

    st.markdown(_step(
        "4", "QAOA — alternate 'judge' and 'mix'",
        f"The circuit alternates two operations for <strong>p = {p} layers</strong>. The "
        "<strong>cost unitary</strong> stamps each candidate partition with a phase "
        "proportional to how bad it is — good plans and bad plans now differ in phase, not "
        "yet in probability. The <strong>mixer</strong> then makes those phases interfere, "
        "converting the phase difference into an <em>amplitude</em> difference. Repeat, and "
        "probability concentrates on low-energy partitions. "
        f"Here that is <strong>{nc} ZZ couplings</strong> per layer "
        f"(<strong>{nc * p} total rotations</strong>) plus {n} mixer rotations per layer.",
        "|ψ⟩ = [ e^(−iβ_p H_M) · e^(−iγ_p H_C) ] … [ e^(−iβ₁ H_M) · e^(−iγ₁ H_C) ] |ψ₀⟩\n"
        "        ↑ mixer (RX)        ↑ cost (RZZ)          γ, β tuned classically"
    ), unsafe_allow_html=True)

    st.markdown(_step(
        "5", "Measure — the bitstring IS the islanding plan",
        "Reading the register collapses it to one bitstring, and that bitstring is directly "
        "the operational answer: bit <em>i</em> says which island substation <em>i</em> "
        "belongs to. Because amplitude was concentrated on low-energy states, the outcome is "
        "very likely a good plan. It is then checked against real constraints — does each "
        "island contain generation, is each island electrically contiguous — before an "
        "operator would ever see it.",
        "measure |ψ⟩  →  b = 0110100…  →  island A = {i : b_i = 0},  island B = {i : b_i = 1}"
    ), unsafe_allow_html=True)

    st.markdown("#### Who does what — the hybrid split")
    st.markdown("""
<div class="split">
  <div class="col q">
    <h5>Quantum layer (simulated here)</h5>
    <ul>
      <li>Hold a superposition over all 2<sup>n</sup> partitions</li>
      <li>Apply the cost unitary — phase-separate by solution quality</li>
      <li>Apply the mixer — interfere phases into amplitudes</li>
      <li>Return the cost expectation ⟨H⟩ for the current parameters</li>
    </ul>
  </div>
  <div class="col c">
    <h5>Classical layer (Dell hardware, always)</h5>
    <ul>
      <li>Build the grid model and derive the Ising couplings</li>
      <li>Propose and refine the (γ, β) parameters — the outer optimizer</li>
      <li>Evolve and store the statevector — the memory-bound work</li>
      <li>Decode bitstrings, verify feasibility, produce the operator schedule</li>
    </ul>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown(ui.card_html("Why the classical side dominates — and why that is the story", """
<p>In the NISQ era the quantum processor is a <strong>subroutine inside a classical loop</strong>,
not a replacement for it. Every optimizer iteration is a fresh circuit with new parameters,
so the outer loop runs hundreds of times; between iterations, all the work is classical.</p>
<p>Which means the practical bottleneck for hybrid quantum computing today is
<strong>classical infrastructure</strong> — memory capacity, memory bandwidth, and the ability to
keep sensitive infrastructure data on-premise. That is the layer Dell supplies, and it is the
layer that stays necessary when real QPUs arrive.</p>"""), unsafe_allow_html=True)

    if run is not None:
        conc = run.concentration or 0.0
        cols = st.columns(3)
        cols[0].markdown(ui.metric_html(
            "Search space", f"{2 ** run.model.n_qubits:,}", "partitions",
            f"{run.model.n_qubits} substations = {run.model.n_qubits} qubits"),
            unsafe_allow_html=True)
        cols[1].markdown(ui.metric_html(
            "Amplitude concentration", f"{conc:.1f}", "x uniform",
            "1.0x would mean the circuit did nothing",
            kind="ok" if conc > 2 else "warn"), unsafe_allow_html=True)
        cols[2].markdown(ui.metric_html(
            "Two-qubit rotations", f"{run.model.n_terms * run.result.get('layers', p):,}", "",
            f"{run.model.n_terms} couplings x {run.result.get('layers', p)} layers"),
            unsafe_allow_html=True)

        if run.exact:
            # is_optimal describes the plan ACTUALLY APPLIED, and post-selection
            # may deliberately prefer a thermally secure candidate over the
            # energy optimum — same framing rule as command_center.py.
            verdict = ("matches the exact optimum"
                       if run.is_optimal else
                       "deliberately differs from the objective's optimum — the "
                       "energy-minimising split failed the thermal screen, so a "
                       "different candidate from the quantum shortlist was applied")
            st.markdown(f"""
<div class="callout" style="border-left-color:var(--ok);
     background:rgba(61,220,151,.06);border-color:rgba(61,220,151,.32)">
  <div class="h" style="color:var(--ok)">Verified against ground truth</div>
  <p>Every one of the <strong>{2 ** run.model.n_qubits:,}</strong> possible partitions was
  also evaluated by brute force. The plan applied <strong>{verdict}</strong>.</p>
  <p>This check is only affordable below ~20 qubits — which is precisely why it matters
  that it runs <em>here</em>. Algorithm correctness gets established in the regime where
  truth is still computable, before scaling to sizes where it is not.</p>
</div>""", unsafe_allow_html=True)
    else:
        st.info("Run an optimization to populate live figures for this grid.")
