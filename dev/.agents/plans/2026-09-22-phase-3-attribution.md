# Phase 3 — Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LCA's normative choices into flags that are enforced and recorded — allocation of co-production, and attribution of a long-lived asset's construction — so that a model which cannot honour a choice says so instead of quietly doing something else.

**Architecture:** The `Runner` gains the run's `Settings` and becomes the one place allocation is applied: it validates the model's Result as it does today, then partitions it according to `settings.attribution.allocation`, writing the rule and the computed shares into the Result's provenance. `substitution` is the one rule that reaches the traversal, by pushing the co-product as a negative demand. A new `trailrunner/attribution/` package holds `amortize`, extracted from the DAC fleet model so every model amortizes identically.

**Tech Stack:** Python >= 3.11, uv, pyarrow, pytest. No new dependencies.

**Spec:** `dev/.agents/specs/2026-09-22-trailrunner-v2-design.md` §3

## Global Constraints

- Python `>= 3.11`. No new runtime dependencies in this phase.
- `AttributionSettings.allocation` defaults to `"none"`, so **every existing
  test must pass untouched**: a single-product model under `none` behaves
  exactly as it does today.
- A co-product missing the property a rule needs raises `MissingProperty`
  naming the model and the co-product. **Never a guessed default** — a
  partition over an assumed price is a fabricated value judgement.
- A model that does not declare support for the run's rule raises
  `UnsupportedAttribution`. Silently ignoring the setting is the exact failure
  theory.md §Attribution describes.
- Allocation scales the **whole** Result — technosphere and biosphere — never
  just one of them.
- All tooling runs through `uv`. Repo root is
  `/Users/timodiepers/Documents/Coding/trailrunner`.
- Work on branch `feat/phase-3-attribution`, branched from `feat/phase-2-resolution`.
- Commit after every task, ending each message with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## What this phase does *not* do

`AttributionSettings.reuse` is validated at construction (Phase 0) and carried
into the report, but **nothing consumes it**. It answers theory.md's
second-life question — whether a product's initial production falls entirely on
its first life or is shared across lives — and there is no model in this repo
with a second life to attribute. Implementing a rule with no caller would mean
inventing the semantics and testing them against nothing.

So: the flag is real, the report states it, and the first reuse model to arrive
brings its consumer with it. Do not quietly wire it into `amortize` to make the
setting look finished.

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/attribution/__init__.py` | public surface |
| `trailrunner/attribution/allocation.py` | `allocate`, `ALLOCATION_PROPERTY` |
| `trailrunner/attribution/capital.py` | `amortize` |
| `trailrunner/core/errors.py` | `MissingProperty`, `UnsupportedAttribution` |
| `trailrunner/core/model.py` | `Model.supports` |
| `trailrunner/orchestration/runner.py` | hold `Settings`, apply the rule, sign-aware validation |
| `trailrunner/orchestration/orchestrator.py` | pass `Settings` to the Runner; carry the settings into the Report |
| `trailrunner/orchestration/report.py` | `attribution`, `attribution_settings` |
| `trailrunner/models/dac.py` | use `amortize` instead of its own arithmetic |
| `tests/test_allocation.py` | the four partition rules |
| `tests/test_substitution.py` | negative demands end to end |
| `tests/test_capital.py` | the three capital rules |

---

### Task 1: Allocation in the Runner

**Files:**
- Create: `trailrunner/attribution/__init__.py`, `trailrunner/attribution/allocation.py`
- Modify: `trailrunner/core/errors.py`, `trailrunner/core/model.py`, `trailrunner/orchestration/runner.py`, `trailrunner/orchestration/orchestrator.py`
- Test: `tests/test_allocation.py` (create)

**Interfaces:**
- Consumes: `Property`, `Exchange.get_property`, `AttributionSettings` (Phase 0).
- Produces:
  `allocate(demand: Demand, result: Result, rule: str, model_name: str) -> Result`;
  `ALLOCATION_PROPERTY = {"mass": "mass", "economic": "price", "energy": "energy"}`;
  `MissingProperty`, `UnsupportedAttribution` exceptions;
  `Model.supports: frozenset[str] = frozenset({"none"})`;
  `Runner(resolver, settings: Settings | None = None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_allocation.py`:

```python
import pytest

from trailrunner.core.errors import MissingProperty, UnsupportedAttribution
from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import AttributionSettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.runner import Runner

HEAT = "https://vocab.sentier.dev/products/heat"
POWER = "https://vocab.sentier.dev/products/electricity"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

HEAT_DEMAND = Demand(flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ")


class CHP(Model):
    """Makes 100 MJ of heat and 50 MJ of electricity from 200 MJ of gas."""

    produces = [HEAT, POWER]
    supports = frozenset({"none", "mass", "economic", "energy", "substitution"})

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[
                Exchange(
                    flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ",
                    properties=(Property("energy", 100.0, "MJ"), Property("price", 3.0, "EUR"),
                                Property("mass", 0.0, "kg")),
                ),
                Exchange(
                    flow=Flow(iri=POWER, location="CH"), amount=50.0, unit="MJ",
                    properties=(Property("energy", 50.0, "MJ"), Property("price", 9.0, "EUR"),
                                Property("mass", 0.0, "kg")),
                ),
            ],
            technosphere=[Demand(flow=Flow(iri=GAS, location="CH"), amount=200.0, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0, unit="kg")],
        )


class Unwilling(CHP):
    supports = frozenset({"none"})


def runner_for(model, allocation="none"):
    return Runner(
        Glossary([model]),
        settings=Settings(attribution=AttributionSettings(allocation=allocation)),
    )


def test_none_rejects_co_production():
    with pytest.raises(ValueError, match="co-product"):
        runner_for(CHP(), "none").apply(HEAT_DEMAND)


def test_energy_allocation_splits_by_energy_content():
    result = runner_for(CHP(), "energy").apply(HEAT_DEMAND)
    # heat is 100 of 150 MJ: two thirds
    assert result.technosphere[0].amount == pytest.approx(200.0 * 2 / 3)
    assert result.biosphere[0].amount == pytest.approx(12.0 * 2 / 3)


def test_economic_allocation_splits_by_price():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    # heat is 3 of 12 EUR: one quarter
    assert result.technosphere[0].amount == pytest.approx(50.0)
    assert result.biosphere[0].amount == pytest.approx(3.0)


def test_allocation_scales_technosphere_and_biosphere_alike():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    assert result.technosphere[0].amount / 200.0 == pytest.approx(
        result.biosphere[0].amount / 12.0
    )


def test_the_allocated_result_keeps_only_the_demanded_product():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    assert [exchange.flow.iri for exchange in result.production] == [HEAT]
    assert result.production[0].amount == 100.0


def test_the_rule_and_the_share_are_recorded():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    attribution = result.provenance["attribution"]
    assert attribution["allocation"] == "economic"
    assert attribution["share"] == pytest.approx(0.25)
    assert attribution["property"] == "price"


def test_a_missing_property_names_the_model_and_the_co_product():
    class NoPrices(CHP):
        def apply(self, demand):
            result = super().apply(demand)
            result.production = [
                Exchange(flow=exchange.flow, amount=exchange.amount, unit=exchange.unit)
                for exchange in result.production
            ]
            return result

    with pytest.raises(MissingProperty, match="NoPrices"):
        runner_for(NoPrices(), "economic").apply(HEAT_DEMAND)


def test_a_model_that_does_not_support_the_rule_says_so():
    with pytest.raises(UnsupportedAttribution, match="Unwilling"):
        runner_for(Unwilling(), "economic").apply(HEAT_DEMAND)


def test_a_single_product_model_is_untouched_by_a_rule_it_ignores():
    class Boiler(Model):
        produces = [HEAT]
        supports = frozenset({"none", "economic"})

        def apply(self, demand):
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=5.0, unit="kg")],
            )

    result = runner_for(Boiler(), "economic").apply(HEAT_DEMAND)
    assert result.biosphere[0].amount == 5.0
    assert result.provenance["attribution"]["share"] == 1.0


def test_the_default_runner_still_takes_no_settings():
    """Every v1 caller constructs Runner(glossary) and must keep working."""
    class Boiler(Model):
        produces = [HEAT]

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    assert Runner(Glossary([Boiler()])).apply(HEAT_DEMAND).production[0].amount == 100.0


def test_a_zero_total_property_is_an_error_not_a_division():
    class Massless(CHP):
        supports = frozenset({"none", "mass"})

    with pytest.raises(MissingProperty, match="mass"):
        runner_for(Massless(), "mass").apply(HEAT_DEMAND)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_allocation.py -v`
Expected: FAIL — `ImportError: cannot import name 'MissingProperty'`.

- [ ] **Step 3: Add the errors and the model declaration**

Append to `trailrunner/core/errors.py`:

```python
class MissingProperty(TrailrunnerError):
    """A co-product lacks the property the run's allocation rule partitions on.

    Raised rather than defaulted: a partition over an assumed price is a
    fabricated value judgement, and it would be invisible in the result.
    """


class UnsupportedAttribution(TrailrunnerError):
    """A model cannot honour the run's attribution setting.

    A model may legitimately limit how far a user setting reaches. Saying so is
    the whole point — a model that silently ignored the setting would produce a
    number answering a different question than the one asked.
    """
```

Add to `trailrunner/core/model.py`, in the class body beside `produces`:

```python
    supports: frozenset[str] = frozenset({"none"})
    """Allocation rules this model can honour.

    The default is the conservative one: a model says nothing about
    multifunctionality until its author has thought about it. A run asking for
    a rule that is not here raises ``UnsupportedAttribution`` rather than
    quietly answering a different question.
    """
```

Document `supports` in `Model.apply`'s docstring contract list as well.

- [ ] **Step 4: Implement allocation**

Create `trailrunner/attribution/allocation.py`:

```python
"""Partitioning a multifunctional Result.

The rule is the run's, not the model's, and it is applied here rather than
inside each model so that every model partitions identically and so the choice
is recorded in one place. A model that cannot honour the rule refuses; it never
silently answers a different question.
"""

from dataclasses import replace

from trailrunner.core.errors import MissingProperty
from trailrunner.core.flow import Demand, Exchange
from trailrunner.core.result import Result

ALLOCATION_PROPERTY = {"mass": "mass", "economic": "price", "energy": "energy"}
"""Which property each rule partitions on. ``economic`` reads ``price``: the
rule is named for the question and the property for the number."""


def allocate(demand: Demand, result: Result, rule: str, model_name: str) -> Result:
    """Return ``result`` partitioned to the demanded product.

    ``substitution`` is not handled here — it changes the traversal rather than
    the arithmetic, so the Runner does it. ``none`` refuses co-production
    outright: model it monofunctionally, or choose a rule.
    """
    demanded = [e for e in result.production if e.flow.iri == demand.flow.iri]
    others = [e for e in result.production if e.flow.iri != demand.flow.iri]

    if not others:
        result.provenance["attribution"] = {"allocation": rule, "share": 1.0, "property": None}
        return result

    if rule == "none":
        raise ValueError(
            f"{model_name} returned co-products "
            f"({', '.join(e.flow.iri for e in others)}) but the run's allocation "
            "rule is 'none'; model it monofunctionally or choose a rule"
        )

    key = ALLOCATION_PROPERTY[rule]
    values = {}
    for exchange in result.production:
        prop = exchange.get_property(key)
        if prop is None:
            raise MissingProperty(
                f"{model_name} produced {exchange.flow.iri} without a {key!r} "
                f"property, which the {rule!r} allocation rule partitions on"
            )
        values[exchange.flow.iri] = values.get(exchange.flow.iri, 0.0) + prop.value

    total = sum(values.values())
    if total == 0:
        raise MissingProperty(
            f"{model_name}'s products all have a {key!r} of zero, so the "
            f"{rule!r} rule has nothing to partition on"
        )

    share = sum(values[e.flow.iri] for e in demanded) / total

    allocated = Result(
        production=list(demanded),
        technosphere=[replace(d, amount=d.amount * share) for d in result.technosphere],
        biosphere=[replace(e, amount=e.amount * share) for e in result.biosphere],
        provenance=dict(result.provenance),
    )
    allocated.provenance["attribution"] = {
        "allocation": rule,
        "property": key,
        "share": share,
        "co_products": [e.flow.iri for e in others],
    }
    return allocated
```

Note `values` sums per product IRI so that a model splitting one product over
several exchanges partitions on their total, matching how the Runner already
sums production when checking coverage.

Create `trailrunner/attribution/__init__.py`:

```python
"""The run's normative choices, applied and recorded."""

from trailrunner.attribution.allocation import ALLOCATION_PROPERTY, allocate

__all__ = ["ALLOCATION_PROPERTY", "allocate"]
```

- [ ] **Step 5: Wire it into the Runner**

In `trailrunner/orchestration/runner.py`:

```python
    def __init__(self, glossary: Glossary, settings: Settings | None = None) -> None:
        self.glossary = glossary
        self.settings = settings if settings is not None else Settings()
```

and in `apply`, after `self.validate(...)`:

```python
        rule = self.settings.attribution.allocation
        supports = getattr(model, "supports", frozenset({"none"}))
        if rule != "none" and rule not in supports:
            raise UnsupportedAttribution(
                f"the run's allocation rule is {rule!r} but "
                f"{type(model).__name__} supports only {sorted(supports)}"
            )
        if rule == "substitution":
            return substitute(demand, result, type(model).__name__)
        return allocate(demand, result, rule, type(model).__name__)
```

`substitute` arrives in Task 2; until then, add it to the imports as a name you
will create and let Task 1's tests avoid that branch — none of them uses
`substitution`. To keep Task 1 self-contained and green, define the branch as:

```python
        if rule == "substitution":
            raise NotImplementedError("substitution lands in Task 2 of this phase")
```

and replace it in Task 2. This is the one place in this plan where a task
deliberately ships a stub, because the alternative is a task that cannot be
tested on its own.

In `trailrunner/orchestration/orchestrator.py`, accept and forward settings:

```python
    def __init__(self, resolver, runner=None, max_depth=10, max_nodes=1000,
                 priority=None, settings: Settings | None = None) -> None:
        ...
        self.settings = settings if settings is not None else Settings()
        self.runner = runner if runner is not None else Runner(self.glossary, settings=self.settings)
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_allocation.py -v`
Expected: PASS, all eleven.

Run: `uv run pytest -q`
Expected: PASS — existing tests construct `Runner(glossary)` with no settings,
which defaults to `allocation="none"`, and none of their models co-produce.

- [ ] **Step 7: Commit**

```bash
git add trailrunner/attribution trailrunner/core/errors.py trailrunner/core/model.py trailrunner/orchestration tests/test_allocation.py
git commit -m "feat(attribution): enforce the run's allocation rule in the Runner

The rule is the run's, applied in one place so every model partitions
identically and the choice is recorded once. A co-product without the
property the rule needs raises rather than defaulting, and a model that
cannot honour the rule refuses rather than answering a different
question.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `substitution` — the avoided burden

**Files:**
- Modify: `trailrunner/attribution/allocation.py`, `trailrunner/orchestration/runner.py`
- Test: `tests/test_substitution.py` (create)

**Interfaces:**
- Consumes: `allocate` from Task 1.
- Produces: `substitute(demand: Demand, result: Result, model_name: str) -> Result`;
  sign-aware production validation in `Runner.validate`.

A negative demand traverses like any other: it is pushed onto the same FIFO
queue, answered by the same models, and its biosphere exchanges accumulate
negatively. The only thing that changes is the sign, which is why the
validation has to stop assuming production is positive.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_substitution.py`:

```python
import pytest

from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import AttributionSettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.orchestration.runner import Runner

HEAT = "https://vocab.sentier.dev/products/heat"
POWER = "https://vocab.sentier.dev/products/electricity"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

HEAT_DEMAND = Demand(flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ")


class CHP(Model):
    produces = [HEAT, POWER]
    supports = frozenset({"none", "economic", "substitution"})

    def apply(self, demand: Demand) -> Result:
        scale = abs(demand.amount) / 100.0
        return Result(
            production=[
                Exchange(flow=Flow(iri=HEAT, location="CH"), amount=100.0 * scale, unit="MJ",
                         properties=(Property("price", 3.0, "EUR"),)),
                Exchange(flow=Flow(iri=POWER, location="CH"), amount=50.0 * scale, unit="MJ",
                         properties=(Property("price", 9.0, "EUR"),)),
            ],
            biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0 * scale, unit="kg")],
        )


class Grid(Model):
    """The displaced electricity. Answers negative demands as readily as positive."""

    produces = [POWER]
    supports = frozenset({"none", "substitution"})

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            biosphere=[
                Exchange(flow=Flow(iri=CO2, location="CH"), amount=0.1 * demand.amount, unit="kg")
            ],
        )


def substituting_runner(models):
    return Runner(
        Glossary(models),
        settings=Settings(attribution=AttributionSettings(allocation="substitution")),
    )


def test_the_co_product_becomes_a_negative_demand():
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    credits = [d for d in result.technosphere if d.amount < 0]
    assert len(credits) == 1
    assert credits[0].flow.iri == POWER
    assert credits[0].amount == -50.0


def test_the_burden_is_not_scaled_down():
    """Substitution credits the avoided product; it does not partition."""
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    assert result.biosphere[0].amount == 12.0


def test_only_the_demanded_product_remains_in_production():
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    assert [e.flow.iri for e in result.production] == [HEAT]


def test_the_rule_is_recorded_with_what_was_credited():
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    attribution = result.provenance["attribution"]
    assert attribution["allocation"] == "substitution"
    assert attribution["substituted"] == [POWER]


def test_a_negative_demand_passes_validation():
    """Production must cover the demand in magnitude, with the same sign."""
    credit = Demand(flow=Flow(iri=POWER, location="CH"), amount=-50.0, unit="MJ")
    result = substituting_runner([Grid()]).apply(credit)
    assert result.production[0].amount == -50.0


def test_the_credit_traverses_and_subtracts_from_the_inventory():
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    report = Orchestrator(Glossary([CHP(), Grid()]), settings=settings).calculate(HEAT_DEMAND)
    total = sum(report.inventory.values())
    # 12 kg from the CHP, minus 5 kg credited for 50 MJ of displaced grid power
    assert total == pytest.approx(12.0 - 5.0)


def test_the_credit_node_appears_in_the_graph():
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    report = Orchestrator(Glossary([CHP(), Grid()]), settings=settings).calculate(HEAT_DEMAND)
    assert any(node.demand.amount < 0 for node in report.nodes)


def test_substitution_under_a_different_rule_does_not_create_credits():
    settings = Settings(attribution=AttributionSettings(allocation="economic"))
    report = Orchestrator(Glossary([CHP(), Grid()]), settings=settings).calculate(HEAT_DEMAND)
    assert all(node.demand.amount > 0 for node in report.nodes)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_substitution.py -v`
Expected: FAIL — `NotImplementedError: substitution lands in Task 2 of this phase`.

- [ ] **Step 3: Implement `substitute`**

Append to `trailrunner/attribution/allocation.py`:

```python
def substitute(demand: Demand, result: Result, model_name: str) -> Result:
    """Credit each co-product as an avoided burden.

    The co-product is pushed onto the queue as a **negative** demand: whoever
    would otherwise have made it is asked what that would have cost, and the
    answer is subtracted. This is the only rule that reaches the traversal
    rather than the arithmetic, which is why the Runner calls it instead of
    ``allocate``.
    """
    demanded = [e for e in result.production if e.flow.iri == demand.flow.iri]
    others = [e for e in result.production if e.flow.iri != demand.flow.iri]

    credits = [
        Demand(flow=exchange.flow, amount=-exchange.amount, unit=exchange.unit)
        for exchange in others
    ]

    substituted = Result(
        production=list(demanded),
        technosphere=[*result.technosphere, *credits],
        biosphere=list(result.biosphere),
        provenance=dict(result.provenance),
    )
    substituted.provenance["attribution"] = {
        "allocation": "substitution",
        "share": 1.0,
        "substituted": [exchange.flow.iri for exchange in others],
    }
    return substituted
```

Export it from `trailrunner/attribution/__init__.py` and replace the
`NotImplementedError` branch in `Runner.apply` with
`return substitute(demand, result, type(model).__name__)`.

- [ ] **Step 4: Make validation sign-aware**

In `Runner.validate`, replace the positivity check and the coverage check with
sign-aware versions. The production loop's check becomes:

```python
            if index < produced and exchange.amount * sign <= 0:
                raise ValidationError(
                    f"{origin} produced {exchange.amount} of {exchange.flow.iri} "
                    f"against a demand of {demand.amount}; production must have "
                    "the same sign as the demand"
                )
```

where `sign = 1.0 if demand.amount >= 0 else -1.0` is computed at the top of
`validate`, and the coverage check becomes:

```python
        total = sum(e.amount for e in matching)
        if total * sign < demand.amount * sign and not math.isclose(
            total, demand.amount, rel_tol=PRODUCTION_RELATIVE_TOLERANCE
        ):
```

with the message extended by one clause: `"(magnitudes are compared, so a
credit demand is covered by a credit of at least the same size)"`.

Update the `validate` docstring: the rule is no longer "production amounts are
positive" but "production has the same sign as the demand, and covers it in
magnitude", with a sentence saying why — a substitution credit is a negative
demand, and refusing it would make the rule unusable.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_substitution.py -v`
Expected: PASS, all eight.

Run: `uv run pytest -q`
Expected: PASS. If an existing Runner test asserts the old "non-positive
amount" wording, update that assertion to the new message — the behaviour it
guards (a model producing zero or the wrong sign is rejected) is unchanged.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/attribution trailrunner/orchestration/runner.py tests/test_substitution.py
git commit -m "feat(attribution): add substitution as a negative demand

The co-product is pushed onto the same FIFO queue with a negative
amount: whoever would otherwise have made it is asked what that would
have cost, and the answer is subtracted. Validation is now sign-aware --
production must match the demand's sign and cover its magnitude -- since
refusing negative demands would make the rule unusable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `amortize`, the DAC refactor, and `report.attribution`

**Files:**
- Create: `trailrunner/attribution/capital.py`
- Modify: `trailrunner/attribution/__init__.py`, `trailrunner/models/dac.py`, `trailrunner/orchestration/report.py`, `trailrunner/orchestration/orchestrator.py`
- Test: `tests/test_capital.py` (create), `tests/test_dac.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `AttributionSettings.capital`.
- Produces:
  `amortize(capital: float, *, rule: str, demanded_output: float, annual_output: float, lifetime_output: float, lifetime_years: int, demand_year: int, build_year: int) -> float`;
  `Report.attribution: dict[int, dict]`, `Report.attribution_settings: AttributionSettings`.

The three rules, stated as formulas so there is nothing to interpret.
`annual_output` is what the asset makes **in the demanded year**;
`lifetime_output` is what it makes over its whole life. Keeping them separate
is what gives the rules different answers:

| rule | attributed capital |
|---|---|
| `per_output` | `capital * demanded_output / lifetime_output` |
| `per_year` | `capital / lifetime_years * demanded_output / annual_output` |
| `first_life` | `capital * demanded_output / annual_output` if `demand_year == build_year`, else `0.0` |

The two coincide when output is flat — `lifetime_output == annual_output *
lifetime_years` — and that is the common case, not a bug. They diverge exactly
when a year is atypical: under `per_year` a lean year still carries a full
year's construction, under `per_output` it carries only its share of what was
made. That divergence is the reason the choice exists.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capital.py`:

```python
import pytest

from trailrunner.attribution import amortize

# A plant built in 2027, running 20 years, making a flat 1000 t/yr.
FLAT = dict(capital=2_000_000.0, annual_output=1000.0, lifetime_output=20_000.0,
            lifetime_years=20, build_year=2027, demand_year=2030)

# The same plant, in a year it only managed 500 t. Its lifetime total is
# unchanged: this is one lean year, not a smaller plant.
LEAN = dict(FLAT, annual_output=500.0)


def test_per_output_spreads_over_the_lifetime_output():
    assert amortize(rule="per_output", demanded_output=1000.0, **FLAT) == pytest.approx(100_000.0)


def test_per_output_is_linear_in_the_demand():
    half = amortize(rule="per_output", demanded_output=500.0, **FLAT)
    full = amortize(rule="per_output", demanded_output=1000.0, **FLAT)
    assert full == pytest.approx(2 * half)


def test_per_year_gives_each_year_an_equal_share():
    assert amortize(rule="per_year", demanded_output=1000.0, **FLAT) == pytest.approx(100_000.0)


def test_the_two_rules_agree_when_output_is_flat():
    assert amortize(rule="per_year", demanded_output=1000.0, **FLAT) == pytest.approx(
        amortize(rule="per_output", demanded_output=1000.0, **FLAT)
    )


def test_a_lean_year_carries_a_full_years_capital_under_per_year():
    """All 500 t made that year carry the whole annual share of 100,000."""
    assert amortize(rule="per_year", demanded_output=500.0, **LEAN) == pytest.approx(100_000.0)


def test_a_lean_year_carries_only_its_own_share_under_per_output():
    """500 t of a 20,000 t lifetime carries 1/40th of the capital."""
    assert amortize(rule="per_output", demanded_output=500.0, **LEAN) == pytest.approx(50_000.0)


def test_first_life_puts_everything_in_the_build_year():
    in_build_year = dict(FLAT, demand_year=2027)
    assert amortize(rule="first_life", demanded_output=1000.0, **in_build_year) == pytest.approx(
        2_000_000.0
    )


def test_first_life_attributes_nothing_to_later_years():
    assert amortize(rule="first_life", demanded_output=1000.0, **FLAT) == 0.0


def test_an_unknown_rule_is_rejected():
    with pytest.raises(ValueError, match="per_fortnight"):
        amortize(rule="per_fortnight", demanded_output=1000.0, **FLAT)


def test_zero_output_is_an_error_not_a_division():
    with pytest.raises(ValueError, match="output"):
        amortize(rule="per_output", demanded_output=1.0, **dict(FLAT, annual_output=0.0))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_capital.py -v`
Expected: FAIL — `ImportError: cannot import name 'amortize'`.

- [ ] **Step 3: Implement**

Create `trailrunner/attribution/capital.py`:

```python
"""How a long-lived asset's construction is attributed to what it makes.

Static LCA never has to ask: the factory and its output are the same instant.
Once the inventory knows what year things happen in, the question is
unavoidable and has no value-free answer, so it is a setting — and the three
answers live here rather than in each model, so that every model gives the
same one.
"""

CAPITAL_RULES = ("per_output", "per_year", "first_life")


def amortize(
    capital: float,
    *,
    rule: str,
    demanded_output: float,
    annual_output: float,
    lifetime_output: float,
    lifetime_years: int,
    demand_year: int,
    build_year: int,
) -> float:
    """The share of ``capital`` attributed to ``demanded_output``.

    ``per_output`` spreads it over everything the asset will ever make, so a
    lean year carries only its own share. ``per_year`` gives each year of life
    an equal share, so a lean year carries as much capital as a busy one.
    ``first_life`` puts all of it in the year the asset was built, keeping
    construction where it physically happened at the cost of a spike.

    ``annual_output`` is the demanded year's output and ``lifetime_output`` is
    the whole life's. They are separate arguments rather than one derived from
    the other because their difference is exactly what makes the first two
    rules give different answers.
    """
    if rule not in CAPITAL_RULES:
        raise ValueError(
            f"{rule!r} is not a known capital rule; allowed: {', '.join(CAPITAL_RULES)}"
        )
    if annual_output <= 0 or lifetime_output <= 0 or lifetime_years <= 0:
        raise ValueError(
            "annual_output, lifetime_output and lifetime_years must all be positive "
            f"to attribute capital; got annual_output={annual_output}, "
            f"lifetime_output={lifetime_output}, lifetime_years={lifetime_years}"
        )

    if rule == "per_output":
        return capital * demanded_output / lifetime_output
    if rule == "per_year":
        return capital / lifetime_years * demanded_output / annual_output
    return capital * demanded_output / annual_output if demand_year == build_year else 0.0
```

Export `amortize` and `CAPITAL_RULES` from `trailrunner/attribution/__init__.py`.

- [ ] **Step 4: Refactor the DAC model onto it**

In `trailrunner/models/dac.py`, replace the inline construction-amortization
arithmetic with a call to `amortize`, reading the rule from
`self.settings.attribution.capital`, and passing the fleet's figures:
`capital` from the plant row's construction amount, `annual_output` from the
plant's capacity in the demanded year, `lifetime_output` from capacity times
lifetime, `lifetime_years` from its declared lifetime, `build_year` from the
fleet row and `demand_year` from `demand.flow.time`. Record the rule
used in the Result's provenance under `capital_rule`.

Run: `uv run pytest tests/test_dac.py -v`
Expected: PASS **unchanged**. The default rule is `per_output`, which is the
formula the model already implemented; if a number moves, the extraction is
wrong, not the test.

- [ ] **Step 5: Surface attribution in the Report**

In `trailrunner/orchestration/report.py`, add:

```python
    attribution: dict[int, dict[str, Any]] = field(default_factory=dict)
    """Per node: the allocation rule applied and the shares computed."""
    attribution_settings: Any = None
    """The run's AttributionSettings, so the report states the choices that
    produced it without the reader having to know how it was called."""
```

Fill `attribution` in `from_log` from each node's
`result.provenance.get("attribution")`, and extend `from_log`'s signature with
`attribution_settings: Any = None`, passed through. In the Orchestrator, pass
`attribution_settings=self.settings.attribution` to `Report.from_log`.

Add to `Report.summary()`, after the proxies line:

```python
        if self.attribution_settings is not None:
            lines.append(
                f"attribution: allocation={self.attribution_settings.allocation}, "
                f"capital={self.attribution_settings.capital}"
            )
```

Append to `tests/test_report.py`:

```python
def test_report_collects_per_node_attribution():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            provenance={"attribution": {"allocation": "economic", "share": 0.25}},
        ),
    )
    report = Report.from_log(log)
    assert report.attribution[node_id]["share"] == 0.25


def test_summary_states_the_runs_normative_choices():
    from trailrunner.core.settings import AttributionSettings

    report = Report.from_log(Log(), attribution_settings=AttributionSettings(allocation="economic"))
    assert "allocation=economic" in report.summary()
```

- [ ] **Step 6: Run everything and document**

Run: `uv run pytest -q`
Expected: PASS.

Create `docs/content/attribution.md` covering: why these are settings and not
model behaviour; the five allocation rules with a worked CHP example showing
the same model giving different numbers under `economic` and `substitution`;
what `MissingProperty` and `UnsupportedAttribution` mean and what to do about
each; the three capital rules with the formulas above; and how to read
`report.attribution`. Add it to the `"User Guide"` nav in `zensical.toml` after
`{ Resolution = "content/resolution.md" }`, plus an `api/attribution.md` page
in the API nav.

- [ ] **Step 7: Commit**

```bash
git add trailrunner/attribution trailrunner/models/dac.py trailrunner/orchestration docs zensical.toml tests/test_capital.py tests/test_report.py
git commit -m "feat(attribution): extract amortize and report the choices made

The three capital rules move out of the DAC model into one function, so
every model attributes construction the same way, and the rule used is
recorded per node. The Report now states the run's allocation and
capital settings in its summary: the value judgements that produced the
number, in the same place as the number.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification

Phase 3 is done when:

- [ ] `uv run pytest -q` passes, with `tests/test_dac.py` unchanged and its
      numbers unmoved.
- [ ] The same CHP model under `allocation="economic"` and
      `allocation="substitution"` gives two different scores, and
      `report.attribution` explains both.
- [ ] `Runner(glossary)` with no settings behaves exactly as in v1.
- [ ] A model without `supports` declared raises `UnsupportedAttribution` under
      any rule but `none`.
- [ ] `report.summary()` names the run's allocation and capital rules.
- [ ] `reuse` is still unconsumed, and the docs say so rather than implying a
      behaviour that does not exist.
