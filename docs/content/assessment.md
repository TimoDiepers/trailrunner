---
icon: lucide/bar-chart
tags:
  - concepts
---

# Assessment

`trailrunner.assessment` turns a finished [`Report`](../api/report.md) into a score
(`assess`) or a time-explicit curve (`assess_dynamic`).

It is a separate package on purpose. An inventory, the flows in and out of a supply chain
keyed by identity, place and time, is a complete deliverable on its own: it says what
happened without deciding how much that matters. Characterization is one method's reading
of it, applied afterwards. `assessment` imports from `orchestration`, never the reverse.
The traversal runs the same whether or not this package is imported, so a model author
only answers "what did this process consume and emit", and changing a method never means
re-running the traversal.

```python
from trailrunner.assessment import Method, assess

report = Orchestrator(glossary).calculate(demand)            # the inventory
assessment = assess(report, Method.from_parquet("gwp100.parquet"))  # one reading of it
```

From the CLI: `trailrunner run ... --method gwp100.parquet` and `--dynamic
radiative_forcing`. See the [CLI tutorial](getting_started/cli.md#5-get-a-score-method).

## Methods

A [`Method`](../api/assessment.md) holds characterization factors keyed by
`(flow_iri, flow_unit, location, time)`.

### In memory

```python
from trailrunner import LocationHierarchy
from trailrunner.assessment import Method

GWP100 = Method(
    rows=[
        {"flow_iri": "https://vocab.sentier.dev/flows/co2-fossil", "flow_unit": "kg", "location": "GLO", "cf": 1.0},
        {"flow_iri": "https://vocab.sentier.dev/flows/ch4-fossil", "flow_unit": "kg", "location": "GLO", "cf": 29.8},
        {"flow_iri": "https://vocab.sentier.dev/flows/n2o", "flow_unit": "kg", "location": "GLO", "cf": 273.0},
    ],
    unit="kg CO2-eq",
    name="IPCC AR6 GWP100",
    hierarchy=LocationHierarchy({"DK": "RER", "RER": "GLO"}),
)
```

### The method parquet layout

`Method.from_parquet(path, hierarchy=...)` reads the same layout as a
[`ParameterSet`](parameters.md): a Frictionless `datapackage.json` in the schema metadata,
with field units under `resources[].schema.fields`.

| Column | Meaning |
| --- | --- |
| `flow_iri` | the elementary flow this factor characterizes |
| `flow_unit` | the unit the factor applies to, matched by string equality with no conversion |
| `location` | *optional.* Where the factor holds, widened through the `LocationHierarchy` like a parameter row |
| `time` | *optional.* A year, for factors that change over time |
| `cf` | the factor. Its declared `unit.name` is the method's score unit |

The method's `name` comes from the datapackage's `name`. The
[CLI tutorial](getting_started/cli.md#5-get-a-score-method) has a complete pyarrow script
that writes one.

The file is refused on load if it is ambiguous or incomplete:

- two rows sharing one key raise [`DuplicateFactor`](../api/errors.md), naming the key and
  the file,
- a missing `flow_iri`, `flow_unit` or `cf` column raises
  [`MissingColumns`](../api/errors.md),
- a `cf` column with no declared unit raises [`MissingUnit`](../api/errors.md), rather than
  producing a score with no unit.

### How a factor is looked up

**Location outranks time.** The lookup walks the location chain (always ending at the
root, so `GLO` factors answer every location) and at each level tries the flow's year,
then a row with no year. A `CH` row with no year beats a `GLO` row for exactly the year
asked for: a method states its factors where they hold, and a regional factor that isn't
dated is still that region's factor. If a year should win over a region, write the
regional row for that year.

**Years match exactly.** A lookup for 2031 against a 2030 row misses and falls through to
an undated row. Factors aren't interpolated: a parameter between two measured years is a
fair estimate, but a factor is a convention for a given horizon, and interpolating between
two conventions gives neither.

**A flow with no location** matches rows whose `location` is empty, then the root. It
never takes the first regional factor in file order.

## `assess()`

```python
from trailrunner.assessment import assess

assessment = assess(report, GWP100)
print(assessment.summary())
```

```text
543.908 kg CO2-eq
method: IPCC AR6 GWP100
8 uncharacterized flows on 6 nodes (not in the score, and not zero)
12 unresolved
0 proxies
```

An [`Assessment`](../api/assessment.md) carries:

| Attribute | What it holds |
| --- | --- |
| `score`, `unit`, `method` | the total, its unit, and the method's name |
| `by_flow` | `{(Flow, unit): contribution}` |
| `direct_by_node` | `{node_id: contribution of that node's own emissions}` |
| `cumulative_by_node` | `{node_id: own contribution plus everything below it}` |
| `provenance` | `{(Flow, unit): how its factor was found}`, e.g. a location fallback |
| `uncharacterized` | `[(Flow, unit, amount)]`, emissions the method has no factor for |
| `uncharacterized_by_node` | the same, per node |
| `truncated`, `unresolved`, `proxies` | carried over from the report |

`to_dataframe()` gives one row per characterized flow, sorted by the absolute score.

`truncated`, `unresolved` and `proxies` travel with the score, because a score is often
passed along without its report, and whoever receives it still needs to know the traversal
stopped at 12 cutoffs.

### `uncharacterized` is part of the answer

A flow with no factor would count as *no impact* the moment it dropped out of the sum,
and a missing factor never means that. `Method.factor` returns `None` rather than `0.0` so
`assess` can tell the difference and record the flow here instead.

A non-empty list means the *method* has a gap, not the inventory. When you see one:

- check whether the flow is genuinely out of scope: a GWP100 method has nothing to say
  about mercury, and that is correct,
- if it should be covered, compare the flow's IRI and unit with the method file's rows.
  A mismatch there is the most common reason a factor "goes missing" (see the
  [Brightway converter](#the-brightway-converter-an-offline-escape-hatch)),
- report the score together with the list. The same score with three flows left out is a
  different claim from one with none left out.

`uncharacterized_by_node` exists because `direct_by_node` alone can't distinguish a node
whose only emission has no factor from a node that emitted nothing: both are `0.0`.

## `assess_dynamic()`: a time-explicit reading

Every exchange carries `flow.time`, so the inventory already is a time series.
`assess_dynamic` characterizes each emission over its own decay curve, using
[`dynamic_characterization`](https://github.com/brightway-lca/dynamic_characterization),
instead of collapsing everything into one factor. It needs the `dynamic` extra:

```bash
uv sync --extra dynamic
```

```python
from trailrunner.assessment import assess_dynamic

dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)

dynamic.series            # DataFrame: date, amount, flow, activity, the per-year series
dynamic.unit              # "W/m2", the unit of series
dynamic.curve             # DataFrame: date, amount, the running total
dynamic.total             # the running total at the end of the horizon
dynamic.cumulative_unit   # "W·yr/m2", the unit of curve and total
print(dynamic.summary())
```

In the [5-minute tour](../showcase.md), the kilns are built in 2026 and 2029 and the cement
is made in 2030. The curve shows the construction years first and the production years
after, because that is when they happened. A single-year characterization can't represent
that.

**`unit` and `cumulative_unit` differ.** `series` is per year. `curve` and `total` are its
running sum, which for radiative forcing is an integral over time: W·yr/m², not W/m². For
`GWP` both are kg CO<sub>2</sub>-eq. Label `total` with `cumulative_unit`.

`activity` in `series` is `"<model>#<node id>"`, so eleven gas boilers in one chain stay
eleven distinguishable series.

### What it reports instead of dropping

Four lists, each `(Flow, unit, amount)` like `Assessment.uncharacterized`:

- **`uncharacterized`**: no characterization function covers the flow. The defaults
  (`default_functions()`) are the IPCC AR6 functions for fossil CO<sub>2</sub>, CO<sub>2</sub>
  from air, biogenic CO<sub>2</sub> uptake, fossil CH<sub>4</sub>, N<sub>2</sub>O and CO.
- **`wrong_unit`**: the flow is covered, but not in this exchange's unit.
- **`undated`**: the exchange has no year, so there is nowhere on the axis to put it.
- **`beyond_horizon`**: the emission entered the characterization but produced no dated
  row, which happens under `fixed_time_horizon=True` when it falls after the shared horizon
  ends.

`truncated`, `unresolved` and `proxies` are carried over from the report, and `summary()`
names everything.

`inventory_dataframe(report)` gives the four-column frame without characterizing it. It
**silently drops undated exchanges**. Use `assess_dynamic`, which lists them, when that
matters.

### Characterization functions are keyed on `(IRI, unit)`

The IPCC AR6 functions are defined **per kilogram**. Handed an amount in grams, one would
characterize 10 g as 10 kg, a factor of 1000 with nothing flagged. So functions are keyed on
`(flow IRI, unit)`, and units match by string equality:

- IRI known in another unit → **`wrong_unit`**,
- IRI not known at all → **`uncharacterized`**.

The first is a mismatch you can fix today: correct the model's unit, or add your own entry.

```python
from trailrunner.assessment import assess_dynamic, default_functions
from trailrunner.assessment.dynamic import CO2_FOSSIL

functions = dict(default_functions())
functions[(CO2_FOSSIL, "g")] = my_per_gram_function   # you supply the factor of 1000
dynamic = assess_dynamic(report, functions=functions)
```

### Two sign conventions for removals

`default_functions()` pairs each removal flow with the function matching its sign:

- `flows/co2-from-air`, which `DirectAirCapture` emits **already negative**, uses the
  ordinary CO<sub>2</sub> function,
- `flows/co2-uptake` uses `characterize_co2_uptake`, which negates, because that flow's
  convention is a **positive** amount meaning uptake.

Mixing them up silently turns a removal into warming of the same size. A model emitting a
removal has to follow the convention of the IRI it emits on.

### Metrics

`METRICS` lists five, but only `radiative_forcing` and `GWP` work as they are. `pGWP`,
`pGTP` and `prospective_radiative_forcing` need
`dynamic_characterization.prospective.set_scenario()` called first, and `assess_dynamic`
has no scenario argument. Import and set it yourself before calling in.

Two conventions of `dynamic_characterization` matter when reading a curve closely: the
CO<sub>2</sub> response is zero in the emission's own year, so the first row falls in
`emission_year + 1`, and years are a fixed 365.2425 days, so a horizon's last row can land
a day short of the calendar anniversary.

### The two horizon conventions

- **`fixed_time_horizon=False`** (default): each emission is characterized over its own
  `horizon` years, starting from its own year.
- **`fixed_time_horizon=True`** (Levasseur): every horizon ends on the same date, so
  earlier emissions are integrated for longer and one at the very end barely counts.

They answer different questions about weighing emissions at different times, and the
literature doesn't settle which a study should ask. Both are exposed so the choice is made
visibly by whoever runs the study.

The fixed horizon has to start somewhere. `dynamic_characterization` defaults to the
current wall-clock time, which would make the same report give a different total next
year. trailrunner anchors it instead to **1 January of the earliest year that actually
enters the characterization**, and records the anchor:

```python
dynamic = assess_dynamic(report, horizon=20, fixed_time_horizon=True)
dynamic.time_horizon_start   # datetime(2030, 1, 1)
```

Only characterized rows count. An uncharacterizable or wrong-unit exchange from 2010 can't
drag the anchor back and push a real 2030 emission past the horizon into a silent zero.
Pass `time_horizon_start=` yourself when the study has a better anchor, such as a
functional unit dated before any emission. With `fixed_time_horizon=False` the anchor is
recorded but changes nothing.

## The Brightway converter: an offline escape hatch

trailrunner never imports `bw2data` at runtime, so a method file travels with a study
without whoever's Brightway project produced it. `dev/convert_brightway_method.py` is a
hand-run script, behind the `brightway` extra, that writes an existing Brightway LCIA
method in the layout above:

```bash
uv sync --extra brightway
uv run --extra brightway python dev/convert_brightway_method.py \
    --project ecoinvent-3.10 \
    --method "EF v3.1" "climate change" "global warming potential (GWP100)" \
    --iri-prefix https://vocab.sentier.dev/flows/ \
    --out gwp100.parquet
```

!!! warning "Check both identity columns before trusting a converted method"

    **Flow identity.** Each Brightway biosphere flow becomes
    `<iri-prefix><slug of name>/<slug of categories>`. The compartment is included because
    ecoinvent has same-named flows in different compartments. Nothing checks these IRIs
    against what your models emit. A factor on an IRI nobody emits isn't an error anywhere.
    It just means no factor for the flows that do emit, and that shows up only as a
    non-empty `uncharacterized`.

    **Units.** Brightway writes `"kilogram"`, `"cubic meter"`, `"megajoule"`, while
    trailrunner's models emit `"kg"`, `"m3"`, `"MJ"`. The converter normalises the
    spellings it knows (`UNIT_SPELLINGS` in the script) and **prints every one it doesn't
    recognise**, leaving it untouched for you. Nothing converts units at runtime.

    Compare `flow_iri` and `flow_unit` in the output with your models' biosphere
    exchanges, or run `assess` and confirm `uncharacterized` is empty for the flows the
    method should cover. On the time-explicit path, a non-empty `wrong_unit` is this same
    mismatch.
