---
tags:
  - concepts
---

# Assessment

`trailrunner.assessment` turns a finished [`Report`](../api/report.md) into a single score or a
time-explicit curve. It is a separate package from `orchestration`, `core` and `params`, and
that separation is deliberate rather than incidental.

## Why this is a separate module

An inventory — the flows in and out of a supply chain, keyed by identity, place and time — is a
complete, valid deliverable on its own. It answers "what happened" without taking a position on
"how much does that matter", and plenty of legitimate uses of a `Report` never need the second
question answered: auditing an unresolved list, comparing two traversals' cutoffs, or handing raw
biosphere exchanges to someone else's characterization pipeline entirely.

Characterization is a separate *reading* of that inventory — one particular method's opinion,
applied afterwards — not a step the traversal performs. `trailrunner.assessment` imports from
`trailrunner.orchestration.report`; the reverse is never true. The `Orchestrator`, the `Queue` and
every `Model` run to completion with no idea that this package exists, and nothing about the
traversal changes if it is never imported at all. That keeps a `Model` author's job to exactly one
thing — what did this process consume and emit — and keeps a change to how flows get characterized
from ever being a reason to re-run the traversal.

```python
from trailrunner import Demand, Flow, Glossary, Orchestrator
from trailrunner.assessment import Method, assess

report = Orchestrator(glossary).calculate(demand)          # the inventory, on its own
assessment = assess(report, Method.from_parquet("gwp100.parquet"))  # a reading of it
```

## The method parquet layout

A [`Method`](../api/assessment.md) reads characterization factors from a parquet file, the same
shape as a [`ParameterSet`](parameters.md): a Frictionless `datapackage.json` embedded in the
schema metadata, columns' units and IRIs read out of `resources[].schema.fields`. Four columns:

| Column | Meaning |
| --- | --- |
| `flow_iri` | which elementary flow this factor characterizes |
| `flow_unit` | the unit the factor applies to — string equality, no conversion |
| `location` | where the factor holds; widened through a [`LocationHierarchy`](../api/location.md) the same way a `ParameterSet` row is |
| `cf` | the characterization factor itself |
| `time` | *optional.* A year, for a method whose factors change over time |

`time` is read only if the column is present, and matched **exactly** — a lookup for year 2031
against a row written for 2030 misses, and falls through to a row with no `time` at all if one
exists. There is no interpolation between two years' CFs, on purpose: a `ParameterSet` row is a
measured or projected quantity, and interpolating between two of those years is a reasonable
estimate of a third; a CF is a modelling convention agreed on for a given horizon, and
interpolating between two conventions produces neither one.

**Location outranks time.** The lookup walks the location chain in the outer loop and tries
`flow.time` then `None` in the inner one, so a `CH` row *with no year* beats a `GLO` row written
for exactly the year asked for. That is a real decision, not an accident of loop order: a method
states its factors where they hold, and a regional convention that did not bother to date itself
is still that region's convention. Reaching past it to the global table because the global table
happened to name the year would answer with a different method's opinion, quietly. If you need a
year to win over a region, state the regional row for that year too.

Two factors sharing one `(flow_iri, flow_unit, location, time)` key is a **data error**, and
`Method.__init__` raises [`DuplicateFactor`](../api/errors.md) naming the key and the file — the
same way two models producing one product raises rather than picking one. Keeping whichever row
came last would put a number in the score that appears in no message anywhere. A parquet missing
`flow_iri`, `flow_unit` or `cf` raises [`MissingColumns`](../api/errors.md), which names the file
and the layout it expected.

The method's *name* comes from the datapackage's `name`; its *score unit* comes from the `cf`
column's declared `unit.name` — the same rule `ParameterSet.unit_of` follows, and for the same
reason: the unit travels with the number that needs it, rather than being assumed by the caller.
A `cf` column with no declared unit raises [`MissingUnit`](../api/errors.md) rather than handing
back a dimensionless score.

```python
from trailrunner.assessment import Method

method = Method.from_parquet("gwp100.parquet")
method.name   # "EF v3.1 | climate change"
method.unit   # "kg CO2eq"
```

## `assess()` and reading `uncharacterized`

```python
from trailrunner.assessment import assess

assessment = assess(report, method)

assessment.score               # total, in method.unit
assessment.by_flow              # {(Flow, unit): contribution}
assessment.direct_by_node        # {node_id: contribution from that node's own emissions}
assessment.cumulative_by_node     # {node_id: that node's own contribution plus everything below it}
assessment.provenance             # {(Flow, unit): factor lookup provenance — location fallback, etc.}
assessment.uncharacterized         # [(Flow, unit, amount), ...]
assessment.uncharacterized_by_node  # {node_id: [(Flow, unit, amount), ...]}
assessment.truncated                 # the traversal hit max_depth or max_nodes
assessment.unresolved                 # how many demands it could not resolve
assessment.proxies                     # how many nodes were answered by something other than a model
print(assessment.summary())              # the score and every reason to distrust it, in one block
```

`uncharacterized_by_node` exists because `direct_by_node` alone cannot tell you the difference
between a node whose only emission has no factor and a node that emitted nothing: both are
`0.0`. `uncharacterized` cannot close that gap on its own either — it carries a `Flow`, not a
node id, so the two lists cannot be joined after the fact. The per-node record is filled in the
loop that has both in hand.

`truncated`, `unresolved` and `proxies` are carried straight over from the `Report`. A consumer
handed only an `Assessment` — the usual case once a score is passed along — would otherwise have
no way to tell a complete traversal's score from one that stopped at `max_nodes` halfway down the
chain. They are the same floats either way.

`summary()` returns (it does not print) a block in the shape of [`Report.summary()`](reports.md):
the score with its unit, the method's name, how many flows went uncharacterized and on how many
nodes, then the inventory flags above. It exists for the same reason `Report.summary()` does — the
caveats belong in front of a reader who did not know to go looking for them.

`uncharacterized` is not an edge case to check once and forget — it is as much a part of the
answer as `score` is, for exactly the reason `report.unresolved` is: a flow the method has no
factor for is silently treated as *no impact* the moment it is left out of the sum, and that is
never what a missing factor means. `Method.factor` returns `None` rather than `0.0` precisely so
`assess` can tell the two apart, and it records every `None` here instead of adding it in as
zero.

A non-empty `uncharacterized` list means the *method* has a gap, not that the inventory does. The
flows are real; the characterization does not cover them yet. When you see one:

- Check whether the flow genuinely falls outside the method's scope (a GWP100 method has nothing
  to say about a `sox` flow, and that is correct, not a bug).
- If it should be covered, check the flow's IRI against what the method file actually has rows
  for — a mismatch there is the single most common reason a factor "goes missing" (see the
  Brightway converter's caveat below).
- Report the score alongside the list, not instead of it. A score with an empty `uncharacterized`
  is a different claim than the same score with three flows left out, and a reader comparing two
  runs needs to know which one they are looking at.

## `assess_dynamic()`: a time-explicit reading

Every `Exchange` already carries `flow.time`, so the inventory *is* a time series; `assess_dynamic`
reshapes it into the four columns [`dynamic_characterization`](https://github.com/brightway-lca/dynamic_characterization)
expects (`date`, `amount`, `flow`, `activity`) and characterizes each emission over its own decay
curve rather than folding everything into one instantaneous factor. It needs the `dynamic` extra:

```bash
uv sync --extra dynamic
```

A worked example: a DAC plant is built in 2026, and the CO2 it captures — plus the fossil CO2 its
own operating heat still emits — happens in 2030. Both years matter to the curve, and the point of
this module is that they stay apart instead of collapsing into a single 2030 number:

```python
from trailrunner import Demand, Flow, Glossary, Orchestrator
from trailrunner.assessment import assess_dynamic

report = Orchestrator(glossary).calculate(demand)  # a two-node traversal: construction in
                                                    # 2026, capture and operating heat in 2030

assessment = assess_dynamic(report, metric="radiative_forcing", horizon=50)
assessment.series           # DataFrame: date, amount, flow, activity — the marginal series
assessment.unit             # "W/m2" — the unit of `series`
assessment.curve            # DataFrame: date, amount — the cumulative integral, for plotting
assessment.total            # that integral at the end of the horizon
assessment.cumulative_unit  # "W·yr/m2" — the unit of `curve` and `total`
assessment.truncated        # the traversal hit max_depth or max_nodes
assessment.unresolved       # how many demands it could not resolve
assessment.proxies          # how many nodes were answered by something other than a model
print(assessment.summary())
```

**`unit` and `cumulative_unit` are not the same thing.** `series` is a marginal quantity per year;
`curve` and `total` are its cumulative sum, which for a radiative-forcing metric is an integral
over time and so is W·yr/m2, not W/m2. For the `GWP` metrics the marginal series is already in
kg CO2eq per year and the cumulative sum is kg CO2eq, so the two coincide — which is exactly why a
single `unit` field looked right for long enough to ship. Label `total` with `cumulative_unit`.

`activity` in `series` is `"<model>#<node id>"`, not the model name alone: a supply chain with
eleven gas boilers in it has eleven distinguishable series, and a row that says only `"GasBoiler"`
cannot be attributed back to a place in the chain.

`inventory_dataframe(report)` is exported for anyone who wants the frame without the
characterization. Note that it **silently leaves out undated exchanges** — it returns a frame, not
a report of what it dropped. Use `assess_dynamic`, which records every one of them, when the
omissions matter.

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot(assessment.curve["date"], assessment.curve["amount"])
ax.set_xlabel("year")
ax.set_ylabel(assessment.cumulative_unit)  # the curve is the integral, not the series
```

The resulting curve is flat until just after 2026 — when the construction pulse's own decay curve
starts contributing — rises through the run-up years, and steps up again just after 2030 when the
capture year's emissions begin theirs. The construction pulse shows up on the timeline *before*
the capture years, because it happened before them; a static, single-year characterization has no
way to represent that at all.

`assess_dynamic` reports four lists rather than silently dropping anything, and all four have
the same shape as `Assessment.uncharacterized` — `(Flow, unit, amount)`, one entry per exchange —
so "how much did this leave out" is the same question with the same kind of answer everywhere:

- **`uncharacterized`** — exchanges whose flow no characterization function covers (by default,
  the IPCC AR6 functions for fossil CO2, biogenic CO2 uptake, fossil CH4, N2O and CO — see
  `default_functions()`). Pass your own `functions` mapping to extend it.
- **`wrong_unit`** — exchanges whose flow *is* covered, but not in the unit the exchange is
  denominated in. See below.
- **`undated`** — exchanges with no `flow.time`. A dynamic assessment has nowhere on the axis to
  put them, so it says so rather than guessing a year. An exchange that is both undated and
  uncharacterized appears in both lists, because each answers its own question.
- **`beyond_horizon`** — exchanges that *did* enter the characterization but contributed no dated
  row to `series`. Under `fixed_time_horizon=True` every horizon ends at the same date, so an
  emission past that date gets a zero-length horizon and comes back undated; it cannot go on the
  curve. Dropping it in silence would leave you with a total that reads as though it had been
  counted, so it is named instead.

`assess_dynamic` also carries `truncated`, `unresolved` and `proxies` over from the `Report`, the
same way `assess` does, and `summary()` names all of them alongside the four lists.

### Characterization functions are keyed on `(IRI, unit)`

`default_functions()` returns a mapping keyed on `("<flow IRI>", "kg")`, not on the IRI alone, and
a `functions` mapping you supply is keyed the same way. The reason is blunt: the IPCC AR6
functions are defined **per kilogram** — their radiative efficiencies are `radiative_efficiency_kg`
— so handing one an amount denominated in grams characterizes 10 g of fossil CO2 as 10 kg. That is
not a rounding error, it is a factor of 1000, arriving with an empty `uncharacterized` list and
nothing anywhere saying it happened. It is reachable from shipped code: `models/electricity.py`
takes its biosphere unit from the parameter file's declared unit, so a file written in `g/MJ`
produces exchanges in `g`.

Unit compatibility here is **string equality**, exactly as in `Method.factor`. A mismatch is
reported, never converted:

- the IRI is known in some *other* unit → the exchange goes to **`wrong_unit`**;
- the IRI is not known at all → it goes to **`uncharacterized`**.

They are kept apart because they are different problems for whoever reads the result. "Nobody
characterized this gas" is a gap in the method and may be correct. "This gas is characterized, per
kilogram, and your model emitted grams" is a mismatch between a model and a method that somebody
can fix today — by fixing the model's unit, or by adding a `(iri, unit)` entry of your own:

```python
from trailrunner.assessment import assess_dynamic
from trailrunner.assessment.dynamic import CO2_FOSSIL, default_functions

functions = dict(default_functions())
functions[(CO2_FOSSIL, "g")] = my_per_gram_function   # you supply the factor of 1000, explicitly
assessment = assess_dynamic(report, functions=functions)
```

Without this, the two paths disagreed about the same input: `assess` put a grams exchange in
`uncharacterized` and `assess_dynamic` characterized it as kilograms.

### The metrics that need a scenario first

`METRICS` lists five, but only `radiative_forcing` and `GWP` work out of the box. `pGWP`, `pGTP`
and `prospective_radiative_forcing` are the Watanabe et al. scenario-based metrics, and they
require `dynamic_characterization.prospective.set_scenario()` to have been called first.
`trailrunner` exposes no way to call it — there is no scenario argument anywhere in
`assess_dynamic` — so reaching those three means importing `dynamic_characterization.prospective`
yourself and setting the scenario before you call in. They are listed because the library accepts
them, not because this module wires them up.

Two of `dynamic_characterization`'s own conventions are worth knowing before reading a curve
closely: the CO2 impulse-response function is exactly zero at the emission's own year, so a
marginal series' first row falls in `emission_year + 1`, not the emission year itself; and the
library's year offsets are a fixed 365.2425-day average Gregorian year rather than a calendar
year, so a horizon's last row can land a day short of its naive last anniversary. Both are the
installed library's behaviour, not this module's.

### The two horizon conventions

`assess_dynamic` exposes `fixed_time_horizon`, and it defaults to `False`:

- **`fixed_time_horizon=False`** (the default) — the *conventional* convention. Each emission is
  characterized over its own `horizon` years, starting at its own emission year. An emission in
  2040 and one in 2050 both get the full horizon, just starting from different points on the
  calendar.
- **`fixed_time_horizon=True`** — the *Levasseur* convention. Every emission's horizon ends at the
  same date, so an earlier emission is integrated for longer than a later one and an emission at
  the very end of the run barely counts at all.

Neither is obviously right — they encode different questions about how to weigh emissions that
happen at different times against each other, and the literature does not settle which question a
given study should ask. `trailrunner` exposes both rather than picking one, so the choice is made
by whoever is close enough to the study to know which question it needs answered, and made
visibly rather than buried in a default.

#### What the fixed horizon is anchored to

"Every emission's horizon ends at the same date" raises the obvious question: *which* date.
`dynamic_characterization.characterize` takes a `time_horizon_start`, and its default is
`datetime.now()` — evaluated once, **at module import**. Left alone, that anchors a study's
Levasseur horizon to the machine's wall clock: the same report gives a different total next year,
a 2030 emission with `horizon=20` silently gets about 16 years of horizon instead of 20, and any
emission past the wall-clock horizon's end comes back as a single undated row.

`trailrunner` derives the anchor from the report instead and passes it explicitly: **the earliest
emission that actually enters the characterization, as 1 January of that year.** That is the
study's own start, it is reproducible, and it does not depend on when the code runs. The value
actually used is recorded on the result:

```python
assessment = assess_dynamic(report, horizon=20, fixed_time_horizon=True)
assessment.time_horizon_start   # datetime(2030, 1, 1) — what the horizon was anchored to
```

"Actually enters the characterization" is load-bearing, and it is the difference between a
reported gap and a silent zero. An exchange in the wrong unit, or one whose flow no function
covers, is reported and never reaches the frame. If such an exchange were allowed to set the
anchor — a stray 2010 entry in grams, say — the shared horizon would end in 2030, and a perfectly
characterizable 2030 emission would fall past it and come back empty. The total would be `0.0`,
with nothing in `uncharacterized`, `wrong_unit` or `undated` to explain it. So the anchor comes
from the rows that are going to be characterized, and nothing else.

Pass `time_horizon_start=` yourself when the study has a better anchor than its own first
characterized emission — a functional unit dated before any emission, most obviously. The field
is recorded on every result, including conventional-convention ones, where it is inert: with
`fixed_time_horizon=False` each emission starts its own horizon and the anchor changes nothing.

## The Brightway converter: an offline escape hatch

`trailrunner` never imports `bw2data` at runtime — a method file has to travel with a study
without dragging along whoever's local Brightway project produced it. `dev/convert_brightway_method.py`
is a hand-run script, behind the `brightway` extra, that reads an existing Brightway LCIA method
and writes it out in the parquet layout above:

```bash
uv sync --extra brightway
uv run --extra brightway python dev/convert_brightway_method.py \
    --project ecoinvent-3.10 \
    --method "EF v3.1" "climate change" "global warming potential (GWP100)" \
    --iri-prefix https://vocab.sentier.dev/flows/ \
    --out gwp100.parquet
```

State the caveat plainly, because it is easy to trust a converted file more than it has earned:
**flow identity is the hard part, and the converter is deliberately dumb about it.** Each
Brightway biosphere flow becomes `<iri-prefix><slugified name>/<slugified categories>` — the
flow's `name` and its compartment, lowercased, with every run of non-alphanumeric characters
collapsed to a single hyphen. The compartment is in there because ecoinvent has many same-named
biosphere flows in different compartments ("Carbon dioxide, fossil" to air, to water, to soil),
and a slug built from the name alone would collide them into one row. Nothing checks that the
result matches the IRI any of your models actually emit. A CF attached to an IRI nothing in your
supply chain produces is not an error anywhere in the pipeline — it is silently *no CF at all* for
every flow that does emit, and the only place that shows up is `Assessment.uncharacterized` (or
`DynamicAssessment.uncharacterized`, for the time-explicit path) coming back non-empty, or a score
that is quietly missing a term nobody flagged.

The **unit is the second trap, and it is the same trap.** Brightway spells biosphere units
`"kilogram"`, `"cubic meter"`, `"megajoule"`; `trailrunner`'s models emit `"kg"`, `"m3"`, `"MJ"`.
Matching in `Method.factor` is string equality in both columns, so a method file full of
`"kilogram"` matches nothing at all and every flow lands in `uncharacterized` — honest, but a
guaranteed empty score on first use. The converter normalises the spellings it knows (see
`UNIT_SPELLINGS` in the script) and **prints every spelling it did not recognise**, leaving those
untouched for you to decide about. That normalisation happens once, at authoring time; nothing in
`trailrunner.assessment` ever converts between units at runtime.

Before trusting a number that came out of a converted method, check **both** identity columns of
the output file:

- **`flow_iri`** against the IRIs your models declare in their `biosphere` exchanges;
- **`flow_unit`** against the units those same exchanges carry — the converter's output line
  names any unit it could not normalise, and those are the first ones to look at;

by hand, or by running `assess` and confirming `uncharacterized` is empty for the flows you expect
the method to cover. For the time-explicit path, check `wrong_unit` too: a non-empty `wrong_unit`
is precisely this mismatch, caught.
