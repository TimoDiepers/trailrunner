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
```

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
assessment.unit    # "W/m2"
assessment.total   # the cumulative integral at the end of the horizon
assessment.curve   # DataFrame: date, amount — running total, for plotting
assessment.series  # DataFrame: date, amount, flow, activity — the marginal series
```

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot(assessment.curve["date"], assessment.curve["amount"])
ax.set_xlabel("year")
ax.set_ylabel(assessment.unit)
```

The resulting curve is flat until just after 2026 — when the construction pulse's own decay curve
starts contributing — rises through the run-up years, and steps up again just after 2030 when the
capture year's emissions begin theirs. The construction pulse shows up on the timeline *before*
the capture years, because it happened before them; a static, single-year characterization has no
way to represent that at all.

`assess_dynamic` reports two lists rather than silently dropping anything:

- **`uncharacterized`** — flow IRIs the characterization functions do not cover (by default, the
  IPCC AR6 functions for fossil CO2, biogenic CO2 uptake, fossil CH4, N2O and CO — see
  `default_functions()`). Pass your own `functions` mapping to extend it.
- **`undated`** — `(iri, unit, amount)` for exchanges with no `flow.time`. A dynamic assessment has
  nowhere on the axis to put them, so it says so rather than guessing a year.

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
Brightway biosphere flow becomes `<iri-prefix><slugified name>` — the flow's `name`, lowercased,
with every run of non-alphanumeric characters collapsed to a single hyphen. Nothing checks that
this matches the IRI any of your models actually emit. A CF attached to an IRI nothing in your
supply chain produces is not an error anywhere in the pipeline — it is silently *no CF at all* for
every flow that does emit, and the only place that shows up is `Assessment.uncharacterized` (or
`DynamicAssessment.uncharacterized`, for the time-explicit path) coming back non-empty, or a score
that is quietly missing a term nobody flagged.

Before trusting a number that came out of a converted method, check the output file's `flow_iri`
column against the IRIs your models declare in their `biosphere` exchanges — by hand, or by
running `assess` and confirming `uncharacterized` is empty for the flows you expect the method to
cover.
