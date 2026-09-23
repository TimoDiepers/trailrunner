---
tags:
  - concepts
---

# Attribution

Every multi-output process and every long-lived asset raises a question with no
value-free answer: how much of *this* burden belongs to *that* product, or to *this*
year? A static LCA tool can bury the answer in the model, because there is usually only
one model per study reader. `trailrunner` traverses supply chains built from many
models, contributed by many authors, so burying the answer would mean every model
answering the question differently — and a reader would have no way to tell.

[`AttributionSettings`](../api/settings.md) makes the choice explicit and applies it in
one place, so that every model in a run answers identically. A model still has the final
word — it declares which rules it can honour via `supports`, and a run that asks for a
rule it cannot honour gets `UnsupportedAttribution` rather than a silently wrong number.

`AttributionSettings` has three fields:

| field | question it answers |
|---|---|
| `allocation` | when a process makes more than one product, how much of its burden goes to each |
| `capital` | when an asset outlives the year it was built in, how its construction is spread over what it makes |
| `reuse` | *(validated, not yet consumed — see [below](#reuse-is-validated-but-unconsumed))* |

## Allocation: `none`, `mass`, `economic`, `energy`, `substitution`

[`allocate()`](../api/attribution.md) and `substitute()` live in
`trailrunner.attribution.allocation` and are applied by the [`Runner`](../api/runner.md)
after every `Model.apply()` call — the model never sees the rule.

| rule | what it does |
|---|---|
| `none` | refuses co-production outright; a model returning more than one product raises `ValueError`. The only rule that does not partition anything, and the default. |
| `mass` | partitions technosphere and biosphere in proportion to each product's `mass` property |
| `economic` | partitions in proportion to each product's `price` property |
| `energy` | partitions in proportion to each product's `energy` property |
| `substitution` | keeps the whole burden on the demanded product, and pushes each *other* product onto the traversal queue as a **negative** demand — whoever would otherwise have made it is asked what that would have cost, and the answer is subtracted as a credit |

`mass`, `economic` and `energy` share one mechanism (`allocate()`): sum the named
property over every exchange of each product IRI (so a product split across several
exchanges is not double-counted), and scale technosphere and biosphere by
`demanded_total / grand_total`. `substitution` is the odd one out — it changes what gets
*traversed*, not the arithmetic on what already came back — which is why the `Runner`
calls a different function (`substitute()`) for it instead.

### Worked example: the same CHP, two different numbers

A CHP plant makes 100 MJ of heat and 50 MJ of electricity from one batch of fuel,
emitting 12 kg of fossil CO2 for the batch. Heat sells at 3 EUR and electricity at 9 EUR
(so heat is a quarter of the batch's revenue, even though it is two thirds of its
energy). A demand asks for 100 MJ of heat.

**`allocation="economic"`** partitions the batch's own 12 kg by revenue share:
`3 / (3 + 9) = 0.25`, so heat carries `12 * 0.25 = 3.0 kg` CO2. The other 9 kg rides with
whoever separately demands the electricity.

**`allocation="substitution"`** does not partition at all: the heat demand keeps the
full 12 kg. But the 50 MJ of electricity the plant also made is credited as an avoided
burden — pushed onto the queue as a demand for *-50 MJ* of electricity, answered by
whatever model represents the displaced alternative (say, a grid mix at 0.1 kg CO2/MJ):
a credit of `-0.1 * 50 = -5 kg`. Net: `12 - 5 = 7.0 kg` CO2 for the same 100 MJ of heat.

Same model, same demand, two different numbers — 3.0 kg against 7.0 kg — because the
question being answered is different: *"what share of this batch is heat's?"* against
*"what would the world have looked like if this plant had not displaced a grid
purchase?"*. `report.attribution[node_id]` names which question was asked and shows the
share or the credited products, so a reader is never left guessing which one produced a
given number. See `tests/test_allocation.py` and `tests/test_substitution.py` for the
runnable versions of this example.

### When a model can't honour the rule

**`MissingProperty`** — the model produced its co-products without the property the
rule partitions on (`mass`, `price` or `energy`), or its co-products disagree on the
property's unit, or the property sums to zero and there is nothing to partition. Fix it
in the model: give every co-product the missing property, in one consistent unit, with a
value that is not uniformly zero. There is no default trailrunner can fall back to — a
fabricated price would be an invisible value judgement.

**`UnsupportedAttribution`** — the run asked for a rule that is not in the model's
`supports`. A model's author, not the run, decides how far a model reaches; if
`CHP.supports = frozenset({"none", "economic"})`, a run configured for `substitution`
gets this error naming the model and what it does support, rather than `CHP` silently
answering `economic` anyway. Fix it by widening `supports` on the model (only after
checking the model actually gives a sound answer under that rule) or by choosing a rule
the model already supports.

## Capital: `per_output`, `per_year`, `first_life`

Once the inventory knows *when* things happen, a second question follows the first: a
plant built in 2027 and running until 2047 made something in 2030 — how much of its
construction belongs there? [`amortize()`](../api/attribution.md), in
`trailrunner.attribution.capital`, is the one place all three answers live, so that every
model attributes construction identically.

`annual_output` is what the asset makes **in the demanded year**; `lifetime_output` is
what it makes over its whole life. Keeping them separate is exactly what gives the first
two rules different answers:

| rule | attributed capital | reads as |
|---|---|---|
| `per_output` | `capital * demanded_output / lifetime_output` | spread over everything the asset will ever make — a lean year carries only its own share |
| `per_year` | `capital / lifetime_years * demanded_output / annual_output` | one equal share per year of life — a lean year still carries a full year's construction |
| `first_life` | `capital * demanded_output / annual_output` if `demand_year == build_year`, else `0.0` | all of it lands in the year the asset was built, at the cost of a spike |

The first two agree exactly when output is flat (`lifetime_output == annual_output *
lifetime_years`), which is the common case, not a bug. They diverge precisely when a
year is atypical — which is the reason the choice exists at all, rather than a single
formula being "obviously" correct.

[`DirectAirCapture`](../api/models.md) is the model that consumes this. Given a
[`Fleet`](../api/fleet.md) of plants built in different years, it amortizes each
plant's own capacity (standing in for that plant's construction) over that plant's own
annual and lifetime output, according to `self.settings.attribution.capital`, and
demands the result **in the year that plant was actually built** — so the construction
input lands in its own year and meets whatever background that year carries. The rule
used is recorded in the result's provenance under `capital_rule`.

## Reuse is validated, but unconsumed

`AttributionSettings.reuse` (`first_life` or `shared`) answers a *second-life* question:
whether a product's initial production falls entirely on the item's first life, or is
shared with whatever comes after it is reused. It is validated at construction time —
an unknown value raises immediately — and it will be reported once something reads it.

Nothing in this repository reads it yet. There is no model here with a second life to
attribute, and wiring a rule with no caller would mean inventing its semantics and
testing them against nothing. So `reuse` sits in `AttributionSettings`, checked and
carried through to `report.attribution_settings`, doing nothing else. This is
deliberate, not an oversight — do not treat its presence as a working feature.

## Reading `report.attribution`

`Report.attribution` is a `dict[int, dict]` keyed by node id, filled from each node's
`result.provenance["attribution"]` — the record `allocate()` or `substitute()` leaves
behind. A node with a single product still gets an entry (`{"share": 1.0, ...}`) so a
reader never has to special-case "no co-production happened here" against "the
attribution key is simply missing".

```python
report = Orchestrator(glossary, settings=settings).calculate(demand)
for node_id, record in report.attribution.items():
    print(node_id, record)
# {'allocation': 'economic', 'property': 'price', 'share': 0.25, 'co_products': [...]}
```

`Report.attribution_settings` carries the `AttributionSettings` the run was configured
with, and `report.summary()` states it in one line:

```text
attribution: allocation=economic, capital=per_output
```

so the choices that produced the numbers sit next to the numbers themselves, and a
reader does not need to know how the run was called to know what it decided.
