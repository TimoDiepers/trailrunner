# trailrunner

Model-based supply chain traversal for life cycle inventories.

A *model* is Python code for one process. It reads its parameters from a
[trailpack](https://github.com/TimoDiepers/trailpack) parquet file and answers
one question: *given this demand, what did I produce, what do I need, and what
did I emit?* The orchestrator walks the resulting demands outward through the
supply chain and accumulates an inventory.

Design: `docs/superpowers/specs/2026-09-21-trailrunner-design.md`

## Status

Early development. Inventory only — no impact characterization yet.

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

Optionally declare a `Coverage` to say where and when the model is valid, and
pass a `ParameterSet` at construction to read its numbers from a parquet file
instead of hard-coding them. A demand outside a model's coverage is reported
as an unresolved leaf with reason `coverage_excluded`, naming the model — so
remember to give the root `Flow` the `time` a time-bounded model expects.

## Example

```python
from trailrunner import Demand, Flow, Glossary, LocationHierarchy, Orchestrator, ParameterSet
from trailrunner.models.dac import CO2_CAPTURED, DirectAirCapture

params = ParameterSet.from_parquet(
    "dac_params.parquet",
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
glossary = Glossary([DirectAirCapture(params=params)])

report = Orchestrator(glossary).calculate(
    Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")
)

for (flow, unit), amount in report.inventory.items():
    print(f"{amount:>12.2f} {unit}  {flow.iri}")

for record in report.unresolved:
    print(f"unresolved: {record.demand.flow.iri} ({record.reason})")
```

A demand nobody models is reported as unresolved, never silently treated as
zero. Every parameter fallback used along the way shows up in
`report.provenance`.

[`examples/dac.ipynb`](examples/dac.ipynb) walks through this end to end with
explanation: writing the parameter parquet, location fallback and year
interpolation, why the regeneration heat has to be code, the cutoff leaves, and
the coverage boundary.
