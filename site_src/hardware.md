# Why it needs this hardware

!!! quote "The whole argument, in two sentences"
    **Every qubit you add doubles the memory needed to simulate it. Turn on noise — which
    you must, to design anything that works on real hardware — and it squares instead.**

    Running a quantum algorithm is not the hard part. *Designing* one that survives a real,
    noisy, sparsely-connected device is the hard part, and that design work happens in
    classical simulation.

## The wall

<div class="figure-wrap" markdown>

--8<-- "figures/memory-wall.html"

</div>

A quantum state of n qubits is a list of 2ⁿ numbers — **17 GB at 30 qubits**, 34 GB at 31,
69 GB at 32. Not steep; *exponential*, which is worse.

Noise changes the shape entirely. Modelling it needs a **density matrix**, 2ⁿ × 2ⁿ instead
of 2ⁿ, so it costs **the square**.

| | measured on our GB10 |
|---|---|
| Clean simulation | **30 qubits** |
| With noise (exact) | **14 qubits** |

Same box, same second, less than half the problem size. The service reports both ceilings
from live free memory rather than a constant, because the GB10's unified memory is shared
with whatever else is resident.

## It is not only capacity — it is bandwidth

Every gate touches **the entire state**. One QAOA energy evaluation at 30 qubits makes
~62 passes over 16 GB — roughly a **terabyte of memory traffic for a single number**.

<div class="figure-wrap" markdown>

--8<-- "figures/scaling-measured.html"

</div>
<p class="figure-note">Measured, not modelled, using cuStateVec kernels on the GB10.</p>

## Noise you can actually afford

The 14-qubit ceiling is the limit of the *exact* method. Trajectories — many random
pure-state runs averaged — cost 2ⁿ each instead of 2^(2n).

<div class="figure-wrap" markdown>

--8<-- "figures/trajectory-convergence.html"

</div>
<p class="figure-note">The running average of random runs converging on the exact answer,
with its shrinking uncertainty band.</p>

<div class="figure-wrap" markdown>

--8<-- "figures/noise-memory.html"

</div>

At 30 qubits the exact method would need **17 exabytes**. Forty trajectories need **16 GB**
and eleven minutes, and are wrong by about 0.2%. Full treatment in
[note 04](notes/04-noise-without-the-density-matrix.md).

## Where classical compute falls off the cliff

<div class="figure-wrap" markdown>

--8<-- "figures/crossover.html"

</div>

A real quantum computer stores 50 qubits *in 50 qubits*. Writing that state down exactly
takes **18 petabytes** — beyond any machine that will be built.

**Two things this does not claim.** Not that quantum beats classical here. And not that
classical simulation stops dead at 50 qubits — that is the limit of *exact state vector*
simulation. Tensor networks reach much further on structured circuits; NVIDIA has
simulated 1,688 qubits of MaxCut, and noisy QAOA has been sampled at 476.

## The figure that matters is the coherent domain

A state vector cannot straddle a slow link. Every gate on a high-order qubit needs an
all-to-all exchange, so the simulation runs at the speed of the **worst link in the
domain** — 900 GB/s inside NVLink against 128 GB/s across PCIe Gen5, a **7× cliff**.

!!! quote ""
    An 8× RTX PRO 6000 node holds **768 GB** of GPU memory and simulates **32 qubits**.
    A 4-GPU H200 NVL island holds **564 GB** and simulates **35**.
    Less total memory, three more qubits, because the memory is coherent.

| Platform | Largest coherent domain | Domain memory | Clean | Noisy | Domains |
|---|---|---|---|---|---|
| Dell Pro Max GB10 | unified | 128 GB | 30* | 14* | 1 |
| XE7745/7740 · 8× RTX PRO 6000 | 1 GPU (no NVLink) | 96 GB | 32 | 16 | **8** |
| XE7740 · 8× H100 NVL | 2-GPU NVL2 | 188 GB | 33 | 16 | 4 |
| XE7745 · 8× H200 NVL | 4-GPU NVL4 | 564 GB | 35 | 17 | 2 |
| XE9780 · 8× HGX B200 | 8-GPU NVSwitch | 1.44 TB | 36 | 18 | 1 |
| XE9780/9785 · 8× HGX B300 NVL8 | 8-GPU NVSwitch | 2.16 TB | 37 | 18 | 1 |
| XE9785 · 8× AMD MI355X | 8-GPU Infinity Fabric | 2.30 TB | 37 | 18 | 1 |
| XE9712 · GB300 NVL72 | 72-GPU unified pool | 20.7 TB | 40 | 20 | 1 |

\* Measured. Every other row is arithmetic from published domain capacity.

**The ranking inverts by method.** The 8× RTX PRO 6000 node is the weakest configuration
on coherent domain — and among the best for trajectory-based noise work, where each run
fits on one GPU and eight run at once. Sizing by total GPU memory picks the wrong machine
about half the time. See [note 05](notes/05-which-method-which-machine.md).

## Why do this now, before the QPUs are ready?

**Because above the frontier, every failure looks the same.**

Below it you know the right answer, so when a result looks wrong you can tell which of
three things went wrong: your **algorithm**, the hardware's **noise**, or simply **not
enough shots**. Above it you have only your answer, and all three are indistinguishable.
You cannot calibrate an error-mitigation strategy without a noiseless reference.

And the frontier moves slowly — exact simulation gains roughly **one qubit per doubling of
memory**. Quantum hardware has been adding them faster. The gap widens structurally.

This project is a worked example. Two algorithm failures were caught here **only** because
brute force was still affordable: a deeper circuit scoring worse than a shallow one, and
an optimizer reporting convergence while returning an unevolved state. Neither announced
itself. On hardware, above the frontier, both would have looked like noise — and both
would have been believed.
