---
icon: lucide/terminal
tags:
  - tutorial
---

# Tutorial: an LCA from the CLI

`trailrunner run` takes one demand, walks the supply chain behind it, and prints the
report. Add a method file and it prints a score. Add a metric and it prints a
time-explicit result. Add `--out` and it writes the whole run to parquet. This tutorial
goes through each step with the models that ship in the repository, then with a models
file of your own.

Everything below runs from the repository root after
[installing from source](../installation.md#from-source).

## 1. What the command needs

```bash
uv run trailrunner run --help
```

```text
usage: trailrunner run [-h] --amount AMOUNT --unit UNIT [--location LOCATION]
                       [--year YEAR] --models MODELS [--method METHOD]
                       [--dynamic DYNAMIC] [--horizon HORIZON]
                       [--allocation ALLOCATION] [--capital CAPITAL]
                       [--context-tolerance NAME=BELOW:ABOVE UNIT]
                       [--proxy-order ORDER] [--max-depth MAX_DEPTH]
                       [--max-nodes MAX_NODES] [--out OUT]
                       iri
```

Three things are required:

- **the product IRI** you demand, as the positional argument,
- **`--amount` and `--unit`**, how much of it,
- **`--models`**, a `.py` file that defines a list called `MODELS`.

`--location` and `--year` place the demand. Every model downstream receives them on its
own demands, so they decide which parameter rows are read and which models are valid.

## 2. Run the shipped cement chain

`examples/showcase_models.py` wires the cement, grid electricity, gas power, gas supply,
pipeline transport and gas extraction models to the parameter files in `examples/`. It is
the same `MODELS` list the [5-minute tour](../../showcase.md) uses. Demand one tonne of
Portland cement (BONSAI `fi_37440`) in Denmark in 2030:

```bash
uv run trailrunner run \
    https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 \
    --amount 1000 --unit kg --location DK --year 2030 \
    --models examples/showcase_models.py \
    --context-tolerance "pressure=0:1e5 Pa"
```

```text
11 nodes, 11 inventory entries
12 unresolved (no_model_found: 12)
1 proxy
attribution: allocation=none, capital=per_output

1000 kg fi_37440 @DK/2030  [model: CementPlant]
  2475 MJ fi_12020 @DK/2030 (pressure=400000 Pa)  [proxy: context: pressure 400000 Pa -> 500000 Pa]
    68.75 m3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
    0.0505312 t natural-gas-transport-offshore-pipeline-long-distance @NO/2030 (distance=1000 km)  [model: NaturalGasOffshorePipelineTransport]
      0.0130625 m3 natural-gas-at-production @NO/2030  [model: NaturalGasExtraction]
      8.99456e-08 unit pipeline-natural-gas-long-distance-high-capacity-offshore @NO/2030  [cutoff: no_model_found]
      16.5404 MJ natural-gas-burned-in-gas-turbine @NO/2030  [cutoff: no_model_found]
      5.86163e-09 t transport-freight-lorry-16t-32t @NO/2030 (distance=1000 km)  [cutoff: no_model_found]
      5.86162e-05 kg disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration @NO/2030  [cutoff: no_model_found]
  100 kWh fi_17100 @DK/2030  [model: GridElectricity]
    8.46561 kWh electricity-natural-gas @DK/2030  [model: GasPower]
      49.1551 MJ fi_12020 @DK/2030  [model: NaturalGasSupply]
        ...
    84.6561 kWh electricity-wind @DK/2030  [cutoff: no_model_found]
    12.6984 kWh electricity-hydro @DK/2030  [cutoff: no_model_found]
  1125 kg fi_15200 @DK/2030  [cutoff: no_model_found]
  10 kg fi_37420 @DK/2030  [cutoff: no_model_found]
```

How to read it:

- **The summary comes first**, because it says how far to trust the rest: 11 nodes ran,
  and 12 demands found no model.
- **Every tree line** is one node: the amount demanded, the product (the last segment of
  its IRI), `@location/year`, any context in parentheses, and in brackets how it was
  answered.
- **The kiln's gas is a proxy.** The kiln's burners ask for gas at 4e5 Pa (4 bar), the only
  supplier delivers at 5e5 Pa (5 bar), and `--context-tolerance "pressure=0:1e5 Pa"`
  accepts that. [Section 4](#4-when-a-supplier-almost-matches-context-tolerance) explains
  the flag.
- **The gas moved.** `NaturalGasSupply` places extraction and pipeline transport in `NO`,
  the gas's origin, not at the Danish consumer, and every model below it works with that.
- **Cutoffs hang where they happened.** Limestone (`fi_15200`) and lime (`fi_37420`) are
  demanded by the cement plant, and wind and hydro power by the grid mix. Nobody models
  them, and the report says so rather than counting them as zero.

## 3. Change the year and a different model answers

`CementPlant` and `MeteredCementPlant` both produce `fi_37440`, with coverage ranges that
don't overlap: the computed plant covers 2026–2050, the stack-monitor readings 2018–2025.
Ask for 2020 and the meter answers:

```bash
uv run trailrunner run \
    https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 \
    --amount 1000 --unit kg --location DK --year 2020 \
    --models examples/showcase_models.py \
    --context-tolerance "pressure=0:1e5 Pa"
```

```text
11 nodes, 11 inventory entries
11 unresolved (no_model_found: 11)
0 proxies
attribution: allocation=none, capital=per_output

1000 kg fi_37440 @DK/2020  [model: MeteredCementPlant]
  2740 MJ fi_12020 @DK/2020  [model: NaturalGasSupply]
  ...
  113 kWh fi_17100 @DK/2020  [model: GridElectricity]
  ...
  11.4 kg fi_37420 @DK/2020  [cutoff: no_model_found]
```

Nothing on the command line said "use the meter". The year on the demand chose it, and the
grid mix and gas chain below it read their 2020 rows as well.

## 4. When a supplier almost matches: `--context-tolerance`

A demand can say more than *what*, *where* and *when*. It can also carry **context**:
named conditions with a value and a unit, such as the pressure gas is wanted at. A model
declares in its `Coverage` which values it can deliver. Both sides are in Python (see
[Resolution](../resolution.md#tier-2-generalising-a-demand)); the CLI decides how strict
the match is.

By default it is exact. In the shipped chain the kiln's burners ask for gas at
**4e5 Pa** (4 bar) and `NaturalGasSupply` delivers at **5e5 Pa** (5 bar), so without any
flag the kiln's gas is not answered:

```text
  2475 MJ fi_12020 @DK/2030 (pressure=400000 Pa)  [cutoff: coverage_excluded]
```

`coverage_excluded` rather than `no_model_found`: a supplier exists, and its coverage is
what refused.

### Accept a nearby value: `--context-tolerance "NAME=BELOW:ABOVE UNIT"`

```bash
--context-tolerance "pressure=0:1e5 Pa"
```

reads as: pressure may be met **up to 0 Pa lower and up to 1e5 Pa higher** than asked. The
unit is resolved through the same catalog as everything else -- a symbol (`Pa`), a
vocabulary id (`PA`) or the full IRI all work -- and a condition may be asked in *any* unit
of the same quantity kind: a demand in bar against a tolerance in Pa is converted exactly.
Two numbers instead of one because most conditions have a safe side: gas at a higher
pressure can be throttled down at the burner, gas at a lower one can't be pushed up there.

With the flag, the demand is moved to 5e5 Pa, answered by `NaturalGasSupply`, and the tree
says so:

```text
  2475 MJ fi_12020 @DK/2030 (pressure=400000 Pa)  [proxy: context: pressure 400000 Pa -> 500000 Pa]
```

The parentheses show what was asked; the brackets show what was conceded. The summary
counts it as `1 proxy`. A 6e5 Pa (6 bar) demand would not be answered with
`pressure=0:1e5 Pa`, because 5e5 is below 6e5.

Repeat the flag for each condition, e.g.
`--context-tolerance "pressure=0:1e5 Pa" --context-tolerance "temperature=0:10 K"`. A
condition given twice, a malformed value, or a unit the catalog does not know stops the
run with exit code `2` before anything runs.

### Several conditions: `--proxy-order`

By default, tolerances are tried **one condition at a time**. That's deliberate: moving
two conditions together is a bigger concession, and trailrunner makes you ask for it. To
see the difference, put this in `burner_models.py`: a burner that asks for gas at 4e5 Pa
(4 bar) *and* 280 K, and a grid that delivers 5e5 Pa (5 bar) at 288 K.

```python title="burner_models.py"
from trailrunner import ContextRange, Coverage, Demand, Exchange, Flow, Model, Property, Result
from trailrunner.core.units import KELVIN, PA

HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


class Burner(Model):
    """Asks for its gas at 4e5 Pa and 280 K."""

    produces = [HEAT]

    def apply(self, demand: Demand) -> Result:
        gas = demand.amount / 0.9
        where = dict(location=demand.flow.location, time=demand.flow.time)
        wanted = (Property("pressure", 4e5, PA), Property("temperature", 280.0, KELVIN))
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[Demand(flow=Flow(iri=GAS, context=wanted, **where), amount=gas, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CO2, **where), amount=0.056 * gas, unit="kg")],
        )


class GasGrid(Model):
    """Delivers at 5e5 Pa and 288 K, and nothing else."""

    produces = [GAS]
    coverage = Coverage(context=(
        ContextRange("pressure", PA, 5e5, 5e5),
        ContextRange("temperature", KELVIN, 288.0, 288.0),
    ))

    def apply(self, demand: Demand) -> Result:
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


MODELS = [Burner(), GasGrid()]
```

Both conditions are off, and both are within tolerance, yet two tolerances alone don't
answer it:

```bash
uv run trailrunner run https://vocab.sentier.dev/products/heat \
    --amount 100 --unit MJ --location CH --year 2030 \
    --models burner_models.py \
    --context-tolerance "pressure=0:1e5 Pa" --context-tolerance "temperature=0:10 K"
```

```text
100 MJ heat @CH/2030  [model: Burner]
  111.111 MJ natural-gas @CH/2030 (pressure=400000 Pa, temperature=280 K)  [cutoff: coverage_excluded]
```

Moving pressure alone leaves the temperature wrong, and the other way round.
`--proxy-order` says which relaxations to try and in what order: entries are separated by
commas and tried left to right, and `+` joins conditions that move **together**. Each
condition is written `context.<name>`:

```bash
uv run trailrunner run https://vocab.sentier.dev/products/heat \
    --amount 100 --unit MJ --location CH --year 2030 \
    --models burner_models.py \
    --context-tolerance "pressure=0:1e5 Pa" --context-tolerance "temperature=0:10 K" \
    --proxy-order context.pressure,context.temperature,context.pressure+context.temperature
```

```text
2 nodes, 1 inventory entry
0 unresolved
1 proxy
attribution: allocation=none, capital=per_output

100 MJ heat @CH/2030  [model: Burner]
  111.111 MJ natural-gas @CH/2030 (pressure=400000 Pa, temperature=280 K)  [proxy: context: pressure 400000 Pa -> 500000 Pa; context: temperature 280 K -> 288 K]
```

That order reads: try pressure alone, then temperature alone, and only if neither works,
both together. Leave out the last entry and the run won't combine them. Each condition
still has to stay within its own tolerance: with `temperature=0:5 K`, 280 K can't reach
288 K and the demand stays a cutoff, whatever the order says.

| `--proxy-order` | tries |
| --- | --- |
| *(not given)* | each tolerated condition on its own, never two together |
| `context.pressure` | pressure only; other conditions must match exactly |
| `context.pressure,context.temperature` | pressure alone, then temperature alone; never both |
| `context.pressure+context.temperature` | only both together |
| `context.pressure,context.pressure+context.temperature` | pressure alone, then both |

Every `context.<name>` in the order needs a `--context-tolerance` for that name, or the
run stops with exit code `2` (`'context.temperature' can never be tried: no
context_tolerance for 'temperature'`). The CLI relaxes context only. Widening the location,
moving the year, climbing the product taxonomy, or mixing those with context (e.g.
`("location", "context.pressure")`), needs a [`ResolutionChain`](../resolution.md) in
Python, which takes the same order.

## 5. Get a score: `--method`

A characterization method is a parquet file with one row per factor: `flow_iri`,
`flow_unit`, an optional `location`, and `cf`. The `cf` column declares the score's unit
in the embedded Data Package metadata. [Assessment](../assessment.md#the-method-parquet-layout)
has the full layout. This script writes a three-gas IPCC AR6 GWP100 with pyarrow alone:

```python title="make_gwp100.py"
import json

import pyarrow as pa
import pyarrow.parquet as pq

rows = [
    {"flow_iri": "https://vocab.sentier.dev/flows/co2-fossil", "flow_unit": "kg", "location": "GLO", "cf": 1.0},
    {"flow_iri": "https://vocab.sentier.dev/flows/ch4-fossil", "flow_unit": "kg", "location": "GLO", "cf": 29.8},
    {"flow_iri": "https://vocab.sentier.dev/flows/n2o", "flow_unit": "kg", "location": "GLO", "cf": 273.0},
]

datapackage = {
    "name": "IPCC AR6 GWP100",  # becomes the method's name
    "resources": [{
        "name": "factors",
        "schema": {"fields": [
            {"name": "flow_iri", "type": "string"},
            {"name": "flow_unit", "type": "string"},
            {"name": "location", "type": "string"},
            {"name": "cf", "type": "number", "unit": {"name": "kg CO2-eq"}},  # the score unit
        ]},
    }],
}

table = pa.Table.from_pylist(rows)
table = table.replace_schema_metadata({"datapackage.json": json.dumps(datapackage)})
pq.write_table(table, "gwp100.parquet")
```

```bash
uv run python make_gwp100.py
uv run trailrunner run \
    https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 \
    --amount 1000 --unit kg --location DK --year 2030 \
    --models examples/showcase_models.py \
    --context-tolerance "pressure=0:1e5 Pa" \
    --method gwp100.parquet
```

After the tree, the CLI prints the assessment:

```text
543.908 kg CO2-eq
method: IPCC AR6 GWP100
8 uncharacterized flows on 6 nodes (not in the score, and not zero)
12 unresolved
1 proxy
```

Factors written for `GLO` apply to Danish and Norwegian flows, because every location
lookup ends at the hierarchy's root. The last three lines are what makes the number
honest:

- **8 uncharacterized flows** are emissions the method has no factor for: ethane, mercury,
  NMVOC, the gas taken out of the ground. A GWP100 method rightly ignores most of them.
  They are listed rather than added in as zero.
- **12 unresolved** and **1 proxy** are carried over from the traversal, so anyone
  handed only the score still sees that the supply chain was cut off in 12 places and
  that one demand was met by a stand-in.

Converting an existing Brightway method instead of writing one by hand is covered in
[Assessment](../assessment.md#the-brightway-converter-an-offline-escape-hatch).

## 6. Get a curve: `--dynamic`

Every flow carries its year, so the inventory is already a time series. `--dynamic` runs
[`assess_dynamic()`](../assessment.md#assess_dynamic-a-time-explicit-reading) on it. This
needs the `dynamic` extra:

```bash
uv sync --extra dev --extra dynamic
uv run trailrunner run \
    https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 \
    --amount 1000 --unit kg --location DK --year 2030 \
    --models examples/showcase_models.py \
    --context-tolerance "pressure=0:1e5 Pa" \
    --dynamic radiative_forcing --horizon 100
```

The CLI prints the cumulative total over the horizon, labelled with its integrated unit
(`W·yr/m2`, not `W/m2`), followed by a gap report like the static one: uncharacterized,
wrong-unit, undated and beyond-horizon exchanges.

`--dynamic GWP` puts the same curve in CO<sub>2</sub>-equivalents:

```text
GWP over 100 years: 543.881 kg CO2eq
543.881 kg CO2eq
metric: GWP, horizon: 100 years
horizon anchored at: 2030-01-01
18 uncharacterized exchanges
0 wrong unit exchanges
0 undated exchanges
0 beyond-horizon exchanges
12 unresolved
1 proxy
```

It nearly matches the static score, because everything in this run happens in 2030. The
two diverge once emissions are spread over years, as in the tour, where the kilns are
built years before the cement is made. For the curve itself, and a plot of it, use the
Python API and [Figures](../figures.md#curve).

## 7. Make the run's choices explicit

Two normative choices can be set per run. Both default to the conservative option and
both appear in the summary's `attribution:` line:

- **`--allocation`**: `none` (default), `mass`, `economic`, `energy` or `substitution`.
  It decides what happens when a model makes more than one product. Under `none`, a
  co-producing model stops the run with `UnallocatedCoProduction`.
- **`--capital`**: `per_output` (default), `per_year` or `first_life`. It decides how a
  long-lived asset's construction is spread over what it makes.

[Attribution](../attribution.md) explains what each rule computes. A typo is refused
before anything runs:

```bash
uv run trailrunner run ... --allocation cheapest
```

```text
'cheapest' is not a known allocation rule; allowed: economic, energy, mass, none, substitution
```

The exit code is `2`, the same as for a models file that can't be imported.

## 8. Bound the walk: `--max-depth`, `--max-nodes`

The traversal never merges nodes, so a loop in the supply chain is bounded instead of
solved. `--max-depth` (default 10) limits how deep a branch goes. `--max-nodes` (default
1000) limits the whole run. Set the depth low to see what happens when a limit is hit:

```bash
uv run trailrunner run \
    https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 \
    --amount 1000 --unit kg --location DK --year 2030 \
    --models examples/showcase_models.py \
    --context-tolerance "pressure=0:1e5 Pa" --max-depth 2
```

```text
3 nodes, 1 inventory entry
7 unresolved (max_depth: 5, no_model_found: 2)
1 proxy
attribution: allocation=none, capital=per_output
traversal was truncated: max_depth or max_nodes was reached

1000 kg fi_37440 @DK/2030  [model: CementPlant]
  2475 MJ fi_12020 @DK/2030 (pressure=400000 Pa)  [proxy: context: pressure 400000 Pa -> 500000 Pa]
    68.75 m3 natural-gas-at-production @NO/2030  [cutoff: max_depth]
    0.0505312 t natural-gas-transport-offshore-pipeline-long-distance @NO/2030 (distance=1000 km)  [cutoff: max_depth]
  100 kWh fi_17100 @DK/2030  [model: GridElectricity]
    8.46561 kWh electricity-natural-gas @DK/2030  [cutoff: max_depth]
  ...
```

The cut-off branches are listed as `max_depth` cutoffs, and the summary says the traversal
was truncated.

## 9. Keep the record: `--out`

```bash
uv run trailrunner run ... --out run.parquet
```

writes the run's [`Log`](../../api/log.md) to one parquet file: one row per biosphere
exchange, cutoff, provenance entry, resolution entry and attribution entry, tagged by a
`kind` column. Read it back with anything that reads parquet:

```python
import pyarrow.parquet as pq

log = pq.read_table("run.parquet").to_pandas()
log[log.kind == "unresolved"][["demand_iri", "demand_amount", "demand_unit", "reason"]]
```

Two runs written this way can be compared by reading both files. Changed cutoffs or
parameter fallbacks show up as changed rows. [Reading a Report](../reports.md#writing-the-log-to-parquet)
lists the columns.

## 10. Bring your own models

`--models` takes any Python file that defines `MODELS`, a list of model **instances**. Here
is a complete two-model chain, a boiler burning gas and the gas supply behind it:

```python title="my_models.py"
from trailrunner import Demand, Exchange, Flow, Model, Result

HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"
CH4 = "https://vocab.sentier.dev/flows/ch4-fossil"


class Boiler(Model):
    produces = [HEAT]

    def apply(self, demand: Demand) -> Result:
        gas = demand.amount / 0.9  # MJ of gas per MJ of heat
        where = dict(location=demand.flow.location, time=demand.flow.time)
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[Demand(flow=Flow(iri=GAS, **where), amount=gas, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CO2, **where), amount=0.056 * gas, unit="kg")],
        )


class GasSupply(Model):
    produces = [GAS]

    def apply(self, demand: Demand) -> Result:
        where = dict(location=demand.flow.location, time=demand.flow.time)
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            biosphere=[Exchange(flow=Flow(iri=CH4, **where), amount=0.0002 * demand.amount, unit="kg")],
        )


MODELS = [Boiler(), GasSupply()]
```

Run all of it at once: traversal, score, curve and log.

```bash
uv run trailrunner run https://vocab.sentier.dev/products/heat \
    --amount 100 --unit MJ --location CH --year 2030 \
    --models my_models.py \
    --method gwp100.parquet \
    --dynamic radiative_forcing \
    --out run.parquet
```

```text
2 nodes, 2 inventory entries
0 unresolved
0 proxies
attribution: allocation=none, capital=per_output

100 MJ heat @CH/2030  [model: Boiler]
  111.111 MJ natural-gas @CH/2030  [model: GasSupply]

6.88444 kg CO2-eq
method: IPCC AR6 GWP100
0 uncharacterized flows
0 unresolved
0 proxies

radiative_forcing over 100 years: 6.03623e-13 W·yr/m2
6.03623e-13 W·yr/m2
metric: radiative_forcing, horizon: 100 years
horizon anchored at: 2030-01-01
0 uncharacterized exchanges
0 wrong unit exchanges
0 undated exchanges
0 beyond-horizon exchanges
0 unresolved
0 proxies

wrote run.parquet
```

Check the score by hand: 111.1 MJ of gas × 0.056 kg/MJ gives 6.22 kg CO<sub>2</sub>, and
111.1 × 0.0002 = 0.0222 kg CH<sub>4</sub> × 29.8 gives 0.66 kg CO2-eq, for 6.88 in total.

The Runner validates every result. A model that produces less than it was asked for, or
drops a unit, stops the run with a `ValidationError` naming the model.
[Writing a Model](../writing_a_model.md) has the full contract, plus parameters and
coverage.

## What the CLI doesn't do

The CLI is a thin layer over the Python API, and a few things are only available from
Python:

- **Only the model tier, plus context.** A demand no model answers is a cutoff, unless
  `--context-tolerance` lets a condition be met differently (section 4). Widening a
  location, moving a year, generalising along the vocabulary, or borrowing from a
  background pack needs a [`ResolutionChain`](../resolution.md).
- **No vocabulary labels.** The tree prints IRI segments. `report.tree(labels=...)` prints
  names instead.
- **No figures.** See [Figures](../figures.md).

The [5-minute tour](../../showcase.md) runs the same cement demand with all three tiers from
Python.
