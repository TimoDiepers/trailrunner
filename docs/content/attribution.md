---
icon: lucide/list-tree
tags:
  - concepts
---

# Attribution

Every multi-output process and every long-lived asset raises a question with no
value-free answer: how much of *this* burden belongs to *that* product, or to *this* year?
A single-author LCA can settle it inside the model. A supply chain assembled from many
models by many authors can't: each model would answer differently, and the reader couldn't
tell.

[`AttributionSettings`](../api/settings.md) states the choice once for the whole run and
applies it in one place. A model still limits how far that choice reaches: it declares the
rules it can honour in `supports`, and a run asking for anything else gets
`UnsupportedAttribution` instead of a silently different number.

```python
from trailrunner import AttributionSettings, Orchestrator, Settings

settings = Settings(attribution=AttributionSettings(allocation="economic", capital="per_year"))
report = Orchestrator(glossary, settings=settings).calculate(demand)
```

From the CLI: `--allocation economic --capital per_year`.

| Field | Question | Default |
| --- | --- | --- |
| `allocation` | when a process makes more than one product, how much of its burden goes to each? | `none` |
| `capital` | when an asset outlives the year it was built in, how is its construction spread over what it makes? | `per_output` |
| `reuse` | *validated, not yet used, see [below](#reuse-is-validated-but-unused)* | `first_life` |

An unknown value raises `ValueError` when the settings are built, so a typo can't select a
different rule.

!!! tip "See it run"

    [`examples/coproduction.ipynb`](https://github.com/TimoDiepers/trailrunner/blob/main/examples/coproduction.ipynb)
    puts a co-producing CHP behind the tour's cement demand and runs it under `none`,
    `economic` and `substitution`: the refusal, the two scores, and what each node recorded.

## Allocation

The [`Runner`](../api/runner.md) applies the rule after every `Model.apply()` call, so the
model never sees it. The functions live in
[`trailrunner.attribution`](../api/attribution.md).

| Rule | What it does |
| --- | --- |
| `none` | refuses co-production. A model returning more than one product raises `UnallocatedCoProduction`. The default. |
| `mass` | partitions technosphere and biosphere by each product's `mass` property |
| `economic` | partitions by each product's `price` property |
| `energy` | partitions by each product's `energy` property |
| `substitution` | keeps the whole burden on the demanded product and pushes each *other* product onto the queue as a **negative** demand. Whoever would otherwise make it is asked what that costs, and the answer comes back as a credit |

`mass`, `economic` and `energy` work the same way (`allocate()`): sum the named
[`Property`](../api/flow.md) over every exchange of each product, then scale technosphere
and biosphere by `demanded / total`. `substitution` (`substitute()`) changes what gets
*traversed* instead of rescaling what came back.

A model with one product has nothing to partition and gives the same answer under every
rule. Every shipped model is monofunctional and declares all five rules in `supports`. The
`Model` base class defaults to `frozenset({"none"})`, so a model says nothing about
multifunctionality until its author has decided.

### Worked example: one CHP, two numbers

A CHP makes 100 MJ of heat and 50 MJ of electricity from one batch of fuel, emitting 12 kg
of fossil CO<sub>2</sub>. The heat sells for 3 EUR and the electricity for 9 EUR, so heat is
a quarter of the revenue though two thirds of the energy. A demand asks for 100 MJ of heat.

**`economic`** partitions the batch's 12 kg by revenue: `3 / (3 + 9) = 0.25`, so heat
carries **3.0 kg**. The other 9 kg belongs to whoever demands the electricity.

**`substitution`** doesn't partition. The heat keeps all 12 kg, but the 50 MJ of
electricity is pushed onto the queue as a demand for **−50 MJ**. If a grid model at
0.1 kg CO<sub>2</sub>/MJ answers it, the credit is −5 kg, and the heat nets to **7.0 kg**.

Same model, same demand, 3.0 kg against 7.0 kg, because the two rules ask different
questions: *what share of this batch is the heat's?* against *what changes if this plant
displaces grid electricity?* `report.attribution` records which question was asked. The
runnable versions are in `tests/test_allocation.py` and `tests/test_substitution.py`.

### Who may answer a credit

A credit is a demand for what *somebody else* would have made. If the plant that made the
co-product could answer its own credit, it would produce the co-product again and credit
itself again. For the only producer of that co-product, its whole burden would cancel to
zero while the report still showed an inventory.

So the model that minted a credit is excluded from answering it, for that one hop. The
exclusion is by **instance**, not class: a `CH` plant and an `FR` plant of the same class
are different processes, and each can answer the other's credits. If nobody else makes the
co-product, the credit becomes a visible `no_model_found` cutoff, and `summary()` counts it
separately:

```text
1 unresolved (no_model_found: 1, of which 1 on a credit branch)
```

The sign matters. A missing burden *understates* impact, and a missing credit *overstates*
it, so they are counted apart. Under any rule but `substitution` nothing negative is ever
demanded and the clause never appears.

### When a model can't honour the rule

All three errors stop the run and are importable from the package root.

**`UnallocatedCoProduction`**: a model returned co-products under `none`. Since `none` is
the default, this is the refusal you are most likely to meet. Model the process
monofunctionally, or choose a rule. It is also a `ValueError`.

**`UnsupportedAttribution`**: the run's rule isn't in the model's `supports`. If
`CHP.supports = frozenset({"none", "economic"})`, a `substitution` run fails naming the
model and what it supports. Widen `supports`, but only after checking the model gives a
sound answer under that rule, or pick a rule it already supports.

**`MissingProperty`**: the co-products lack the property the rule partitions on, disagree
on its unit, sum to zero, or include a **negative** value. There is no default to fall back
on, since a made-up price would be an invisible value judgement. A negative price means
that output is a waste the process pays to get rid of: model it as a treatment demand, or
use `substitution`. A share over a negative total isn't a share: with heat at +10 EUR and
power at −8 EUR, heat's "share" would be 5.0.

## Capital: `per_output`, `per_year`, `first_life`

Because the inventory is dated, a second question comes up: a plant built in 2027 and
running until 2047 made something in 2030, so how much of its construction belongs there?
[`amortize()`](../api/attribution.md) holds all three answers in one place:

| Rule | Attributed capital | Reads as |
| --- | --- | --- |
| `per_output` | `capital × demanded / lifetime_output` | spread over everything the asset will ever make. A lean year carries only its own share |
| `per_year` | `capital / lifetime_years × demanded / annual_output` | an equal share per year of life. A lean year still carries a full year's construction |
| `first_life` | `capital × demanded / annual_output` if the demand year is the build year, else `0` | all of it lands in the year the asset was built |

`annual_output` is what the asset makes **in the demanded year**, and `lifetime_output` is
what it makes over its whole life. The first two rules agree whenever output is flat, and
diverge exactly when a year is atypical, which is why there is a choice at all.

`first_life` attributes **zero** to any year that isn't a build year. A 2030 study of kilns
built in 2026 and 2029 shows no construction at all under it. That is the rule working,
not a fleet that failed to load: only a study that spans the build years sees the spike. A
demand with no year is refused under `first_life`.

`DirectAirCapture` and `CementPlant` use this when given a [`Fleet`](parameters.md#when-many-rows-are-the-answer-fleets).
Each running plant's construction is amortized over that plant's own output under
`self.settings.attribution.capital` and demanded **in the year that plant was built**, so it
meets whatever background that year has. The rule used is recorded in the node's provenance
as `capital_rule`.

## Reuse is validated but unused

`AttributionSettings.reuse` (`first_life` or `shared`) will answer a second-life question:
does a product's initial production fall entirely on its first life, or is it shared with
what comes after reuse? It is validated and carried through to
`report.attribution_settings`, but nothing reads it yet. No model here has a second life,
and wiring a rule with no caller would mean inventing semantics nothing tests. Don't treat
it as a working feature.

## Reading `report.attribution`

`report.attribution` maps each node id to the record `allocate()` or `substitute()` left
behind. It is kept apart from `report.provenance` on purpose: provenance is what the
*model* recorded, and the model neither chose nor saw the run's rule. Single-product nodes
get an entry too, so a missing key never has to be interpreted.

```python
for node_id, record in report.attribution.items():
    print(node_id, record)
# 0 {'allocation': 'economic', 'property': 'price', 'share': 0.25, 'co_products': [...]}
# 1 {'allocation': 'economic', 'share': 1.0, 'property': None}
# under substitution: {'allocation': 'substitution', 'share': 1.0, 'substituted': [...]}
```

`report.attribution_settings` is the `AttributionSettings` the run used, and
`report.summary()` states it on one line:

```text
attribution: allocation=economic, capital=per_output
```

So the choices behind the numbers sit next to them, and a reader doesn't need to know how
the run was invoked.
