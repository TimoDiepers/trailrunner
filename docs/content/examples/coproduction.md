---
icon: lucide/split
tags:
  - example
  - notebook
  - attribution
---

<!-- Generated from examples/coproduction.ipynb by docs/convert_notebooks.py.
     Edit the notebook, then re-run the script; edits here are lost. -->

<div hidden data-source-edit-url="https://github.com/TimoDiepers/trailrunner/edit/main/examples/coproduction.ipynb" data-source-view-url="https://github.com/TimoDiepers/trailrunner/blob/main/examples/coproduction.ipynb"></div>

# When a model makes two things

The [5-minute tour](../../showcase.md) leaves one thread hanging. Its Danish
cement works buys electricity, and a grid-mix model answers — one product, one
burden, nothing to argue about.

Real suppliers are often not so tidy. A combined heat and power plant makes
electricity *and* heat from one lot of fuel, and how that fuel's burden splits
between the two is a choice. `trailrunner` will not make it for you.

This notebook picks the thread up: the same cement demand, but the works is on
an industrial estate and its electricity comes from a CHP that also sells heat
into a district network. `GasCHP` stands in for `GridElectricity`, because two
models producing the same IRI would be an `AmbiguousModelMatch` rather than a
choice.

`GasCHP`'s efficiencies and prices are invented. What is being demonstrated is
the rule's effect on the answer, and the fact that the run records which rule it
used — not this particular plant.

Nothing here touches the network.

??? note "Show the notebook's path bootstrap"

    ```python
    import sys
    from pathlib import Path

    EXAMPLES = Path.cwd() if (Path.cwd() / "showcase_models.py").exists() else Path.cwd() / "examples"
    sys.path.insert(0, str(EXAMPLES))

    from showcase_models import MODELS
    from trailrunner import (
        AttributionSettings, Demand, Exchange, Flow, Glossary, LocationHierarchy,
        Model, Orchestrator, ParameterSet, Property, Result, Settings,
    )
    from trailrunner.assessment import Method, assess
    from trailrunner.models import cement
    from trailrunner.models.cement import CEMENT, CO2_FOSSIL, ELECTRICITY, NATURAL_GAS
    from trailrunner.models.electricity import GridElectricity
    from trailrunner.resolution import (
        GeneralisingProvider, ModelProvider, PystLabels, PystTaxonomy, ResolutionChain,
    )

    HIERARCHY = LocationHierarchy({"CH": "RER", "DK": "RER", "FR": "RER", "RER": "GLO"})
    VOCAB = PystLabels(EXAMPLES / "pyst_labels.json", client=None)

    DEMAND = Demand(
        flow=Flow(iri=CEMENT, location="DK", time=2030), amount=1000.0, unit="kg"
    )
    print(DEMAND.amount, DEMAND.unit, VOCAB.label(CEMENT))
    ```

        1000.0 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers

## A model that co-produces

`GasCHP` declares two products. It also declares which allocation rules it can
honour — and `none` is not among them, because there is no honest way to answer
a demand for its heat without saying what to do with its electricity.

Each product carries a `price` property. Economic allocation needs one; a rule
that partitions by something else would need that something else instead, and
the model states what it has rather than guessing what the study will want.

```python
DISTRICT_HEAT = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730"


class GasCHP(Model):
    """Gas-fired combined heat and power. Illustrative efficiencies and prices.

    Declares ``electricity`` as its product and hands back district heat
    alongside it. ``supports`` leaves out ``none`` deliberately: there is no
    honest way to answer a demand for its electricity without saying what to do
    with its heat.

    Each product carries a ``price`` property, because economic allocation
    needs one. A rule partitioning on something else would need that something
    else instead, and the model states what it has rather than guessing what
    the study will want.
    """

    produces = [ELECTRICITY]
    supports = frozenset({"economic", "substitution"})  # it co-produces

    electrical_efficiency = 0.35
    heat_efficiency = 0.45
    co2_per_mj_fuel = 0.056  # the same factor examples/gas_power_params.parquet carries
    electricity_price = 0.10  # EUR/kWh
    heat_price = 0.02         # EUR/MJ

    def apply(self, demand):
        here = {"location": demand.flow.location, "time": demand.flow.time}
        fuel = demand.amount * 3.6 / self.electrical_efficiency  # kWh -> MJ of gas
        heat = fuel * self.heat_efficiency
        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit,
                         properties=(Property("price", demand.amount * self.electricity_price, "EUR"),)),
                Exchange(flow=Flow(iri=DISTRICT_HEAT, **here), amount=heat, unit="MJ",
                         properties=(Property("price", heat * self.heat_price, "EUR"),)),
            ],
            technosphere=[Demand(flow=Flow(iri=NATURAL_GAS, **here), amount=fuel, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CO2_FOSSIL, **here),
                                amount=fuel * self.co2_per_mj_fuel, unit="kg")],
            provenance={"fuel_mj": fuel},
        )
```

```python
cement_params = ParameterSet.from_parquet(
    EXAMPLES / "cement_params.parquet", hierarchy=HIERARCHY
)

# GasCHP replaces GridElectricity rather than joining it. Both declare
# fi_17100, and Glossary.resolve treats two candidates for one flow as a data
# error rather than resolving it by silent precedence -- which is the right
# call, and the reason this is a swap.
MODELS_PLUS = [
    *(model for model in MODELS if not isinstance(model, GridElectricity)),
    GasCHP(),
]
tier1 = ModelProvider(Glossary(MODELS_PLUS))
taxonomy = PystTaxonomy(EXAMPLES / "pyst_cache.json", client=None)  # client=None: no network
CHAIN = ResolutionChain([tier1, GeneralisingProvider(tier1, hierarchy=HIERARCHY, taxonomy=taxonomy)])


def walk(allocation):
    settings = Settings(attribution=AttributionSettings(allocation=allocation))
    return Orchestrator(CHAIN, settings=settings).calculate(DEMAND)
```

## The refusal

The default rule is `none`, which means *this study has not chosen*. The run
reaches the CHP, finds a second product, and stops.

The refusal happens in the `Runner`, between applying the model and validating
what came back, so the model neither makes the choice nor sees it.

```python
from trailrunner import UnallocatedCoProduction

try:
    walk("none")
except UnallocatedCoProduction as refusal:
    print("allocation='none' ->", refusal)
```

    allocation='none' -> GasCHP returned co-products (https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730) but the run's allocation rule is 'none'; model it monofunctionally or choose a rule

## Choose a rule, and the run carries it

Two rules, the same model, the same 1000 kg of cement.

`economic` partitions the CHP's burden between heat and electricity by their
revenue. `substitution` instead credits the electricity: the co-product goes
back on the queue as a *negative* demand, is answered by someone other than the
CHP, and brings its own cutoffs, counted separately.

```python
GWP100 = Method(
    rows=[
        {"flow_iri": "https://vocab.sentier.dev/flows/co2-fossil", "flow_unit": "kg",
         "location": "GLO", "cf": 1.0},
        {"flow_iri": "https://vocab.sentier.dev/flows/ch4-fossil", "flow_unit": "kg",
         "location": "GLO", "cf": 29.8},
        {"flow_iri": "https://vocab.sentier.dev/flows/n2o", "flow_unit": "kg",
         "location": "GLO", "cf": 273.0},
    ],
    unit="kg CO2-eq",
    name="IPCC AR6 GWP100",
    hierarchy=HIERARCHY,
)

runs = {rule: walk(rule) for rule in ("economic", "substitution")}

for rule, run in runs.items():
    score = assess(run, GWP100).score
    print(f"{rule:>13}: {score:>9.1f} kg CO2-eq   ({run.summary().splitlines()[1]})")

credited = runs["substitution"]
chp_node = [node for node in credited.nodes if node.demand.flow.iri == ELECTRICITY][0]
print()
print("what the CHP node recorded under substitution:")
for key, value in credited.attribution[chp_node.id].items():
    print(f"  {key}: {value}")
```

         economic:     566.0 kg CO2-eq   (4 unresolved (generalisation_exhausted: 4))
     substitution:     593.7 kg CO2-eq   (5 unresolved (generalisation_exhausted: 5, of which 1 on a credit branch))
    what the CHP node recorded under substitution:
      allocation: substitution
      share: 1.0
      substituted: ['https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730']

Two numbers for one question, and the gap between them is set by `GasCHP`'s
invented prices, since economic allocation partitions by revenue. That is the
point rather than a weakness of the example: the rule moves the answer, the
choice belongs to the study, and the report records which one ran.

---

- The tour this picks up from: [trailrunner in five minutes](../../showcase.md)
- The rules themselves: [Attribution](../attribution.md)
