---
icon: lucide/workflow
tags:
  - tutorial
---

# Writing a Model

A model is Python code for exactly one process. It never sees the rest of the supply
chain: it is handed a demand and returns what it produced, what it needs, and what it
emitted.

## The contract

```python
from trailrunner import Demand, Exchange, Flow, Model, Result

ELECTRICITY = "https://vocab.sentier.dev/products/electricity"
CO2 = "https://vocab.sentier.dev/flows/carbon-dioxide"


class GasTurbine(Model):
    produces = [ELECTRICITY]

    def apply(self, demand: Demand) -> Result:
        efficiency = 0.55
        fuel = demand.amount / efficiency

        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(
                    flow=Flow(
                        iri="https://vocab.sentier.dev/products/natural-gas",
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=fuel,
                    unit="kWh",
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                    amount=fuel * 0.2,
                    unit="kg",
                )
            ],
        )
```

Four rules the [`Runner`](../api/runner.md) checks on every result:

1. **Every exchange carries a unit.** An empty unit is a `ValidationError`.
2. **Production amounts are positive.**
3. **The demanded product is among the production**, in the demanded unit.
4. **Production covers the demand.** `apply` receives the full demanded amount and nothing
   downstream rescales, so producing less silently shrinks the whole inventory. Producing
   more is fine.

Breaking any of them raises [`ValidationError`](../api/errors.md) naming the model.

!!! note "Assign `produces`, never append to it"

    The base class default is an empty tuple, not a list, because a mutable class attribute
    is shared: a subclass appending instead of assigning would add its product to every
    other model in the run. A subclass may assign either a list or a tuple — only
    membership is ever tested.

!!! warning "Do not scale to a unit demand"

    `apply` gets `demand.amount` as it is. Writing a model that returns per-unit figures and
    expecting the orchestrator to multiply them will fail rule 4 — and would defeat the
    purpose, since nonlinearity is the reason a model is code at all.

## Nonlinear and context-dependent behaviour

This is what a coefficient cannot express. The direct air capture model that ships with
`trailrunner` makes the regeneration heat depend on ambient air:

```python
REFERENCE_TEMPERATURE = 10.0   # degC, the temperature the parquet figures assume
REFERENCE_HUMIDITY = 0.70      # dimensionless, likewise
TEMPERATURE_SENSITIVITY = 0.01 # per degC below reference
HUMIDITY_SENSITIVITY = 0.30    # per unit of relative humidity below reference


def ambient_penalty(temperature: float, humidity: float) -> float:
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    humidity_term = HUMIDITY_SENSITIVITY * (REFERENCE_HUMIDITY - humidity)
    return 1.0 + temperature_term + humidity_term
```

Colder or drier than the reference gives a multiplier above 1.0. The curve is deliberately
simple — the point is that the dependency lives in code, not that this particular response
is the right one.

## Parameters

Read the numbers from the model's [`ParameterSet`](../api/parameter_set.md), and pass the
row's provenance straight through so the report can state which parameters were used:

```python
class DirectAirCapture(Model):
    produces = [CO2_CAPTURED]
    coverage = Coverage(time_range=(2020, 2050))

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        penalty = ambient_penalty(row["temperature"], row["humidity"])
        heat = row["heat_demand"] * penalty * demand.amount

        return Result(
            production=[...],
            technosphere=[
                Demand(flow=heat_flow, amount=heat, unit=row.unit_of("heat_demand")),
            ],
            biosphere=[...],
            provenance=dict(row.provenance),
        )
```

Values are reachable as `row["heat_demand"]` or `row.heat_demand`. `row.unit_of(column)`
and `row.iri_of(column)` give the unit and the concept IRI declared for that column, so
units come from the data rather than being hardcoded in the model.

## Coverage

[`Coverage`](../api/coverage.md) declares where and when a model is valid. `None` on either
field means no restriction:

```python
from trailrunner import Coverage

coverage = Coverage(locations=frozenset({"CH", "DE"}), time_range=(2020, 2050))
```

A flow outside the coverage means the glossary does not select this model. If *no* model
covers the flow but one declares the product, the orchestrator records the demand as
`coverage_excluded` rather than `no_model_found`, with a `detail` naming the model — so the
reader fixes the coverage instead of hunting for a model that is already registered.

## Settings

[`Settings`](../api/settings.md) is one flat namespace for the whole run: scenario names, a
default year, model-specific switches. Anything varying per process belongs in that
process's parameter set instead.

```python
from trailrunner import Settings

model = GasTurbine(settings=Settings({"scenario": "SSP2"}))
model.settings.get("scenario", "baseline")
```

## Registering it

```python
from trailrunner import Glossary

glossary = Glossary([GasTurbine(params=turbine_params), DirectAirCapture(params=dac_params)])
```

Two registered models producing the same IRI for the same flow raise
[`AmbiguousModelMatch`](../api/errors.md). Narrow one of their coverages.
