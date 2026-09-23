# Re-basing the showcase on a cement plant

**Date:** 2026-09-24
**Status:** design, awaiting review

## Why

The showcase demand is 1000 kg of CO<sub>2</sub> captured from air. The number
it produces is negative, the product is a removal rather than a thing, and a
reader meeting `trailrunner` for the first time spends attention on the example
instead of on the library. Direct air capture is also unusual in a way that
costs the tour a beat it should have: the plant emits nothing of its own, so
there is no place to show a process whose emissions are measured rather than
computed.

A cement plant fixes all three. The product is a thing, the number is positive
and rises monotonically, the direct emissions are the textbook case of
emissions that come from chemistry rather than from fuel, and every real cement
kiln in Europe has a continuous emission monitor on its stack — so "some data
is measured" is authentic rather than staged.

## What changes, and what does not

`DirectAirCapture` stays in `trailrunner/models/dac.py` as a library model.
`examples/dac.ipynb` is untouched. Every existing test is untouched: nothing in
`tests/` learns about cement, and nothing it currently asserts about DAC stops
being true.

What changes is which model the showcase puts on stage.

## The model

New module `trailrunner/models/cement.py`, holding two model classes that both
declare the same product and never overlap in time.

### Product and flows

Every IRI below was verified against the live vocabulary service on 2026-09-24.

| role | IRI | `skos:prefLabel` |
| --- | --- | --- |
| product | `…/BONSAI2025.1/fi_37440` | Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers |
| limestone | `…/BONSAI2025.1/fi_15200` | Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement |
| kiln fuel | `…/BONSAI2025.1/fi_12020` | Natural gas, liquefied or in the gaseous state |
| electricity | `…/BONSAI2025.1/fi_17100` | electricity |
| drying steam | `…/BONSAI2025.1/fi_1730_6` | heat from electric boilers |
| its parent | `…/BONSAI2025.1/fi_1730` | Steam and hot water |
| direct emission | `…/flows/co2-fossil` | — |

`fi_12020`, `fi_17100`, `fi_1730` and `co2-fossil` are already in
`examples/pyst_cache.json` and `examples/pyst_labels.json`. `fi_37440`,
`fi_15200` and `fi_1730_6` are new and need one warming run.

Calcination CO<sub>2</sub> is written on `co2-fossil`. It is geogenic rather
than fossil, but it is counted as fossil by every inventory convention in use,
and `co2-fossil` is already characterized in both `assessment/dynamic.py` and
`assessment/static.py`. No new characterization code.

### `CementPlant`

`Coverage(time_range=(2026, 2050))`, monofunctional at `fi_37440`,
`supports = ALLOCATION_RULES` for the same reason `DirectAirCapture` declares
it: with one product there is nothing to partition.

Its demand-dependence is raw meal moisture. Wet feed carries water that has to
be evaporated before anything calcines, so both the drying steam and the kiln
fuel rise with it. `ambient_penalty` becomes `moisture_penalty(moisture,
temperature)` — the same linear shape, the same "the dependency exists and
lives in code" argument, and a physical story that survives a question from the
audience better than the sorbent one did.

For 1000 kg of cement at CH/2030, with a clinker factor of 0.75:

```text
   production    1000.0 kg   Portland cement …                 @CH/2030
 technosphere    1125.0 kg   Gypsum; anhydrite; limestone …    @CH/2030
 technosphere    2475.0 MJ   Natural gas, liquefied …          @CH/2030
 technosphere     340.0 MJ   heat from electric boilers        @CH/2030
 technosphere     100.0 kWh  electricity                       @CH/2030
    biosphere     398.0 kg   co2-fossil  (calcination)         @CH/2030
    biosphere     139.0 kg   co2-fossil  (combustion)          @CH/2030
   provenance  {'location_requested': 'CH', …}
```

Two biosphere exchanges rather than one, deliberately: the calcination figure
comes from stoichiometry and the combustion figure from the fuel the model just
demanded. A reader can see which is which, and the measured beat then lands on
the fact that a stack meter cannot.

The `Fleet` handling is lifted from `DirectAirCapture._construction`
unchanged — kilns built in 2026 and 2029, amortized over capacity and lifetime,
demanded in the year each kiln was actually built. The construction product
keeps an invented IRI, as `direct-air-capture-plant` did and for the same
reason: BONSAI's product classification does not carry capital goods at this
granularity.

### `MeteredCementPlant`

`Coverage(time_range=(2018, 2025))`, same product IRI, computes nothing.

It reads one row per location and year and returns it. Metered natural gas,
metered steam and metered electricity go out as technosphere demands, because
those emissions happen upstream of the plant and a meter at the plant boundary
says nothing about them. The stack figure — one number, calcination and
combustion together, because that is what a CEMS gives you — goes out as a
single `co2-fossil` exchange.

```text
   production    1000.0 kg   Portland cement …                 @CH/2023
 technosphere    2610.0 MJ   Natural gas, liquefied …          @CH/2023   (gas meter)
 technosphere     385.0 MJ   heat from electric boilers        @CH/2023   (heat meter)
 technosphere     108.0 kWh  electricity                       @CH/2023   (kWh meter)
    biosphere     562.0 kg   co2-fossil  (stack CEMS)          @CH/2023
```

### How the two are selected

`Glossary.resolve` already filters candidates by `Coverage.covers(flow)`, so
two models declaring `fi_37440` with non-overlapping `time_range`s resolve by
the demand's year with no new library code and no ambiguity error. A demand for
2023 reaches the meter; one for 2030 reaches the model; the report's node line
names the class that answered.

This is the point of the beat. The choice between a measurement and a
calculation is visible in the report rather than buried in a branch inside one
model's `apply`.

## Parameters

`dev/build_showcase_params.py` gains two writers and keeps every existing one.

- `examples/cement_params.parquet` — location, time, `clinker_factor`,
  `fuel_demand`, `steam_demand`, `electricity_demand`, `moisture`,
  `temperature`, for CH and RER in 2030 and 2040.
- `examples/cement_metered_params.parquet` — location, time, `metered_fuel`,
  `metered_steam`, `metered_electricity`, `metered_co2`, for CH in 2018
  through 2025.

The DAC, grid, gas and pipeline parquets stay where they are, because
`examples/dac.ipynb` and the existing tests still read them.

`examples/showcase_models.py` swaps `DirectAirCapture` for `CementPlant` and
`MeteredCementPlant` in `MODELS`. `GridElectricity`, `GasPower` and the
pipeline model stay exactly as they are.

The plant's natural gas demand stays a cutoff, as it is in the current
showcase. Answering it would cost the tour its most-quoted output — a report
that says in words what it does not cover — to gain nothing the beat needs.

## The showcase beats

`docs/showcase.md` and `examples/showcase.ipynb` are rewritten against the new
demand. The structure changes in one place.

1. **A process is something you run.** Unchanged in argument. The
   demand-dependence table becomes moisture rather than air temperature.
2. **Models find each other through a vocabulary.** Unchanged. The pop trace is
   longer and every name in it now resolves to a real label.
3. **A demand nobody answers is relaxed along the vocabulary.** The plant asks
   for `fi_1730_6`, "heat from electric boilers", because that is the boiler
   the site installed. Nobody models it. One `skos:broader` step reaches
   `fi_1730`, "Steam and hot water", and a generic `HeatSupply` answers. That
   model is written in the notebook rather than shipped, exactly as `GasCHP`
   was and for the same reason: nothing in this repository produces `fi_1730`,
   and the library being demonstrated is the `skos:broader` walk, not the
   boiler. The
   concession is legible as a loss: a technology was asked for and an average
   was returned. The second half of the beat — kiln construction resolved out
   of the background pack, tagged `incomplete` — is unchanged.
4. **Some data is measured.** New. The same 1000 kg asked for in 2023 and in
   2030, answered by two different models, and the report says which. The line
   the beat exists for: the meter says 562 kg, the model says 537, and the
   meter cannot tell you which part was rock and which was fuel.
5. **Time rides along.** Unchanged in mechanism. The curve improves: a
   construction pulse in 2026 and 2029, then the operating spike in 2030, all
   positive and monotonically accumulating. It reads aloud in one sentence,
   which the removal curve never did.
6. **The run leaves a record.** Unchanged.

The old beat 4, on allocation and co-production, leaves the showcase. Cement as
modelled here is monofunctional and inventing a co-product for it would undo
the simplification this whole change is for. `docs/showcase.md` links to
`docs/content/attribution.md` and to the new notebook instead.

## The co-production notebook

New `examples/coproduction.ipynb`, carrying the `GasCHP` material that beat 4
used to hold: the `UnallocatedCoProduction` refusal, the economic and
substitution runs, and the node's recorded allocation metadata.

It starts clean rather than inheriting beat 3's disclaimer. That disclaimer
covered several things at once — invented efficiencies, invented prices,
invented IRIs, the background pack's deliberate gaps — and only the price and
efficiency parts belong here. The notebook states in its own opening that
`GasCHP`'s numbers are illustrative and that what is being demonstrated is the
rule's effect on the answer, not the CHP.

## Assets and CI

`dev/build_showcase_assets.py` finds figure cells by tag, so it needs no change
as long as the rewritten notebook keeps the `figure:sankey`, `figure:curve` and
`figure:contributions` tags. The three SVGs in `docs/assets/showcase/` are
regenerated.

`.github/workflows/showcase.yml` executes the notebook offline. The new IRIs
must therefore be in the committed caches before CI can pass, which makes the
warming run a prerequisite rather than a cleanup step.

## Tests

New `tests/test_cement.py`, mirroring `tests/test_dac.py`: the moisture penalty
at and away from reference, the two biosphere exchanges and their signs, the
clinker factor reaching the limestone demand, the fleet construction years, and
the metered model returning its row untouched.

New coverage-selection test: a glossary holding both cement models resolves
2023 to the meter and 2030 to the model, and raises nothing for either.

`tests/test_cli.py` references the showcase models list and needs its
expectations updated to the new `MODELS`.

## Order of work

1. Warm `examples/pyst_cache.json` and `examples/pyst_labels.json` with
   `fi_37440`, `fi_15200` and `fi_1730_6`. Nothing downstream can run offline
   until this lands.
2. `trailrunner/models/cement.py` and `tests/test_cement.py`, test-first.
3. Parameter writers in `dev/build_showcase_params.py`, and the two parquets.
4. `examples/showcase_models.py`, then `tests/test_cli.py`.
5. `examples/showcase.ipynb`, beat by beat.
6. `dev/build_showcase_assets.py` run; commit the three SVGs.
7. `docs/showcase.md`, quoting the executed notebook's output verbatim.
8. `examples/coproduction.ipynb`.
9. Sweep `README.md` and `docs/content/*.md` for showcase references that now
   describe the wrong example.

## Open questions

None outstanding. The vocabulary lookups are done, the resolution behaviour is
verified in `orchestration/glossary.py`, and the characterization path for
`co2-fossil` already exists.
