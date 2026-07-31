# How it works

!!! info "Read this first — what this demonstration is"
    This runs **exact statevector simulation** of a quantum algorithm on classical Dell
    hardware. There is **no quantum processor** in the loop, and none is being claimed.

    That is the point, not a limitation. QAOA is a **hybrid** algorithm: even with a
    perfect QPU attached, the overwhelming majority of the work — building the
    Hamiltonian, proposing parameters, converging the optimizer, decoding results into an
    islanding plan — runs on classical infrastructure. Simulating the quantum half today
    on the same hardware that will *drive* a real QPU tomorrow is how the algorithm, the
    encoding, and the operator tooling get developed and validated now.

## 1. One qubit per substation

Each substation gets a single binary decision: **which island does it join?** That is one
qubit. With 12 substations there are 2¹² = **4,096** ways to split the grid.

## 2. The objective becomes an energy function

Three competing requirements become one cost function whose lowest energy is the best
plan: minimise the power severed by the cut, keep each island able to supply its own load,
and forbid the degenerate "one island, cut nothing" answer.

```
H(s) = A·Σ w_ij(1 − s_i s_j)/2  +  B·(Σ p_i s_i)²  +  C·(Σ s_i)²
        ↑ severed flow            ↑ island balance    ↑ non-degenerate
```

The balance term couples **every node to every other node**, so the problem is dense
all-to-all rather than the sparse transmission graph — at 24 nodes, 276 two-qubit
rotations per layer.

### What the objective is choosing between

<div class="figure-wrap" markdown>

--8<-- "figures/tradeoff.html"

</div>
<p class="figure-note">Every possible split, evaluated with real power flow. Left-to-right:
customer load switched off. Bottom-to-top: how hard the worst surviving line is pushed.</p>

**The bottom-left corner is empty**, and no amount of better optimization changes that.
Safety is bought by switching off customers. See [note 03](notes/03-what-a-qubo-cannot-express.md)
for what this means for the encoding.

## 3. Superposition — every plan at once

<div class="figure-wrap" markdown>

--8<-- "figures/interference.html"

</div>
<p class="figure-note">Every bar is one possible answer; its height is how likely the
machine is to return it. Press play. The green bars are the best answer and its mirror
image.</p>

It starts flat — the machine is guessing. Each layer marks the good answers, then makes
those marks interfere, so probability drains out of bad answers and piles into good ones.

Notice what does **not** happen: no bar reaches certainty. QAOA does not find the answer,
it **loads the dice**.

## 4. The part that is actually hard — choosing the dials

<div class="figure-wrap" markdown>

--8<-- "figures/landscape.html"

</div>
<p class="figure-note">The surface a classical optimizer must search, for a single layer.
Every point is one setting of γ and β. Darker is better.</p>

- **β matters more than you would guess.** A broad good band and a broad bad band, sharply
  separated. Choose β badly and no value of γ rescues the run.
- **There is real structure here, and that is good news.** The flatness that kills
  optimizers — the *barren plateau* — emerges as systems grow. **You develop where you can
  still see the slope, then scale.**
- **The two vertical lines are a real bug from this project.** We sized the γ search range
  from the largest single coupling instead of the spread of the whole cost function.
  Deeper circuits scored *worse* than shallow ones until it was fixed —
  [note 02](notes/02-why-depth-can-hurt.md).

## 5. Measure — the bitstring is the plan

Reading the register collapses it to one bitstring, and that bitstring *is* the
operational answer: bit *i* says which island substation *i* joins.

What comes back is a ranked shortlist, not a single answer. Each candidate is screened
with a real power flow, and the electrically securest is applied.

## Who does what

| Quantum layer (simulated here) | Classical layer (Dell hardware, always) |
|---|---|
| Hold a superposition over all 2ⁿ partitions | Build the grid model, derive the couplings |
| Apply the cost unitary — phase-separate by quality | Propose and refine (γ, β) — the outer optimizer |
| Apply the mixer — interfere phases into amplitudes | Evolve and store the state vector |
| Return ⟨H⟩ for the current parameters | Decode bitstrings, verify feasibility, produce the schedule |

In the NISQ era the quantum processor is a **subroutine inside a classical loop**. Every
optimizer iteration is a fresh circuit; between iterations, all the work is classical.
Which means the practical bottleneck for hybrid quantum computing today is **classical
infrastructure**.
