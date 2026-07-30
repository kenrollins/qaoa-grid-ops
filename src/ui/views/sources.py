"""Tab: Sources — where every claim on this demo came from.

Annotated deliberately. A bare link list is not a citation, it is a gesture. Each
entry says what is actually in the source and where this project used it, so a
reader can check a specific claim rather than being handed homework.

Grouped by what they underwrite: the quantum algorithm, the classical
simulation limits, the power-systems modelling, and the visual conventions.
"""

from __future__ import annotations

import streamlit as st


def _src(title: str, url: str, what: str, used: str, kind: str = "") -> str:
    tag = f'<span class="srckind">{kind}</span>' if kind else ""
    return f"""
<div class="source">
  <div class="srchead"><a href="{url}" target="_blank" rel="noopener">{title}</a>{tag}</div>
  <div class="srcwhat"><b>What it is:</b> {what}</div>
  <div class="srcused"><b>How this demo used it:</b> {used}</div>
</div>"""


def render() -> None:
    st.markdown("""
<div class="callout">
  <div class="h">On sourcing</div>
  <p>Everything on the other tabs is either <b>measured on this hardware</b>, <b>computed
  from first principles</b>, or <b>taken from a source below</b>. Where a number is measured
  it carries the machine and the date; where it is arithmetic (anything of the form 2ⁿ) it
  says so. Nothing here is a vendor benchmark reproduced on trust.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("### The algorithm")
    st.markdown(
        _src("Farhi, Goldstone & Gutmann — <i>A Quantum Approximate Optimization Algorithm</i> (2014)",
             "https://arxiv.org/abs/1411.4028",
             "The original QAOA paper. Defines the alternating cost/mixer ansatz, the "
             "variational parameters (γ, β), and the approximation-ratio framing.",
             "The circuit this demo runs is exactly this construction: |+⟩<sup>⊗n</sup>, then "
             "p alternating layers of exp(−iγH<sub>C</sub>) and exp(−iβH<sub>M</sub>). Our "
             "implementation lives in <code>src/simulation/qaoa_core.py</code>.",
             "foundational") +
        _src("Zhou, Wang, Choi, Pichler & Lukin — <i>QAOA: Performance, Mechanism, and Implementation on Near-Term Devices</i>",
             "https://arxiv.org/abs/1812.01041",
             "Analyses why QAOA's optimal parameters vary smoothly with depth, and introduces "
             "INTERP and FOURIER heuristics that seed depth p+1 from the optimum at depth p. "
             "Also frames QAOA as a Trotterised adiabatic sweep.",
             "Directly motivated our parameter-initialisation work. We first tried a "
             "layer-wise INTERP schedule, found it starved the optimiser at the small step "
             "budgets this demo uses, and settled on the annealing-inspired linear ramp that "
             "the same adiabatic framing suggests. Both the failure and the fix are on the "
             "<b>Under the Hood</b> tab.",
             "parameter strategy") +
        _src("McClean, Boixo, Smelyanskiy, Babbush & Neven — <i>Barren plateaus in quantum neural network training landscapes</i>",
             "https://arxiv.org/abs/1803.11173",
             "Shows that for many variational ansätze the gradient vanishes exponentially "
             "with qubit count, leaving the optimisation landscape essentially flat — the "
             "'barren plateau'.",
             "The theoretical backdrop for the second failure we hit: an optimiser that "
             "reported convergence while returning the unevolved |+⟩ state. Our case was "
             "budget starvation rather than a true barren plateau, but the failure mode — "
             "confident convergence on nothing — is the same one this literature warns about.",
             "why optimisers stall"),
        unsafe_allow_html=True)

    st.markdown("### Simulation limits — the memory argument")
    st.markdown(
        _src("NVIDIA — <i>cuQuantum sets a quantum simulation world record</i>",
             "https://blogs.nvidia.com/blog/cuquantum-world-record/",
             "NVIDIA simulated a 1,688-qubit MaxCut QAOA circuit using cuTensorNet on the "
             "Selene supercomputer — tensor-network contraction, not statevector.",
             "This is the source that <b>corrected a claim we had wrong</b>. An earlier draft "
             "asserted classical simulation becomes impossible past ~50 qubits. That is true "
             "only for exact statevector simulation; tensor networks go far beyond it on "
             "structured, low-entanglement circuits — including QAOA, our own problem class. "
             "The Under the Hood tab now states this explicitly rather than waiting to be "
             "challenged on it.",
             "corrected our claim") +
        _src("<i>Pilot-Wave Simulator: exact classical sampling from ideal and noisy quantum circuits up to hundreds of qubits</i> — Quantum (2026)",
             "https://quantum-journal.org/papers/q-2026-07-23-2173/",
             "Samples from ideal and noisy QAOA circuits at up to 476 qubits, including "
             "depolarising and amplitude-damping noise, via tensor-network methods.",
             "Second source for the same correction, and the more pointed one: it reaches "
             "hundreds of qubits <i>with noise</i>, which is the regime we describe as "
             "expensive. Our density-matrix approach is exact and general; theirs is "
             "structure-exploiting and approximate. Both facts belong on the page.",
             "noisy simulation at scale") +
        _src("NERSC — <i>Record-breaking 45-qubit quantum computing simulation</i>",
             "https://phys.org/news/2017-07-record-breaking-qubit-quantum-simulation-nersc.html",
             "A 45-qubit full statevector simulation on Cori at NERSC, near the practical "
             "ceiling for exact statevector methods on a leadership-class machine.",
             "Anchors the ~50-qubit exact-statevector wall on the cliff chart with a real "
             "result rather than pure arithmetic. Our own measured GB10 ceiling — 30 clean "
             "qubits — sits on the same curve, far lower down.",
             "the statevector wall") +
        _src("Mahadev — <i>Classical Verification of Quantum Computations</i> (2018)",
             "https://arxiv.org/abs/1804.01082",
             "The first protocol by which a purely classical verifier can check the result of "
             "an efficient quantum computation, sound under the hardness of Learning With "
             "Errors. Later work reduces the round complexity.",
             "Keeps our 'why now' argument honest. Classical verification of quantum "
             "computation is not impossible in principle — it exists. It is currently "
             "impractical (hundreds of auxiliary qubits per delegated measurement), which is "
             "why we argue about <i>error attribution</i> rather than claiming verification "
             "is unobtainable.",
             "keeps us honest"),
        unsafe_allow_html=True)

    st.markdown("### Power systems — the problem being solved")
    st.markdown(
        _src("NERC — <i>Reference Document: Balancing and Frequency Control</i>",
             "https://www.nerc.com/comm/RSTC_Reliability_Guidelines/Reference_Document_NERC_Balancing_and_Frequency_Control.pdf",
             "The reliability reference for how interconnections hold 60 Hz: Area Control "
             "Error, governor droop, primary/secondary/tertiary control, and reserve "
             "deployment after a disturbance.",
             "Source for the frequency instrument and for treating a generation deficit as a "
             "frequency event rather than a bookkeeping shortfall. Our frequency model is a "
             "deliberately simplified proportional response, labelled as such in "
             "<code>power_flow.py</code> — it is not a dynamic stability simulation.",
             "frequency & reserves") +
        _src("Overbye & Weber — <i>Visualization of Large Scale Power Systems</i>",
             "https://overbye.engr.tamu.edu/wp-content/uploads/sites/146/2022/06/EPSOM98_Overbye_Weber.pdf",
             "Foundational paper on power-system visualisation: animated flow indicators, "
             "contouring, and how to represent transmission loading so operators can read a "
             "large network at a glance.",
             "The basis for the one-line diagram: arrows whose direction follows real power "
             "flow and whose density tracks loading, and colour bands keyed to percentage of "
             "rating rather than to raw MW.",
             "how operators read a grid") +
        _src("PowerWorld — <i>Animated flows and contouring</i>",
             "https://www.powerworld.com/WebHelp/Content/MainDocumentation_HTML/Animated_Flows_Options.htm",
             "Documents the industry-standard convention that animated arrow size and speed "
             "encode either absolute MW flow or percentage loading of a line.",
             "We chose percentage loading for arrow speed, so a heavily loaded corridor "
             "visibly runs harder — which is what makes the post-fault screen legible without "
             "reading a single number.",
             "animation conventions") +
        _src("Smart Grid Wide-Area Transmission System Visualization — <i>Engineering</i> (2016)",
             "https://www.sciencedirect.com/science/article/pii/S2095809916300273",
             "Survey of wide-area visualisation practice, including the voltage-class colour "
             "convention (345 kV light blue, 115 kV grey) and the use of line thickness to "
             "distinguish voltage levels.",
             "Our kV colour and width scheme comes straight from here, so the backbone is "
             "visually obvious to anyone who has seen a real EMS display.",
             "voltage-class colours"),
        unsafe_allow_html=True)

    st.markdown("### Built on")
    st.markdown(
        _src("NVIDIA cuQuantum — cuStateVec",
             "https://docs.nvidia.com/cuda/cuquantum/",
             "GPU-accelerated libraries for quantum circuit simulation. cuStateVec handles "
             "statevector operations; cuTensorNet handles tensor-network contraction.",
             "The GB10 compute service runs on <code>cuquantum-python-cu12</code> plus CuPy. "
             "This was <b>forced, not chosen</b>: <code>qiskit-aer-gpu</code> ships x86_64 "
             "wheels only and cannot be installed on the GB10's aarch64 silicon at all, which "
             "is why simulation is a separate service from the UI.",
             "the GPU path") +
        _src("NetworkX · SciPy · Plotly · Streamlit",
             "https://networkx.org/",
             "Graph modelling, the derivative-free COBYLA optimiser used for the classical "
             "outer loop, the charting layer, and the application framework.",
             "NetworkX builds the transmission topology and does the connectivity checks that "
             "decide whether an islanding plan is electrically viable; SciPy's COBYLA tunes "
             "(γ, β); the entire control-room view is Plotly.",
             "the rest of the stack"),
        unsafe_allow_html=True)

    st.markdown("""
<div class="callout">
  <div class="h">What is ours, and therefore unsourced</div>
  <p>The three-term islanding QUBO, the DC power-flow model and its rating calibration, the
  N-1 contingency screen, the physics-aware post-selection over QAOA's measured shortlist,
  and every measured figure on the GB10 are original to this project. They are described in
  the code with their reasoning and their known limitations — including the ones that make
  the demo look worse, such as the objective having no thermal term.</p>
</div>""", unsafe_allow_html=True)
