# Sources

Everything on this site is either **measured on the hardware**, **computed from first
principles**, or **taken from a source below**. Where a number is measured it carries the
machine and the date; where it is arithmetic — anything of the form 2ⁿ — it says so.
Nothing here is a vendor benchmark reproduced on trust.

## The algorithm

**Farhi, Goldstone & Gutmann — *A Quantum Approximate Optimization Algorithm* (2014)**
· [arXiv:1411.4028](https://arxiv.org/abs/1411.4028)
The original QAOA paper: the alternating cost/mixer ansatz, the variational parameters,
the approximation-ratio framing. The circuit this project runs is exactly this
construction.

**Zhou, Wang, Choi, Pichler & Lukin — *QAOA: Performance, Mechanism, and Implementation on
Near-Term Devices*** · [arXiv:1812.01041](https://arxiv.org/abs/1812.01041)
Why optimal parameters vary smoothly with depth, the INTERP heuristic, and the adiabatic
framing. Directly motivated our parameter-initialisation work — we tried layer-wise INTERP,
found it starved the optimizer at small step budgets, and settled on the annealing-inspired
linear ramp the same framing suggests.

**McClean et al. — *Barren plateaus in quantum neural network training landscapes***
· [arXiv:1803.11173](https://arxiv.org/abs/1803.11173)
Exponentially vanishing gradients. The theoretical backdrop for our second failure: an
optimizer reporting convergence while returning the unevolved state.

## Simulation limits

**NVIDIA — *cuQuantum sets a quantum simulation world record***
· [blogs.nvidia.com](https://blogs.nvidia.com/blog/cuquantum-world-record/)
:material-alert: **This source corrected a claim we had wrong.** An earlier draft asserted
classical simulation becomes impossible past ~50 qubits. That holds only for exact state
vector simulation; tensor networks reach 1,688 qubits of MaxCut. The correction is stated
on the hardware page rather than waiting to be challenged.

***Pilot-Wave Simulator*** · [Quantum 10, 2173 (2026)](https://quantum-journal.org/papers/q-2026-07-23-2173/)
Samples ideal and noisy QAOA at up to 476 qubits via tensor networks — the more pointed
version of the same correction, because it reaches that scale *with noise*.

**NERSC — *Record-breaking 45-qubit simulation***
· [phys.org](https://phys.org/news/2017-07-record-breaking-qubit-quantum-simulation-nersc.html)
Anchors the exact-state-vector wall with a real result rather than arithmetic.

**Mahadev — *Classical Verification of Quantum Computations* (2018)**
· [arXiv:1804.01082](https://arxiv.org/abs/1804.01082)
Keeps our "why now" argument honest. Classical verification is not impossible in
principle; it is currently impractical. Which is why we argue about *error attribution*
rather than claiming verification is unobtainable.

## Power systems

**NERC — *Balancing and Frequency Control***
· [nerc.com](https://www.nerc.com/comm/RSTC_Reliability_Guidelines/Reference_Document_NERC_Balancing_and_Frequency_Control.pdf)
How interconnections hold 60 Hz. Source for the frequency instrument and for treating a
generation deficit as a frequency event. Our frequency model is a deliberately simplified
proportional response, labelled as such in the code.

**Overbye & Weber — *Visualization of Large Scale Power Systems***
· [TAMU](https://overbye.engr.tamu.edu/wp-content/uploads/sites/146/2022/06/EPSOM98_Overbye_Weber.pdf)
Animated flow indicators and how to represent transmission loading legibly.

**PowerWorld — animated flows and contouring**
· [powerworld.com](https://www.powerworld.com/WebHelp/Content/MainDocumentation_HTML/Animated_Flows_Options.htm)
The convention that arrow size and speed encode MW or percentage loading.

**Smart Grid Wide-Area Transmission System Visualization** · [Engineering (2016)](https://www.sciencedirect.com/science/article/pii/S2095809916300273)
The voltage-class colour convention our diagram follows.

## Hardware sizing

**Dell PowerEdge sourcebooks and GPU Qualification Matrix** · [Dell AI Factory](https://www.dell.com/en-us/lp/dt/nvidia-ai)
Per-platform GPU topology: which GPUs form an NVLink domain, how large, per-GPU memory,
and in-domain versus off-domain bandwidth.

:material-information: **Which GPUs actually form a domain, on these platforms.** The
**RTX PRO 6000 Blackwell** has no NVLink — NVIDIA dropped it from this line after Ampere.
Eight of them in an XE7745 are eight independent PCIe Gen5 devices at 128 GB/s, so the
coherent domain is **one GPU at 96 GB**, however much memory the chassis holds in total.
The 4-GPU NVL4 domain on that same chassis belongs to **H200 NVL**, at 564 GB.

That pairing is the clearest case of the ranking inversion on the
[Hardware](hardware.md) page: 768 GB across eight RTX PRO 6000s simulates **fewer** qubits
than 564 GB across four H200 NVL, because only the second is one domain.

## Built on

**NVIDIA cuQuantum — cuStateVec** · [docs.nvidia.com](https://docs.nvidia.com/cuda/cuquantum/)
GPU-accelerated quantum circuit simulation. The QAOA mixer executes through cuStateVec;
the rest of the state-vector work is CuPy.

**NetworkX · SciPy · Plotly · Streamlit** — graph modelling and connectivity checks,
the COBYLA outer loop, the charting layer, the application framework.

## What is ours, and therefore unsourced

The three-term islanding QUBO, the DC power-flow model and its rating calibration, the N-1
contingency screen, the physics-aware post-selection over QAOA's measured shortlist, the
trajectory implementation, and every measured figure. They are described in the code with
their reasoning and their known limitations — including the ones that make the demo look
worse.
