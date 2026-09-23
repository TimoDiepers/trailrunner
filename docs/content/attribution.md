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
| `none` | refuses co-production outright; a model returning more than one product raises `UnallocatedCoProduction`. The only rule that does not partition anything, and the default. |
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

Every model in a run declares which of the five rules it can honour, in `supports`. Every
model that ships with `trailrunner` is monofunctional and so declares all five: with one
product there is nothing to partition, and the answer is the same under every rule. The
`Model` base class still defaults to `frozenset({"none"})`, because a model says nothing
about multifunctionality until its author has thought about it.

### Who may answer a credit

A credit is a demand for what *somebody else* would have made. If the process that just
produced the co-product were allowed to answer its own credit, it would answer by producing
its co-product again, crediting itself again, and — for a process that is the only producer
of its co-product — its entire burden would cancel to zero while the report still showed an
inventory entry.

So the credit carries one piece of context with it for exactly one hop: the model that
minted it, which resolution then drops. The exclusion is by **instance identity**, not by
class — a CH plant and an FR plant of the same class are different processes, and each
stays a candidate for the other's credits. If nobody else makes the co-product, the credit
becomes a visible cutoff (`no_model_found`, counted in `summary()` as being on a credit
branch), which is the honest answer: this credit has no counterfactual in the model set.

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

All three of these propagate straight out of `Orchestrator.calculate`, so they are
importable from the package root: `from trailrunner import MissingProperty,
UnsupportedAttribution, UnallocatedCoProduction`.

**`MissingProperty`** — the model produced its co-products without the property the
rule partitions on (`mass`, `price` or `energy`), or its co-products disagree on the
property's unit, or the property sums to zero and there is nothing to partition, or one of
them is **negative**. Fix it in the model: give every co-product the missing property, in
one consistent unit, with a value that is not uniformly zero. There is no default
trailrunner can fall back to — a fabricated price would be an invisible value judgement.

A negative value is refused for a different reason than the others. A share taken over a
negative value is not a share: with heat at +10 EUR and power at −8 EUR, heat's "share"
comes out at **5.0**, and the demanded product silently carries five times the process's own
burden. A negative price means that output is a waste the process pays to be rid of, not a
co-product — model it as a treatment demand, or choose `substitution`.

**`UnallocatedCoProduction`** — a model returned co-products under `none`, which is the
default rule and so the likeliest refusal a user meets. Model the process
monofunctionally, or choose a rule. A `TrailrunnerError`, so `except TrailrunnerError`
around a calculation catches it like every other refusal; also a `ValueError`, which is
what it was before it had a class of its own.

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

The spike is visible only if the study year *is* a build year. Ask `first_life` for any
other year and it attributes **zero** capital — not a small share, none at all — because by
then the construction has already been charged to the year it happened in. A 2030 study of a
fleet built in 2026 and 2029 therefore shows no construction whatsoever: that is the rule
working, not a fleet that failed to load. Only a study spanning the build years sees the
spike the name promises. A demand with no year at all is refused under `first_life` rather
than silently falling on the zero side of the comparison.

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
`NodeRecord.attribution` — the record `allocate()` or `substitute()` leaves behind on the
Result, lifted onto the node beside `resolution`. It is deliberately *not* part of
`report.provenance`: provenance is what the **model** recorded, and the model neither chose
the run's allocation rule nor saw it. A node with a single product still gets an entry
(`{"share": 1.0, ...}`) so a reader never has to special-case "no co-production happened
here" against "the attribution key is simply missing".

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
