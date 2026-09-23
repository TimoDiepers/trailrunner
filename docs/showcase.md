---
tags:
  - tutorial
---

# The 5-minute tour

One demand, carried end to end:

**1000 kg of CO<sub>2</sub> captured from the air — in Switzerland, in 2030.**

Seven beats. Every number and every block of output below came out of
[`examples/showcase.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb),
which runs offline, from committed files alone.

??? note "Presenter note (running order)"
    Beats 1, 2, 4 and 6 are the argument and must be read whatever happens to
    the clock. Beat 4 is where `GasCHP` and `DacPlantConstruction` arrive, and
    without them beat 6's construction pulse is unintelligible — it is not
    optional scenery. Beats 3, 5 and 7 are the craft that makes it believable.

    Timed at a conference-realistic **130 words a minute** — a reading pace is
    faster than a speaking one — with a beat of silence on each block of output,
    all seven beats run about **7:30**. Five minutes therefore means cutting,
    and the cuts are: **beat 7 first** (−0:30), then 5 (−1:10), then 3 (−0:40).
    Beats 1, 2, 4 and 6 alone come to about **5:05**. Decide which cut you are
    making before you start, not at minute four.

---

## 1. A matrix row is a fixed coefficient

A direct air capture plant's inventory, as it is usually written down: a column
of numbers per kilogram captured.

```python
CLASSIC_DAC_COLUMN = {  # per kg CO2 captured
    "heat": (5.0, "MJ"),
    "electricity": (0.40, "kWh"),
}

for place, year in [("Switzerland", 2030), ("Iceland", 2030), ("Switzerland", 2045)]:
    heat = CLASSIC_DAC_COLUMN["heat"][0] * DEMAND.amount
    print(f"{place:12} {year}   heat = {heat:.0f} MJ")
```

```text
Switzerland  2030   heat = 5000 MJ
Iceland      2030   heat = 5000 MJ
Switzerland  2045   heat = 5000 MJ
```

Three places, three years, one number. The coefficient has nowhere to put the
fact that a sorbent regenerating in cold, dry Icelandic air needs more heat than
one in Swiss spring air.

**Real processes depend on where and when. That cannot live in a number.**

??? note "Presenter note (0:40)"
    Say: this is the state of the art, and it is a table. Point at the three
    identical numbers. Do not apologise for the example being simple — its being
    simple is the point. Move on fast; beat 6 is where the time is needed.

---

## 2. The process is the code

In `trailrunner` that column is a `Model`: Python that receives a `Demand` and
returns what it produced, what it needs and what it emitted. `DirectAirCapture`
exists for one dependency a table cannot hold.

```python
def ambient_penalty(temperature: float, humidity: float) -> float:
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    humidity_term = HUMIDITY_SENSITIVITY * (REFERENCE_HUMIDITY - humidity)
    return 1.0 + temperature_term + humidity_term
```

The same 1000 kg, asked for in four different places and years:

```text
 where   when   degC     RH   penalty   heat [MJ]
    CH   2020    9.0   0.75     0.995      5970.0
    CH   2030   10.0   0.70     1.000      5000.0
   RER   2020   11.0   0.68     0.996      6573.6
   RER   2030   12.0   0.65     0.995      5472.5
```

The line that does it is `heat = row["heat_demand"] * penalty * demand.amount`.
`demand.amount` is the **full** 1000 kg, never a unit demand, and nothing
downstream rescales the answer — so a model that is not proportional does not
have to pretend it is.

**The process is the code.**

??? note "Presenter note (0:50)"
    Say: the coefficient cannot depend on where and when; a function can. Show
    the two Swiss heat numbers, 5970 against 5000. Say "full demand, not unit
    demand" once and move on. Do not explain the sorbent chemistry, and do not
    claim this model is nonlinear in the amount — it is not. What is not a
    coefficient here is the ambient response.

---

## 3. The walk, and what it could not answer

`Orchestrator` pops the demand, finds a model, runs it, and pushes that model's
own demands back onto the queue. With only the four shipped models, the walk
stops where nobody models anything.

```bash
uv run trailrunner run \
  "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_2811_21" \
  --amount 1000 --unit kg --location CH --year 2030 \
  --models examples/showcase_models.py
```

```text
3 nodes, 2 inventory entries
4 unresolved (no_model_found: 4)
0 proxies
attribution: allocation=none, capital=per_output

1000 kg fi_2811_21 @CH/2030  [model: DirectAirCapture]
  400 kWh fi_17100 @CH/2030  [model: GridElectricity]
    8.51064 kWh electricity-natural-gas @CH/2030  [model: GasPower]
      49.4166 MJ fi_12020 @CH/2030  [cutoff: no_model_found]
    76.5957 kWh electricity-wind @CH/2030  [cutoff: no_model_found]
    340.426 kWh electricity-hydro @CH/2030  [cutoff: no_model_found]
  5000 MJ fi_1730_9 @CH/2030  [cutoff: no_model_found]
```

Nothing was dropped and nothing was quietly zero. Four demands sit on the cutoff
list with a reason, hanging under the node that asked for them.

**Every node says how honestly it was answered.**

??? note "Presenter note (0:40)"
    Say: one command, no notebook. Read the tag on the last line out loud —
    `[cutoff: no_model_found]`. Say: a matrix gives you a number here and no
    list of what was missing from it. This one gives you both. That heat cutoff
    is the next beat.

---

## 4. When nothing matches: generalise, then borrow

Two concessions, in a declared order.

**Generalise.** Nothing produces `fi_1730_9`, "heat from main producers of
heat". One level up `skos:broader` sits `fi_1730`, "Steam and hot water" — a real
BONSAI concept, read from the committed `examples/pyst_cache.json`: no network,
no token. A gas CHP registered there answers the relaxed demand.

**Borrow.** Given its `Fleet`, `DirectAirCapture` demands each plant's
construction **in the year that plant was built**. A construction model turns
that into steel and aluminium, borrowed from the background pack.

**Two of the models below are written on this page, not shipped.** Nothing in
this repository produces `fi_1730`, and nothing in it co-produces — so there was
no target for the generalisation tier to find, and nothing for beat 5 to
allocate. `GasCHP` and `DacPlantConstruction` exist so those mechanisms have
something to bite on. Their efficiencies, prices and material intensities are
invented. Everything around them is not: the `skos:broader` walk, the pack
lookup, the completeness flag, the credit traversal and the construction pulse
are the library, and every block of output below is what it actually printed.

```python
CHAIN = ResolutionChain([tier1, tier2, BackgroundProvider(pack)])
report = Orchestrator(CHAIN, settings=settings).calculate(DEMAND)
```

```text
10 nodes, 6 inventory entries
4 unresolved (generalisation_exhausted: 4)
5 proxies (4 incomplete)
attribution: allocation=economic, capital=per_output

1000 kg fi_2811_21 @CH/2030  [model: DirectAirCapture]
  5000 MJ fi_1730_9 @CH/2030  [proxy: product: fi_1730_9 -> fi_1730]
    5070.42 MJ fi_12020 @CH/2030  [cutoff: generalisation_exhausted]
  400 kWh fi_17100 @CH/2030  [model: GridElectricity]
    8.51064 kWh electricity-natural-gas @CH/2030  [model: GasPower]
      49.4166 MJ fi_12020 @CH/2030  [cutoff: generalisation_exhausted]
    76.5957 kWh electricity-wind @CH/2030  [cutoff: generalisation_exhausted]
    340.426 kWh electricity-hydro @CH/2030  [cutoff: generalisation_exhausted]
  11.5385 kg/year direct-air-capture-plant @CH/2026  [model: DacPlantConstruction]
    34.6154 kg steel-low-alloyed @CH/2026  [background: unit_process, incomplete]
    17.3077 kg aluminium-primary @CH/2026  [background: unit_process, incomplete]
  38.4615 kg/year direct-air-capture-plant @CH/2029  [model: DacPlantConstruction]
    115.385 kg steel-low-alloyed @CH/2029  [background: unit_process, incomplete]
    57.6923 kg aluminium-primary @CH/2029  [background: unit_process, incomplete]
```

```text
       model: GasCHP
 relaxations: ['product: fi_1730_9 -> fi_1730']
       asked: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9 @CH/2030
    answered: https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730 @CH/2030
        tier: generalising
```

![The traversal, coloured by the tier that answered each node](assets/showcase/sankey.svg)

The borrowed rows say `incomplete` because the pack holds each dataset's
*direct* exchanges only: their upstream is missing, and the report says so.

**We concede on purpose, along a declared hierarchy, and we log it.**

!!! warning "What this beat does not claim"

    - `direct-air-capture-plant` is **not** a vocabulary concept — the service
      answers 404 for it — so the product dimension cannot generalise it, and
      nothing here pretends otherwise.
    - `electricity-wind`, `electricity-hydro` and `electricity-natural-gas` are
      likewise `trailrunner`'s own invented IRIs. They stay cutoffs.
    - The background pack has **no electricity dataset, on purpose**: a grid-mix
      unit process delegates its combustion upstream, so borrowing one would
      answer a kilowatt hour with a plausible-looking near-zero. A visible
      cutoff is better than that.

??? note "Presenter note (1:55)"
    Say: nothing matched, so we asked for less — one level up a published
    vocabulary, from a file in the repo. Read the proxy tag aloud. Then point at
    the word `incomplete` and say: that is a borrowed row whose own upstream we
    do not have, and it is labelled, not laundered. If asked about the
    electricity cutoffs, use the box above — it is the strongest thing on the
    page. Read the "written on this page, not shipped" paragraph out loud
    before the output, not after it and not only if challenged: said first it is
    the argument, said last it is an excuse.

---

## 5. Value judgements are flags, not appendices

The CHP makes heat *and* electricity. How its burden splits between them is not
a measurement, it is a choice — and `trailrunner` will not make it for you.

```python
try:
    walk("none")
except UnallocatedCoProduction as refusal:
    print("allocation='none' ->", refusal)
```

```text
allocation='none' -> GasCHP returned co-products (https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100) but the run's allocation rule is 'none'; model it monofunctionally or choose a rule
```

```text
     economic:    -580.6 kg CO2-eq   (4 unresolved (generalisation_exhausted: 4))
 substitution:    -311.3 kg CO2-eq   (7 unresolved (generalisation_exhausted: 7, of which 3 on a credit branch))

what the CHP node recorded under substitution:
  allocation: substitution
  share: 1.0
  substituted: ['https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100']
```

Same model, same 1000 kg: 581 kg of CO<sub>2</sub>-eq removed under one rule,
311 kg under the other. The credit is traversed as a *negative* demand, answered
by someone other than the CHP, and counted separately.

The gap between 581 and 311 is set by `GasCHP`'s invented heat and electricity
prices — economic allocation partitions by revenue. What is demonstrated is that
the rule moves the answer and that the report records which rule ran, not that
either number is right for a real CHP.

**The rule is on the report, next to the number it produced.**

??? note "Presenter note (1:10)"
    Say: the library refuses to run until you choose. Show the refusal, then the
    two numbers. Say "581 or 311, and neither is wrong" — that is the line.
    Do not get drawn into which rule is correct; the point is that the answer
    depends on it and the report says which one you used.

---

## 6. Time

Every exchange already carries the year it happens in. The plants doing the
capturing were built in 2026 and 2029; the capture, and the gas heat driving it,
are in 2030. So the inventory *is* a time series, and can be characterized as one.

```python
# No characterization table is passed: default_functions() maps the DAC uptake
# flow to the ordinary CO2 function, because the model emits it as an already
# negative CO2 exchange and nothing should negate it a second time.
dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
```

```text
-5.14244e-11 W·yr/m2
metric: radiative_forcing, horizon: 100 years
horizon anchored at: 2026-01-01
0 uncharacterized exchanges
0 wrong unit exchanges
0 undated exchanges
0 beyond-horizon exchanges
4 unresolved
5 proxies

marginal radiative forcing, first years [W/m2]:
date
2027    5.054518e-14
2028    9.235309e-14
2029    4.282174e-14
2030    1.684839e-13
2031   -9.756895e-13
2032   -1.776486e-12
```

![Marginal and cumulative radiative forcing over 100 years](assets/showcase/curve.svg)

The faint bars are the per-year forcing; the red line is its running total. It
starts **above** zero — those are the plants built in 2026 and 2029 — and only
turns down once the capture lands in 2030. Four warming years, then a century of
payback, because of *when* each kilogram happened and not only how much of it
there was. A static score gives one number for all of that.

The pulse's size is `DacPlantConstruction`'s illustrative intensities; the
shape — warming first, cooling later — is what the traversal produced from the
dates it carried.

**`bw_temporalis` and `bw_timex` get here too — from a matrix. This got here
because the traversal never lost the date.**

??? note "Presenter note (1:25)"
    This is the beat. Slow down. Say: no second model, no second database, no
    matrix — the traversal already kept the year on every flow, so this is a
    reading of the inventory you already have. Trace the curve with a finger:
    up here, turning here. Then say the punchline and stop talking. The
    punchline names `bw_temporalis` and `bw_timex` on purpose: someone in the
    room knows they do this, and conceding it first is what buys the second
    half of the sentence.

---

## 7. The record

```python
print(report.summary())
report.log.to_parquet("showcase_log.parquet")
```

```text
10 nodes, 6 inventory entries
4 unresolved (generalisation_exhausted: 4)
5 proxies (4 incomplete)
attribution: allocation=economic, capital=per_output

wrote showcase_log.parquet: 142 rows, 19 columns
kinds: ['attribution', 'biosphere', 'node', 'provenance', 'resolution', 'unresolved']
```

![Contribution to the GWP100 score by node](assets/showcase/contributions.svg)

Every node, every cutoff, every parameter fallback, every proxy, and the rule
that made the number — one row each.

**Parquet in, parquet out, every choice on the record.**

??? note "Presenter note (0:30)"
    Say: the run is a file, and the file includes what the run could not do.
    Then give the two links and stop.

---

- The notebook this page is made of: [`examples/showcase.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/showcase.ipynb)
- [Installation](content/installation.md)
