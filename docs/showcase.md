---
icon: lucide/footprints
tags:
  - tutorial
  - notebook
---

<!-- Generated from examples/showcase.ipynb by docs/convert_notebooks.py.
     Edit the notebook, then re-run the script; edits here are lost. -->

<div hidden data-source-edit-url="https://github.com/TimoDiepers/trailrunner/edit/main/examples/showcase.ipynb" data-source-view-url="https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb"></div>

# trailrunner in five minutes

What is the impact of **1000 kg of Portland cement, in Denmark, in 2030?**

Ordinary practice answers that by modelling static unit processes.
trailrunner instead builds on computational process model.

Every flow crossing a model's boundary — what it makes, what it needs, what it
emits — is a concept from the hierarchical
[sentier vocabulary](https://vocab.sentier.dev). That is what lets two models
connect to each other.

Nothing here touches the network. The vocabulary lookups come from the committed
`examples/pyst_cache.json` and `examples/pyst_labels.json`, the background
datasets from `examples/background_pack.parquet`, and the parameters from the
committed parquet files beside this notebook.

??? note "Show the notebook's path bootstrap"

    ```python
    import sys
    from pathlib import Path

    # Run from anywhere: nbconvert starts the kernel in the notebook's directory,
    # a human might start it from the repository root.
    EXAMPLES = Path.cwd() if (Path.cwd() / "showcase_models.py").exists() else Path.cwd() / "examples"
    sys.path.insert(0, str(EXAMPLES))

    from trailrunner import Demand, Flow
    from trailrunner.models.cement import CEMENT
    from trailrunner.resolution import PystLabels

    DEMAND = Demand(
        flow=Flow(iri=CEMENT, location="DK", time=2030), amount=1000.0, unit="kg"
    )

    # What a flow *is* is an IRI in https://vocab.sentier.dev -- not a free-text
    # name. The vocabulary also knows what that concept is called, and those names
    # are cached beside this notebook, so every print below reads in English with
    # no network and no token.
    VOCAB = PystLabels(EXAMPLES / "pyst_labels.json", client=None)


    def name(iri: str, width: int | None = None) -> str:
        """The vocabulary's name for a concept, else the IRI's last segment."""
        label = VOCAB.label(iri) or iri.rsplit("/", 1)[-1]
        if width is not None and len(label) > width:
            label = label[: width - 1] + "…"  # a column, not a claim: tree() prints it in full
        return label


    print(DEMAND.amount, DEMAND.unit, DEMAND.flow.iri)
    print("that IRI is:", name(DEMAND.flow.iri))
    print("where:", DEMAND.flow.location, " when:", DEMAND.flow.time)
    ```

        1000.0 kg https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440
        that IRI is: Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers
        where: DK  when: 2030

## 1. What a model does

A [`Model`](api/model.md) has one method. It takes a
[`Demand`](api/flow.md) and returns a [`Result`](api/result.md), answering
three questions at once. What did I make, what do I need, what did I emit.

```python
from trailrunner import LocationHierarchy, ParameterSet
from trailrunner.models import cement
from trailrunner.models.cement import CementPlant

HIERARCHY = LocationHierarchy({"CH": "RER", "DK": "RER", "FR": "RER", "RER": "GLO"})
cement_params = ParameterSet.from_parquet(
    EXAMPLES / "cement_params.parquet", hierarchy=HIERARCHY
)
cement_model = CementPlant(params=cement_params)

answer = cement_model.apply(DEMAND)

# where and when get their own columns: a flow's location and year are part of
# its identity, not an annotation on its name.
print(f"{'':>13}  {'amount':>8} {'unit':<4} {'flow':<44} {'where':<5} {'when':>5}")
for field in ("production", "technosphere", "biosphere"):
    for exchange in getattr(answer, field):
        flow = exchange.flow
        print(
            f"{field:>13}  {exchange.amount:>8.1f} {exchange.unit:<4} "
            f"{name(flow.iri, 44):<44} {flow.location:<5} {flow.time:>5}"
        )
print(f"{'provenance':>13}  {answer.provenance}")
```

                     amount unit flow                                         where  when
       production    1000.0 kg   Portland cement, aluminous cement, slag cem… DK     2030
     technosphere    1125.0 kg   Gypsum; anhydrite; limestone flux; limeston… DK     2030
     technosphere    2475.0 MJ   Natural gas, liquefied or in the gaseous st… DK     2030
     technosphere      10.0 kg   Quicklime, slaked lime and hydraulic lime    DK     2030
     technosphere     100.0 kWh  electricity                                  DK     2030
        biosphere     397.5 kg   co2-fossil                                   DK     2030
        biosphere     138.6 kg   co2-fossil                                   DK     2030
       provenance  {'location_requested': 'DK', 'location_used': 'DK', 'location_fallback': False, 'time_requested': 2030, 'time_used': 2030, 'time_interpolated': False, 'source': 'modelled'}

Every name printed there — `Quicklime, slaked lime and hydraulic lime`,
`co2-fossil` — is the vocabulary's label for a real concept.

Because the cement plant is a computation model, we can do additional calculations, taking into account the context the process is run in.
This data is retrieved from a set of parquet files based on their embedded metadata, created with [`trailpack`](https://github.com/TimoDiepers/trailpack).
For example, fuel demands could increase with higher ambient moisture and lower temperatures:

```python
penalty = moisture_penalty(row["moisture"], row["temperature"])
fuel = row["fuel_demand"] * clinker * penalty
```

The same 1000 kg, asked for in four different places and years:

```python
print(f"{'where':>6} {'when':>6} {'moisture':>9} {'degC':>6} {'penalty':>9} {'gas [MJ]':>10}")
for location in ("DK", "RER"):
    for year in (2030, 2040):
        feed = cement_params.at(location=location, time=year)
        answer = cement_model.apply(
            Demand(flow=Flow(iri=CEMENT, location=location, time=year),
                   amount=1000.0, unit="kg")
        )
        gas = [d for d in answer.technosphere if d.flow.iri == cement.NATURAL_GAS][0]
        print(
            f"{location:>6} {year:>6} {feed['moisture']:>9.3f} {feed['temperature']:>6.1f} "
            f"{cement.moisture_penalty(feed['moisture'], feed['temperature']):>9.3f} "
            f"{gas.amount:>10.1f}"
        )
```

     where   when  moisture   degC   penalty   gas [MJ]
        DK   2030     0.040   10.0     1.000     2475.0
        DK   2040     0.040   11.0     0.996     2099.6
       RER   2030     0.060    9.0     1.044     2923.2
       RER   2040     0.055   10.0     1.030     2447.3

Not every process needs computing, though: where a process has real history —
years of stack-monitor readings, say — trailrunner reads that instead of
calculating it, and reaches for a computational model only where there is
none, such as a future year or a process that does not exist yet.

The plant has a stack monitor and years of historic readings.
`MeteredCementPlant` declares the same product IRI as `CementPlant` and a
[`Coverage`](api/coverage.md) that ends where the other one begins.
Nothing else changes: [`Glossary`](api/glossary.md)`.resolve` already
filters candidates by coverage, so the year on the demand decides which one
answers.

```python
coverage = Coverage(time_range=(2018, 2025))  # MeteredCementPlant
coverage = Coverage(time_range=(2026, 2050))  # CementPlant
```

```python
from showcase_models import MODELS
from trailrunner import Glossary, Orchestrator

for year in (2023, 2030):
    run = Orchestrator(Glossary(MODELS)).calculate(
        Demand(flow=Flow(iri=CEMENT, location="DK", time=year), amount=1000.0, unit="kg")
    )
    root = run.nodes[0]
    direct = [e for e in root.result.biosphere if e.flow.iri == cement.CO2_FOSSIL]
    print(f"{year}  answered by {root.model}")
    print(f"      source: {run.provenance[root.id]['source']}")
    print(f"      direct CO2: {sum(e.amount for e in direct):>6.1f} kg "
          f"in {len(direct)} exchange(s)")
    for exchange in direct:
        print(f"          {exchange.amount:>6.1f} kg")
```

    2023  answered by MeteredCementPlant
          source: measured
          direct CO2:  562.0 kg in 1 exchange(s)
               562.0 kg
    2030  answered by CementPlant
          source: modelled
          direct CO2:  536.1 kg in 2 exchange(s)
               397.5 kg
               138.6 kg

Look at the biosphere flows above: 2023 has one, 2030 has two. The model
knows which kilogram came from the limestone and which from the flame,
because it computed them separately. The meter does not: a stack monitor sees
one plume and cannot tell you what made it.

Note what the metered model still sends upstream. Its gas, its lime and its
electricity are *inputs* — their emissions happen somewhere else — so they go
back on the queue and are answered by whoever supplies them, exactly as the
computed model's are. A meter at the fence line says nothing about what happens
beyond it.

The normative choices a study still has to make, and a model that co-produces,
are in [When a model makes two things](content/examples/coproduction.md) and
[Attribution](content/attribution.md).

## 2. Models find each other through a vocabulary

Every flow is identified by an IRI from the hierarchical
[sentier vocabulary](https://vocab.sentier.dev). A `Demand` for
`.../BONSAI2025.1/fi_37420` finds whoever declared that same IRI in `produces`,
with no name matching and no unit guessing in between. That is what lets two
models written by two people compose at all, and it is what the orchestrator uses
to walk outward.

```mermaid
%%{init: {'layout': 'elk'}}%%
flowchart TB
    D([initial demand]) --> Q
    Q[[Queue]]

    Q -->|pop demand| C{{ResolutionChain}}
    C -->|who offers?| G[(Glossary: available models)]
    G -->|Offer: model + demand| C

    C -->|nobody offers| L[(Log)]
    C -->|selected offer| R[Runner]

    R -->|apply demand| M[Model: your code]
    M -->|Result| R

    R -->|Result: technosphere demands| Q
    R -->|Result: biosphere flows| I[(inventory)]

    R --> L
    L --> P([Report])

    classDef resolution fill:#2dd4bf22,stroke:#2dd4bf
    classDef execution fill:#f59e0b22,stroke:#f59e0b
    classDef record fill:#8b5cf622,stroke:#8b5cf6
    class C,G resolution
    class R,M execution
    class L,P record
```

*Legend: resolution (teal), execution (amber), record (violet).*

`Orchestrator.calculate` is a `while queue:` and little else. Pop a demand, ask
the chain who can answer it, hand the offer to the [`Runner`](api/runner.md),
push the `Result`'s technosphere demands back on, write everything to the
[`Log`](api/log.md). Here's the queue for the cement example:

```python
from showcase_models import MODELS  # the same list `trailrunner run --models` loads
from trailrunner import Glossary, Orchestrator
from trailrunner.resolution import ModelProvider, ResolutionChain


class Narrating(ResolutionChain):
    """A chain that says what it was asked. The Orchestrator takes any chain."""

    def offer(self, demand, exclude=()):
        offer = super().offer(demand, exclude=exclude)
        who = type(offer.model).__name__ if offer else "cutoff (nobody offered)"
        flow = demand.flow
        print(
            f"pop {demand.amount:>9.4g} {demand.unit:<4} {name(flow.iri, 32):<32} "
            f"{flow.location:<5} {flow.time:>5}  -> {who}"
        )
        return offer


tier1 = ModelProvider(Glossary(MODELS))
print(f"{'':>3} {'amount':>9} {'unit':<4} {'flow':<32} {'where':<5} {'when':>5}  -> answered by")
first = Orchestrator(Narrating([tier1])).calculate(DEMAND)
```

           amount unit flow                             where  when  -> answered by
    pop      1000 kg   Portland cement, aluminous ceme… DK     2030  -> CementPlant
    pop      1125 kg   Gypsum; anhydrite; limestone fl… DK     2030  -> cutoff (nobody offered)
    pop      2475 MJ   Natural gas, liquefied or in th… DK     2030  -> NaturalGasSupply
    pop        10 kg   Quicklime, slaked lime and hydr… DK     2030  -> cutoff (nobody offered)
    pop       100 kWh  electricity                      DK     2030  -> GridElectricity
    pop     68.75 Nm3  natural-gas-at-production        NO     2030  -> NaturalGasExtraction
    pop     50.53 tkm  natural-gas-transport-offshore-… NO     2030  -> NaturalGasOffshorePipelineTransport
    pop     8.466 kWh  electricity-natural-gas          DK     2030  -> GasPower
    pop     84.66 kWh  electricity-wind                 DK     2030  -> cutoff (nobody offered)
    pop      12.7 kWh  electricity-hydro                DK     2030  -> cutoff (nobody offered)
    pop 8.995e-08 unit pipeline-natural-gas-long-dista… NO     2030  -> cutoff (nobody offered)
    pop   0.01306 Nm3  natural-gas-at-production        NO     2030  -> NaturalGasExtraction
    pop     16.54 MJ   natural-gas-burned-in-gas-turbi… NO     2030  -> cutoff (nobody offered)
    pop 5.862e-06 tkm  transport-freight-lorry-16t-32t  NO     2030  -> cutoff (nobody offered)
    pop 5.862e-05 kg   disposal-used-mineral-oil-10-pe… NO     2030  -> cutoff (nobody offered)
    pop     49.16 MJ   Natural gas, liquefied or in th… DK     2030  -> NaturalGasSupply
    pop     1.365 Nm3  natural-gas-at-production        NO     2030  -> NaturalGasExtraction
    pop     1.004 tkm  natural-gas-transport-offshore-… NO     2030  -> NaturalGasOffshorePipelineTransport
    pop 1.786e-09 unit pipeline-natural-gas-long-dista… NO     2030  -> cutoff (nobody offered)
    pop 0.0002594 Nm3  natural-gas-at-production        NO     2030  -> NaturalGasExtraction
    pop    0.3285 MJ   natural-gas-burned-in-gas-turbi… NO     2030  -> cutoff (nobody offered)
    pop 1.164e-07 tkm  transport-freight-lorry-16t-32t  NO     2030  -> cutoff (nobody offered)
    pop 1.164e-06 kg   disposal-used-mineral-oil-10-pe… NO     2030  -> cutoff (nobody offered)

```python
print(first.summary())
print()
print(first.tree(labels=VOCAB.label))  # the vocabulary's names, where it has one
```

    11 nodes, 11 inventory entries
    12 unresolved (no_model_found: 12)
    0 proxies
    attribution: allocation=none, capital=per_output
    1000 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @DK/2030  [model: CementPlant]
      2475 MJ Natural gas, liquefied or in the gaseous state @DK/2030  [model: NaturalGasSupply]
        68.75 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
        50.5312 tkm natural-gas-transport-offshore-pipeline-long-distance @NO/2030  [model: NaturalGasOffshorePipelineTransport]
          0.0130625 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
          8.99456e-08 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030  [cutoff: no_model_found]
          16.5404 MJ natural-gas-burned-in-gas-turbine @NO/2030  [cutoff: no_model_found]
          5.86162e-06 tkm transport-freight-lorry-16t-32t @NO/2030  [cutoff: no_model_found]
          5.86162e-05 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030  [cutoff: no_model_found]
      100 kWh electricity @DK/2030  [model: GridElectricity]
        8.46561 kWh electricity-natural-gas @DK/2030  [model: GasPower]
          49.1551 MJ Natural gas, liquefied or in the gaseous state @DK/2030  [model: NaturalGasSupply]
            1.36542 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
            1.00358 tkm natural-gas-transport-offshore-pipeline-long-distance @NO/2030  [model: NaturalGasOffshorePipelineTransport]
              0.00025943 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
              1.78638e-09 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030  [cutoff: no_model_found]
              0.328503 MJ natural-gas-burned-in-gas-turbine @NO/2030  [cutoff: no_model_found]
              1.16416e-07 tkm transport-freight-lorry-16t-32t @NO/2030  [cutoff: no_model_found]
              1.16416e-06 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030  [cutoff: no_model_found]
        84.6561 kWh electricity-wind @DK/2030  [cutoff: no_model_found]
        12.6984 kWh electricity-hydro @DK/2030  [cutoff: no_model_found]
      1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @DK/2030  [cutoff: no_model_found]
      10 kg Quicklime, slaked lime and hydraulic lime @DK/2030  [cutoff: no_model_found]

The fuel is no longer a leaf. `NaturalGasSupply` answers the kiln's 2475 MJ,
turns them into wellhead volume and route length, and hands those to a gas
field and to `NaturalGasOffshorePipelineTransport` — a model reverse-engineered
from the BAFU/ecoinvent pipeline datasets, which was registered in this list
long before anything asked it for a tonne-kilometre.

Note where the pipeline runs. The supply model places both demands at the
*origin*, so the Danish kiln's gas is transported in `NO` and its leakage is
priced at the Norwegian shelf's low-leakage tier, not at a Danish average that
does not exist. The pipeline's own inputs — compressor fuel, the pipe itself,
a maintenance lorry — are cutoffs, and they are in the report with a reason.

## 3. A demand nobody answers is relaxed along the vocabulary

[`ResolutionChain`](api/resolution.md) is a list of providers, asked in
order, and the first offer wins. Tier 1 is the computational models. Every later tier is a concession, and the tier that
made it writes what it conceded into the node's resolution.

**Tier 2 generalises the demand.** The plant blends in a little hydrated lime,
so it asks for `fi_37420`, "Quicklime, slaked lime and hydraulic lime". Nobody
produces it. One `skos:broader` step reaches `fi_3742` — spelled identically,
and produced by nobody either. The *second* step reaches `fi_374`, "Plaster,
lime and cement", and a supplier registered there can answer.

Notice what that concession costs. `fi_374` is an average over plaster, lime
**and cement** — so a lime demand was answered by a category containing the very
product this plant is making. It is the best answer available and a poor answer
in substance, and it is written at the node rather than lost.

**Tier 2 also relaxes context.** Place and year are not the only things a
demand can ask for. This plant's burners take gas at 4 bar, so its gas demand
carries `pressure=4 bar` in its [`Flow`](api/flow.md)'s `context`. `NaturalGasSupply`
declares in its `Coverage` that it delivers at 5 bar, so tier 1 does not match
it. The practitioner allows pressure to be met up to 1 bar *higher*, never
lower, because gas can be throttled down at the burner and cannot be pushed
up there. Tier 2 moves the demand to 5 bar and records the move. The gas power
plant's own gas demand names no pressure, so any supplier answers it and it
stays a plain tier-1 match.

**Tier 3 borrows a dataset.** Given its `Fleet`, `CementPlant` demands each
kiln's construction in the year that kiln was built, and a construction model
turns that into steel and aluminium taken from the curated background pack.

`BinderSupply` and `CementKilnConstruction` below are written in this notebook
rather than shipped, because nothing in the repository produces `fi_374`. Their
burdens and material intensities are invented. The `skos:broader` walk, the
step budget, the pack lookup, the completeness flag and the construction pulse
are the library, and every block of output below is what it actually printed.

```python
from trailrunner import Exchange, Fleet, Model, Result
from trailrunner.core.settings import ALLOCATION_RULES
from trailrunner.models.cement import CEMENT_KILN, CO2_FOSSIL

BINDERS = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_374"
STEEL = "https://vocab.sentier.dev/products/steel-low-alloyed"
ALUMINIUM = "https://vocab.sentier.dev/products/aluminium-primary"


class BinderSupply(Model):
    """Plaster, lime and cement, averaged. Illustrative burden.

    Registered two skos:broader steps above the lime the plant asks for, which
    is the point: it cannot answer a demand for lime, only the generalised
    demand that tier 2 makes out of it after the first step finds nobody.

    One consequence worth naming rather than leaving as a trap: a cement demand
    in a year *neither* CementPlant nor MeteredCementPlant covers would relax
    fi_37440 -> fi_3744 -> fi_374 and land here, because cement is also a
    binder. The tour never asks for such a year. A study that might should
    narrow this model's coverage rather than rely on that.
    """

    produces = [BINDERS]
    supports = ALLOCATION_RULES  # monofunctional

    co2_per_kg = 0.9  # kg CO2 per kg of binder, calcination and kiln fuel together

    def apply(self, demand):
        here = {"location": demand.flow.location, "time": demand.flow.time}
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[],
            biosphere=[Exchange(flow=Flow(iri=CO2_FOSSIL, **here),
                                amount=demand.amount * self.co2_per_kg, unit="kg")],
            provenance={"binder_average": True},
        )


class CementKilnConstruction(Model):
    """What a kiln line is made of. Illustrative material intensities."""

    produces = [CEMENT_KILN]
    supports = ALLOCATION_RULES

    steel_per_capacity = 0.012      # kg steel per kg/year of clinker capacity
    aluminium_per_capacity = 0.0008  # kg aluminium, likewise

    def apply(self, demand):
        here = {"location": demand.flow.location, "time": demand.flow.time}
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(flow=Flow(iri=STEEL, **here),
                       amount=demand.amount * self.steel_per_capacity, unit="kg"),
                Demand(flow=Flow(iri=ALUMINIUM, **here),
                       amount=demand.amount * self.aluminium_per_capacity, unit="kg"),
            ],
            biosphere=[],
        )
```

```python
from trailrunner import ProxySettings
from trailrunner.resolution import (
    BackgroundPack, BackgroundProvider, GeneralisingProvider, PystTaxonomy,
)

# The kilns that were actually built. The 1985 line is past its lifetime by
# 2030, so the fleet leaves it out and the report never mentions it.
FLEET_ROWS = [
    {"kiln": "dk-old", "location": "DK", "build_year": 1985, "capacity": 250_000_000.0, "lifetime": 40.0},
    {"kiln": "dk-1", "location": "DK", "build_year": 2026, "capacity": 400_000_000.0, "lifetime": 40.0},
    {"kiln": "dk-2", "location": "DK", "build_year": 2029, "capacity": 800_000_000.0, "lifetime": 40.0},
]
fleet = Fleet(FLEET_ROWS, units={"capacity": "kg/year", "lifetime": "year"}, hierarchy=HIERARCHY)

MODELS_PLUS = [
    # Burners at 4 bar; NaturalGasSupply delivers at 5.
    CementPlant(params=cement_params, fleet=fleet, burner_pressure=4.0),
    *(model for model in MODELS if not isinstance(model, CementPlant)),
    BinderSupply(),
    CementKilnConstruction(),
]

tier1 = ModelProvider(Glossary(MODELS_PLUS))
# client=None: no network, ever. Every skos:broader answer comes from the file.
taxonomy = PystTaxonomy(EXAMPLES / "pyst_cache.json", client=None)
# Pressure may be met up to 1 bar higher, never lower: gas is throttled at
# the burner, not boosted there.
PROXY = ProxySettings(context_tolerance={"pressure": (0.0, 1.0)})
tier2 = GeneralisingProvider(tier1, settings=PROXY, hierarchy=HIERARCHY, taxonomy=taxonomy)
pack = BackgroundPack.from_parquet(EXAMPLES / "background_pack.parquet", hierarchy=HIERARCHY)
CHAIN = ResolutionChain([tier1, tier2, BackgroundProvider(pack)])

report = Orchestrator(CHAIN).calculate(DEMAND)
print(report.summary())
print()
print(report.tree(labels=VOCAB.label))
```

    18 nodes, 13 inventory entries
    11 unresolved (generalisation_exhausted: 11)
    6 proxies (4 incomplete)
    attribution: allocation=none, capital=per_output
    1000 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @DK/2030  [model: CementPlant]
      2475 MJ Natural gas, liquefied or in the gaseous state @DK/2030 (pressure=4 bar)  [proxy: context: pressure 4 bar -> 5 bar]
        68.75 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
        50.5312 tkm natural-gas-transport-offshore-pipeline-long-distance @NO/2030  [model: NaturalGasOffshorePipelineTransport]
          0.0130625 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
          8.99456e-08 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030  [cutoff: generalisation_exhausted]
          16.5404 MJ natural-gas-burned-in-gas-turbine @NO/2030  [cutoff: generalisation_exhausted]
          5.86162e-06 tkm transport-freight-lorry-16t-32t @NO/2030  [cutoff: generalisation_exhausted]
          5.86162e-05 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030  [cutoff: generalisation_exhausted]
      10 kg Quicklime, slaked lime and hydraulic lime @DK/2030  [proxy: product: fi_37420 -> fi_374]
      100 kWh electricity @DK/2030  [model: GridElectricity]
        8.46561 kWh electricity-natural-gas @DK/2030  [model: GasPower]
          49.1551 MJ Natural gas, liquefied or in the gaseous state @DK/2030  [model: NaturalGasSupply]
            1.36542 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
            1.00358 tkm natural-gas-transport-offshore-pipeline-long-distance @NO/2030  [model: NaturalGasOffshorePipelineTransport]
              0.00025943 Nm3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
              1.78638e-09 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030  [cutoff: generalisation_exhausted]
              0.328503 MJ natural-gas-burned-in-gas-turbine @NO/2030  [cutoff: generalisation_exhausted]
              1.16416e-07 tkm transport-freight-lorry-16t-32t @NO/2030  [cutoff: generalisation_exhausted]
              1.16416e-06 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030  [cutoff: generalisation_exhausted]
        84.6561 kWh electricity-wind @DK/2030  [cutoff: generalisation_exhausted]
        12.6984 kWh electricity-hydro @DK/2030  [cutoff: generalisation_exhausted]
      8.33333 kg/year cement-kiln @DK/2026  [model: CementKilnConstruction]
        0.1 kg steel-low-alloyed @DK/2026  [background: unit_process, incomplete]
        0.00666667 kg aluminium-primary @DK/2026  [background: unit_process, incomplete]
      16.6667 kg/year cement-kiln @DK/2029  [model: CementKilnConstruction]
        0.2 kg steel-low-alloyed @DK/2029  [background: unit_process, incomplete]
        0.0133333 kg aluminium-primary @DK/2029  [background: unit_process, incomplete]
      1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @DK/2030  [cutoff: generalisation_exhausted]

```python
lime_node = [node for node in report.nodes if node.demand.flow.iri == cement.LIME][0]
for key, value in report.proxies[lime_node.id].items():
    print(f"{key:>12}: {value}")

print()
print("     asked, in words:", name(cement.LIME))
print("  answered, in words:", name(BINDERS))
print()
# The rung in between, which the walk passed through and nobody produces.
STEP_ONE = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_3742"
print("one step up would be:", name(STEP_ONE), "-- same words, still nobody")
```

           model: BinderSupply
     relaxations: ['product: fi_37420 -> fi_374']
           asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37420 @DK/2030
        answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_374 @DK/2030
            tier: generalising
         asked, in words: Quicklime, slaked lime and hydraulic lime
      answered, in words: Plaster, lime and cement
    one step up would be: Quicklime, slaked lime and hydraulic lime -- same words, still nobody

```python
gas_node = [node for node in report.nodes
            if node.demand.flow.iri == cement.NATURAL_GAS and node.demand.flow.context][0]
for key, value in report.proxies[gas_node.id].items():
    print(f"{key:>12}: {value}")
```

           model: NaturalGasSupply
     relaxations: ['context: pressure 4 bar -> 5 bar']
           asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020 @DK/2030 [pressure=4 bar]
        answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020 @DK/2030 [pressure=5 bar]
            tier: generalising

Every concession is deliberate, ordered by the practitioner, and written down.

```python
from trailrunner import viz
from trailrunner.assessment import Method, assess

# IPCC AR6 GWP100, stated here rather than read from a background database:
# the mapping from a gas to its warming potential is a fact about the gas.
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

assessment = assess(report, GWP100)
sankey_figure = viz.sankey(report, assessment=assessment)
sankey_figure
```

<div class="plotly-figure" data-plotly-height="780" data-plotly-name="sankey" data-plotly-layout='{"margin":{"l":20,"r":150,"t":60,"b":20}}'><script type="application/json">{"data":[{"link":{"color":"rgba(134,142,150,0.45)","source":[0,0,0,0,0,1,1,3,4,4,5,5,7,8,14,14,16],"target":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17],"value":[4.957150513333333,9.0,2.8511404778517377,0.01805333333333333,0.03610666666666666,4.697916666666666,0.2592338466666667,2.8511404778517377,0.007559999999999999,0.010493333333333334,0.015119999999999998,0.020986666666666667,0.0008926041666666667,0.09845230580872731,0.0933037492177277,0.005148556590999603,1.7727712351368266e-05]},"node":{"color":["#0b7285","#f59f00","#f59f00","#0b7285","#0b7285","#0b7285","#0b7285","#0b7285","#0b7285","#868e96","#868e96","#868e96","#868e96","#0b7285","#0b7285","#0b7285","#0b7285","#0b7285"],"label":["fi_37440 (CementPlant) [model]","fi_12020 (NaturalGasSupply) [generalising]","fi_37420 (BinderSupply) [generalising]","fi_17100 (GridElectricity) [model]","cement-kiln (CementKilnConstruction) [model]","cement-kiln (CementKilnConstruction) [model]","natural-gas-at-production (NaturalGasExtraction) [model]","natural-gas-transport-offshore-pipeline-long-distance (NaturalGasOffshorePipelineTransport) [model]","electricity-natural-gas (GasPower) [model]","steel-low-alloyed (BackgroundDataset) [background]","aluminium-primary (BackgroundDataset) [background]","steel-low-alloyed (BackgroundDataset) [background]","aluminium-primary (BackgroundDataset) [background]","natural-gas-at-production (NaturalGasExtraction) [model]","fi_12020 (NaturalGasSupply) [model]","natural-gas-at-production (NaturalGasExtraction) [model]","natural-gas-transport-offshore-pipeline-long-distance (NaturalGasOffshorePipelineTransport) [model]","natural-gas-at-production (NaturalGasExtraction) [model]"],"pad":18,"thickness":14},"type":"sankey"}],"layout":{"margin":{"b":40,"l":40,"r":20,"t":50},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","template":{"data":{"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"barpolar":[{"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"#E5ECF6","showlakes":true,"showland":true,"subunitcolor":"white"},"hoverlabel":{"align":"left"},"hovermode":"closest","paper_bgcolor":"white","plot_bgcolor":"#E5ECF6","polar":{"angularaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","radialaxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"yaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"zaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"baxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","caxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2}}},"title":{"text":"Supply chain traversal"}}}</script></div>

## 4. Time rides along

Nothing in the loop was ever told about time. A [`Flow`](api/flow.md)
carries its year the way it carries its location, so every demand pushed, every emission accumulated and
every node logged is already dated. The kilns doing the calcining were built in
2026 and 2029. The cement, and the gas firing the kiln, happen in 2030.

So the inventory is a time series, and can be characterized as one.

```python
from trailrunner.assessment import assess_dynamic

# No characterization table is passed: default_functions() covers co2-fossil
# and ch4-fossil, which is where the calcination CO2, the combustion CO2 and
# the pipeline's leaked methane are written. The uncharacterized count below
# is the rest of what the gas chain emits -- ethane, mercury, NMVOC, and the
# gas taken out of the ground -- which no climate method scores, and which is
# reported rather than dropped.
dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
print(dynamic.summary())

by_year = dynamic.series.groupby(dynamic.series["date"].dt.year)["amount"].sum()
print()
print("marginal radiative forcing, first years [W/m2]:")
print(by_year.head(6).to_string())
```

    4.897e-11 W·yr/m2
    metric: radiative_forcing, horizon: 100 years
    horizon anchored at: 2026-01-01
    18 uncharacterized exchanges
    0 wrong unit exchanges
    0 undated exchanges
    0 beyond-horizon exchanges
    11 unresolved
    6 proxies
    marginal radiative forcing, first years [W/m2]:
    date
    2027    2.973750e-17
    2028    5.434073e-17
    2029    2.520040e-17
    2030    5.947499e-17
    2031    9.120960e-13
    2032    1.666609e-12

```python
curve_figure = viz.curve(dynamic)
curve_figure
```

<div class="plotly-figure" data-plotly-height="480" data-plotly-name="curve" data-plotly-layout='{"margin":{"l":70,"r":70,"t":80,"b":60}}'><script type="application/json">{"data":[{"name":"radiative_forcing, per year","type":"bar","x":["2027-01-01T05:49:12","2028-01-01T11:38:24","2028-12-31T17:27:36","2029-12-31T23:16:48","2030-01-01T05:49:12","2031-01-01T05:06:00","2031-01-01T05:49:12","2031-01-01T11:38:24","2032-01-01T10:55:12","2032-01-01T11:38:24","2032-01-01T17:27:36","2032-12-31T16:44:24","2032-12-31T17:27:36","2032-12-31T23:16:48","2033-12-31T22:33:36","2033-12-31T23:16:48","2034-01-01T05:06:00","2035-01-01T04:22:48","2035-01-01T05:06:00","2035-01-01T10:55:12","2036-01-01T10:12:00","2036-01-01T10:55:12","2036-01-01T16:44:24","2036-12-31T16:01:12","2036-12-31T16:44:24","2036-12-31T22:33:36","2037-12-31T21:50:24","2037-12-31T22:33:36","2038-01-01T04:22:48","2039-01-01T03:39:36","2039-01-01T04:22:48","2039-01-01T10:12:00","2040-01-01T09:28:48","2040-01-01T10:12:00","2040-01-01T16:01:12","2040-12-31T15:18:00","2040-12-31T16:01:12","2040-12-31T21:50:24","2041-12-31T21:07:12","2041-12-31T21:50:24","2042-01-01T03:39:36","2043-01-01T02:56:24","2043-01-01T03:39:36","2043-01-01T09:28:48","2044-01-01T08:45:36","2044-01-01T09:28:48","2044-01-01T15:18:00","2044-12-31T14:34:48","2044-12-31T15:18:00","2044-12-31T21:07:12","2045-12-31T20:24:00","2045-12-31T21:07:12","2046-01-01T02:56:24","2047-01-01T02:13:12","2047-01-01T02:56:24","2047-01-01T08:45:36","2048-01-01T08:02:24","2048-01-01T08:45:36","2048-01-01T14:34:48","2048-12-31T13:51:36","2048-12-31T14:34:48","2048-12-31T20:24:00","2049-12-31T19:40:48","2049-12-31T20:24:00","2050-01-01T02:13:12","2051-01-01T01:30:00","2051-01-01T02:13:12","2051-01-01T08:02:24","2052-01-01T07:19:12","2052-01-01T08:02:24","2052-01-01T13:51:36","2052-12-31T13:08:24","2052-12-31T13:51:36","2052-12-31T19:40:48","2053-12-31T18:57:36","2053-12-31T19:40:48","2054-01-01T01:30:00","2055-01-01T00:46:48","2055-01-01T01:30:00","2055-01-01T07:19:12","2056-01-01T06:36:00","2056-01-01T07:19:12","2056-01-01T13:08:24","2056-12-31T12:25:12","2056-12-31T13:08:24","2056-12-31T18:57:36","2057-12-31T18:14:24","2057-12-31T18:57:36","2058-01-01T00:46:48","2059-01-01T00:03:36","2059-01-01T00:46:48","2059-01-01T06:36:00","2060-01-01T05:52:48","2060-01-01T06:36:00","2060-01-01T12:25:12","2060-12-31T11:42:00","2060-12-31T12:25:12","2060-12-31T18:14:24","2061-12-31T17:31:12","2061-12-31T18:14:24","2062-01-01T00:03:36","2062-12-31T23:20:24","2063-01-01T00:03:36","2063-01-01T05:52:48","2064-01-01T05:09:36","2064-01-01T05:52:48","2064-01-01T11:42:00","2064-12-31T10:58:48","2064-12-31T11:42:00","2064-12-31T17:31:12","2065-12-31T16:48:00","2065-12-31T17:31:12","2065-12-31T23:20:24","2066-12-31T22:37:12","2066-12-31T23:20:24","2067-01-01T05:09:36","2068-01-01T04:26:24","2068-01-01T05:09:36","2068-01-01T10:58:48","2068-12-31T10:15:36","2068-12-31T10:58:48","2068-12-31T16:48:00","2069-12-31T16:04:48","2069-12-31T16:48:00","2069-12-31T22:37:12","2070-12-31T21:54:00","2070-12-31T22:37:12","2071-01-01T04:26:24","2072-01-01T03:43:12","2072-01-01T04:26:24","2072-01-01T10:15:36","2072-12-31T09:32:24","2072-12-31T10:15:36","2072-12-31T16:04:48","2073-12-31T15:21:36","2073-12-31T16:04:48","2073-12-31T21:54:00","2074-12-31T21:10:48","2074-12-31T21:54:00","2075-01-01T03:43:12","2076-01-01T03:00:00","2076-01-01T03:43:12","2076-01-01T09:32:24","2076-12-31T08:49:12","2076-12-31T09:32:24","2076-12-31T15:21:36","2077-12-31T14:38:24","2077-12-31T15:21:36","2077-12-31T21:10:48","2078-12-31T20:27:36","2078-12-31T21:10:48","2079-01-01T03:00:00","2080-01-01T02:16:48","2080-01-01T03:00:00","2080-01-01T08:49:12","2080-12-31T08:06:00","2080-12-31T08:49:12","2080-12-31T14:38:24","2081-12-31T13:55:12","2081-12-31T14:38:24","2081-12-31T20:27:36","2082-12-31T19:44:24","2082-12-31T20:27:36","2083-01-01T02:16:48","2084-01-01T01:33:36","2084-01-01T02:16:48","2084-01-01T08:06:00","2084-12-31T07:22:48","2084-12-31T08:06:00","2084-12-31T13:55:12","2085-12-31T13:12:00","2085-12-31T13:55:12","2085-12-31T19:44:24","2086-12-31T19:01:12","2086-12-31T19:44:24","2087-01-01T01:33:36","2088-01-01T00:50:24","2088-01-01T01:33:36","2088-01-01T07:22:48","2088-12-31T06:39:36","2088-12-31T07:22:48","2088-12-31T13:12:00","2089-12-31T12:28:48","2089-12-31T13:12:00","2089-12-31T19:01:12","2090-12-31T18:18:00","2090-12-31T19:01:12","2091-01-01T00:50:24","2092-01-01T00:07:12","2092-01-01T00:50:24","2092-01-01T06:39:36","2092-12-31T05:56:24","2092-12-31T06:39:36","2092-12-31T12:28:48","2093-12-31T11:45:36","2093-12-31T12:28:48","2093-12-31T18:18:00","2094-12-31T17:34:48","2094-12-31T18:18:00","2095-01-01T00:07:12","2095-12-31T23:24:00","2096-01-01T00:07:12","2096-01-01T05:56:24","2096-12-31T05:13:12","2096-12-31T05:56:24","2096-12-31T11:45:36","2097-12-31T11:02:24","2097-12-31T11:45:36","2097-12-31T17:34:48","2098-12-31T16:51:36","2098-12-31T17:34:48","2098-12-31T23:24:00","2099-12-31T22:40:48","2099-12-31T23:24:00","2100-01-01T05:13:12","2101-01-01T04:30:00","2101-01-01T05:13:12","2101-01-01T11:02:24","2102-01-01T10:19:12","2102-01-01T11:02:24","2102-01-01T16:51:36","2103-01-01T16:08:24","2103-01-01T16:51:36","2103-01-01T22:40:48","2104-01-01T21:57:36","2104-01-01T22:40:48","2104-01-02T04:30:00","2105-01-01T03:46:48","2105-01-01T04:30:00","2105-01-01T10:19:12","2106-01-01T09:36:00","2106-01-01T10:19:12","2106-01-01T16:08:24","2107-01-01T15:25:12","2107-01-01T16:08:24","2107-01-01T21:57:36","2108-01-01T21:14:24","2108-01-01T21:57:36","2108-01-02T03:46:48","2109-01-01T03:03:36","2109-01-01T03:46:48","2109-01-01T09:36:00","2110-01-01T08:52:48","2110-01-01T09:36:00","2110-01-01T15:25:12","2111-01-01T14:42:00","2111-01-01T15:25:12","2111-01-01T21:14:24","2112-01-01T20:31:12","2112-01-01T21:14:24","2112-01-02T03:03:36","2113-01-01T02:20:24","2113-01-01T03:03:36","2113-01-01T08:52:48","2114-01-01T08:09:36","2114-01-01T08:52:48","2114-01-01T14:42:00","2115-01-01T13:58:48","2115-01-01T14:42:00","2115-01-01T20:31:12","2116-01-01T19:48:00","2116-01-01T20:31:12","2116-01-02T02:20:24","2117-01-01T01:37:12","2117-01-01T02:20:24","2117-01-01T08:09:36","2118-01-01T07:26:24","2118-01-01T08:09:36","2118-01-01T13:58:48","2119-01-01T13:15:36","2119-01-01T13:58:48","2119-01-01T19:48:00","2120-01-01T19:04:48","2120-01-01T19:48:00","2120-01-02T01:37:12","2121-01-01T00:54:00","2121-01-01T01:37:12","2121-01-01T07:26:24","2122-01-01T06:43:12","2122-01-01T07:26:24","2122-01-01T13:15:36","2123-01-01T12:32:24","2123-01-01T13:15:36","2123-01-01T19:04:48","2124-01-01T18:21:36","2124-01-01T19:04:48","2124-01-02T00:54:00","2125-01-01T00:10:48","2125-01-01T00:54:00","2125-01-01T06:43:12","2126-01-01T06:43:12","2126-01-01T12:32:24","2127-01-01T12:32:24","2127-01-01T18:21:36","2128-01-01T18:21:36","2128-01-02T00:10:48","2129-01-01T00:10:48"],"y":{"bdata":"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","dtype":"f8"}},{"mode":"lines","name":"cumulative (W\u00b7yr/m2)","type":"scatter","x":["2027-01-01T05:49:12","2028-01-01T11:38:24","2028-12-31T17:27:36","2029-12-31T23:16:48","2030-01-01T05:49:12","2031-01-01T05:06:00","2031-01-01T05:49:12","2031-01-01T11:38:24","2032-01-01T10:55:12","2032-01-01T11:38:24","2032-01-01T17:27:36","2032-12-31T16:44:24","2032-12-31T17:27:36","2032-12-31T23:16:48","2033-12-31T22:33:36","2033-12-31T23:16:48","2034-01-01T05:06:00","2035-01-01T04:22:48","2035-01-01T05:06:00","2035-01-01T10:55:12","2036-01-01T10:12:00","2036-01-01T10:55:12","2036-01-01T16:44:24","2036-12-31T16:01:12","2036-12-31T16:44:24","2036-12-31T22:33:36","2037-12-31T21:50:24","2037-12-31T22:33:36","2038-01-01T04:22:48","2039-01-01T03:39:36","2039-01-01T04:22:48","2039-01-01T10:12:00","2040-01-01T09:28:48","2040-01-01T10:12:00","2040-01-01T16:01:12","2040-12-31T15:18:00","2040-12-31T16:01:12","2040-12-31T21:50:24","2041-12-31T21:07:12","2041-12-31T21:50:24","2042-01-01T03:39:36","2043-01-01T02:56:24","2043-01-01T03:39:36","2043-01-01T09:28:48","2044-01-01T08:45:36","2044-01-01T09:28:48","2044-01-01T15:18:00","2044-12-31T14:34:48","2044-12-31T15:18:00","2044-12-31T21:07:12","2045-12-31T20:24:00","2045-12-31T21:07:12","2046-01-01T02:56:24","2047-01-01T02:13:12","2047-01-01T02:56:24","2047-01-01T08:45:36","2048-01-01T08:02:24","2048-01-01T08:45:36","2048-01-01T14:34:48","2048-12-31T13:51:36","2048-12-31T14:34:48","2048-12-31T20:24:00","2049-12-31T19:40:48","2049-12-31T20:24:00","2050-01-01T02:13:12","2051-01-01T01:30:00","2051-01-01T02:13:12","2051-01-01T08:02:24","2052-01-01T07:19:12","2052-01-01T08:02:24","2052-01-01T13:51:36","2052-12-31T13:08:24","2052-12-31T13:51:36","2052-12-31T19:40:48","2053-12-31T18:57:36","2053-12-31T19:40:48","2054-01-01T01:30:00","2055-01-01T00:46:48","2055-01-01T01:30:00","2055-01-01T07:19:12","2056-01-01T06:36:00","2056-01-01T07:19:12","2056-01-01T13:08:24","2056-12-31T12:25:12","2056-12-31T13:08:24","2056-12-31T18:57:36","2057-12-31T18:14:24","2057-12-31T18:57:36","2058-01-01T00:46:48","2059-01-01T00:03:36","2059-01-01T00:46:48","2059-01-01T06:36:00","2060-01-01T05:52:48","2060-01-01T06:36:00","2060-01-01T12:25:12","2060-12-31T11:42:00","2060-12-31T12:25:12","2060-12-31T18:14:24","2061-12-31T17:31:12","2061-12-31T18:14:24","2062-01-01T00:03:36","2062-12-31T23:20:24","2063-01-01T00:03:36","2063-01-01T05:52:48","2064-01-01T05:09:36","2064-01-01T05:52:48","2064-01-01T11:42:00","2064-12-31T10:58:48","2064-12-31T11:42:00","2064-12-31T17:31:12","2065-12-31T16:48:00","2065-12-31T17:31:12","2065-12-31T23:20:24","2066-12-31T22:37:12","2066-12-31T23:20:24","2067-01-01T05:09:36","2068-01-01T04:26:24","2068-01-01T05:09:36","2068-01-01T10:58:48","2068-12-31T10:15:36","2068-12-31T10:58:48","2068-12-31T16:48:00","2069-12-31T16:04:48","2069-12-31T16:48:00","2069-12-31T22:37:12","2070-12-31T21:54:00","2070-12-31T22:37:12","2071-01-01T04:26:24","2072-01-01T03:43:12","2072-01-01T04:26:24","2072-01-01T10:15:36","2072-12-31T09:32:24","2072-12-31T10:15:36","2072-12-31T16:04:48","2073-12-31T15:21:36","2073-12-31T16:04:48","2073-12-31T21:54:00","2074-12-31T21:10:48","2074-12-31T21:54:00","2075-01-01T03:43:12","2076-01-01T03:00:00","2076-01-01T03:43:12","2076-01-01T09:32:24","2076-12-31T08:49:12","2076-12-31T09:32:24","2076-12-31T15:21:36","2077-12-31T14:38:24","2077-12-31T15:21:36","2077-12-31T21:10:48","2078-12-31T20:27:36","2078-12-31T21:10:48","2079-01-01T03:00:00","2080-01-01T02:16:48","2080-01-01T03:00:00","2080-01-01T08:49:12","2080-12-31T08:06:00","2080-12-31T08:49:12","2080-12-31T14:38:24","2081-12-31T13:55:12","2081-12-31T14:38:24","2081-12-31T20:27:36","2082-12-31T19:44:24","2082-12-31T20:27:36","2083-01-01T02:16:48","2084-01-01T01:33:36","2084-01-01T02:16:48","2084-01-01T08:06:00","2084-12-31T07:22:48","2084-12-31T08:06:00","2084-12-31T13:55:12","2085-12-31T13:12:00","2085-12-31T13:55:12","2085-12-31T19:44:24","2086-12-31T19:01:12","2086-12-31T19:44:24","2087-01-01T01:33:36","2088-01-01T00:50:24","2088-01-01T01:33:36","2088-01-01T07:22:48","2088-12-31T06:39:36","2088-12-31T07:22:48","2088-12-31T13:12:00","2089-12-31T12:28:48","2089-12-31T13:12:00","2089-12-31T19:01:12","2090-12-31T18:18:00","2090-12-31T19:01:12","2091-01-01T00:50:24","2092-01-01T00:07:12","2092-01-01T00:50:24","2092-01-01T06:39:36","2092-12-31T05:56:24","2092-12-31T06:39:36","2092-12-31T12:28:48","2093-12-31T11:45:36","2093-12-31T12:28:48","2093-12-31T18:18:00","2094-12-31T17:34:48","2094-12-31T18:18:00","2095-01-01T00:07:12","2095-12-31T23:24:00","2096-01-01T00:07:12","2096-01-01T05:56:24","2096-12-31T05:13:12","2096-12-31T05:56:24","2096-12-31T11:45:36","2097-12-31T11:02:24","2097-12-31T11:45:36","2097-12-31T17:34:48","2098-12-31T16:51:36","2098-12-31T17:34:48","2098-12-31T23:24:00","2099-12-31T22:40:48","2099-12-31T23:24:00","2100-01-01T05:13:12","2101-01-01T04:30:00","2101-01-01T05:13:12","2101-01-01T11:02:24","2102-01-01T10:19:12","2102-01-01T11:02:24","2102-01-01T16:51:36","2103-01-01T16:08:24","2103-01-01T16:51:36","2103-01-01T22:40:48","2104-01-01T21:57:36","2104-01-01T22:40:48","2104-01-02T04:30:00","2105-01-01T03:46:48","2105-01-01T04:30:00","2105-01-01T10:19:12","2106-01-01T09:36:00","2106-01-01T10:19:12","2106-01-01T16:08:24","2107-01-01T15:25:12","2107-01-01T16:08:24","2107-01-01T21:57:36","2108-01-01T21:14:24","2108-01-01T21:57:36","2108-01-02T03:46:48","2109-01-01T03:03:36","2109-01-01T03:46:48","2109-01-01T09:36:00","2110-01-01T08:52:48","2110-01-01T09:36:00","2110-01-01T15:25:12","2111-01-01T14:42:00","2111-01-01T15:25:12","2111-01-01T21:14:24","2112-01-01T20:31:12","2112-01-01T21:14:24","2112-01-02T03:03:36","2113-01-01T02:20:24","2113-01-01T03:03:36","2113-01-01T08:52:48","2114-01-01T08:09:36","2114-01-01T08:52:48","2114-01-01T14:42:00","2115-01-01T13:58:48","2115-01-01T14:42:00","2115-01-01T20:31:12","2116-01-01T19:48:00","2116-01-01T20:31:12","2116-01-02T02:20:24","2117-01-01T01:37:12","2117-01-01T02:20:24","2117-01-01T08:09:36","2118-01-01T07:26:24","2118-01-01T08:09:36","2118-01-01T13:58:48","2119-01-01T13:15:36","2119-01-01T13:58:48","2119-01-01T19:48:00","2120-01-01T19:04:48","2120-01-01T19:48:00","2120-01-02T01:37:12","2121-01-01T00:54:00","2121-01-01T01:37:12","2121-01-01T07:26:24","2122-01-01T06:43:12","2122-01-01T07:26:24","2122-01-01T13:15:36","2123-01-01T12:32:24","2123-01-01T13:15:36","2123-01-01T19:04:48","2124-01-01T18:21:36","2124-01-01T19:04:48","2124-01-02T00:54:00","2125-01-01T00:10:48","2125-01-01T00:54:00","2125-01-01T06:43:12","2126-01-01T06:43:12","2126-01-01T12:32:24","2127-01-01T12:32:24","2127-01-01T18:21:36","2128-01-01T18:21:36","2128-01-02T00:10:48","2129-01-01T00:10:48"],"y":{"bdata":"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","dtype":"f8"},"yaxis":"y2"}],"layout":{"margin":{"b":40,"l":40,"r":20,"t":50},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","template":{"data":{"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"barpolar":[{"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"#E5ECF6","showlakes":true,"showland":true,"subunitcolor":"white"},"hoverlabel":{"align":"left"},"hovermode":"closest","paper_bgcolor":"white","plot_bgcolor":"#E5ECF6","polar":{"angularaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","radialaxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"yaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"zaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"baxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","caxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2}}},"title":{"text":"radiative_forcing over 100 years"},"xaxis":{"title":{"text":"year"}},"yaxis":{"title":{"text":"W/m2"}},"yaxis2":{"overlaying":"y","side":"right","title":{"text":"W\u00b7yr/m2"}}}}</script></div>

The faint bars are the per-year forcing and the red line is its running total.
The kilns show up in 2027 and 2029, and then 2031 arrives and the scale of the
plot changes: building two cement plants is four orders of magnitude
below one year of making cement in them. That is not a flaw in the example. It
is what the industry's problem actually looks like, and it is visible here only
because the dates survived.

A static score gives one number for all of that, and no way to ask when any of
it happened. No matrix was rebuilt and no second model was written:
characterization is a separate reading of an inventory whose dates were never
lost.

## 5. The run leaves a record

```python
import pyarrow.parquet as pq

print(report.summary())

out = Path("showcase_log.parquet")
report.log.to_parquet(out)
table = pq.read_table(out)
print()
print(f"wrote {out.name}: {table.num_rows} rows, {table.num_columns} columns")
print("kinds:", sorted(set(table.column("kind").to_pylist())))
out.unlink()
```

    18 nodes, 13 inventory entries
    11 unresolved (generalisation_exhausted: 11)
    6 proxies (4 incomplete)
    attribution: allocation=none, capital=per_output
    wrote showcase_log.parquet: 299 rows, 19 columns
    kinds: ['attribution', 'biosphere', 'node', 'provenance', 'resolution', 'unresolved']

```python
contributions_figure = viz.contributions(
    assessment, by="node", labels={node.id: node.model for node in report.nodes}
)
contributions_figure
```

<div class="plotly-figure" data-plotly-height="520" data-plotly-name="contributions" data-plotly-layout='{"margin":{"l":70,"r":20,"t":60,"b":150}}'><script type="application/json">{"data":[{"type":"bar","x":["CementPlant","BinderSupply","NaturalGasExtraction","GasPower","NaturalGasOffshorePipelineTransport","NaturalGasExtraction","BackgroundDataset","BackgroundDataset","BackgroundDataset","BackgroundDataset"],"y":[536.1,9.0,4.697916666666666,2.7526881720430105,0.25834124250000007,0.0933037492177277,0.020986666666666667,0.015119999999999998,0.010493333333333334,0.007559999999999999]}],"layout":{"margin":{"b":40,"l":40,"r":20,"t":50},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","template":{"data":{"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"barpolar":[{"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"#E5ECF6","showlakes":true,"showland":true,"subunitcolor":"white"},"hoverlabel":{"align":"left"},"hovermode":"closest","paper_bgcolor":"white","plot_bgcolor":"#E5ECF6","polar":{"angularaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","radialaxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"yaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"zaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"baxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","caxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2}}},"title":{"text":"Contributions by node"},"xaxis":{"title":{"text":"node"}},"yaxis":{"title":{"text":"kg CO2-eq"}}}}</script></div>

Every node, every cutoff, every parameter fallback and every proxy, one row
each. Parameters arrive as parquet and the whole run leaves as parquet, so two
studies can be diffed with a single read.

## What this changes

- **The supply chain assembles itself.** Models declare vocabulary IRIs, and the
  orchestrator finds who answers what.
- **Missing data is visible.** Cutoffs carry a reason and a position in the
  chain, so a reader can see what a number excludes.
- **Concessions are declared and recorded.** A generalised demand or a borrowed
  dataset is tagged at the node, with what was asked and what answered it.
- **Inventories are time-explicit by construction.** Dates survive the
  traversal, so dynamic characterization needs no second model.
- **The run is a file.** One parquet holds the graph, the gaps and the choices.
- **A process can depend on its demand.** Location, year, scale and feed
  conditions live in the model, where a physical dependency belongs.
- **A model can be a measurement.** Two models, one product, disjoint coverage:
  the year on the demand decides whether you get a meter reading or a
  calculation, and the report says which.

---

- Normative choices, and a model that co-produces: [When a model makes two things](content/examples/coproduction.md)
- The deeper worked example: [Direct air capture, end to end](content/examples/dac.md)
- The same pieces in reference form: [Core Concepts](content/concepts.md)
- [Installation](content/installation.md)
