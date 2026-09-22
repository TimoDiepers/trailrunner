# Phase 2 — Resolution Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer demands nothing models exactly — by generalising them along a hierarchy the practitioner declares, and failing that by borrowing a cumulative background dataset — with every concession recorded.

**Architecture:** `Glossary` becomes tier 1 of an ordered `ResolutionChain`. Each `Provider` answers `offer(demand) -> Offer | None`, and an `Offer` always carries a real `Model`, so the Runner and its validation are untouched. When the whole chain declines, `chain.explain(demand)` produces the reason the Log records. Tier 2 generalises time, location and product; tier 3 answers linearly from a curated pack and terminates.

**Tech Stack:** Python >= 3.11, uv, pyarrow; `pyst-client` behind the `[pyst]` extra for the product dimension; pytest. No network in any test.

**Spec:** `dev/.agents/specs/2026-09-22-trailrunner-v2-design.md` §2

## Naming: `resolution`, not `provenance`

The field an `Offer` carries is called **`resolution`**, matching
`NodeRecord.resolution`, which is where the Orchestrator stores it. It is
deliberately *not* called `provenance`: `Result.provenance` is the **model's**
record of which parameter rows and fallbacks it used, and `resolution` is the
**orchestrator's** record of how that model was chosen. One word for both
would collapse a distinction phase 0 established and this phase depends on.

That distinction is about to be tested by a coincidence: `ParameterSet`
already records a `CH -> RER` location fallback (the model widening its
*parameter* lookup, in `provenance`), and `GeneralisingProvider` will record a
`CH -> RER` relaxation (the orchestrator widening the *demand*, in
`resolution`). Same words, two different concessions, both true at once. The
report must make clear which is which — say so in the relaxation strings and
in `docs/content/resolution.md`, rather than leaving a reader to infer it.

## Global Constraints

- Python `>= 3.11`. Runtime dependency stays **pyarrow only**; `pyst-client`
  requires >= 3.12 and lives behind the `[pyst]` extra, lazily imported.
- **No test touches the network.** The PyST client is stubbed in tests, and a
  cache-hit test proves the second lookup does not call out.
- The PyST token is read from the `PYST_AUTH_TOKEN` environment variable. It is
  never written to a file in the repository, never passed as a literal, and
  never printed.
- Ambiguity *within* a tier stays an error (`AmbiguousModelMatch`). Precedence
  *across* tiers is not silent — the user declared the order.
- An `Offer` always carries a `Model`. Nothing downstream learns that a node
  came from a different tier except through `resolution`.
- `Orchestrator(glossary)` must keep working unchanged: every existing test in
  `tests/test_orchestrator.py` passes untouched.
- All tooling runs through `uv`. Repo root is
  `/Users/timodiepers/Documents/Coding/trailrunner`.
- Work on branch `feat/phase-2-resolution`, branched from `feat/phase-1-assessment`.
- Commit after every task, ending each message with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/resolution/__init__.py` | public surface |
| `trailrunner/resolution/chain.py` | `Provider` protocol, `Offer`, `ResolutionChain` |
| `trailrunner/resolution/models.py` | `ModelProvider` — tier 1 over a `Glossary` |
| `trailrunner/resolution/generalising.py` | `GeneralisingProvider`, `Taxonomy`, `StaticTaxonomy` |
| `trailrunner/resolution/pyst.py` | `PystTaxonomy` — `skos:broader` with an on-disk cache |
| `trailrunner/resolution/background.py` | `BackgroundProvider`, `BackgroundDataset` |
| `trailrunner/orchestration/orchestrator.py` | ask the chain; record the offer's resolution |
| `tests/test_resolution_chain.py` | tiers, order, explain |
| `tests/test_generalising.py` | time, location, product, budgets |
| `tests/test_pyst_taxonomy.py` | stubbed client, cache hit |
| `tests/test_background.py` | pack lookup, linear scaling, termination |

---

### Task 1: The chain, tier 1, and the Orchestrator switch

**Files:**
- Create: `trailrunner/resolution/__init__.py`, `trailrunner/resolution/chain.py`, `trailrunner/resolution/models.py`
- Modify: `trailrunner/orchestration/orchestrator.py`, `trailrunner/__init__.py`
- Test: `tests/test_resolution_chain.py` (create), `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `Glossary.resolve`, `Glossary.declared_models`, `Model`, `Demand`.
- Produces:
  `Offer(model: Model, demand: Demand, tier: str, resolution: dict[str, Any])`;
  `Provider` protocol with `offer(demand) -> Offer | None` and
  `explain(demand) -> tuple[str, str] | None`;
  `ResolutionChain(providers: Sequence[Provider])` with `.offer`, `.explain`,
  `.glossary`;
  `ModelProvider(glossary: Glossary)`.

`Offer.demand` is the demand the model is actually applied to. For tier 1 it is
the demand that came in; for tier 2 it is the **relaxed** one, so the Runner
validates production against what the model was actually asked.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolution_chain.py`:

```python
import pytest

from trailrunner.core.errors import AmbiguousModelMatch
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import Coverage
from trailrunner.resolution import ModelProvider, Offer, ResolutionChain

HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"

DEMAND = Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=10.0, unit="MJ")


class Boiler(Model):
    produces = [HEAT]

    def apply(self, demand: Demand) -> Result:
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class AlwaysOffers:
    """A stub tier that answers everything, to prove ordering."""

    def __init__(self, tier: str) -> None:
        self.tier = tier
        self.model = Boiler()

    def offer(self, demand):
        return Offer(model=self.model, demand=demand, tier=self.tier,
                     resolution={"tier": self.tier})

    def explain(self, demand):
        return None


def test_model_provider_offers_an_exact_match():
    offer = ModelProvider(Glossary([Boiler()])).offer(DEMAND)
    assert isinstance(offer.model, Boiler)
    assert offer.tier == "model"
    assert offer.demand is DEMAND


def test_model_provider_declines_what_it_does_not_produce():
    gas_demand = Demand(flow=Flow(iri=GAS), amount=1.0, unit="kg")
    assert ModelProvider(Glossary([Boiler()])).offer(gas_demand) is None


def test_model_provider_still_raises_on_ambiguity():
    class OtherBoiler(Boiler):
        pass

    with pytest.raises(AmbiguousModelMatch):
        ModelProvider(Glossary([Boiler(), OtherBoiler()])).offer(DEMAND)


def test_chain_returns_the_first_offer():
    chain = ResolutionChain([AlwaysOffers("first"), AlwaysOffers("second")])
    assert chain.offer(DEMAND).tier == "first"


def test_chain_falls_through_to_a_later_tier():
    chain = ResolutionChain([ModelProvider(Glossary()), AlwaysOffers("second")])
    assert chain.offer(DEMAND).tier == "second"


def test_chain_returns_none_when_every_tier_declines():
    assert ResolutionChain([ModelProvider(Glossary())]).offer(DEMAND) is None


def test_explain_reports_a_coverage_miss_from_tier_one():
    class Dated(Model):
        produces = [HEAT]
        coverage = Coverage(time_range=(2040, 2050))

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    chain = ResolutionChain([ModelProvider(Glossary([Dated()]))])
    reason, detail = chain.explain(DEMAND)
    assert reason == "coverage_excluded"
    assert "Dated" in detail


def test_explain_defaults_to_no_model_found():
    reason, _ = ResolutionChain([ModelProvider(Glossary())]).explain(DEMAND)
    assert reason == "no_model_found"


def test_chain_exposes_the_glossary_of_its_model_tier():
    glossary = Glossary([Boiler()])
    assert ResolutionChain([ModelProvider(glossary)]).glossary is glossary
```

Append to `tests/test_orchestrator.py`:

```python
def test_orchestrator_accepts_a_resolution_chain():
    from trailrunner.resolution import ModelProvider, ResolutionChain

    chain = ResolutionChain([ModelProvider(Glossary([OneNode()]))])
    report = Orchestrator(chain).calculate(ROOT_DEMAND)
    assert len(report.nodes) == 1


def test_node_resolution_records_the_tier_that_answered():
    report = Orchestrator(Glossary([OneNode()])).calculate(ROOT_DEMAND)
    assert report.resolutions[0]["tier"] == "model"
    assert report.proxies == {}
```

`OneNode` and `ROOT_DEMAND` are the existing single-node model and root demand
in `tests/test_orchestrator.py`. If they are named differently there, reuse the
existing names rather than adding duplicates.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_resolution_chain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.resolution'`.

- [ ] **Step 3: Implement the chain and tier 1**

Create `trailrunner/resolution/chain.py`:

```python
"""An ordered chain of ways to answer a demand.

Tier 1 is the models. Later tiers are concessions — a generalised demand, a
borrowed background dataset — and each one says so in its resolution. The
order is the practitioner's, which is why precedence across tiers is not
silent the way a hidden default would be.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from trailrunner.core.flow import Demand
from trailrunner.core.model import Model


@dataclass(frozen=True)
class Offer:
    """A tier's answer: a model, and the demand to apply it to.

    ``demand`` is not always the demand that came in. A generalising tier
    relaxes it — a different year, a wider region — and the model is applied
    to, and validated against, the relaxed one. The original is what the Log
    records, so the report shows both what was asked and what was answered.
    """

    model: Model
    demand: Demand
    tier: str
    resolution: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    def offer(self, demand: Demand) -> Offer | None:
        """Answer this demand, or decline by returning ``None``."""

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        """Why this tier declined, as ``(reason, detail)``, or ``None``.

        Called only after the whole chain has declined, and only to write an
        honest unresolved record. Stateless on purpose: a provider that
        remembered its last refusal would give a different answer depending on
        what else had been asked.
        """


class ResolutionChain:
    """Asks each provider in order; the first offer wins."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        self._providers = list(providers)

    def offer(self, demand: Demand) -> Offer | None:
        for provider in self._providers:
            offer = provider.offer(demand)
            if offer is not None:
                return offer
        return None

    def explain(self, demand: Demand) -> tuple[str, str]:
        """The most specific reason any tier can give, else no_model_found.

        Tier order is reused deliberately: tier 1 knows about coverage misses,
        which is a more useful thing to tell the reader than "generalisation
        ran out", and the reader who widens the coverage fixes both.
        """
        for provider in self._providers:
            explanation = provider.explain(demand)
            if explanation is not None:
                return explanation
        return ("no_model_found", "")

    @property
    def glossary(self):
        """The first tier-1 Glossary, for callers that need the registry itself."""
        for provider in self._providers:
            registry = getattr(provider, "glossary", None)
            if registry is not None:
                return registry
        return None
```

Create `trailrunner/resolution/models.py`:

```python
"""Tier 1: the models themselves. An exact product IRI, within coverage."""

from trailrunner.core.flow import Demand
from trailrunner.orchestration.glossary import Glossary
from trailrunner.resolution.chain import Offer


class ModelProvider:
    """A Provider over a Glossary. Semantics unchanged from v1.

    A thin wrapper rather than a rewrite: ``Glossary`` stays in
    ``orchestration``, keeps its public API, and works standalone for anyone
    who wants tier 1 alone.
    """

    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary

    def offer(self, demand: Demand) -> Offer | None:
        model = self.glossary.resolve(demand.flow)
        if model is None:
            return None
        return Offer(
            model=model,
            demand=demand,
            tier="model",
            resolution={"tier": "model", "model": type(model).__name__},
        )

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        near_misses = self.glossary.declared_models(demand.flow)
        if not near_misses:
            return None
        names = ", ".join(type(model).__name__ for model in near_misses)
        return (
            "coverage_excluded",
            f"{names} declares this product but its coverage does not cover "
            f"location={demand.flow.location!r} time={demand.flow.time!r}",
        )
```

Create `trailrunner/resolution/__init__.py`:

```python
"""How a demand finds something that can answer it."""

from trailrunner.resolution.chain import Offer, Provider, ResolutionChain
from trailrunner.resolution.models import ModelProvider

__all__ = ["ModelProvider", "Offer", "Provider", "ResolutionChain"]
```

- [ ] **Step 4: Switch the Orchestrator over**

In `trailrunner/orchestration/orchestrator.py`:

Change the constructor's first parameter to accept either, keeping the old
call shape working:

```python
    def __init__(
        self,
        resolver: Glossary | ResolutionChain,
        runner: Runner | None = None,
        max_depth: int = 10,
        max_nodes: int = 1000,
        priority: Callable[[Demand], float] | None = None,
    ) -> None:
        # A bare Glossary is still a valid argument: it is the one-tier chain,
        # and every v1 caller passes one.
        self.chain = (
            resolver
            if isinstance(resolver, ResolutionChain)
            else ResolutionChain([ModelProvider(resolver)])
        )
        self.glossary = self.chain.glossary
        self.runner = runner if runner is not None else Runner(self.glossary)
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.priority = priority
```

Replace the resolve-and-report block in `calculate` with:

```python
            offer = self.chain.offer(item.demand)
            if offer is None:
                reason, detail = self.chain.explain(item.demand)
                log.unresolved(
                    item.demand,
                    reason=reason,
                    depth=item.depth,
                    parent=item.parent,
                    detail=detail or None,
                )
                continue

            result = self.runner.apply(offer.demand, model=offer.model)
            node_id = log.write(
                item.demand,
                result,
                depth=item.depth,
                parent=item.parent,
                model=type(offer.model).__name__,
                resolution=dict(offer.resolution),
            )
```

Add the imports `from trailrunner.resolution.chain import ResolutionChain` and
`from trailrunner.resolution.models import ModelProvider`. This is the one
place `orchestration` imports `resolution`; the reverse import in
`models.py` is of `orchestration.glossary` only, so there is no cycle — but
run `uv run python -c "import trailrunner"` to be sure before continuing.

Export `ModelProvider`, `Offer` and `ResolutionChain` from
`trailrunner/__init__.py` and add them to `__all__`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, including every existing orchestrator test. The
`coverage_excluded` detail text is now produced by `ModelProvider.explain`
rather than inline in the Orchestrator; if an existing test asserts on that
wording, it must still match — the string above is copied from the current
Orchestrator verbatim.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/resolution trailrunner/orchestration/orchestrator.py trailrunner/__init__.py tests/test_resolution_chain.py tests/test_orchestrator.py
git commit -m "feat(resolution): put the Glossary behind an ordered provider chain

Each tier answers offer(demand) with an Offer carrying a real Model, so
the Runner and its validation are untouched. When every tier declines,
explain() produces the reason the Log records -- coverage_excluded still
comes from tier 1, which is the more useful thing to tell the reader.

Orchestrator(glossary) still works: a bare Glossary is the one-tier
chain.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `GeneralisingProvider` — time, location, product

**Files:**
- Create: `trailrunner/resolution/generalising.py`
- Modify: `trailrunner/resolution/__init__.py`
- Test: `tests/test_generalising.py` (create)

**Interfaces:**
- Consumes: `Offer`, `ModelProvider` from Task 1; `ProxySettings` from Phase 0;
  `LocationHierarchy`; `Coverage.time_range`.
- Produces:
  `GeneralisingProvider(inner: ModelProvider, settings: ProxySettings | None = None, hierarchy: LocationHierarchy | None = None, taxonomy: Taxonomy | None = None)`;
  `Taxonomy` protocol with `broader(iri: str) -> list[str]`;
  `StaticTaxonomy(parents: dict[str, list[str]])`.

**Relaxation is non-composing in v2.** Each dimension is tried from the
*original* demand, in the declared order. A demand needing both a wider region
and an earlier year is not answered. This is a deliberate limitation — the
composed search is a cross-product whose preference order is a second
normative choice, and inventing one silently is exactly what this module
exists to avoid. It is documented in the docstring and in the deferred list.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generalising.py`:

```python
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ProxySettings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import Coverage
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import GeneralisingProvider, ModelProvider, StaticTaxonomy

HEAT = "https://vocab.sentier.dev/products/heat"
GREEN_TRUCK = "https://vocab.sentier.dev/products/truck-green"
TRUCK = "https://vocab.sentier.dev/products/truck"

HIERARCHY = LocationHierarchy({"CH": "RER", "RER": "GLO"})


class RegionalBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(locations=frozenset({"RER"}))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class DatedBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(time_range=(2035, 2050))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class GenericTruck(Model):
    produces = [TRUCK]

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def provider(models, settings=None, taxonomy=None):
    return GeneralisingProvider(
        ModelProvider(Glossary(models)),
        settings=settings or ProxySettings(),
        hierarchy=HIERARCHY,
        taxonomy=taxonomy,
    )


def test_location_is_widened_up_the_hierarchy():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    offer = provider([RegionalBoiler()]).offer(demand)
    assert isinstance(offer.model, RegionalBoiler)
    assert offer.demand.flow.location == "RER"


def test_the_relaxation_is_recorded_in_the_offer():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    offer = provider([RegionalBoiler()]).offer(demand)
    assert offer.tier == "generalising"
    assert offer.resolution["relaxations"] == ["location: CH -> RER"]


def test_the_amount_and_unit_survive_the_relaxation():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    offer = provider([RegionalBoiler()]).offer(demand)
    assert offer.demand.amount == 10.0
    assert offer.demand.unit == "MJ"


def test_location_budget_is_respected():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    settings = ProxySettings(order=("location",), max_steps={"location": 0})
    assert provider([RegionalBoiler()], settings=settings).offer(demand) is None


def test_time_is_snapped_to_a_covered_year_within_tolerance():
    demand = Demand(flow=Flow(iri=HEAT, time=2032), amount=10.0, unit="MJ")
    offer = provider([DatedBoiler()]).offer(demand)
    assert offer.demand.flow.time == 2035
    assert offer.resolution["relaxations"] == ["time: 2032 -> 2035"]


def test_time_outside_the_tolerance_is_not_snapped():
    demand = Demand(flow=Flow(iri=HEAT, time=2020), amount=10.0, unit="MJ")
    assert provider([DatedBoiler()]).offer(demand) is None


def test_product_is_widened_through_the_taxonomy():
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit="unit")
    offer = provider([GenericTruck()], taxonomy=taxonomy).offer(demand)
    assert isinstance(offer.model, GenericTruck)
    assert offer.resolution["relaxations"] == [f"product: {GREEN_TRUCK} -> {TRUCK}"]


def test_product_relaxation_needs_a_taxonomy():
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit="unit")
    assert provider([GenericTruck()], taxonomy=None).offer(demand) is None


def test_dimensions_are_tried_in_the_declared_order():
    """Location first finds the regional boiler; time first finds the dated one."""
    demand = Demand(flow=Flow(iri=HEAT, location="CH", time=2032), amount=10.0, unit="MJ")
    location_first = provider(
        [RegionalBoiler(), DatedBoiler()],
        settings=ProxySettings(order=("location", "time")),
    ).offer(demand)
    time_first = provider(
        [RegionalBoiler(), DatedBoiler()],
        settings=ProxySettings(order=("time", "location")),
    ).offer(demand)
    assert isinstance(location_first.model, RegionalBoiler)
    assert isinstance(time_first.model, DatedBoiler)


def test_an_exact_match_is_left_to_tier_one():
    """The generalising tier never answers a demand tier 1 could have."""
    class ExactBoiler(Model):
        produces = [HEAT]

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    assert provider([ExactBoiler()]).offer(demand) is not None  # it would answer
    # but in a real chain ModelProvider is asked first and wins:
    from trailrunner.resolution import ResolutionChain
    chain = ResolutionChain([ModelProvider(Glossary([ExactBoiler()])),
                             provider([ExactBoiler()])])
    assert chain.offer(demand).tier == "model"


def test_explain_says_generalisation_was_tried():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    reason, detail = provider([]).explain(demand)
    assert reason == "generalisation_exhausted"
    assert "location" in detail


def test_explain_is_silent_when_no_budget_was_available():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    settings = ProxySettings(order=(), max_steps={})
    assert provider([], settings=settings).explain(demand) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_generalising.py -v`
Expected: FAIL — `ImportError: cannot import name 'GeneralisingProvider'`.

- [ ] **Step 3: Implement**

Create `trailrunner/resolution/generalising.py`:

```python
"""Tier 2: answer a demand nothing models exactly, by asking for less.

Which concession is acceptable, and in what order, is a modelling decision —
so the order and the budgets come from ``ProxySettings`` and every step taken
is recorded. A proxy nobody can see is indistinguishable from a wrong number.

**Relaxations do not compose.** Each dimension is tried from the original
demand, in the declared order; a demand needing both a wider region and an
earlier year is not answered. The composed search is a cross-product whose
preference order is a second normative choice, and inventing one silently is
the thing this module exists to prevent. Deferred, not forgotten.
"""

from collections.abc import Iterator
from dataclasses import replace
from typing import Protocol

from trailrunner.core.flow import Demand, Flow
from trailrunner.core.settings import ProxySettings
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution.chain import Offer
from trailrunner.resolution.models import ModelProvider


class Taxonomy(Protocol):
    def broader(self, iri: str) -> list[str]:
        """Concepts directly above ``iri``, most specific first."""


class StaticTaxonomy:
    """A hand-written parent map, for tests and for offline runs."""

    def __init__(self, parents: dict[str, list[str]]) -> None:
        self._parents = dict(parents)

    def broader(self, iri: str) -> list[str]:
        return list(self._parents.get(iri, []))


class GeneralisingProvider:
    """Relaxes a demand one dimension at a time and re-asks tier 1."""

    def __init__(
        self,
        inner: ModelProvider,
        settings: ProxySettings | None = None,
        hierarchy: LocationHierarchy | None = None,
        taxonomy: Taxonomy | None = None,
    ) -> None:
        self.inner = inner
        self.settings = settings if settings is not None else ProxySettings()
        self.hierarchy = hierarchy if hierarchy is not None else LocationHierarchy()
        self.taxonomy = taxonomy

    def offer(self, demand: Demand) -> Offer | None:
        for dimension in self.settings.order:
            budget = self.settings.steps_allowed(dimension)
            if budget <= 0:
                continue
            for step, (candidate, note) in enumerate(self._candidates(demand, dimension)):
                if step >= budget:
                    break
                inner_offer = self.inner.offer(candidate)
                if inner_offer is None:
                    continue
                return Offer(
                    model=inner_offer.model,
                    demand=candidate,
                    tier="generalising",
                    resolution={
                        "tier": "generalising",
                        "model": type(inner_offer.model).__name__,
                        "relaxations": [note],
                        "asked": demand.flow.iri,
                    },
                )
        return None

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        tried = [
            f"{dimension}({self.settings.steps_allowed(dimension)})"
            for dimension in self.settings.order
            if self.settings.steps_allowed(dimension) > 0
        ]
        if not tried:
            return None
        return (
            "generalisation_exhausted",
            f"generalisation budget spent without a match; tried {', '.join(tried)}",
        )

    def _candidates(self, demand: Demand, dimension: str) -> Iterator[tuple[Demand, str]]:
        if dimension == "location":
            yield from self._location_candidates(demand)
        elif dimension == "time":
            yield from self._time_candidates(demand)
        elif dimension == "product":
            yield from self._product_candidates(demand)

    def _location_candidates(self, demand: Demand) -> Iterator[tuple[Demand, str]]:
        original = demand.flow.location
        if original is None:
            return
        for location in self.hierarchy.chain(original)[1:]:
            flow = replace(demand.flow, location=location)
            yield replace(demand, flow=flow), f"location: {original} -> {location}"

    def _time_candidates(self, demand: Demand) -> Iterator[tuple[Demand, str]]:
        """Snap to the nearest year a declaring model covers, within tolerance.

        Asks the registry rather than guessing: the only years worth trying are
        the ones some model actually claims.
        """
        original = demand.flow.time
        if original is None:
            return
        years: list[int] = []
        for model in self.inner.glossary.declared_models(demand.flow):
            window = getattr(model.coverage, "time_range", None) if model.coverage else None
            if window is None:
                continue
            earliest, latest = window
            years.append(min(max(original, earliest), latest))
        for year in sorted(set(years), key=lambda candidate: abs(candidate - original)):
            if abs(year - original) > self.settings.time_tolerance or year == original:
                continue
            flow = replace(demand.flow, time=year)
            yield replace(demand, flow=flow), f"time: {original} -> {year}"

    def _product_candidates(self, demand: Demand) -> Iterator[tuple[Demand, str]]:
        if self.taxonomy is None:
            return
        original = demand.flow.iri
        for broader in self.taxonomy.broader(original):
            flow = replace(demand.flow, iri=broader)
            yield replace(demand, flow=flow), f"product: {original} -> {broader}"
```

`Flow` is imported for the type annotations of the helpers; if the linter
reports it unused, remove the import rather than adding a pointless annotation.

Add to `trailrunner/resolution/__init__.py`:

```python
from trailrunner.resolution.generalising import (
    GeneralisingProvider,
    StaticTaxonomy,
    Taxonomy,
)
```

and extend `__all__`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_generalising.py -v`
Expected: PASS, all fourteen.

- [ ] **Step 5: Check the unresolved reason reaches the report**

Run:
```bash
uv run python - <<'PY'
from trailrunner import Demand, Flow, Glossary, Orchestrator
from trailrunner.core.settings import ProxySettings
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import GeneralisingProvider, ModelProvider, ResolutionChain

HEAT = "https://vocab.sentier.dev/products/heat"
glossary = Glossary()
chain = ResolutionChain([
    ModelProvider(glossary),
    GeneralisingProvider(ModelProvider(glossary), ProxySettings(),
                         LocationHierarchy({"CH": "RER", "RER": "GLO"})),
])
report = Orchestrator(chain).calculate(
    Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=1.0, unit="MJ")
)
print(report.unresolved[0].reason, "|", report.unresolved[0].detail)
PY
```
Expected: `generalisation_exhausted | generalisation budget spent without a match; tried time(1), location(3), product(2)`.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/resolution tests/test_generalising.py
git commit -m "feat(resolution): generalise a demand along a declared hierarchy

Tier 2 relaxes time, location or product one step at a time and re-asks
tier 1, in the order and within the budgets ProxySettings declares. Every
step taken is recorded on the offer, because a proxy nobody can see is
indistinguishable from a wrong number.

Relaxations do not compose in v2: the composed search is a cross-product
whose preference order is a second normative choice, and inventing one
silently is what this tier exists to prevent.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `PystTaxonomy` — `skos:broader` with an offline cache

**Files:**
- Create: `trailrunner/resolution/pyst.py`
- Modify: `trailrunner/resolution/__init__.py`, `pyproject.toml`
- Test: `tests/test_pyst_taxonomy.py` (create)

**Interfaces:**
- Consumes: the `Taxonomy` protocol from Task 2.
- Produces:
  `PystTaxonomy(cache_path: str | Path, client: Any | None = None, base_url: str = "https://vocab.sentier.dev")`;
  `PystTaxonomy.broader(iri) -> list[str]`; `PystTaxonomy.save()`.

- [ ] **Step 1: Add the extra**

In `pyproject.toml`, under `[project.optional-dependencies]`:

```toml
pyst = [
  # pyst-client requires >=3.12, so the marker has to match it. The product
  # dimension of the generalising tier is the only thing that needs it; time
  # and location relax without any network at all.
  "pyst-client>=1.2; python_version >= '3.12'",
]
```

Run: `uv sync --extra dev --extra pyst`

- [ ] **Step 2: Write the failing tests**

Create `tests/test_pyst_taxonomy.py`:

```python
import json

from trailrunner.resolution import PystTaxonomy

GREEN_TRUCK = "https://vocab.sentier.dev/products/truck-green"
TRUCK = "https://vocab.sentier.dev/products/truck"
VEHICLE = "https://vocab.sentier.dev/products/road-vehicle"


class StubConcept:
    def __init__(self, broader):
        self.broader = [{"@id": iri} for iri in broader]


class StubClient:
    """Stands in for pyst_client.ConceptApi. Counts calls, so a cache hit is
    provable rather than assumed."""

    def __init__(self, concepts):
        self.concepts = concepts
        self.calls = 0

    def concept_get(self, iri):
        self.calls += 1
        return StubConcept(self.concepts.get(iri, []))


def test_broader_reads_the_concept(tmp_path):
    client = StubClient({GREEN_TRUCK: [TRUCK]})
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=client)
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK]


def test_an_unknown_concept_has_no_parents(tmp_path):
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=StubClient({}))
    assert taxonomy.broader(GREEN_TRUCK) == []


def test_several_parents_are_all_returned(tmp_path):
    client = StubClient({GREEN_TRUCK: [TRUCK, VEHICLE]})
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=client)
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK, VEHICLE]


def test_the_second_lookup_does_not_call_out(tmp_path):
    client = StubClient({GREEN_TRUCK: [TRUCK]})
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=client)
    taxonomy.broader(GREEN_TRUCK)
    taxonomy.broader(GREEN_TRUCK)
    assert client.calls == 1


def test_the_cache_is_written_and_reread_without_a_client(tmp_path):
    path = tmp_path / "cache.json"
    client = StubClient({GREEN_TRUCK: [TRUCK]})
    PystTaxonomy(path, client=client).broader(GREEN_TRUCK)

    offline = PystTaxonomy(path, client=None)
    assert offline.broader(GREEN_TRUCK) == [TRUCK]


def test_a_cache_miss_without_a_client_is_empty_not_an_error(tmp_path):
    offline = PystTaxonomy(tmp_path / "cache.json", client=None)
    assert offline.broader(VEHICLE) == []


def test_a_corrupt_cache_file_does_not_crash_the_run(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json")
    taxonomy = PystTaxonomy(path, client=StubClient({GREEN_TRUCK: [TRUCK]}))
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK]


def test_the_cache_file_is_plain_readable_json(tmp_path):
    path = tmp_path / "cache.json"
    PystTaxonomy(path, client=StubClient({GREEN_TRUCK: [TRUCK]})).broader(GREEN_TRUCK)
    assert json.loads(path.read_text())[GREEN_TRUCK] == [TRUCK]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pyst_taxonomy.py -v`
Expected: FAIL — `ImportError: cannot import name 'PystTaxonomy'`.

- [ ] **Step 4: Implement**

Create `trailrunner/resolution/pyst.py`:

```python
"""``skos:broader`` from the sentier vocabulary, cached to disk.

The cache is not an optimisation. A run that needs the network to reproduce is
a run that cannot be reproduced on a plane, in a lecture hall, or in two years'
time, and the generalisation a study took is part of its result. So every
lookup is written to a plain JSON file that can be committed beside the study.

The token comes from ``PYST_AUTH_TOKEN``. It is never written to the cache.
"""

import json
import os
from pathlib import Path
from typing import Any

PYST_TOKEN_ENV = "PYST_AUTH_TOKEN"
DEFAULT_BASE_URL = "https://vocab.sentier.dev"


def default_client(base_url: str = DEFAULT_BASE_URL) -> Any:
    """A configured ``pyst_client.ConceptApi``.

    Imported here rather than at module top so that ``trailrunner.resolution``
    imports with pyarrow alone, and so a cached run needs neither the extra
    nor the token.
    """
    try:
        from pyst_client import ApiClient, ConceptApi, Configuration
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "pyst-client is needed to look up broader concepts; install it with "
            "`uv sync --extra pyst`, or pass a pre-warmed cache and no client"
        ) from exc

    configuration = Configuration(host=base_url)
    client = ApiClient(configuration)
    token = os.environ.get(PYST_TOKEN_ENV)
    if token:
        # PyST authenticates with its own header, not a bearer token.
        client.default_headers["x-pyst-auth-token"] = token
    return ConceptApi(client)


class PystTaxonomy:
    """``Taxonomy`` backed by PyST, answering from a JSON cache first.

    A miss with no client is an empty list, not an error: an offline run
    generalises less, and says so through the report's proxies, which is a
    better failure than refusing to run at all.
    """

    def __init__(
        self,
        cache_path: str | Path,
        client: Any | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.client = client
        self.base_url = base_url
        self._cache: dict[str, list[str]] = self._load()

    def _load(self) -> dict[str, list[str]]:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            # A damaged cache is a slow run, not a failed one.
            return {}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2, sort_keys=True))

    def broader(self, iri: str) -> list[str]:
        if iri in self._cache:
            return list(self._cache[iri])
        if self.client is None:
            return []
        concept = self.client.concept_get(iri)
        parents = [
            entry.get("@id") if isinstance(entry, dict) else str(entry)
            for entry in (getattr(concept, "broader", None) or [])
        ]
        parents = [parent for parent in parents if parent]
        self._cache[iri] = parents
        self.save()
        return list(parents)
```

Add `from trailrunner.resolution.pyst import PystTaxonomy, default_client` to
`trailrunner/resolution/__init__.py` and extend `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_pyst_taxonomy.py -v`
Expected: PASS, all eight. No test constructs a real client, so none touches
the network.

- [ ] **Step 6: Warm a cache for the examples**

Create `examples/pyst_cache.json` by running, once, with a token in the
environment:

```bash
PYST_AUTH_TOKEN=<your token> uv run --extra pyst python - <<'PY'
from trailrunner.resolution import PystTaxonomy, default_client

IRIS = [
    "https://vocab.sentier.dev/products/co2-captured",
    "https://vocab.sentier.dev/products/heat",
    "https://vocab.sentier.dev/products/electricity",
    "https://vocab.sentier.dev/products/natural-gas",
]
taxonomy = PystTaxonomy("examples/pyst_cache.json", client=default_client())
for iri in IRIS:
    print(iri, "->", taxonomy.broader(iri))
taxonomy.save()
PY
```

Commit the resulting JSON. Do **not** commit the token, and do not put it in
any file — it belongs in the environment only.

- [ ] **Step 7: Commit**

```bash
git add trailrunner/resolution/pyst.py trailrunner/resolution/__init__.py tests/test_pyst_taxonomy.py pyproject.toml uv.lock examples/pyst_cache.json
git commit -m "feat(resolution): look up broader concepts in PyST, cached to disk

The cache is not an optimisation: a run that needs the network cannot be
reproduced on a plane or in two years, and the generalisation a study
took is part of its result. Plain JSON, committable beside the study.

A cache miss with no client generalises less and says so through the
report's proxies, rather than refusing to run.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `BackgroundProvider` — borrow a cumulative dataset

**Files:**
- Create: `trailrunner/resolution/background.py`, `examples/background_pack.parquet` (generated)
- Create: `dev/build_background_pack.py`
- Modify: `trailrunner/resolution/__init__.py`
- Test: `tests/test_background.py` (create)

**Interfaces:**
- Consumes: `Offer`, `Model`, `LocationHierarchy`.
- Produces:
  `BackgroundPack.from_parquet(path, hierarchy=None) -> BackgroundPack`;
  `BackgroundProvider(pack: BackgroundPack)`;
  `BackgroundDataset(Model)` — built per demand, produces the demanded flow and
  emits the pack's biosphere exchanges scaled by the demanded amount.

Pack parquet columns: `product_iri` (string), `product_unit` (string),
`location` (string), `dataset` (string), `flow_iri` (string),
`flow_unit` (string), `amount` (double — **per unit of product**).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_background.py`:

```python
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from trailrunner.core.flow import Demand, Flow
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import BackgroundPack, BackgroundProvider

GAS = "https://vocab.sentier.dev/products/natural-gas"
STEEL = "https://vocab.sentier.dev/products/steel"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"
CH4 = "https://vocab.sentier.dev/flows/ch4-fossil"


@pytest.fixture
def pack_file(tmp_path):
    path = tmp_path / "pack.parquet"
    rows = [
        {"product_iri": GAS, "product_unit": "kg", "location": "GLO",
         "dataset": "natural gas, at consumer", "flow_iri": CO2, "flow_unit": "kg", "amount": 0.4},
        {"product_iri": GAS, "product_unit": "kg", "location": "GLO",
         "dataset": "natural gas, at consumer", "flow_iri": CH4, "flow_unit": "kg", "amount": 0.01},
        {"product_iri": STEEL, "product_unit": "kg", "location": "RER",
         "dataset": "steel, low-alloyed", "flow_iri": CO2, "flow_unit": "kg", "amount": 1.9},
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def provider(path, hierarchy=None):
    return BackgroundProvider(BackgroundPack.from_parquet(path, hierarchy=hierarchy))


def test_a_pack_row_answers_the_demand(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.tier == "background"


def test_biosphere_scales_linearly_with_the_demand(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    result = offer.model.apply(demand)
    amounts = {exchange.flow.iri: exchange.amount for exchange in result.biosphere}
    assert amounts[CO2] == pytest.approx(4.0)
    assert amounts[CH4] == pytest.approx(0.1)


def test_the_result_produces_the_demanded_flow_and_terminates(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    result = provider(pack_file).offer(demand).model.apply(demand)
    assert result.production[0].flow == demand.flow
    assert result.production[0].amount == 10.0
    assert result.technosphere == []


def test_the_borrowed_subtree_says_it_is_matrix_lca(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.resolution["tier"] == "background"
    assert offer.resolution["kind"] == "linear_background"
    assert offer.resolution["dataset"] == "natural gas, at consumer"


def test_the_biosphere_flows_carry_the_demands_time(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO", time=2030), amount=1.0, unit="kg")
    result = provider(pack_file).offer(demand).model.apply(demand)
    assert all(exchange.flow.time == 2030 for exchange in result.biosphere)


def test_location_falls_back_up_the_hierarchy(pack_file):
    demand = Demand(flow=Flow(iri=STEEL, location="CH"), amount=1.0, unit="kg")
    offer = provider(pack_file, LocationHierarchy({"CH": "RER", "RER": "GLO"})).offer(demand)
    assert offer.resolution["location_used"] == "RER"


def test_a_product_not_in_the_pack_is_declined(pack_file):
    demand = Demand(flow=Flow(iri="https://vocab.sentier.dev/products/unobtainium"),
                    amount=1.0, unit="kg")
    assert provider(pack_file).offer(demand) is None


def test_a_different_unit_is_declined(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="tonne")
    assert provider(pack_file).offer(demand) is None


def test_the_background_tier_never_explains(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    assert provider(pack_file).explain(demand) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_background.py -v`
Expected: FAIL — `ImportError: cannot import name 'BackgroundPack'`.

- [ ] **Step 3: Implement**

Create `trailrunner/resolution/background.py`:

```python
"""Tier 3: borrow a cumulative dataset, and say so.

The last resort is a row of coefficients — exactly the thing trailrunner
exists to avoid — so it is labelled ``linear_background`` in the resolution of
every node it answers. A reader can then see precisely where the modelled
foreground stops and the borrowed matrix starts, which is a more honest
picture than either a cutoff or a seamless number.

The datasets are cumulative: their biosphere exchanges are the whole upstream,
per unit of product, so a background node has no technosphere children and the
traversal terminates there. That is also what a Brightway-backed provider would
return from ``lca.inventory``, so nothing above this tier changes when one
arrives.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution.chain import Offer


@dataclass(frozen=True)
class BackgroundEntry:
    """One borrowed dataset: what it makes, and what it emits per unit."""

    product_iri: str
    product_unit: str
    location: str | None
    dataset: str
    exchanges: tuple[tuple[str, str, float], ...]
    """(flow IRI, unit, amount per unit of product)."""


class BackgroundPack:
    """Cumulative datasets, indexed by (product IRI, unit, location)."""

    def __init__(
        self,
        entries: Sequence[BackgroundEntry],
        hierarchy: LocationHierarchy | None = None,
        source: str | None = None,
    ) -> None:
        self.source = source
        self._hierarchy = hierarchy if hierarchy is not None else LocationHierarchy()
        self._entries = {
            (entry.product_iri, entry.product_unit, entry.location): entry for entry in entries
        }

    @classmethod
    def from_parquet(
        cls, path: str | Path, hierarchy: LocationHierarchy | None = None
    ) -> "BackgroundPack":
        grouped: dict[tuple[str, str, str | None, str], list[tuple[str, str, float]]] = {}
        for row in pq.read_table(path).to_pylist():
            key = (row["product_iri"], row["product_unit"], row.get("location"), row["dataset"])
            grouped.setdefault(key, []).append(
                (row["flow_iri"], row["flow_unit"], float(row["amount"]))
            )
        entries = [
            BackgroundEntry(
                product_iri=product_iri,
                product_unit=product_unit,
                location=location,
                dataset=dataset,
                exchanges=tuple(exchanges),
            )
            for (product_iri, product_unit, location, dataset), exchanges in grouped.items()
        ]
        return cls(entries, hierarchy=hierarchy, source=str(path))

    def lookup(self, demand: Demand) -> tuple[BackgroundEntry, str | None, bool] | None:
        """The entry for this demand, the location used, and whether it fell back."""
        chain = list(self._hierarchy.chain(demand.flow.location))
        if self._hierarchy.root not in chain:
            chain.append(self._hierarchy.root)
        for index, location in enumerate(chain):
            entry = self._entries.get((demand.flow.iri, demand.unit, location))
            if entry is not None:
                return entry, location, index > 0
        return None


class BackgroundDataset(Model):
    """A cumulative dataset as a Model, so the Runner validates it like any other."""

    supports = frozenset({"none"})

    def __init__(self, entry: BackgroundEntry) -> None:
        super().__init__()
        self.entry = entry
        self.produces = [entry.product_iri]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[],
            biosphere=[
                Exchange(
                    flow=replace(Flow(iri=iri), location=demand.flow.location, time=demand.flow.time),
                    amount=amount * demand.amount,
                    unit=unit,
                )
                for iri, unit, amount in self.entry.exchanges
            ],
            resolution={"background_dataset": self.entry.dataset, "kind": "linear_background"},
        )


class BackgroundProvider:
    """Tier 3. Answers linearly, terminates, and labels itself."""

    def __init__(self, pack: BackgroundPack) -> None:
        self.pack = pack

    def offer(self, demand: Demand) -> Offer | None:
        found = self.pack.lookup(demand)
        if found is None:
            return None
        entry, location, fell_back = found
        return Offer(
            model=BackgroundDataset(entry),
            demand=demand,
            tier="background",
            resolution={
                "tier": "background",
                "kind": "linear_background",
                "dataset": entry.dataset,
                "location_used": location,
                "location_fallback": fell_back,
            },
        )

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        """Never explains: a demand the background cannot answer is better
        described by the tiers above, which know what was actually attempted."""
        return None
```

Add `BackgroundDataset`, `BackgroundEntry`, `BackgroundPack` and
`BackgroundProvider` to `trailrunner/resolution/__init__.py` and `__all__`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_background.py -v`
Expected: PASS, all nine.

- [ ] **Step 5: Build the curated pack**

Create `dev/build_background_pack.py`: a script with the ~20 datasets the
showcase chain actually hits, written as a literal list of rows and saved to
`examples/background_pack.parquet`. Cover at minimum: grid electricity for CH
and RER, natural gas at consumer, hard coal, steel low-alloyed, concrete,
cement, aluminium, copper, lorry transport, rail freight transport, pipeline
transport, and heat from a gas boiler. Each row carries CO2 fossil, CH4 fossil
and N2O amounts per unit, so a GWP method characterizes them all.

Every number in that file must carry a comment naming where it came from.
An uncited figure in a background pack is worse than a cutoff, because it
looks like data.

Run: `uv run python dev/build_background_pack.py`
Expected: writes `examples/background_pack.parquet`; print the row count.

Verify it loads:
```bash
uv run python -c "
from trailrunner.resolution import BackgroundPack
pack = BackgroundPack.from_parquet('examples/background_pack.parquet')
print('loaded')
"
```

- [ ] **Step 6: One parquet row per relaxation**

`Log.to_parquet` stringifies each resolution value, so a `relaxations` list
lands as one row holding `"['location: CH -> RER']"` — a Python repr a reader
has to parse. With one relaxation that is ugly; in this phase, where a node can
carry several, it is unusable.

Write `kind="resolution"` rows one per relaxation instead, keyed
`relaxation.0`, `relaxation.1`, … while non-list values keep their single row.
Add a test asserting that a node with two relaxations produces two rows and
that neither value contains a bracket.

- [ ] **Step 7: Document and commit**

Create `docs/content/resolution.md` covering: the tier order and why it is the
practitioner's to declare; the three relaxation dimensions with a worked
example of each; why relaxations do not compose; the PyST cache and offline
runs; the background pack's format and what `linear_background` in a node's
resolution means; and how to read `report.proxies`.

Add `{ Resolution = "content/resolution.md" }` to the `"User Guide"` nav in
`zensical.toml` after `{ Parameters = "content/parameters.md" }`, and an
`api/resolution.md` page following `docs/api/glossary.md`'s pattern with
`mkdocstrings` directives for the four resolution modules; add it to the API
nav after `{ Glossary = "api/glossary.md" }`.

Run: `uv run pytest -q && uv sync --extra docs && uv run zensical build`
Expected: both pass.

```bash
git add trailrunner/resolution dev/build_background_pack.py examples/background_pack.parquet docs zensical.toml tests/test_background.py
git commit -m "feat(resolution): add the background tier

Cumulative datasets from a curated parquet pack, answering linearly and
terminating. Every node they answer is labelled linear_background, so a
reader sees exactly where the modelled foreground stops and the borrowed
matrix starts.

This is the shape a Brightway-backed provider would take -- lca.inventory
returns the same cumulative per-unit exchanges -- so nothing above this
tier changes when one arrives.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification

Phase 2 is done when:

- [ ] `uv run pytest -q` passes, including every pre-existing orchestrator test
      unmodified.
- [ ] `Orchestrator(Glossary([...]))` still works with no chain in sight.
- [ ] A DAC run with all three tiers registered produces fewer unresolved
      leaves than the same run with tier 1 alone, and `report.proxies` names
      every node that made up the difference.
- [ ] No test makes a network call: `grep -rn "default_client" tests/` returns
      nothing.
- [ ] `PYST_AUTH_TOKEN` appears in no committed file:
      `git grep -n "ns_" -- . ':!uv.lock'` returns nothing.
