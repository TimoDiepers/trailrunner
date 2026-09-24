---
icon: lucide/presentation
tags:
  - tutorial
---

# The pitch (5 min)

**1 t Portland cement, Denmark, 15 June 2030 — what's the impact?**

`trailrunner`: computational process models, not static unit processes.

*Shorter version: [3-minute pitch](pitch.md).*

---

## Models instead of unit processes

```python
# called directly, a model gets exactly what it is handed: kilograms
answer = cement_model.apply(Demand(flow=DEMAND.flow, amount=1000.0, unit=KG))
```

```text
                 amount unit flow                                         where       when
   production    1000.0 kg   Portland cement, aluminous cement, slag cem… DK    2030-06-15
 technosphere    1125.0 kg   Gypsum; anhydrite; limestone flux; limeston… DK    2030-06-15
 technosphere    2475.0 MJ   Natural gas, liquefied or in the gaseous st… DK    2030-06-15
 technosphere      10.0 kg   Quicklime, slaked lime and hydraulic lime    DK    2030-06-15
 technosphere     100.0 kWh  electricity                                  DK    2030-06-15
    biosphere     397.5 kg   co2-fossil                                   DK    2030-06-15
    biosphere     138.6 kg   co2-fossil                                   DK    2030-06-15
```

- Takes a `Demand`, returns a `Result`: made, needed, emitted
- Names = concepts from the [sentier vocabulary](https://vocab.sentier.dev) — shared, so two models can compose with no name matching
- Physics-aware: process can react to *where* and *when* it's asked

```python
row = params.at(location="DK", **in_year(2030))
penalty = moisture_penalty(row["moisture"], row["temperature"])
fuel = row["fuel_demand"] * clinker * penalty
```

```text
 where   when  moisture   degC   penalty   gas [MJ]
    DK   2030     0.040   10.0     1.000     2475.0
   RER   2030     0.060    9.0     1.044     2923.2
```

!!! info "trailpack"
    Params from [`trailpack`](https://github.com/TimoDiepers/trailpack) parquet — units & vocab IRIs embedded per column. BrightCon 2025 hackathon project.

**Measured beats modelled, when it exists.** Same product, disjoint
coverage — time on the demand picks meter vs. model:

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

Meter sees one plume. Model knows which kg came from where.

---

## Orchestrating multiple models

```mermaid
%%{init: {'layout': 'elk'}}%%
flowchart TB
    D([demand]) --> Q[[Queue]]
    Q -->|pop| C{{ResolutionChain}}
    C -->|who offers?| G[(Glossary)]
    G -->|Offer| C
    C -->|selected| R[Runner]
    R -->|apply| M[Model]
    M -->|Result| R
    R -->|new demands| Q
    R -->|elementary flows| I[(inventory)]

    classDef resolution fill:#2dd4bf22,stroke:#2dd4bf
    classDef execution fill:#f59e0b22,stroke:#f59e0b
    classDef record fill:#8b5cf622,stroke:#8b5cf6
    class C,G resolution
    class R,M execution
    class I record
```

`Orchestrator.calculate` = `while queue:`, little else. Pop a demand, ask who
can answer it, push what comes back, write everything down. A model is found
by the IRI it declares in `produces` — no wiring, no registry.

---

## Finding fallback models

Tier 1 = models. Every later tier = **concession**, written at the node.

**Tier 2 generalises the demand** one `skos:broader` step at a time:

```text
       model: BinderSupply
 relaxations: ['product: fi_37420 -> fi_374']
       asked: Quicklime, slaked lime and hydraulic lime
    answered: Plaster, lime and cement
        tier: generalising
```

"Plaster, lime **and cement**" — contains the very product this plant
makes. Best available, poor in substance. Not hidden.

**Tier 2 also relaxes context.** Time and place are not the only things a
demand asks for. The kiln burners want gas at **4e5 Pa** (4 bar), carried in
the flow's `context`; `NaturalGasSupply` declares in its coverage that it
delivers at **5e5 Pa**. Tier 1 misses. The practitioner allows pressure to be
met up to 1e5 Pa higher, never lower — gas is throttled at the burner, not
boosted:

```python
ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})  # (below, above, unit)
```

```text
       model: NaturalGasSupply
 relaxations: ['context: pressure 400000 Pa -> 500000 Pa']
       asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020 @DK/2030-06-15 [pressure=400000 Pa]
    answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020 @DK/2030-06-15 [pressure=500000 Pa]
        tier: generalising
```

The gas plant's own gas names no pressure, so any supplier answers it — a
plain tier-1 match, same supplier, same run.

**Tier 3 borrows a dataset** from a curated background pack and tags it
`incomplete`, because its own upstream is missing rather than deferred.

---

## The cement chain, end to end

**A unit falls back exactly.** The demand is **1 t** on **15 June 2030**;
`CementPlant` reasons in kilograms, per year:

```python
DEMAND = Demand(
    flow=Flow(iri=CEMENT, location="DK", time="2030-06-15", time_standard=DATE),
    amount=1.0,
    unit=TONNE,
)
```

```text
1 t Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @DK/2030-06-15  [model: CementPlant; unit: t -> kg ×1000]
```

Same quantity, different unit: converted by the vocabulary's own multiplier,
logged on the node, and not counted as a concession.

One `while queue:` later — 1 t of Danish cement, every tier in one run:

```text
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
  0.00833333 t/yr cement-kiln @DK/2026  [model: CementKilnConstruction]
    0.1 kg steel-low-alloyed @DK/2026  [background: unit_process, incomplete]
    0.00666667 kg aluminium-primary @DK/2026  [background: unit_process, incomplete]
  0.0166667 t/yr cement-kiln @DK/2029  [model: CementKilnConstruction]
    0.2 kg steel-low-alloyed @DK/2029  [background: unit_process, incomplete]
    0.0133333 kg aluminium-primary @DK/2029  [background: unit_process, incomplete]
  1125 kg Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement @DK/2030-06-15  [cutoff: generalisation_exhausted]
```

```mermaid
%%{init: {'layout': 'elk'}}%%
flowchart TB
    D(["1 t cement @DK/2030-06-15"]) --> CP["CementPlant<br/>DK · 2030-06-15 · in kg"]

    CP -->|"2475 MJ natural gas @ 4e5 Pa<br/>tier 2 · met at 5e5 Pa"| NGS["NaturalGasSupply<br/>DK · 2030-06-15 · delivers 5e5 Pa"]
    CP -->|"100 kWh electricity"| GE["GridElectricity<br/>DK · 2030-06-15"]
    CP -->|"10 kg lime"| BS["BinderSupply<br/>DK · 2030-06-15<br/>tier 2 · asked fi_37420, answered fi_374"]
    CP -->|"0.0083 t/yr kiln line"| K26["CementKilnConstruction<br/>DK · 2026"]
    CP -->|"0.0167 t/yr kiln line"| K29["CementKilnConstruction<br/>DK · 2029"]
    CP -.->|"1125 kg limestone"| XG["cutoff<br/>DK · 2030-06-15"]

    NGS -->|"68.75 m3 gas at production"| NGE["NaturalGasExtraction<br/>NO · 2030-06-15"]
    NGS -->|"0.0505 t gas over 1000 km"| PT["OffshorePipelineTransport<br/>NO · 2030-06-15"]
    PT -->|"0.013 m3 leaked gas"| NGE
    PT -.->|"pipe · turbine fuel · lorry · oil"| XP["4 cutoffs<br/>NO · 2030-06-15"]

    GE -->|"8.47 kWh gas power"| GP["GasPower<br/>DK · 2030-06-15"]
    GE -.->|"84.66 kWh wind · 12.7 kWh hydro"| XE["2 cutoffs<br/>DK · 2030-06-15"]
    GP -->|"49.16 MJ natural gas"| NGS

    K26 -->|"0.1 kg steel · 6.7 g aluminium"| B26["background dataset<br/>DK · 2026<br/>tier 3 · incomplete"]
    K29 -->|"0.2 kg steel · 13 g aluminium"| B29["background dataset<br/>DK · 2029<br/>tier 3 · incomplete"]

    CP -->|"536.1 kg CO2"| INV[("inventory")]
    BS -->|"9 kg CO2"| INV
    GP -->|"2.75 kg CO2"| INV
    NGE -->|"4.79 kg CO2 · 71.5 m3 gas in ground"| INV
    PT -->|"8.8 g CH4 · ethane · Hg · NMVOC"| INV
    B26 -->|"18 mg CO2"| INV
    B29 -->|"36 mg CO2"| INV

    classDef t1 fill:#f59e0b22,stroke:#f59e0b
    classDef t2 fill:#3b82f622,stroke:#3b82f6
    classDef t3 fill:#14b8a622,stroke:#14b8a6
    classDef gap fill:#ef444422,stroke:#ef4444,stroke-dasharray:4 3
    classDef record fill:#8b5cf622,stroke:#8b5cf6
    class CP,NGS,NGE,PT,GE,GP,K26,K29 t1
    class BS t2
    class B26,B29 t3
    class XG,XP,XE gap
    class INV record

    linkStyle 1,3 stroke:#3b82f6
    linkStyle 14,15 stroke:#14b8a6
    linkStyle 6,10,12 stroke:#ef4444
    linkStyle 16,17,18,19,20,21,22 stroke:#8b5cf6
```

*Amber = tier 1, a model answered · blue = tier 2, a relaxed demand (broader
concept, or pressure met higher) · teal = tier 3, borrowed dataset · red dashed = cutoff · violet =
elementary flows into the inventory.*

Read the years. The kilns were built in **2026** and **2029**, so their
construction and the background steel behind it are dated there; the cement
and the gas that fires it are **15 June 2030**; and the gas itself is extracted and
piped in **NO**, not DK. Nothing in the loop was told about time or place —
the flows carried both.

```text
18 nodes, 13 inventory entries
11 unresolved (generalisation_exhausted: 11)
6 proxies (4 incomplete)
attribution: allocation=none, capital=per_output
```

`capital=per_output` — normative choice, stated next to the numbers.

!!! info "Where the pipeline model comes from"
    Reverse-engineered from BAFU-2026 ecoinvent EcoSpold data and the Bussa et al. 2025 LCI report — not invented.

---

## Tracing time and place for free

Those dates survived the traversal, so the inventory is already a time series:

```python
dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
```

![Marginal and cumulative radiative forcing over 100 years](assets/showcase/curve.svg)

- Kilns (2027/2029): barely register
- 2031 cement production: 4 orders of magnitude bigger
- No matrix rebuilt, no second model — dates were never lost

---

## Why we want this

- **Supply chain assembles itself** — vocabulary IRIs, not wiring
- **Missing data is visible** — every cutoff carries a reason and a position
- **Concessions are declared and recorded** — not buried in an assumption
- **Inventories are time-explicit by construction** — dynamic LCIA needs no second model
- **The run is a file** — one parquet holds the graph, the gaps and the choices
- **A process can depend on its demand** — location, year, scale, feed conditions live in the model
- **Demands match on more than time and place** — a declared condition like pressure is covered, or relaxed on the record
- **A model can be a measurement** — same interface, disjoint coverage, report says which answered

---

*Shorter cut: [3-minute pitch](pitch.md) · Full tour: [showcase.md](showcase.md) ·
Notebook: [`examples/showcase.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb)*
