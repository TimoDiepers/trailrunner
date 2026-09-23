---
tags:
  - tutorial
---

# The 5-minute tour

One demand, carried end to end.

**1000 kg of Portland cement, in Switzerland, in 2030.**

Ordinary practice answers that by looking the process up in a dataset and
multiplying. `trailrunner` asks a model, and the model answers for the demand it
was actually given, in the place and the year it was given. Everything on this
page follows from that one change.

Every number and every block of output came out of
[`examples/showcase.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb),
which runs offline from committed files.

---

## 1. A process is something you run

A [`Model`](api/model.md) has one method. It takes a [`Demand`](api/flow.md) and
returns a [`Result`](api/result.md), answering three questions at once. What did
I make, what do I need, what did I emit.

```python
answer = works.apply(DEMAND)  # no orchestrator involved, a model is callable on its own
```

```text
   production    1000.0 kg   Portland cement, aluminous cement, slag cem… @CH/2030
 technosphere    1125.0 kg   Gypsum; anhydrite; limestone flux; limeston… @CH/2030
 technosphere    2475.0 MJ   Natural gas, liquefied or in the gaseous st… @CH/2030
 technosphere     340.0 MJ   heat from electric boilers                   @CH/2030
 technosphere     100.0 kWh  electricity                                  @CH/2030
    biosphere     397.5 kg   co2-fossil                                   @CH/2030
    biosphere     138.6 kg   co2-fossil                                   @CH/2030
   provenance  {'location_requested': 'CH', 'location_used': 'CH', 'location_fallback': False, 'time_requested': 2030, 'time_used': 2030, 'time_interpolated': False, 'source': 'modelled'}
```

Three lists, three destinations. `production` is checked against the demand that
triggered the run and then dropped. `technosphere` goes back on the queue, and
is where the traversal comes from. `biosphere` accumulates into the inventory.
`provenance` records which parameter row the model read and which fallbacks it
took.

Two biosphere lines, not one. The kiln's CO<sub>2</sub> has two origins —
limestone giving up its carbon, and gas burning to drive that off — and the
model keeps them apart because it knows which is which. Beat 4 is about what
happens when your data source does not.

The demand arrives as an argument, so the answer can depend on it. Inside
`CementPlant` the kiln fuel responds to the raw meal the works is fed, because
water in the feed has to be boiled off before any limestone calcines.

```python
penalty = moisture_penalty(row["moisture"], row["temperature"])
fuel = row["fuel_demand"] * clinker * penalty
```

The same 1000 kg, asked for in four different places and years.

```text
 where   when  moisture   degC   penalty   gas [MJ]
    CH   2030     0.040   10.0     1.000     2475.0
    CH   2040     0.040   11.0     0.996     2099.6
   RER   2030     0.060    9.0     1.044     2923.2
   RER   2040     0.055   10.0     1.030     2447.3
```

`apply` receives the **full** demanded amount, the whole thing that was asked
for, and nothing downstream rescales what comes back. A model whose response
bends with scale can say so.

---

## 2. Models find each other through a vocabulary

Every flow is identified by an IRI from the hierarchical
[sentier vocabulary](https://vocab.sentier.dev). A `Demand` for
`…/BONSAI2025.1/fi_1730_6` finds whoever declared that same IRI in `produces`,
with no name matching and no unit guessing in between. That is what lets two
models written by two people compose at all, and it is what the orchestrator
uses to walk outward.

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

`Orchestrator.calculate` is a `while queue:` and little else. Pop a demand, ask
the chain who can answer it, hand the offer to the [`Runner`](api/runner.md),
push the `Result`'s technosphere demands back on, write everything to the
[`Log`](api/log.md). Every seam in that sentence is an object you can replace,
which also makes the loop easy to watch. Subclass the chain, print each demand
it is asked about, and the traversal narrates itself.

```python
class Narrating(ResolutionChain):
    def offer(self, demand, exclude=()):
        offer = super().offer(demand, exclude=exclude)
        who = type(offer.model).__name__ if offer else "cutoff (nobody offered)"
        print(f"pop {demand.amount:>9.4g} {demand.unit:<4} {name(demand.flow.iri, 32):<32} -> {who}")
        return offer


first = Orchestrator(Narrating([ModelProvider(Glossary(MODELS))])).calculate(DEMAND)
```

```text
pop      1000 kg   Portland cement, aluminous ceme… -> CementPlant
pop      1125 kg   Gypsum; anhydrite; limestone fl… -> cutoff (nobody offered)
pop      2475 MJ   Natural gas, liquefied or in th… -> cutoff (nobody offered)
pop       340 MJ   heat from electric boilers       -> cutoff (nobody offered)
pop       100 kWh  electricity                      -> GridElectricity
pop     2.128 kWh  electricity-natural-gas          -> GasPower
pop     19.15 kWh  electricity-wind                 -> cutoff (nobody offered)
pop     85.11 kWh  electricity-hydro                -> cutoff (nobody offered)
pop     12.35 MJ   Natural gas, liquefied or in th… -> cutoff (nobody offered)
```

Breadth-first, and every pop after the first is a demand some earlier model
returned. The supply chain assembled itself from the registered models and one
starting demand.

The names come from the vocabulary as well. Each concept carries a
`skos:prefLabel`, read here from a committed cache, so the run prints in words.
The lines that still show identifiers are `trailrunner`'s own invented IRIs, and
the vocabulary has no concept for them. Beat 3 returns to that.

Two pops found a model. The rest found nobody, and every one of those is in the
report with a reason and a parent.

```text
3 nodes, 1 inventory entry
6 unresolved (no_model_found: 6)
0 proxies
attribution: allocation=none, capital=per_output

1000 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @CH/2030  [model: CementPlant]
  100 kWh electricity @CH/2030  [model: GridElectricity]
    2.12766 kWh electricity-natural-gas @CH/2030  [model: GasPower]
      12.3542 MJ Natural gas, liquefied or in the gaseous state @CH/2030  [cutoff: no_model_found]
    19.1489 kWh electricity-wind @CH/2030  [cutoff: no_model_found]
    85.1064 kWh electricity-hydro @CH/2030  [cutoff: no_model_found]
  1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @CH/2030  [cutoff: no_model_found]
  2475 MJ Natural gas, liquefied or in the gaseous state @CH/2030  [cutoff: no_model_found]
  340 MJ heat from electric boilers @CH/2030  [cutoff: no_model_found]
```

A gap in the supply chain is data in the answer. Every line says how honestly it
was reached, and a cutoff hangs under the node that asked for it.

---

## 3. A demand nobody answers is relaxed along the vocabulary

[`ResolutionChain`](api/resolution.md) is a list of providers, asked in order,
and the first offer wins. Tier 1 is the models. Every later tier is a
concession, and the tier that made it writes what it conceded into the node's
resolution.

**Tier 2 generalises the demand.** The works asks for `fi_1730_6`, "heat from
electric boilers", because that is the boiler the site installed. Nothing
produces it. One `skos:broader` step up sits `fi_1730`, "Steam and hot water", a
real BONSAI concept read from a committed cache, and a generic `HeatSupply`
registered at the parent can answer the relaxed demand. The report says in words
how far the demand travelled.

```text
       model: HeatSupply
 relaxations: ['product: fi_1730_6 -> fi_1730']
       asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_6 @CH/2030
    answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730 @CH/2030
        tier: generalising

   asked, in words: heat from electric boilers
answered, in words: Steam and hot water
```

A technology was asked for and an average came back. That is the concession, and
it is written at the node rather than lost.

**Tier 3 borrows a dataset.** Given its `Fleet`, `CementPlant` demands each
kiln's construction in the year that kiln was built, and a construction model
turns that into steel and aluminium taken from a curated background pack.

```text
10 nodes, 5 inventory entries
6 unresolved (generalisation_exhausted: 6)
5 proxies (4 incomplete)
attribution: allocation=none, capital=per_output

1000 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @CH/2030  [model: CementPlant]
  340 MJ heat from electric boilers @CH/2030  [proxy: product: fi_1730_6 -> fi_1730]
    400 MJ Natural gas, liquefied or in the gaseous state @CH/2030  [cutoff: generalisation_exhausted]
  100 kWh electricity @CH/2030  [model: GridElectricity]
    2.12766 kWh electricity-natural-gas @CH/2030  [model: GasPower]
      12.3542 MJ Natural gas, liquefied or in the gaseous state @CH/2030  [cutoff: generalisation_exhausted]
    19.1489 kWh electricity-wind @CH/2030  [cutoff: generalisation_exhausted]
    85.1064 kWh electricity-hydro @CH/2030  [cutoff: generalisation_exhausted]
  8.33333 kg/year cement-kiln @CH/2026  [model: CementKilnConstruction]
    0.1 kg steel-low-alloyed @CH/2026  [background: unit_process, incomplete]
    0.00666667 kg aluminium-primary @CH/2026  [background: unit_process, incomplete]
  16.6667 kg/year cement-kiln @CH/2029  [model: CementKilnConstruction]
    0.2 kg steel-low-alloyed @CH/2029  [background: unit_process, incomplete]
    0.0133333 kg aluminium-primary @CH/2029  [background: unit_process, incomplete]
  1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @CH/2030  [cutoff: generalisation_exhausted]
  2475 MJ Natural gas, liquefied or in the gaseous state @CH/2030  [cutoff: generalisation_exhausted]
```

![The traversal, coloured by the tier that answered each node](assets/showcase/sankey.svg)

The tag on each line says which tier put it there. The borrowed rows carry
`incomplete` because the pack holds each dataset's direct exchanges only, so
their own upstream is missing and the report says so.

Every concession is deliberate, ordered by the practitioner, and written down.

!!! warning "What this beat does not claim"

    - `HeatSupply` and `CementKilnConstruction` are written in the notebook
      rather than shipped, because nothing in this repository produces
      `fi_1730`. Their efficiency and material intensities are invented. The
      `skos:broader` walk, the pack lookup, the completeness flag and the
      construction pulse are the library.
    - `cement-kiln`, `electricity-wind`, `electricity-hydro` and
      `electricity-natural-gas` are `trailrunner`'s own IRIs. The vocabulary
      answers 404 for them, which is why they have no printed name and why the
      product dimension can never relax them. They stay cutoffs.
    - The background pack holds no electricity dataset, deliberately. A grid-mix
      unit process delegates its combustion upstream, so borrowing one would
      answer a kilowatt hour with a plausible looking near-zero. A visible
      cutoff is worth more.

---

## 4. Some data is measured

A model does not have to compute anything. What makes something a model here is
that it answers a demand, not that it calculates one — so a process that has
been metered is a model too, reading its numbers from the same kind of parquet
any other parameter comes from.

The works has a stack monitor and years of readings. `MeteredCementPlant`
declares the same product IRI as `CementPlant` and a `Coverage` that ends where
the other one begins. Nothing else changes:
[`Glossary`](api/glossary.md)`.resolve` already filters candidates by coverage,
so the year on the demand decides which model answers.

```python
coverage = Coverage(time_range=(2018, 2025))  # MeteredCementPlant
coverage = Coverage(time_range=(2026, 2050))  # CementPlant
```

```text
2023  answered by MeteredCementPlant
      source: measured
      direct CO2:  562.0 kg in 1 exchange(s)
           562.0 kg
2030  answered by CementPlant
      source: modelled
      direct CO2:  536.1 kg in 2 exchange(s)
           397.5 kg
           138.6 kg
```

Two exchanges in 2030, one in 2023, and that difference is the beat. The model
knows which kilogram came from the limestone and which from the flame, because
it computed them separately. The meter does not: a stack monitor sees one plume
and cannot tell you what made it.

Neither answer is better. The measured year is the real plant; the modelled year
is an argument about a plant that does not exist yet. What matters is that the
report says which one you are reading, at the node, without anyone having to
remember a convention.

Note what the metered model still sends upstream. Its gas, its steam and its
electricity are *inputs* — their emissions happen somewhere else — so they go
back on the queue and are answered by whoever supplies them, exactly as the
computed model's are. A meter at the fence line says nothing about what happens
beyond it.

The normative choices a study still has to make, and a model that co-produces,
are in [`examples/coproduction.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/coproduction.ipynb)
and [Attribution](content/attribution.md).

---

## 5. Time rides along

Nothing in the loop was ever told about time. A [`Flow`](api/flow.md) carries its
year the way it carries its location, so every demand pushed, every emission
accumulated and every node logged is already dated. The kilns doing the
calcining were built in 2026 and 2029. The cement, and the gas firing the kiln,
happen in 2030.

So the inventory is a time series, and can be characterized as one.

```python
dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
```

```text
4.95295e-11 W·yr/m2
metric: radiative_forcing, horizon: 100 years
horizon anchored at: 2026-01-01
0 uncharacterized exchanges
0 wrong unit exchanges
0 undated exchanges
0 beyond-horizon exchanges
6 unresolved
5 proxies

marginal radiative forcing, first years [W/m2]:
date
2027    3.366920e-17
2028    6.149503e-17
2029    2.849848e-17
2030    6.733840e-17
2031    9.211927e-13
2032    1.683342e-12
```

![Marginal and cumulative radiative forcing over 100 years](assets/showcase/curve.svg)

The faint bars are the per-year forcing and the red line is its running total.
The kilns show up in 2027 and 2029, and then 2031 arrives and the scale of the
plot changes: building two cement works is four orders of magnitude below one
year of making cement in them. That is not a flaw in the example. It is what the
industry's problem actually looks like, and it is visible here only because the
dates survived.

No matrix was rebuilt and no second model was written. Characterization is a
separate reading of an inventory whose dates were never lost.

---

## 6. The run leaves a record

```python
print(report.summary())
report.log.to_parquet("showcase_log.parquet")
```

```text
10 nodes, 5 inventory entries
6 unresolved (generalisation_exhausted: 6)
5 proxies (4 incomplete)
attribution: allocation=none, capital=per_output

wrote showcase_log.parquet: 145 rows, 19 columns
kinds: ['attribution', 'biosphere', 'node', 'provenance', 'resolution', 'unresolved']
```

![Contribution to the GWP100 score by node](assets/showcase/contributions.svg)

Every node, every cutoff, every parameter fallback and every proxy, one row
each. Parameters arrive as parquet and the whole run leaves as parquet, so two
studies can be diffed with a single read.

---

## What this changes

- **A process can depend on its demand.** Location, year, scale and feed
  conditions live in the model, where a physical dependency belongs.
- **A model can be a measurement.** Two models, one product, disjoint coverage:
  the year on the demand decides whether you get a meter reading or a
  calculation, and the report says which.
- **The supply chain assembles itself.** Models declare vocabulary IRIs, and the
  orchestrator finds who answers what.
- **Missing data is visible.** Cutoffs carry a reason and a position in the
  chain, so a reader can see what a number excludes.
- **Concessions are declared and recorded.** A generalised demand or a borrowed
  dataset is tagged at the node, with what was asked and what answered it.
- **Inventories are time-explicit by construction.** Dates survive the
  traversal, so dynamic characterization needs no second model.
- **The run is a file.** One parquet holds the graph, the gaps and the choices.

??? note "Presenting this"

    Beats 1, 2 and 4 are the argument and should be read whatever happens to the
    clock. They come to roughly three minutes. Beat 3 is where `HeatSupply` and
    `CementKilnConstruction` arrive, so cutting it also costs beat 5's
    construction pulse its explanation.

    Cut in this order. Beat 6 first, then the second half of beat 3.

    Two lines are worth saying aloud rather than reading. On beat 2, after the
    pop trace, that a matrix gives you a number here and no list of what was
    missing from it. On beat 4, that neither answer is the better one — the
    point is that the report tells you which you are holding. Read the
    disclaimer in beat 3 before the output rather than after it.

---

- The notebook this page is made of: [`examples/showcase.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb)
- The same pieces in reference form: [Core Concepts](content/concepts.md)
- [Installation](content/installation.md)
