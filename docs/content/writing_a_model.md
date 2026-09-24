---
icon: lucide/workflow
tags:
  - tutorial
---

# Writing a Model

A model is code for exactly one process. It never sees the rest of the supply chain: it
receives a demand and returns what it produced, what it needs, and what it emitted.

## The contract

```python
from trailrunner import Demand, Exchange, Flow, Model, Result

ELECTRICITY = "https://vocab.sentier.dev/products/electricity"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


class GasTurbine(Model):
    produces = [ELECTRICITY]

    def apply(self, demand: Demand) -> Result:
        fuel = demand.amount / 0.55  # kWh of gas per kWh of electricity
        here = dict(location=demand.flow.location, time=demand.flow.time)

        return Result(
            # what I made: the demand, echoed back
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            # what I need: queued and traversed in turn
            technosphere=[Demand(flow=Flow(iri=GAS, **here), amount=fuel, unit="kWh")],
            # what I emitted: summed into the inventory
            biosphere=[Exchange(flow=Flow(iri=CO2, **here), amount=0.2 * fuel, unit="kg")],
        )
```

Passing `location` and `time` on to every flow you create is what keeps the inventory
placed and dated. Change them where the process really does happen elsewhere or at another
time: the shipped `NaturalGasSupply` puts extraction at the gas's origin, and a
construction demand goes in the year the plant was built.

The [`Runner`](../api/runner.md) checks four rules on every result and raises
[`ValidationError`](../api/errors.md), naming the model, if one is broken:

1. **Every exchange carries a unit.** An empty unit is refused in all three lists.
2. **Production has the same sign as the demand.** In practice it is positive; only a
   substitution credit is a negative demand.
3. **The demanded product is in the production**, on the same IRI and in the demanded unit.
4. **Production covers the demand.** `apply` receives the full demanded amount and nothing
   downstream rescales it, so producing less would silently shrink the whole inventory.
   Producing more is fine. The comparison allows a relative 1e-9 of float noise.

!!! warning "Don't scale to a unit demand"

    `apply` gets `demand.amount` as it is. A model that returns per-unit figures and
    expects the orchestrator to multiply them fails rule 4. It would also give up the
    reason a model is code at all: its response need not be linear.

!!! note "Assign `produces`, never append to it"

    The base class default is an empty tuple, because a mutable class attribute would be
    shared: a subclass appending to it would add its product to every other model in the
    run. Assign a list or a tuple.

## Nonlinear and context-dependent behaviour

This is what a coefficient can't express. The shipped direct air capture model makes its
regeneration heat depend on the ambient air where and when it runs:

```python
REFERENCE_TEMPERATURE = 10.0    # degC, the temperature the parquet figures assume
REFERENCE_HUMIDITY = 0.70       # dimensionless, likewise
TEMPERATURE_SENSITIVITY = 0.01  # per degC below reference
HUMIDITY_SENSITIVITY = 0.30     # per unit of relative humidity below reference


def ambient_penalty(temperature: float, humidity: float) -> float:
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    humidity_term = HUMIDITY_SENSITIVITY * (REFERENCE_HUMIDITY - humidity)
    return 1.0 + temperature_term + humidity_term
```

Colder or drier air than the reference gives a multiplier above 1.0. The response is
deliberately simple. What matters is that the dependency lives in code, with the demand's
place and year as inputs.

## Reading parameters

Read numbers from the model's [`ParameterSet`](../api/parameter_set.md), take units from the
data rather than hard-coding them, and pass the row's provenance through so the report can
say which rows were used:

```python
from trailrunner import Coverage, Demand, Exchange, Flow, Model, Result


class DirectAirCapture(Model):
    produces = [CO2_CAPTURED]
    coverage = Coverage(time_range=(2020, 2050))

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        penalty = ambient_penalty(row["temperature"], row["humidity"])
        heat = row["heat_demand"] * penalty * demand.amount
        heat_flow = Flow(iri=HEAT, location=demand.flow.location, time=demand.flow.time)

        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(flow=heat_flow, amount=heat, unit=row.unit_of("heat_demand")),
            ],
            biosphere=[...],
            provenance=dict(row.provenance),
        )
```

Pass parameters in when you instantiate the model: `DirectAirCapture(params=params)`.
`row["heat_demand"]` and `row.heat_demand` both read a value. `row.unit_of(column)` and
`row.iri_of(column)` give the unit and concept IRI the file declares for that column.
`unit_of` raises [`MissingUnit`](../api/errors.md) if none is declared. See
[Parameters](parameters.md).

## A model that only measures

Nothing requires `apply` to compute anything. The shipped `MeteredCementPlant` reads one
row of stack-monitor data, normalised per tonne, and returns it:

```python
class MeteredCementPlant(Model):
    produces = [CEMENT]
    coverage = Coverage(time_range=(2018, 2025))

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        scale = demand.amount / 1000.0
        ...
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[Demand(flow=here(NATURAL_GAS), amount=row["metered_fuel"] * scale,
                                 unit=row.unit_of("metered_fuel")), ...],
            biosphere=[Exchange(flow=here(CO2_FOSSIL), amount=row["metered_co2"] * scale,
                                unit=row.unit_of("metered_co2"))],
            provenance={**row.provenance, "source": "measured"},
        )
```

`CementPlant` declares the same product with `Coverage(time_range=(2026, 2050))`. The
ranges don't overlap, so the year on the demand decides whether a measurement or a
calculation answers. The [CLI tutorial](getting_started/cli.md#3-change-the-year-and-a-different-model-answers)
shows the switch.

## Coverage

[`Coverage`](../api/coverage.md) declares where and when a model is valid. `None` on
either field means no restriction:

```python
from trailrunner import Coverage

coverage = Coverage(locations=frozenset({"CH", "DE"}), time_range=(2020, 2050))
```

`time_range` includes both ends. A restricted field also rejects a flow that doesn't state
it: a model with a `time_range` never answers an undated demand. A flow outside the coverage means the glossary doesn't
offer this model. If no model covers the flow but one declares the product, the demand is
recorded as `coverage_excluded`, not `no_model_found`, and its `detail` names the model.
That tells the reader to widen a coverage instead of looking for a model that is already
registered.

## Co-products and `supports`

A model that makes more than one product returns all of them in `production`, each with
the [`Property`](../api/flow.md) values an allocation rule might partition on:

```python
from trailrunner import Exchange, Flow, Property

production = [
    Exchange(flow=heat_flow, amount=100.0, unit="MJ",
             properties=(Property("price", 3.0, "EUR"), Property("energy", 100.0, "MJ"))),
    Exchange(flow=power_flow, amount=50.0, unit="MJ",
             properties=(Property("price", 9.0, "EUR"), Property("energy", 50.0, "MJ"))),
]
```

The model doesn't apply the rule. The Runner does, after `apply` returns, using the run's
[`AttributionSettings`](attribution.md). The model declares which rules it can honour in
`supports`:

```python
from trailrunner.core.settings import ALLOCATION_RULES

class CHP(Model):
    supports = frozenset({"none", "economic", "energy"})


class Boiler(Model):
    supports = ALLOCATION_RULES  # one product: every rule gives the same answer
```

The base-class default is `frozenset({"none"})`: a model says nothing about
multifunctionality until its author has thought about it. A run under a rule the model
doesn't list raises `UnsupportedAttribution`, so a model never silently answers a different
question. Every shipped model is monofunctional and declares all five rules.

## Settings

`self.settings` is the run's [`Settings`](../api/settings.md), passed in at construction.
Use `settings.get(key, default)` for run-wide switches such as a scenario name, and
`settings.attribution` for the run's normative choices:

```python
from trailrunner import Settings

model = GasTurbine(settings=Settings({"scenario": "SSP2"}))
model.settings.get("scenario", "baseline")   # "SSP2"
model.settings.attribution.capital           # "per_output"
```

The `Orchestrator`'s own `settings` controls allocation in the Runner. A model reading
`attribution.capital` (as `DirectAirCapture` and `CementPlant` do to amortize
construction) reads its own `settings`, so give both the same object.

## Registering it

In Python, put instances in a [`Glossary`](../api/glossary.md):

```python
from trailrunner import Glossary

glossary = Glossary([GasTurbine(), DirectAirCapture(params=dac_params)])
```

For the [CLI](getting_started/cli.md#10-bring-your-own-models), put the same instances in a
module-level list called `MODELS`:

```python
MODELS = [GasTurbine(), DirectAirCapture(params=dac_params)]
```

Two registered models that both cover the same product at the same place and year raise
[`AmbiguousModelMatch`](../api/errors.md). Narrow one of their coverages.

## Testing it

`Runner.validate` is the same check the orchestrator runs, callable on its own:

```python
from trailrunner import Demand, Flow, Runner

demand = Demand(flow=Flow(iri=ELECTRICITY, location="CH", time=2030), amount=10.0, unit="kWh")
Runner.validate(demand, GasTurbine().apply(demand), model=GasTurbine())
```

The shipped models in `trailrunner/models/` and their tests are worked examples of every
pattern on this page. [Example Models](../api/models.md) explains why each one is code.
