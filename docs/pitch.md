---
icon: lucide/megaphone
tags:
  - tutorial
---

# The pitch (3 min)

`trailrunner` treats one physical activity as one *model*, a piece of code
for one process. Given a demand for one of its products, the model works out
which inputs it needs and what it emits, reading its parameters from a
[trailpack](https://github.com/TimoDiepers/trailpack) parquet file.

Every flow is named by an IRI from the
[sentier vocabulary](https://vocab.sentier.dev). The orchestrator reads a
model's further demands, finds the models that produce them and calls those in
turn, until nothing in the supply chain is left open.

*The [5-minute pitch](pitch-5min.md) has more detail.*

---

## One process, one model

Our example is 1000 kg of Portland cement, made in Denmark in 2030.

```python
answer = cement_model.apply(DEMAND)
```

```text
                 amount unit flow                                         where  when
   production    1000.0 kg   Portland cement, aluminous cement, slag cem… DK     2030
 technosphere    1125.0 kg   Gypsum; anhydrite; limestone flux; limeston… DK     2030
 technosphere    2475.0 MJ   Natural gas, liquefied or in the gaseous st… DK     2030
 technosphere      10.0 kg   Quicklime, slaked lime and hydraulic lime    DK     2030
 technosphere     100.0 kWh  electricity                                  DK     2030
    biosphere     397.5 kg   co2-fossil                                   DK     2030
    biosphere     138.6 kg   co2-fossil                                   DK     2030
```

The model takes a `Demand` and returns a `Result` with what it made, what it
needs from upstream and what it emitted. Its fuel demand follows the moisture
and temperature recorded for the place and year it was asked about.

```python
row = params.at(location="DK", time=2030)
penalty = moisture_penalty(row["moisture"], row["temperature"])
fuel = row["fuel_demand"] * clinker * penalty
```

!!! info "trailpack"
    Parameters come from a [`trailpack`](https://github.com/TimoDiepers/trailpack) parquet file, which stores units and vocabulary IRIs per column. It started at the BrightCon 2025 hackathon.

**A model can be a measurement.** A metered plant covers 2023 and the modelled
plant covers 2030, so the year on the demand decides which one answers.

```text
2023  answered by MeteredCementPlant   source: measured    562.0 kg CO2
2030  answered by CementPlant          source: modelled     536.1 kg CO2 (2 flows, not 1)
```

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

`Orchestrator.calculate` is a `while queue:` loop. It pops a demand, asks who
can answer it, pushes the new demands and logs each step. Models are found by
the product IRIs they declare in `produces`.

---

## Finding fallback models

Tier 1 is a model that matches the demand exactly. Each later tier makes a
concession, and the concession is written at the node.

**Tier 2 generalises** the product one `skos:broader` step at a time.

```text
       model: BinderSupply
 relaxations: ['product: fi_37420 -> fi_374']
       asked: Quicklime, slaked lime and hydraulic lime
    answered: Plaster, lime and cement   (broader concept, 2 hops up)
```

The answer is an average that includes cement, the product this plant makes.
It is the best data available, and the report says so.

A demand can also carry a **context**, such as a pressure named by its QUDT
IRI. The kiln burners ask for gas at 4 bar and the supplier delivers at 5 bar.
The study allows pressure to be met up to 1 bar higher.

```text
       model: NaturalGasSupply
 relaxations: ['context: http://qudt.org/vocab/quantitykind/Pressure 4 http://qudt.org/vocab/unit/BAR -> 5 http://qudt.org/vocab/unit/BAR']
       asked: …/fi_12020 @DK/2030 [http://qudt.org/vocab/quantitykind/Pressure=4 http://qudt.org/vocab/unit/BAR]
    answered: …/fi_12020 @DK/2030 [http://qudt.org/vocab/quantitykind/Pressure=5 http://qudt.org/vocab/unit/BAR]
```

**Tier 3 borrows a dataset** from a background pack, tagged `incomplete`.

---

## The cement chain, end to end

The full run, with every tier.

```text
1000 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers @DK/2030  [model: CementPlant]
  2475 MJ Natural gas, liquefied or in the gaseous state @DK/2030 (http://qudt.org/vocab/quantitykind/Pressure=4 http://qudt.org/vocab/unit/BAR)  [proxy: context: http://qudt.org/vocab/quantitykind/Pressure 4 http://qudt.org/vocab/unit/BAR -> 5 http://qudt.org/vocab/unit/BAR]
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
```

```mermaid
%%{init: {'layout': 'elk'}}%%
flowchart TB
    D(["1000 kg cement @DK/2030"]) --> CP["CementPlant<br/>DK · 2030"]

    CP -->|"2475 MJ natural gas @ 4 bar<br/>tier 2 · met at 5 bar"| NGS["NaturalGasSupply<br/>DK · 2030 · delivers 5 bar"]
    CP -->|"100 kWh electricity"| GE["GridElectricity<br/>DK · 2030"]
    CP -->|"10 kg lime"| BS["BinderSupply<br/>DK · 2030<br/>tier 2 · asked fi_37420, answered fi_374"]
    CP -->|"8.33 kg/yr kiln line"| K26["CementKilnConstruction<br/>DK · 2026"]
    CP -->|"16.7 kg/yr kiln line"| K29["CementKilnConstruction<br/>DK · 2029"]
    CP -.->|"1125 kg limestone"| XG["cutoff<br/>DK · 2030"]

    NGS -->|"68.75 Nm3 gas at production"| NGE["NaturalGasExtraction<br/>NO · 2030"]
    NGS -->|"50.53 tkm pipeline transport"| PT["OffshorePipelineTransport<br/>NO · 2030"]
    PT -->|"0.013 Nm3 leaked gas"| NGE
    PT -.->|"pipe · turbine fuel · lorry · oil"| XP["4 cutoffs<br/>NO · 2030"]

    GE -->|"8.47 kWh gas power"| GP["GasPower<br/>DK · 2030"]
    GE -.->|"84.66 kWh wind · 12.7 kWh hydro"| XE["2 cutoffs<br/>DK · 2030"]
    GP -->|"49.16 MJ natural gas"| NGS

    K26 -->|"0.1 kg steel · 6.7 g aluminium"| B26["background dataset<br/>DK · 2026<br/>tier 3 · incomplete"]
    K29 -->|"0.2 kg steel · 13 g aluminium"| B29["background dataset<br/>DK · 2029<br/>tier 3 · incomplete"]

    CP -->|"536.1 kg CO2"| INV[("inventory")]
    BS -->|"9 kg CO2"| INV
    GP -->|"2.75 kg CO2"| INV
    NGE -->|"4.79 kg CO2 · 71.5 Nm3 gas in ground"| INV
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

*Amber is tier 1, where a model answered. Blue is tier 2, a relaxed demand.
Teal is tier 3, a borrowed dataset. Red dashed is a cutoff. Violet marks
elementary flows into the inventory.*

The kilns are dated **2026** and **2029**, the cement **2030**, and the gas
comes from **NO**. The loop itself knows nothing about time or place. Each flow
carries both.

!!! info "Where the pipeline model comes from"
    Reverse-engineered from BAFU-2026 ecoinvent EcoSpold data and the Bussa et al. 2025 LCI report.

---

## Tracing time and place for free

```python
dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
```

![Marginal and cumulative radiative forcing over 100 years](assets/showcase/curve.svg)

The curve is read from the same report. The dates came through the whole
traversal.

---

## Why we want this

- The supply chain **assembles itself** from shared vocabulary IRIs
- Demands match on **conditions** such as pressure, beyond time and place
- Every **cutoff** is listed in the report with its reason
- Every **concession** is recorded at its node
- Inventories are **time-explicit** by construction
- A process can **depend on its demand**, its location, year and conditions
- A **measurement** fits the same interface as a model

---

*[5-minute pitch](pitch-5min.md) · [Full tour](showcase.md) ·
[Notebook `examples/showcase.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb)*
