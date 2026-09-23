# sentier-trailrunner

Model-based supply chain traversal for life cycle inventories.

Installs as `sentier-trailrunner`, imports as `trailrunner`.

A life cycle inventory is usually a matrix of fixed coefficients: one row per
process, and a separate dataset for every location, year and technology variant
of the same activity, because a coefficient cannot adapt to context on its own.
`trailrunner` replaces those static datasets with computational models that call
each other — one per process, most often Python code but as readily a plain
measurement, each working out what it needs to meet *this* demand and what it
emitted, from parameters read out of a
[trailpack](https://github.com/TimoDiepers/trailpack) parquet file.

Every flow crossing a model's boundary is an IRI from the hierarchical
[sentier vocabulary](https://vocab.sentier.dev), so the orchestrator can take a
model's further demands, work out which models produce them, and call those in
turn — cascading outward until nothing is left open.

```mermaid
flowchart TB
    D([initial demand]) --> Q[[Queue]]
    Q -->|pop demand| C{{ResolutionChain}}
    C -->|ask model tier: who can offer?| G[(Glossary: available models)]
    G -->|Offer: model + demand| C
    C -->|nobody offers| X[cutoff, with a reason]
    C -->|selected offer| R[Runner]
    R -->|apply demand| M[Model: your code]
    M -->|Result| R
    R -->|Result - technosphere demands| Q
    R -->|Result - biosphere flows| I[(inventory)]
    X --> L[(Log)]
    R --> L
    L --> P([Report])
```

## Documentation

- [The 5-minute tour](docs/showcase.md) — one demand carried end to end, with
  the real output at every step, built from [`examples/showcase.ipynb`](examples/showcase.ipynb)
- [Core Concepts](docs/content/concepts.md) — the parts above, one at a time
- [Quick Start](docs/content/getting_started/quickstart.md) — a first calculation
- [Writing a Model](docs/content/writing_a_model.md) · [Parameters](docs/content/parameters.md) · [Resolution](docs/content/resolution.md) · [Attribution](docs/content/attribution.md) · [Assessment](docs/content/assessment.md)
- [`examples/dac.ipynb`](examples/dac.ipynb) — the worked example, end to end

Design: `docs/superpowers/specs/2026-09-21-trailrunner-design.md`

## Status

Early development. Computes an inventory, plus static and time-explicit (dynamic)
impact characterization of it.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## Writing a model

A model answers one demand. `apply` receives the **full** demanded amount, not
a unit demand, and must echo it back as production: the same flow, the same
unit, and an amount that covers what was asked. Nothing downstream rescales,
so a model that under-produces would silently shrink the inventory; the Runner
rejects it instead.

```python
from trailrunner import Demand, Exchange, Flow, Model, Result

HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


class MyBoiler(Model):
    produces = (HEAT,)  # the product IRIs this model can make

    def apply(self, demand: Demand) -> Result:
        gas = demand.amount / 40.0  # kg of gas per MJ of heat, 90% efficient
        here = dict(location=demand.flow.location, time=demand.flow.time)
        return Result(
            # what I made: the demand, echoed back
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            # what I need: pushed onto the queue and traversed in turn
            technosphere=[Demand(flow=Flow(iri=GAS, **here), amount=gas, unit="kg")],
            # what I emitted: accumulated into the inventory
            biosphere=[Exchange(flow=Flow(iri=CO2, **here), amount=2.75 * gas, unit="kg")],
        )
```

[Writing a Model](docs/content/writing_a_model.md) covers the rest: declaring a
`Coverage`, reading parameters from a parquet file, and what the report says
about a demand nobody models.
