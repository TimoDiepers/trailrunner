# sentier-trailrunner

`trailrunner` computes a life cycle inventory by orchestrating computational
models instead of static unit-process datasets.

A *model* stands for one process, most often Python code, and as readily a
plain measurement such as metered emissions for this process at this location
and time. Given a demand for one of its products it works out what other inputs
it needs to produce that, and what it emitted, reading its parameters from a
[trailpack](https://github.com/TimoDiepers/trailpack) parquet file rather than
hard-coding them.

Every flow crossing a model's boundary is an IRI from the hierarchical
[sentier vocabulary](https://vocab.sentier.dev), so the orchestrator can take a
model's further demands, work out which models produce them, and call those in
turn, cascading outward until nothing is left open.

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

- [The 5-minute tour](docs/showcase.md), one demand carried end to end with the
  real output at every step, built from [`examples/showcase.ipynb`](examples/showcase.ipynb)
- [Core Concepts](docs/content/concepts.md), the parts above one at a time
- [Quick Start](docs/content/getting_started/quickstart.md), a first calculation
- [Tutorial: an LCA from the CLI](docs/content/getting_started/cli.md), a supply
  chain, a score and a curve without writing Python
- [Writing a Model](docs/content/writing_a_model.md) · [Parameters](docs/content/parameters.md) · [Resolution](docs/content/resolution.md) · [Attribution](docs/content/attribution.md) · [Reading a Report](docs/content/reports.md) · [Assessment](docs/content/assessment.md) · [Figures](docs/content/figures.md)
- [`examples/coproduction.ipynb`](examples/coproduction.ipynb), what a run does
  when one model makes two things
- [`examples/dac.ipynb`](examples/dac.ipynb), the worked example end to end

## Status

Early development. Computes an inventory, plus static and time-explicit (dynamic)
impact characterization of it.

## Running from the shell

```bash
uv run trailrunner run \
    https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 \
    --amount 1000 --unit kg --location DK --year 2030 \
    --models examples/showcase_models.py
```

prints the report's summary and the supply chain it walked. Add `--method` for a score,
`--dynamic radiative_forcing` for a time-explicit result and `--out run.parquet` for the
full log; the [CLI tutorial](docs/content/getting_started/cli.md) goes through each.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## Writing a model

A model answers one demand. `apply` receives the **full** demanded amount, the
whole thing that was asked for, and must echo it back as production with the
same flow, the same unit, and an amount that covers the demand. Nothing
downstream rescales, so a model that under-produces would silently shrink the
inventory. The Runner rejects one that does.

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
