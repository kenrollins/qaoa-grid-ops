# How it works

!!! info "Read this first — what this demonstration is"
    This runs **exact state-vector simulation** of a quantum algorithm on classical Dell hardware.
    There is **no quantum processor** in the loop, and none is being claimed.

    That is the point. Exact simulation exposes the complete probability distribution, noiseless
    expectation, parameter landscape, and ground truth needed to develop an algorithm before
    transferring it to physical hardware.

## 1. One qubit per substation

Each substation gets one binary decision: **which island does it join?** With n substations there
are 2ⁿ assignments. Complementary bit strings exchange the names “island A” and “island B” but
describe the same physical split.

## 2. Two ways to construct the objective

### Analytic three-term QUBO

The baseline writes three preferences directly as a quadratic energy:

```
H(s) = A·Σ w_ij(1 − s_i s_j)/2  +  B·(Σ p_i s_i)²  +  C·(Σ s_i)²
        ↑ severed flow            ↑ island balance    ↑ non-degenerate
```

Here sᵢ is the ±1 island assignment, wᵢⱼ is solved base-case flow, and pᵢ is generation
minus load. The balance term couples every node to every other node, so the Hamiltonian is dense:
24 nodes produce 276 ZZ interactions per QAOA layer.

This formulation is transparent and exactly quadratic. Its limitation is equally precise: it
does not know the post-cut thermal loading or load shed that emerges only after solving the
surviving network.

### Emulator-fitted operational surrogate

At small sizes the emulator can enumerate or sample assignments and score each one with classical
DC power flow. The training target combines overload count, overload severity, load shed,
interrupted flow, and infeasibility. Least squares then projects those labels onto the pairwise
Ising basis:

```
L_power-flow(s) ≈ c + Σ_(i<j) J_ij s_i s_j
```

The fitted coefficients are a QUBO, so the quantum circuit and optimizer are unchanged. What
changes is the proxy they optimize.

The application retains training count, validation count, RMSE, and normalized RMSE with the run.
A high error is not hidden: overload thresholds and power redistribution contain behavior an
unconstrained quadratic model over the original bits cannot reproduce exactly. Auxiliary variables
or continued classical screening are the honest alternatives.

### What either objective is choosing between

<div class="figure-wrap" markdown>

--8<-- "figures/tradeoff.html"

</div>
<p class="figure-note">Every possible split, evaluated with power flow. Left-to-right is customer
load switched off; bottom-to-top is the worst surviving line loading.</p>

The bottom-left corner is empty. No optimizer can recover a solution that the physical grid does
not contain.

## 3. QAOA loads the dice

A Hadamard gate initializes equal amplitude over all assignments. Each QAOA layer alternates:

- a **cost unitary**, which changes phase according to the selected objective;
- a **mixer**, which converts phase differences into amplitude differences.

<div class="figure-wrap" markdown>

--8<-- "figures/interference.html"

</div>
<p class="figure-note">Probability begins uniform and concentrates on lower-energy assignments.
No bar reaches certainty: QAOA returns a distribution, not a guaranteed answer.</p>

## 4. A classical optimizer chooses the circuit angles

Each layer contributes a cost angle γ and mixer angle β. A classical optimizer repeatedly asks the
simulator for ⟨H⟩ and refines those parameters.

<div class="figure-wrap" markdown>

--8<-- "figures/landscape.html"

</div>

Exact emulation exposed a real bug here: sizing γ from the largest individual coupling searched
outside the informative basin on dense problems. Sizing it from the spread of the complete cost
distribution restored useful depth behavior. See [note 02](notes/02-why-depth-can-hurt.md).

## 5. Keep the four answers separate

“The quantum answer” is ambiguous in a hybrid workflow:

| Answer | What it establishes |
|---|---|
| Exact QUBO ground state | Whether the mathematical objective was optimized correctly |
| Ideal QAOA argmax | Where the complete simulated distribution peaks |
| Best finite-shot observation | What a measurement batch actually returned |
| Applied plan | What survived classical feasibility and thermal-security screening |

The applied plan may deliberately differ from the QAOA argmax. That is not quietly repaired output;
it is the visible boundary between the quadratic proxy and the grid physics it cannot express.

## 6. Admit physical reality one factor at a time

The Algorithm Lab holds the optimized angles fixed and compares:

1. exact ideal expectation;
2. finite-shot estimation, whose statistical error shrinks as 1/√shots;
3. generic depolarizing noise, which changes the state and reduces purity.

Density-matrix noise costs 2^(2n) memory rather than 2ⁿ, which is why the same GB10 reaches roughly
half as many qubits with exact noise enabled. The model is generic, not calibrated to a named QPU.

## 7. Preview device connectivity

The logical Hamiltonian is dense, while physical devices are usually sparse. The application
estimates the SWAP and two-qubit-gate expansion under fixed placement on all-to-all, square-grid,
ring, and linear graphs. The assumptions are printed with the result. A named hardware claim still
requires target-specific transpilation and calibration.

## Who does what

| Quantum layer, simulated here | Classical layer, always required |
|---|---|
| Hold amplitudes over 2ⁿ assignments | Build or fit the objective |
| Apply cost phases and mixer rotations | Optimize γ and β |
| Produce a measurement distribution | Label training partitions with power flow |
| Return samples on physical hardware | Check feasibility, security, and MW served |

The emulator is therefore not merely a stand-in for a QPU. It is the instrument used to inspect,
debug, compare, and validate the algorithm while those questions still have exact answers.
