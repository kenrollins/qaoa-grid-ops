# The demonstration

Three steps. The whole point of the first is that nothing is wrong yet.

## ① Normal operation

A transmission network carrying its load, every line inside its rating.

<div class="figure-wrap" markdown>

--8<-- "figures/grid-normal.html"

</div>

Squares are power stations, circles are substations delivering load. Line colour and
thickness are **voltage class** — the light, heavy lines are the high-voltage backbone.
In the live application the arrows move, faster where a line works harder.

## ② A line fails

<div class="figure-wrap" markdown>

--8<-- "figures/grid-faulted.html"

</div>
<div class="figure-wrap" markdown>

--8<-- "figures/loading-key.html"

</div>

**The power that line was carrying did not stop. It rerouted** onto whatever lines remain,
and those lines were not built for it.

On the default scenario, losing the 345 kV corridor carrying 111 MW takes peak line
loading from **54% to 137%**, with two lines past their rating. A line held above its
rating overheats, sags, and its own protection trips it out — which pushes its power onto
the next line, which trips too. That chain reaction is how a blackout happens, and it is
how the 2003 Northeast blackout began.

The operator has minutes, sometimes seconds, to decide where to deliberately break the
grid apart so the failure cannot spread. With 12 substations there are **4,096** ways to
do it.

## ③ The quantum algorithm chooses

QAOA searches all 4,096 splits at once and returns a **ranked shortlist** rather than a
single answer. Each candidate is then checked against real power-flow physics, and the
electrically securest is applied.

That last step matters because the cost function has **no notion of thermal line ratings**
— the power flowing on a line after a cut depends on the whole surviving network, which a
QUBO cannot express. The quantum stage proposes; classical physics disposes.

!!! warning "An honest result, kept on screen"
    Exhaustive search over all 4,096 partitions finds **64** electrically feasible and only
    **10** thermally secure — and every one of those 10 sheds **128–163 MW of 325 MW**.
    There is no answer that both keeps all load energised and respects thermal limits on
    this contingency. Security costs roughly 40% of demand. That is a property of the grid,
    not a failure of the optimizer.

## Try it

The live application is interactive and passkey-protected. This site is the public
overview; the figures here are exported from the same engine.
