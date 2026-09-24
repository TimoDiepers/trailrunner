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

What is the impact of **1 t of Portland cement, in Denmark, on 15 June 2030?**

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
    from trailrunner.core.time import DATE, in_year
    from trailrunner.core.units import KG, PA, TONNE, TONNE_PER_YEAR, YEAR, symbol
    from trailrunner.models.cement import CEMENT
    from trailrunner.resolution import PystLabels

    # A unit is a vocabulary IRI too (https://vocab.sentier.dev/units/), and a
    # time is a string in a declared standard: here a day, as xsd:date.
    DEMAND = Demand(
        flow=Flow(iri=CEMENT, location="DK", time="2030-06-15", time_standard=DATE),
        amount=1.0,
        unit=TONNE,
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


    print(DEMAND.amount, symbol(DEMAND.unit), DEMAND.flow.iri)
    print("the unit is:", DEMAND.unit)
    print("that IRI is:", name(DEMAND.flow.iri))
    print("where:", DEMAND.flow.location, " when:", DEMAND.flow.time, "in", DEMAND.flow.time_standard)
    ```

        1.0 t https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440
        the unit is: https://vocab.sentier.dev/units/unit/TONNE
        that IRI is: Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers
        where: DK  when: 2030-06-15 in http://www.w3.org/2001/XMLSchema#date

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

# Called directly, a model gets exactly what it is handed, so ask in its own
# unit. Inside a run the Runner does that conversion (section 2).
IN_KG = Demand(flow=DEMAND.flow, amount=1000.0, unit=KG)
answer = cement_model.apply(IN_KG)

# where and when get their own columns: a flow's location and time are part of
# its identity, not an annotation on its name.
print(f"{'':>13}  {'amount':>8} {'unit':<4} {'flow':<44} {'where':<5} {'when':>10}")
for field in ("production", "technosphere", "biosphere"):
    for exchange in getattr(answer, field):
        flow = exchange.flow
        print(
            f"{field:>13}  {exchange.amount:>8.1f} {symbol(exchange.unit):<4} "
            f"{name(flow.iri, 44):<44} {flow.location:<5} {flow.time:>10}"
        )
print(f"{'provenance':>13}  {answer.provenance}")
```

                     amount unit flow                                         where       when
       production    1000.0 kg   Portland cement, aluminous cement, slag cem… DK    2030-06-15
     technosphere    1125.0 kg   Gypsum; anhydrite; limestone flux; limeston… DK    2030-06-15
     technosphere    2475.0 MJ   Natural gas, liquefied or in the gaseous st… DK    2030-06-15
     technosphere      10.0 kg   Quicklime, slaked lime and hydraulic lime    DK    2030-06-15
     technosphere     100.0 kWh  electricity                                  DK    2030-06-15
        biosphere     397.5 kg   co2-fossil                                   DK    2030-06-15
        biosphere     138.6 kg   co2-fossil                                   DK    2030-06-15
       provenance  {'location_requested': 'DK', 'location_used': 'DK', 'location_fallback': False, 'time_requested': '2030-06-15', 'time_used': '2030', 'time_interpolated': False, 'source': 'modelled'}

Every name printed there — `Quicklime, slaked lime and hydraulic lime`,
`co2-fossil` — is the vocabulary's label for a real concept.

Because the cement plant is a computation model, we can do additional calculations, taking into account the context the process is run in.
This data is retrieved from a set of parquet files based on their embedded metadata, created with [`trailpack`](https://github.com/TimoDiepers/trailpack).
For example, fuel demands could increase with higher ambient moisture and lower temperatures:

```python
penalty = moisture_penalty(row["moisture"], row["temperature"])
fuel = row["fuel_demand"] * clinker * penalty
```

The same 1000 kg, asked for in two places and two years:

```python
print(f"{'where':>6} {'when':>6} {'moisture':>9} {'degC':>6} {'penalty':>9} {'gas [MJ]':>10}")
for location in ("DK", "RER"):
    for year in (2030, 2040):
        feed = cement_params.at(location=location, **in_year(year))
        answer = cement_model.apply(
            Demand(flow=Flow(iri=CEMENT, location=location, **in_year(year)),
                   amount=1000.0, unit=KG)
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
filters candidates by coverage, so the time on the demand decides which one
answers.

```python
coverage = Coverage(time_range=year_range(2018, 2025), units=frozenset({KG}))  # MeteredCementPlant
coverage = Coverage(time_range=year_range(2026, 2050), units=frozenset({KG}))  # CementPlant
```

```python
from showcase_models import MODELS
from trailrunner import Glossary, Orchestrator

for year in (2023, 2030):
    run = Orchestrator(Glossary(MODELS)).calculate(
        Demand(flow=Flow(iri=CEMENT, location="DK", **in_year(year)), amount=1000.0, unit=KG)
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
            f"pop {demand.amount:>9.4g} {symbol(demand.unit):<4} {name(flow.iri, 32):<32} "
            f"{flow.location:<5} {flow.time:>10}  -> {who}"
        )
        return offer


tier1 = ModelProvider(Glossary(MODELS))
print(f"{'':>3} {'amount':>9} {'unit':<4} {'flow':<32} {'where':<5} {'when':>10}  -> answered by")
first = Orchestrator(Narrating([tier1])).calculate(DEMAND)
```

           amount unit flow                             where       when  -> answered by
    pop         1 t    Portland cement, aluminous ceme… DK    2030-06-15  -> CementPlant
    pop      1125 kg   Gypsum; anhydrite; limestone fl… DK    2030-06-15  -> cutoff (nobody offered)
    pop      2475 MJ   Natural gas, liquefied or in th… DK    2030-06-15  -> cutoff (nobody offered)
    pop        10 kg   Quicklime, slaked lime and hydr… DK    2030-06-15  -> cutoff (nobody offered)
    pop       100 kWh  electricity                      DK    2030-06-15  -> GridElectricity
    pop     8.466 kWh  electricity-natural-gas          DK    2030-06-15  -> GasPower
    pop     84.66 kWh  electricity-wind                 DK    2030-06-15  -> cutoff (nobody offered)
    pop      12.7 kWh  electricity-hydro                DK    2030-06-15  -> cutoff (nobody offered)
    pop     49.16 MJ   Natural gas, liquefied or in th… DK    2030-06-15  -> NaturalGasSupply
    pop     1.365 m3   natural-gas-at-production        NO    2030-06-15  -> NaturalGasExtraction
    pop  0.001004 t    natural-gas-transport-offshore-… NO    2030-06-15  -> NaturalGasOffshorePipelineTransport
    pop 1.786e-09 unit pipeline-natural-gas-long-dista… NO    2030-06-15  -> cutoff (nobody offered)
    pop 0.0002594 m3   natural-gas-at-production        NO    2030-06-15  -> NaturalGasExtraction
    pop    0.3285 MJ   natural-gas-burned-in-gas-turbi… NO    2030-06-15  -> cutoff (nobody offered)
    pop 1.164e-10 t    transport-freight-lorry-16t-32t  NO    2030-06-15  -> cutoff (nobody offered)
    pop 1.164e-06 kg   disposal-used-mineral-oil-10-pe… NO    2030-06-15  -> cutoff (nobody offered)

```python
print(first.summary())
print()
print(first.tree(labels=VOCAB.label))  # the vocabulary's names, where it has one
```

    7 nodes, 11 inventory entries
    9 unresolved (coverage_excluded: 1, no_model_found: 8)
    0 proxies
    attribution: allocation=none, capital=per_output
    1 t Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @DK/2030-06-15  [model: CementPlant; unit: t -> kg ×1000]
      100 kWh electricity @DK/2030-06-15  [model: GridElectricity]
        8.46561 kWh electricity-natural-gas @DK/2030-06-15  [model: GasPower]
          49.1551 MJ Natural gas, liquefied or in the gaseous state @DK/2030-06-15  [model: NaturalGasSupply]
            1.36542 m3 natural-gas-at-production @NO/2030-06-15  [model: NaturalGasExtraction]
            0.00100358 t natural-gas-transport-offshore-pipeline-long-distance @NO/2030-06-15 (distance=1000 km)  [model: NaturalGasOffshorePipelineTransport]
              0.00025943 m3 natural-gas-at-production @NO/2030-06-15  [model: NaturalGasExtraction]
              1.78638e-09 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030-06-15  [cutoff: no_model_found]
              0.328503 MJ natural-gas-burned-in-gas-turbine @NO/2030-06-15  [cutoff: no_model_found]
              1.16416e-10 t transport-freight-lorry-16t-32t @NO/2030-06-15 (distance=1000 km)  [cutoff: no_model_found]
              1.16416e-06 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030-06-15  [cutoff: no_model_found]
        84.6561 kWh electricity-wind @DK/2030-06-15  [cutoff: no_model_found]
        12.6984 kWh electricity-hydro @DK/2030-06-15  [cutoff: no_model_found]
      1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @DK/2030-06-15  [cutoff: no_model_found]
      2475 MJ Natural gas, liquefied or in the gaseous state @DK/2030-06-15 (pressure=400000 Pa)  [cutoff: coverage_excluded]
      10 kg Quicklime, slaked lime and hydraulic lime @DK/2030-06-15  [cutoff: no_model_found]

The demand is **1 t** of cement on **15 June 2030**. `CementPlant` reasons in
kilograms and its parameters are per year: it answers the day because the day
lies inside 2030, and it is handed 1000 kg because a tonne is exactly that —
`unit: t -> kg ×1000`, written on the node, costing nothing. A conversion is
not a proxy.

The gas chain runs. The gas power plant's 49 MJ reach `NaturalGasSupply`, which
turns them into wellhead volume and route length and hands those to a gas
field and to `NaturalGasOffshorePipelineTransport` — a model reverse-engineered
from the BAFU/ecoinvent pipeline datasets, which was registered in this list
long before anything asked it to move a tonne of gas over a distance.

Note where the pipeline runs. The supply model places both demands at the
*origin*, so the Danish gas is transported in `NO` and its leakage is priced
at the Norwegian shelf's low-leakage tier, not at a Danish average that does
not exist. The pipeline's own inputs — compressor fuel, the pipe itself, a
maintenance lorry — are cutoffs, and they are in the report with a reason.

The kiln's own 2475 MJ are a cutoff too, but for a different reason:
`coverage_excluded`, not `no_model_found`. The kiln burners ask for gas at
`pressure=400000 Pa` (4 bar), and `NaturalGasSupply` declares in its
coverage that it delivers at 500000 Pa. A supplier exists, but it doesn't match exactly, and tier 1
alone won't pretend it does. Section 3 lets that condition be relaxed, on the
record.

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
demand can ask for. This plant's burners take gas at 4e5 Pa (4 bar), so its
gas demand carries `pressure=400000 Pa` in its [`Flow`](api/flow.md)'s `context`. `NaturalGasSupply`
declares in its `Coverage` that it delivers at 5e5 Pa, so tier 1 does not match
it. The practitioner allows pressure to be met up to 1e5 Pa *higher*, never
lower, because gas can be throttled down at the burner and cannot be pushed
up there. Tier 2 moves the demand to 5e5 Pa and records the move. The gas power
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
from trailrunner.core.time import when
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
        here = {"location": demand.flow.location, **when(demand.flow)}
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[],
            biosphere=[Exchange(flow=Flow(iri=CO2_FOSSIL, **here),
                                amount=demand.amount * self.co2_per_kg, unit=KG)],
            provenance={"binder_average": True},
        )


class CementKilnConstruction(Model):
    """What a kiln line is made of. Illustrative material intensities."""

    produces = [CEMENT_KILN]
    supports = ALLOCATION_RULES

    # kg per unit of kiln demanded, which CementPlant states in the fleet's
    # capacity unit (t/yr).
    steel_per_capacity = 0.012      # kg steel
    aluminium_per_capacity = 0.0008  # kg aluminium, likewise

    def apply(self, demand):
        here = {"location": demand.flow.location, **when(demand.flow)}
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(flow=Flow(iri=STEEL, **here),
                       amount=demand.amount * self.steel_per_capacity, unit=KG),
                Demand(flow=Flow(iri=ALUMINIUM, **here),
                       amount=demand.amount * self.aluminium_per_capacity, unit=KG),
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
    {"kiln": "dk-old", "location": "DK", "build_year": 1985, "capacity": 250_000.0, "lifetime": 40.0},
    {"kiln": "dk-1", "location": "DK", "build_year": 2026, "capacity": 400_000.0, "lifetime": 40.0},
    {"kiln": "dk-2", "location": "DK", "build_year": 2029, "capacity": 800_000.0, "lifetime": 40.0},
]
fleet = Fleet(FLEET_ROWS, units={"capacity": TONNE_PER_YEAR, "lifetime": YEAR}, hierarchy=HIERARCHY)

MODELS_PLUS = [
    # Burners at 4e5 Pa (4 bar); NaturalGasSupply delivers at 5e5 Pa.
    CementPlant(params=cement_params, fleet=fleet, burner_pressure=4e5),
    *(model for model in MODELS if not isinstance(model, CementPlant)),
    BinderSupply(),
    CementKilnConstruction(),
]

tier1 = ModelProvider(Glossary(MODELS_PLUS))
# client=None: no network, ever. Every skos:broader answer comes from the file.
taxonomy = PystTaxonomy(EXAMPLES / "pyst_cache.json", client=None)
# Pressure may be met up to 1e5 Pa (1 bar) higher, never lower: gas is
# throttled at the burner, not boosted there. (below, above, unit)
PROXY = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})
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
    1 t Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @DK/2030-06-15  [model: CementPlant; unit: t -> kg ×1000]
      2475 MJ Natural gas, liquefied or in the gaseous state @DK/2030-06-15 (pressure=400000 Pa)  [proxy: context: pressure 400000 Pa -> 500000 Pa]
        68.75 m3 natural-gas-at-production @NO/2030-06-15  [model: NaturalGasExtraction]
        0.0505312 t natural-gas-transport-offshore-pipeline-long-distance @NO/2030-06-15 (distance=1000 km)  [model: NaturalGasOffshorePipelineTransport]
          0.0130625 m3 natural-gas-at-production @NO/2030-06-15  [model: NaturalGasExtraction]
          8.99456e-08 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030-06-15  [cutoff: generalisation_exhausted]
          16.5404 MJ natural-gas-burned-in-gas-turbine @NO/2030-06-15  [cutoff: generalisation_exhausted]
          5.86163e-09 t transport-freight-lorry-16t-32t @NO/2030-06-15 (distance=1000 km)  [cutoff: generalisation_exhausted]
          5.86162e-05 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030-06-15  [cutoff: generalisation_exhausted]
      10 kg Quicklime, slaked lime and hydraulic lime @DK/2030-06-15  [proxy: product: fi_37420 -> fi_374]
      100 kWh electricity @DK/2030-06-15  [model: GridElectricity]
        8.46561 kWh electricity-natural-gas @DK/2030-06-15  [model: GasPower]
          49.1551 MJ Natural gas, liquefied or in the gaseous state @DK/2030-06-15  [model: NaturalGasSupply]
            1.36542 m3 natural-gas-at-production @NO/2030-06-15  [model: NaturalGasExtraction]
            0.00100358 t natural-gas-transport-offshore-pipeline-long-distance @NO/2030-06-15 (distance=1000 km)  [model: NaturalGasOffshorePipelineTransport]
              0.00025943 m3 natural-gas-at-production @NO/2030-06-15  [model: NaturalGasExtraction]
              1.78638e-09 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030-06-15  [cutoff: generalisation_exhausted]
              0.328503 MJ natural-gas-burned-in-gas-turbine @NO/2030-06-15  [cutoff: generalisation_exhausted]
              1.16416e-10 t transport-freight-lorry-16t-32t @NO/2030-06-15 (distance=1000 km)  [cutoff: generalisation_exhausted]
              1.16416e-06 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030-06-15  [cutoff: generalisation_exhausted]
        84.6561 kWh electricity-wind @DK/2030-06-15  [cutoff: generalisation_exhausted]
        12.6984 kWh electricity-hydro @DK/2030-06-15  [cutoff: generalisation_exhausted]
      8.33333 t/yr cement-kiln @DK/2026  [model: CementKilnConstruction]
        0.1 kg steel-low-alloyed @DK/2026  [background: unit_process, incomplete]
        0.00666667 kg aluminium-primary @DK/2026  [background: unit_process, incomplete]
      16.6667 t/yr cement-kiln @DK/2029  [model: CementKilnConstruction]
        0.2 kg steel-low-alloyed @DK/2029  [background: unit_process, incomplete]
        0.0133333 kg aluminium-primary @DK/2029  [background: unit_process, incomplete]
      1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @DK/2030-06-15  [cutoff: generalisation_exhausted]

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
           asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37420 @DK/2030-06-15
        answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_374 @DK/2030-06-15
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
     relaxations: ['context: pressure 400000 Pa -> 500000 Pa']
           asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020 @DK/2030-06-15 [pressure=400000 Pa]
        answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020 @DK/2030-06-15 [pressure=500000 Pa]
            tier: generalising

Every concession is deliberate, ordered by the practitioner, and written down.

```python
from trailrunner import viz
from trailrunner.assessment import Method, assess

# IPCC AR6 GWP100, stated here rather than read from a background database:
# the mapping from a gas to its warming potential is a fact about the gas.
GWP100 = Method(
    rows=[
        {"flow_iri": "https://vocab.sentier.dev/flows/co2-fossil", "flow_unit": KG,
         "location": "GLO", "cf": 1.0},
        {"flow_iri": "https://vocab.sentier.dev/flows/ch4-fossil", "flow_unit": KG,
         "location": "GLO", "cf": 29.8},
        {"flow_iri": "https://vocab.sentier.dev/flows/n2o", "flow_unit": KG,
         "location": "GLO", "cf": 273.0},
    ],
    unit=KG,  # of CO2-equivalent: the indicator is in the name, not the unit
    name="IPCC AR6 GWP100",
    hierarchy=HIERARCHY,
)

assessment = assess(report, GWP100)
sankey_figure = viz.sankey(report, assessment=assessment)
sankey_figure
```

<div class="plotly-figure" data-plotly-height="780" data-plotly-name="sankey" data-plotly-layout='{"margin":{"l":20,"r":150,"t":60,"b":20}}'><script type="application/json">{"data":[{"link":{"color":"rgba(134,142,150,0.45)","source":[0,0,0,0,0,1,1,3,4,4,5,5,7,8,14,14,16],"target":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17],"value":[4.959285622123288,9.0,2.8511828825322008,0.01805333333333333,0.03610666666666666,4.700051369863014,0.259234252260274,2.8511828825322008,0.007559999999999999,0.010493333333333334,0.015119999999999998,0.020986666666666667,0.0008930097602739727,0.09849471048919005,0.09334614584283167,0.005148564646358373,1.7735767710138017e-05]},"node":{"color":["#0b7285","#f59f00","#f59f00","#0b7285","#0b7285","#0b7285","#0b7285","#0b7285","#0b7285","#868e96","#868e96","#868e96","#868e96","#0b7285","#0b7285","#0b7285","#0b7285","#0b7285"],"label":["fi_37440 (CementPlant) [model]","fi_12020 (NaturalGasSupply) [generalising]","fi_37420 (BinderSupply) [generalising]","fi_17100 (GridElectricity) [model]","cement-kiln (CementKilnConstruction) [model]","cement-kiln (CementKilnConstruction) [model]","natural-gas-at-production (NaturalGasExtraction) [model]","natural-gas-transport-offshore-pipeline-long-distance (NaturalGasOffshorePipelineTransport) [model]","electricity-natural-gas (GasPower) [model]","steel-low-alloyed (BackgroundDataset) [background]","aluminium-primary (BackgroundDataset) [background]","steel-low-alloyed (BackgroundDataset) [background]","aluminium-primary (BackgroundDataset) [background]","natural-gas-at-production (NaturalGasExtraction) [model]","fi_12020 (NaturalGasSupply) [model]","natural-gas-at-production (NaturalGasExtraction) [model]","natural-gas-transport-offshore-pipeline-long-distance (NaturalGasOffshorePipelineTransport) [model]","natural-gas-at-production (NaturalGasExtraction) [model]"],"pad":18,"thickness":14},"type":"sankey"}],"layout":{"margin":{"b":40,"l":40,"r":20,"t":50},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","template":{"data":{"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"barpolar":[{"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"#E5ECF6","showlakes":true,"showland":true,"subunitcolor":"white"},"hoverlabel":{"align":"left"},"hovermode":"closest","paper_bgcolor":"white","plot_bgcolor":"#E5ECF6","polar":{"angularaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","radialaxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"yaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"zaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"baxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","caxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2}}},"title":{"text":"Supply chain traversal"}}}</script></div>

## 4. Time rides along

Nothing in the loop was ever told about time. A [`Flow`](api/flow.md)
carries its time the way it carries its location, so every demand pushed, every emission accumulated and
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

    4.89702e-11 W·yr/m2
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
    2031    9.120996e-13
    2032    8.562483e-13

```python
curve_figure = viz.curve(dynamic)
curve_figure
```

<div class="plotly-figure" data-plotly-height="480" data-plotly-name="curve" data-plotly-layout='{"margin":{"l":70,"r":70,"t":80,"b":60}}'><script type="application/json">{"data":[{"name":"radiative_forcing, per year","type":"bar","x":["2027-01-01T05:49:12","2028-01-01T11:38:24","2028-12-31T17:27:36","2029-12-31T23:16:48","2030-01-01T05:49:12","2031-01-01T05:06:00","2031-01-01T11:38:24","2031-06-15T05:49:12","2032-01-01T10:55:12","2032-01-01T17:27:36","2032-06-14T11:38:24","2032-12-31T16:44:24","2032-12-31T23:16:48","2033-06-14T17:27:36","2033-12-31T22:33:36","2034-01-01T05:06:00","2034-06-14T23:16:48","2035-01-01T04:22:48","2035-01-01T10:55:12","2035-06-15T05:06:00","2036-01-01T10:12:00","2036-01-01T16:44:24","2036-06-14T10:55:12","2036-12-31T16:01:12","2036-12-31T22:33:36","2037-06-14T16:44:24","2037-12-31T21:50:24","2038-01-01T04:22:48","2038-06-14T22:33:36","2039-01-01T03:39:36","2039-01-01T10:12:00","2039-06-15T04:22:48","2040-01-01T09:28:48","2040-01-01T16:01:12","2040-06-14T10:12:00","2040-12-31T15:18:00","2040-12-31T21:50:24","2041-06-14T16:01:12","2041-12-31T21:07:12","2042-01-01T03:39:36","2042-06-14T21:50:24","2043-01-01T02:56:24","2043-01-01T09:28:48","2043-06-15T03:39:36","2044-01-01T08:45:36","2044-01-01T15:18:00","2044-06-14T09:28:48","2044-12-31T14:34:48","2044-12-31T21:07:12","2045-06-14T15:18:00","2045-12-31T20:24:00","2046-01-01T02:56:24","2046-06-14T21:07:12","2047-01-01T02:13:12","2047-01-01T08:45:36","2047-06-15T02:56:24","2048-01-01T08:02:24","2048-01-01T14:34:48","2048-06-14T08:45:36","2048-12-31T13:51:36","2048-12-31T20:24:00","2049-06-14T14:34:48","2049-12-31T19:40:48","2050-01-01T02:13:12","2050-06-14T20:24:00","2051-01-01T01:30:00","2051-01-01T08:02:24","2051-06-15T02:13:12","2052-01-01T07:19:12","2052-01-01T13:51:36","2052-06-14T08:02:24","2052-12-31T13:08:24","2052-12-31T19:40:48","2053-06-14T13:51:36","2053-12-31T18:57:36","2054-01-01T01:30:00","2054-06-14T19:40:48","2055-01-01T00:46:48","2055-01-01T07:19:12","2055-06-15T01:30:00","2056-01-01T06:36:00","2056-01-01T13:08:24","2056-06-14T07:19:12","2056-12-31T12:25:12","2056-12-31T18:57:36","2057-06-14T13:08:24","2057-12-31T18:14:24","2058-01-01T00:46:48","2058-06-14T18:57:36","2059-01-01T00:03:36","2059-01-01T06:36:00","2059-06-15T00:46:48","2060-01-01T05:52:48","2060-01-01T12:25:12","2060-06-14T06:36:00","2060-12-31T11:42:00","2060-12-31T18:14:24","2061-06-14T12:25:12","2061-12-31T17:31:12","2062-01-01T00:03:36","2062-06-14T18:14:24","2062-12-31T23:20:24","2063-01-01T05:52:48","2063-06-15T00:03:36","2064-01-01T05:09:36","2064-01-01T11:42:00","2064-06-14T05:52:48","2064-12-31T10:58:48","2064-12-31T17:31:12","2065-06-14T11:42:00","2065-12-31T16:48:00","2065-12-31T23:20:24","2066-06-14T17:31:12","2066-12-31T22:37:12","2067-01-01T05:09:36","2067-06-14T23:20:24","2068-01-01T04:26:24","2068-01-01T10:58:48","2068-06-14T05:09:36","2068-12-31T10:15:36","2068-12-31T16:48:00","2069-06-14T10:58:48","2069-12-31T16:04:48","2069-12-31T22:37:12","2070-06-14T16:48:00","2070-12-31T21:54:00","2071-01-01T04:26:24","2071-06-14T22:37:12","2072-01-01T03:43:12","2072-01-01T10:15:36","2072-06-14T04:26:24","2072-12-31T09:32:24","2072-12-31T16:04:48","2073-06-14T10:15:36","2073-12-31T15:21:36","2073-12-31T21:54:00","2074-06-14T16:04:48","2074-12-31T21:10:48","2075-01-01T03:43:12","2075-06-14T21:54:00","2076-01-01T03:00:00","2076-01-01T09:32:24","2076-06-14T03:43:12","2076-12-31T08:49:12","2076-12-31T15:21:36","2077-06-14T09:32:24","2077-12-31T14:38:24","2077-12-31T21:10:48","2078-06-14T15:21:36","2078-12-31T20:27:36","2079-01-01T03:00:00","2079-06-14T21:10:48","2080-01-01T02:16:48","2080-01-01T08:49:12","2080-06-14T03:00:00","2080-12-31T08:06:00","2080-12-31T14:38:24","2081-06-14T08:49:12","2081-12-31T13:55:12","2081-12-31T20:27:36","2082-06-14T14:38:24","2082-12-31T19:44:24","2083-01-01T02:16:48","2083-06-14T20:27:36","2084-01-01T01:33:36","2084-01-01T08:06:00","2084-06-14T02:16:48","2084-12-31T07:22:48","2084-12-31T13:55:12","2085-06-14T08:06:00","2085-12-31T13:12:00","2085-12-31T19:44:24","2086-06-14T13:55:12","2086-12-31T19:01:12","2087-01-01T01:33:36","2087-06-14T19:44:24","2088-01-01T00:50:24","2088-01-01T07:22:48","2088-06-14T01:33:36","2088-12-31T06:39:36","2088-12-31T13:12:00","2089-06-14T07:22:48","2089-12-31T12:28:48","2089-12-31T19:01:12","2090-06-14T13:12:00","2090-12-31T18:18:00","2091-01-01T00:50:24","2091-06-14T19:01:12","2092-01-01T00:07:12","2092-01-01T06:39:36","2092-06-14T00:50:24","2092-12-31T05:56:24","2092-12-31T12:28:48","2093-06-14T06:39:36","2093-12-31T11:45:36","2093-12-31T18:18:00","2094-06-14T12:28:48","2094-12-31T17:34:48","2095-01-01T00:07:12","2095-06-14T18:18:00","2095-12-31T23:24:00","2096-01-01T05:56:24","2096-06-14T00:07:12","2096-12-31T05:13:12","2096-12-31T11:45:36","2097-06-14T05:56:24","2097-12-31T11:02:24","2097-12-31T17:34:48","2098-06-14T11:45:36","2098-12-31T16:51:36","2098-12-31T23:24:00","2099-06-14T17:34:48","2099-12-31T22:40:48","2100-01-01T05:13:12","2100-06-14T23:24:00","2101-01-01T04:30:00","2101-01-01T11:02:24","2101-06-15T05:13:12","2102-01-01T10:19:12","2102-01-01T16:51:36","2102-06-15T11:02:24","2103-01-01T16:08:24","2103-01-01T22:40:48","2103-06-15T16:51:36","2104-01-01T21:57:36","2104-01-02T04:30:00","2104-06-14T22:40:48","2105-01-01T03:46:48","2105-01-01T10:19:12","2105-06-15T04:30:00","2106-01-01T09:36:00","2106-01-01T16:08:24","2106-06-15T10:19:12","2107-01-01T15:25:12","2107-01-01T21:57:36","2107-06-15T16:08:24","2108-01-01T21:14:24","2108-01-02T03:46:48","2108-06-14T21:57:36","2109-01-01T03:03:36","2109-01-01T09:36:00","2109-06-15T03:46:48","2110-01-01T08:52:48","2110-01-01T15:25:12","2110-06-15T09:36:00","2111-01-01T14:42:00","2111-01-01T21:14:24","2111-06-15T15:25:12","2112-01-01T20:31:12","2112-01-02T03:03:36","2112-06-14T21:14:24","2113-01-01T02:20:24","2113-01-01T08:52:48","2113-06-15T03:03:36","2114-01-01T08:09:36","2114-01-01T14:42:00","2114-06-15T08:52:48","2115-01-01T13:58:48","2115-01-01T20:31:12","2115-06-15T14:42:00","2116-01-01T19:48:00","2116-01-02T02:20:24","2116-06-14T20:31:12","2117-01-01T01:37:12","2117-01-01T08:09:36","2117-06-15T02:20:24","2118-01-01T07:26:24","2118-01-01T13:58:48","2118-06-15T08:09:36","2119-01-01T13:15:36","2119-01-01T19:48:00","2119-06-15T13:58:48","2120-01-01T19:04:48","2120-01-02T01:37:12","2120-06-14T19:48:00","2121-01-01T00:54:00","2121-01-01T07:26:24","2121-06-15T01:37:12","2122-01-01T06:43:12","2122-01-01T13:15:36","2122-06-15T07:26:24","2123-01-01T12:32:24","2123-01-01T19:04:48","2123-06-15T13:15:36","2124-01-01T18:21:36","2124-01-02T00:54:00","2124-06-14T19:04:48","2125-01-01T00:10:48","2125-01-01T06:43:12","2125-06-15T00:54:00","2126-01-01T12:32:24","2126-06-15T06:43:12","2127-01-01T18:21:36","2127-06-15T12:32:24","2128-01-02T00:10:48","2128-06-14T18:21:36","2129-06-15T00:10:48"],"y":{"bdata":"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","dtype":"f8"}},{"mode":"lines","name":"cumulative (W\u00b7yr/m2)","type":"scatter","x":["2027-01-01T05:49:12","2028-01-01T11:38:24","2028-12-31T17:27:36","2029-12-31T23:16:48","2030-01-01T05:49:12","2031-01-01T05:06:00","2031-01-01T11:38:24","2031-06-15T05:49:12","2032-01-01T10:55:12","2032-01-01T17:27:36","2032-06-14T11:38:24","2032-12-31T16:44:24","2032-12-31T23:16:48","2033-06-14T17:27:36","2033-12-31T22:33:36","2034-01-01T05:06:00","2034-06-14T23:16:48","2035-01-01T04:22:48","2035-01-01T10:55:12","2035-06-15T05:06:00","2036-01-01T10:12:00","2036-01-01T16:44:24","2036-06-14T10:55:12","2036-12-31T16:01:12","2036-12-31T22:33:36","2037-06-14T16:44:24","2037-12-31T21:50:24","2038-01-01T04:22:48","2038-06-14T22:33:36","2039-01-01T03:39:36","2039-01-01T10:12:00","2039-06-15T04:22:48","2040-01-01T09:28:48","2040-01-01T16:01:12","2040-06-14T10:12:00","2040-12-31T15:18:00","2040-12-31T21:50:24","2041-06-14T16:01:12","2041-12-31T21:07:12","2042-01-01T03:39:36","2042-06-14T21:50:24","2043-01-01T02:56:24","2043-01-01T09:28:48","2043-06-15T03:39:36","2044-01-01T08:45:36","2044-01-01T15:18:00","2044-06-14T09:28:48","2044-12-31T14:34:48","2044-12-31T21:07:12","2045-06-14T15:18:00","2045-12-31T20:24:00","2046-01-01T02:56:24","2046-06-14T21:07:12","2047-01-01T02:13:12","2047-01-01T08:45:36","2047-06-15T02:56:24","2048-01-01T08:02:24","2048-01-01T14:34:48","2048-06-14T08:45:36","2048-12-31T13:51:36","2048-12-31T20:24:00","2049-06-14T14:34:48","2049-12-31T19:40:48","2050-01-01T02:13:12","2050-06-14T20:24:00","2051-01-01T01:30:00","2051-01-01T08:02:24","2051-06-15T02:13:12","2052-01-01T07:19:12","2052-01-01T13:51:36","2052-06-14T08:02:24","2052-12-31T13:08:24","2052-12-31T19:40:48","2053-06-14T13:51:36","2053-12-31T18:57:36","2054-01-01T01:30:00","2054-06-14T19:40:48","2055-01-01T00:46:48","2055-01-01T07:19:12","2055-06-15T01:30:00","2056-01-01T06:36:00","2056-01-01T13:08:24","2056-06-14T07:19:12","2056-12-31T12:25:12","2056-12-31T18:57:36","2057-06-14T13:08:24","2057-12-31T18:14:24","2058-01-01T00:46:48","2058-06-14T18:57:36","2059-01-01T00:03:36","2059-01-01T06:36:00","2059-06-15T00:46:48","2060-01-01T05:52:48","2060-01-01T12:25:12","2060-06-14T06:36:00","2060-12-31T11:42:00","2060-12-31T18:14:24","2061-06-14T12:25:12","2061-12-31T17:31:12","2062-01-01T00:03:36","2062-06-14T18:14:24","2062-12-31T23:20:24","2063-01-01T05:52:48","2063-06-15T00:03:36","2064-01-01T05:09:36","2064-01-01T11:42:00","2064-06-14T05:52:48","2064-12-31T10:58:48","2064-12-31T17:31:12","2065-06-14T11:42:00","2065-12-31T16:48:00","2065-12-31T23:20:24","2066-06-14T17:31:12","2066-12-31T22:37:12","2067-01-01T05:09:36","2067-06-14T23:20:24","2068-01-01T04:26:24","2068-01-01T10:58:48","2068-06-14T05:09:36","2068-12-31T10:15:36","2068-12-31T16:48:00","2069-06-14T10:58:48","2069-12-31T16:04:48","2069-12-31T22:37:12","2070-06-14T16:48:00","2070-12-31T21:54:00","2071-01-01T04:26:24","2071-06-14T22:37:12","2072-01-01T03:43:12","2072-01-01T10:15:36","2072-06-14T04:26:24","2072-12-31T09:32:24","2072-12-31T16:04:48","2073-06-14T10:15:36","2073-12-31T15:21:36","2073-12-31T21:54:00","2074-06-14T16:04:48","2074-12-31T21:10:48","2075-01-01T03:43:12","2075-06-14T21:54:00","2076-01-01T03:00:00","2076-01-01T09:32:24","2076-06-14T03:43:12","2076-12-31T08:49:12","2076-12-31T15:21:36","2077-06-14T09:32:24","2077-12-31T14:38:24","2077-12-31T21:10:48","2078-06-14T15:21:36","2078-12-31T20:27:36","2079-01-01T03:00:00","2079-06-14T21:10:48","2080-01-01T02:16:48","2080-01-01T08:49:12","2080-06-14T03:00:00","2080-12-31T08:06:00","2080-12-31T14:38:24","2081-06-14T08:49:12","2081-12-31T13:55:12","2081-12-31T20:27:36","2082-06-14T14:38:24","2082-12-31T19:44:24","2083-01-01T02:16:48","2083-06-14T20:27:36","2084-01-01T01:33:36","2084-01-01T08:06:00","2084-06-14T02:16:48","2084-12-31T07:22:48","2084-12-31T13:55:12","2085-06-14T08:06:00","2085-12-31T13:12:00","2085-12-31T19:44:24","2086-06-14T13:55:12","2086-12-31T19:01:12","2087-01-01T01:33:36","2087-06-14T19:44:24","2088-01-01T00:50:24","2088-01-01T07:22:48","2088-06-14T01:33:36","2088-12-31T06:39:36","2088-12-31T13:12:00","2089-06-14T07:22:48","2089-12-31T12:28:48","2089-12-31T19:01:12","2090-06-14T13:12:00","2090-12-31T18:18:00","2091-01-01T00:50:24","2091-06-14T19:01:12","2092-01-01T00:07:12","2092-01-01T06:39:36","2092-06-14T00:50:24","2092-12-31T05:56:24","2092-12-31T12:28:48","2093-06-14T06:39:36","2093-12-31T11:45:36","2093-12-31T18:18:00","2094-06-14T12:28:48","2094-12-31T17:34:48","2095-01-01T00:07:12","2095-06-14T18:18:00","2095-12-31T23:24:00","2096-01-01T05:56:24","2096-06-14T00:07:12","2096-12-31T05:13:12","2096-12-31T11:45:36","2097-06-14T05:56:24","2097-12-31T11:02:24","2097-12-31T17:34:48","2098-06-14T11:45:36","2098-12-31T16:51:36","2098-12-31T23:24:00","2099-06-14T17:34:48","2099-12-31T22:40:48","2100-01-01T05:13:12","2100-06-14T23:24:00","2101-01-01T04:30:00","2101-01-01T11:02:24","2101-06-15T05:13:12","2102-01-01T10:19:12","2102-01-01T16:51:36","2102-06-15T11:02:24","2103-01-01T16:08:24","2103-01-01T22:40:48","2103-06-15T16:51:36","2104-01-01T21:57:36","2104-01-02T04:30:00","2104-06-14T22:40:48","2105-01-01T03:46:48","2105-01-01T10:19:12","2105-06-15T04:30:00","2106-01-01T09:36:00","2106-01-01T16:08:24","2106-06-15T10:19:12","2107-01-01T15:25:12","2107-01-01T21:57:36","2107-06-15T16:08:24","2108-01-01T21:14:24","2108-01-02T03:46:48","2108-06-14T21:57:36","2109-01-01T03:03:36","2109-01-01T09:36:00","2109-06-15T03:46:48","2110-01-01T08:52:48","2110-01-01T15:25:12","2110-06-15T09:36:00","2111-01-01T14:42:00","2111-01-01T21:14:24","2111-06-15T15:25:12","2112-01-01T20:31:12","2112-01-02T03:03:36","2112-06-14T21:14:24","2113-01-01T02:20:24","2113-01-01T08:52:48","2113-06-15T03:03:36","2114-01-01T08:09:36","2114-01-01T14:42:00","2114-06-15T08:52:48","2115-01-01T13:58:48","2115-01-01T20:31:12","2115-06-15T14:42:00","2116-01-01T19:48:00","2116-01-02T02:20:24","2116-06-14T20:31:12","2117-01-01T01:37:12","2117-01-01T08:09:36","2117-06-15T02:20:24","2118-01-01T07:26:24","2118-01-01T13:58:48","2118-06-15T08:09:36","2119-01-01T13:15:36","2119-01-01T19:48:00","2119-06-15T13:58:48","2120-01-01T19:04:48","2120-01-02T01:37:12","2120-06-14T19:48:00","2121-01-01T00:54:00","2121-01-01T07:26:24","2121-06-15T01:37:12","2122-01-01T06:43:12","2122-01-01T13:15:36","2122-06-15T07:26:24","2123-01-01T12:32:24","2123-01-01T19:04:48","2123-06-15T13:15:36","2124-01-01T18:21:36","2124-01-02T00:54:00","2124-06-14T19:04:48","2125-01-01T00:10:48","2125-01-01T06:43:12","2125-06-15T00:54:00","2126-01-01T12:32:24","2126-06-15T06:43:12","2127-01-01T18:21:36","2127-06-15T12:32:24","2128-01-02T00:10:48","2128-06-14T18:21:36","2129-06-15T00:10:48"],"y":{"bdata":"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","dtype":"f8"},"yaxis":"y2"}],"layout":{"margin":{"b":40,"l":40,"r":20,"t":50},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","template":{"data":{"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"barpolar":[{"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"#E5ECF6","showlakes":true,"showland":true,"subunitcolor":"white"},"hoverlabel":{"align":"left"},"hovermode":"closest","paper_bgcolor":"white","plot_bgcolor":"#E5ECF6","polar":{"angularaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","radialaxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"yaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"zaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"baxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","caxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2}}},"title":{"text":"radiative_forcing over 100 years"},"xaxis":{"title":{"text":"year"}},"yaxis":{"title":{"text":"W/m2"}},"yaxis2":{"overlaying":"y","side":"right","title":{"text":"W\u00b7yr/m2"}}}}</script></div>

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
    wrote showcase_log.parquet: 304 rows, 27 columns
    kinds: ['attribution', 'biosphere', 'node', 'provenance', 'resolution', 'unresolved']

```python
contributions_figure = viz.contributions(
    assessment, by="node", labels={node.id: node.model for node in report.nodes}
)
contributions_figure
```

<div class="plotly-figure" data-plotly-height="520" data-plotly-name="contributions" data-plotly-layout='{"margin":{"l":70,"r":20,"t":60,"b":150}}'><script type="application/json">{"data":[{"type":"bar","x":["CementPlant","BinderSupply","NaturalGasExtraction","GasPower","NaturalGasOffshorePipelineTransport","NaturalGasExtraction","BackgroundDataset","BackgroundDataset","BackgroundDataset","BackgroundDataset"],"y":[536.1,9.0,4.700051369863014,2.7526881720430105,0.25834124250000007,0.09334614584283167,0.020986666666666667,0.015119999999999998,0.010493333333333334,0.007559999999999999]}],"layout":{"margin":{"b":40,"l":40,"r":20,"t":50},"paper_bgcolor":"rgba(0,0,0,0)","plot_bgcolor":"rgba(0,0,0,0)","template":{"data":{"bar":[{"error_x":{"color":"#2a3f5f"},"error_y":{"color":"#2a3f5f"},"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"bar"}],"barpolar":[{"marker":{"line":{"color":"#E5ECF6","width":0.5},"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"barpolar"}],"carpet":[{"aaxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"baxis":{"endlinecolor":"#2a3f5f","gridcolor":"white","linecolor":"white","minorgridcolor":"white","startlinecolor":"#2a3f5f"},"type":"carpet"}],"choropleth":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"choropleth"}],"contour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"contour"}],"contourcarpet":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"contourcarpet"}],"heatmap":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"heatmap"}],"histogram":[{"marker":{"pattern":{"fillmode":"overlay","size":10,"solidity":0.2}},"type":"histogram"}],"histogram2d":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2d"}],"histogram2dcontour":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"histogram2dcontour"}],"mesh3d":[{"colorbar":{"outlinewidth":0,"ticks":""},"type":"mesh3d"}],"parcoords":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"parcoords"}],"pie":[{"automargin":true,"type":"pie"}],"scatter":[{"fillpattern":{"fillmode":"overlay","size":10,"solidity":0.2},"type":"scatter"}],"scatter3d":[{"line":{"colorbar":{"outlinewidth":0,"ticks":""}},"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatter3d"}],"scattercarpet":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattercarpet"}],"scattergeo":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergeo"}],"scattergl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattergl"}],"scattermap":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scattermap"}],"scatterpolar":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolar"}],"scatterpolargl":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterpolargl"}],"scatterternary":[{"marker":{"colorbar":{"outlinewidth":0,"ticks":""}},"type":"scatterternary"}],"surface":[{"colorbar":{"outlinewidth":0,"ticks":""},"colorscale":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"type":"surface"}],"table":[{"cells":{"fill":{"color":"#EBF0F8"},"line":{"color":"white"}},"header":{"fill":{"color":"#C8D4E3"},"line":{"color":"white"}},"type":"table"}]},"layout":{"annotationdefaults":{"arrowcolor":"#2a3f5f","arrowhead":0,"arrowwidth":1},"autotypenumbers":"strict","coloraxis":{"colorbar":{"outlinewidth":0,"ticks":""}},"colorscale":{"diverging":[[0,"#8e0152"],[0.1,"#c51b7d"],[0.2,"#de77ae"],[0.3,"#f1b6da"],[0.4,"#fde0ef"],[0.5,"#f7f7f7"],[0.6,"#e6f5d0"],[0.7,"#b8e186"],[0.8,"#7fbc41"],[0.9,"#4d9221"],[1,"#276419"]],"sequential":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]],"sequentialminus":[[0.0,"#0d0887"],[0.1111111111111111,"#46039f"],[0.2222222222222222,"#7201a8"],[0.3333333333333333,"#9c179e"],[0.4444444444444444,"#bd3786"],[0.5555555555555556,"#d8576b"],[0.6666666666666666,"#ed7953"],[0.7777777777777778,"#fb9f3a"],[0.8888888888888888,"#fdca26"],[1.0,"#f0f921"]]},"colorway":["#636efa","#EF553B","#00cc96","#ab63fa","#FFA15A","#19d3f3","#FF6692","#B6E880","#FF97FF","#FECB52"],"font":{"color":"#2a3f5f"},"geo":{"bgcolor":"white","lakecolor":"white","landcolor":"#E5ECF6","showlakes":true,"showland":true,"subunitcolor":"white"},"hoverlabel":{"align":"left"},"hovermode":"closest","paper_bgcolor":"white","plot_bgcolor":"#E5ECF6","polar":{"angularaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","radialaxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"scene":{"xaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"yaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"},"zaxis":{"backgroundcolor":"#E5ECF6","gridcolor":"white","gridwidth":2,"linecolor":"white","showbackground":true,"ticks":"","zerolinecolor":"white"}},"shapedefaults":{"line":{"color":"#2a3f5f"}},"ternary":{"aaxis":{"gridcolor":"white","linecolor":"white","ticks":""},"baxis":{"gridcolor":"white","linecolor":"white","ticks":""},"bgcolor":"#E5ECF6","caxis":{"gridcolor":"white","linecolor":"white","ticks":""}},"title":{"x":0.05},"xaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2},"yaxis":{"automargin":true,"gridcolor":"white","linecolor":"white","ticks":"","title":{"standoff":15},"zerolinecolor":"white","zerolinewidth":2}}},"title":{"text":"Contributions by node"},"xaxis":{"title":{"text":"node"}},"yaxis":{"title":{"text":"kg"}}}}</script></div>

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
