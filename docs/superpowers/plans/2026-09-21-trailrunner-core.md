# trailrunner Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `trailrunner`: Python models of technologies that consume trailpack parquet parameters and return products, demands and elementary flows, plus an orchestrator that traverses the resulting supply chain and reports an aggregated inventory.

**Architecture:** A `Glossary` maps product IRIs to `Model` instances. The `Orchestrator` pops a demand off a `Queue`, asks the `Glossary` who makes it, has the `Runner` call `model.apply(demand)` and validate the `Result`, writes the result to an append-only `Log`, and pushes the result's technosphere demands back onto the queue. Demands with no model become recorded cutoff leaves. The `Report` is built by reading the graph back out of the `Log`.

**Tech Stack:** Python >= 3.11, uv, pyarrow (only runtime dependency), pytest, dataclasses. No pydantic, no Brightway, no pandas.

**Spec:** `docs/superpowers/specs/2026-09-21-trailrunner-design.md`

## Global Constraints

- Python `>= 3.11`. Use `X | None` unions, not `Optional[X]`.
- Runtime dependency: `pyarrow` only. `trailrunner` never imports `trailpack`
  and the test suite does not need it installed: fixtures write the
  trailpack-compatible parquet metadata directly with pyarrow (Task 5 shows
  the exact layout, taken from `trailpack/packing/packing.py`).
- All tooling runs through `uv`: `uv run pytest`, `uv add`, `uv sync`. Never
  `pip`, never `conda`.
- Standard library `dataclasses` for all data types. No pydantic.
- Every value that crosses a component boundary carries an explicit unit
  string. Unit compatibility in v1 is **string equality** — no conversion.
- Repo root is `/Users/timodiepers/Documents/Coding/trailrunner`. Paths below
  are relative to it.
- Commit after every task. **Commit messages must carry no Claude attribution
  trailers** — no `Co-Authored-By: Claude`, no `Generated with Claude Code`.
- Work directly on `main`. This is a new repo with no shared history.

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/core/flow.py` | `Flow`, `Exchange`, `Demand` — identity and quantity |
| `trailrunner/core/result.py` | `Result` — what a model run returned |
| `trailrunner/core/settings.py` | `Settings` — run-wide knobs |
| `trailrunner/core/model.py` | `Model` base class |
| `trailrunner/core/errors.py` | Exception hierarchy |
| `trailrunner/params/coverage.py` | `Coverage` — a model's location/time validity |
| `trailrunner/params/location.py` | `LocationHierarchy` — `CH -> RER -> GLO` |
| `trailrunner/params/parameter_set.py` | `ParameterSet`, `ParameterRow` — parquet params with fallback + provenance |
| `trailrunner/orchestration/glossary.py` | product IRI -> `Model` |
| `trailrunner/orchestration/runner.py` | resolve, apply, validate |
| `trailrunner/orchestration/queue.py` | `QueueItem`, `Queue` |
| `trailrunner/orchestration/log.py` | append-only node/edge/unresolved records |
| `trailrunner/orchestration/orchestrator.py` | the traversal loop |
| `trailrunner/orchestration/report.py` | aggregation over the log |
| `trailrunner/models/dac.py` | `DirectAirCapture` example model |

---

### Task 1: Project scaffold and core flow types

**Files:**
- Create: `pyproject.toml`, `README.md`
- Create: `trailrunner/__init__.py`, `trailrunner/core/__init__.py`
- Create: `trailrunner/core/flow.py`, `trailrunner/core/errors.py`
- Create: `tests/__init__.py`, `tests/test_flow.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Flow(iri: str, location: str | None = None, time: int | None = None)`;
  `Exchange(flow: Flow, amount: float, unit: str)`; `Demand = Exchange`;
  exceptions `TrailrunnerError`, `NoProducer`, `AmbiguousProducer`,
  `ValidationError`, `ParameterNotFound`.

- [ ] **Step 1: Write `pyproject.toml` by hand**

Do not run `uv init`: it would create a `src/` layout, and this project uses a
flat one. Write the file, then let `uv sync` build the environment in Step 2.

```toml
[project]
name = "trailrunner"
version = "0.1.0"
description = "Model-based supply chain traversal for life cycle inventories"
readme = "README.md"
requires-python = ">=3.11"
dependencies = ["pyarrow>=15"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["trailrunner"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Build the environment**

```bash
cd /Users/timodiepers/Documents/Coding/trailrunner
uv sync --extra dev
```

Expected: a `.venv/` and a `uv.lock` appear, with pyarrow and pytest installed.

- [ ] **Step 3: Write the failing test**

Create `tests/test_flow.py`:

```python
import pytest

from trailrunner.core.flow import Demand, Exchange, Flow


def test_flow_is_hashable_and_value_equal():
    a = Flow(iri="https://vocab.sentier.dev/products/co2-captured", location="CH", time=2030)
    b = Flow(iri="https://vocab.sentier.dev/products/co2-captured", location="CH", time=2030)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_flow_location_and_time_are_optional():
    flow = Flow(iri="https://vocab.sentier.dev/products/heat")
    assert flow.location is None
    assert flow.time is None


def test_flow_is_usable_as_an_aggregation_key():
    flow = Flow(iri="co2", location="CH", time=2030)
    totals: dict[Flow, float] = {}
    totals[flow] = totals.get(flow, 0.0) + 2.0
    totals[Flow(iri="co2", location="CH", time=2030)] = totals.get(flow, 0.0) + 3.0
    assert totals == {flow: 5.0}


def test_exchange_carries_amount_and_unit():
    exchange = Exchange(flow=Flow(iri="heat"), amount=5.4, unit="MJ")
    assert exchange.amount == 5.4
    assert exchange.unit == "MJ"


def test_exchange_is_immutable():
    exchange = Exchange(flow=Flow(iri="heat"), amount=5.4, unit="MJ")
    with pytest.raises(Exception):
        exchange.amount = 9.0


def test_demand_is_an_alias_for_exchange():
    assert Demand is Exchange
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_flow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.core'`

- [ ] **Step 5: Write `trailrunner/core/flow.py`**

```python
"""Identity and quantity: the two things every exchange in trailrunner is made of."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Flow:
    """Identity of a thing: what it is, where it is, when it is.

    Carries no amount and no unit so that it stays hashable and can be used
    directly as an aggregation key.
    """

    iri: str
    location: str | None = None
    time: int | None = None


@dataclass(frozen=True)
class Exchange:
    """A quantified flow. The unit lives here, not on the Flow."""

    flow: Flow
    amount: float
    unit: str


Demand = Exchange
"""A technosphere Exchange that someone must satisfy.

An alias rather than a subclass so the two cannot drift apart.
"""
```

- [ ] **Step 6: Write `trailrunner/core/errors.py`**

```python
"""Exception hierarchy.

Unresolvable *data* becomes a recorded leaf in the Log. Unresolvable
*contracts* raise one of these.
"""


class TrailrunnerError(Exception):
    """Base class for every error trailrunner raises."""


class NoProducer(TrailrunnerError):
    """No registered model produces the requested flow."""


class AmbiguousProducer(TrailrunnerError):
    """More than one registered model produces the requested flow."""


class ValidationError(TrailrunnerError):
    """A model returned a Result that breaks the Model contract."""


class ParameterNotFound(TrailrunnerError):
    """No parameter row could be resolved for the requested location and time."""
```

- [ ] **Step 7: Create the package `__init__.py` files**

`trailrunner/__init__.py`:

```python
"""Model-based supply chain traversal for life cycle inventories."""

__version__ = "0.1.0"
```

`trailrunner/core/__init__.py` and `tests/__init__.py`: empty files.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_flow.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 9: Write `README.md`**

```markdown
# trailrunner

Model-based supply chain traversal for life cycle inventories.

A *model* is Python code for one technology. It reads its parameters from a
[trailpack](https://github.com/TimoDiepers/trailpack) parquet file and answers
one question: *given this demand, what did I produce, what do I need, and what
did I emit?* The orchestrator walks the resulting demands outward through the
supply chain and accumulates an inventory.

Design: `docs/superpowers/specs/2026-09-21-trailrunner-design.md`

## Status

Early development. Inventory only — no impact characterization yet.

## Development

```bash
uv sync --extra dev
uv run pytest
```
```

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml README.md uv.lock trailrunner tests
git commit -m "feat: project scaffold and core flow types"
```

---

### Task 2: Result, Settings, Coverage and the Model base class

**Files:**
- Create: `trailrunner/core/result.py`, `trailrunner/core/settings.py`, `trailrunner/core/model.py`
- Create: `trailrunner/params/__init__.py`, `trailrunner/params/coverage.py`
- Create: `tests/test_model.py`, `tests/test_coverage.py`

**Interfaces:**
- Consumes: `Flow`, `Exchange`, `Demand` from `trailrunner.core.flow`.
- Produces:
  - `Result(production: list[Exchange], technosphere: list[Demand] = [], biosphere: list[Exchange] = [], provenance: dict = {})`
  - `Settings(values: dict[str, Any] = {})` with `.get(key, default=None)`
  - `Coverage(locations: frozenset[str] | None = None, time_range: tuple[int, int] | None = None)` with `.covers(flow) -> bool`
  - `Model` with class attributes `produces: list[str]`, `coverage: Coverage | None`, `params`, instance attribute `settings`, and method `apply(demand: Demand) -> Result`.

- [ ] **Step 1: Write the failing test for Coverage**

Create `tests/test_coverage.py`:

```python
from trailrunner.core.flow import Flow
from trailrunner.params.coverage import Coverage


def test_empty_coverage_covers_everything():
    coverage = Coverage()
    assert coverage.covers(Flow(iri="heat"))
    assert coverage.covers(Flow(iri="heat", location="CH", time=2030))


def test_location_coverage_accepts_listed_location():
    coverage = Coverage(locations=frozenset({"CH", "DE"}))
    assert coverage.covers(Flow(iri="heat", location="CH"))


def test_location_coverage_rejects_unlisted_location():
    coverage = Coverage(locations=frozenset({"CH"}))
    assert not coverage.covers(Flow(iri="heat", location="DE"))


def test_location_coverage_rejects_missing_location():
    coverage = Coverage(locations=frozenset({"CH"}))
    assert not coverage.covers(Flow(iri="heat"))


def test_time_range_is_inclusive_on_both_ends():
    coverage = Coverage(time_range=(2020, 2050))
    assert coverage.covers(Flow(iri="heat", time=2020))
    assert coverage.covers(Flow(iri="heat", time=2050))
    assert not coverage.covers(Flow(iri="heat", time=2019))
    assert not coverage.covers(Flow(iri="heat", time=2051))


def test_time_range_rejects_missing_time():
    coverage = Coverage(time_range=(2020, 2050))
    assert not coverage.covers(Flow(iri="heat"))


def test_coverage_is_hashable():
    coverage = Coverage(locations=frozenset({"CH"}), time_range=(2020, 2050))
    assert hash(coverage) == hash(Coverage(locations=frozenset({"CH"}), time_range=(2020, 2050)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.params'`

- [ ] **Step 3: Write `trailrunner/params/coverage.py`**

Create an empty `trailrunner/params/__init__.py`, then:

```python
"""A model's declared validity in space and time."""

from dataclasses import dataclass

from trailrunner.core.flow import Flow


@dataclass(frozen=True)
class Coverage:
    """Where and when a model is valid.

    ``locations`` is a frozenset rather than a set so that Coverage stays
    hashable. ``None`` on either field means "no restriction".
    """

    locations: frozenset[str] | None = None
    time_range: tuple[int, int] | None = None

    def covers(self, flow: Flow) -> bool:
        if self.locations is not None:
            if flow.location is None or flow.location not in self.locations:
                return False
        if self.time_range is not None:
            if flow.time is None:
                return False
            earliest, latest = self.time_range
            if not earliest <= flow.time <= latest:
                return False
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_coverage.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Write the failing test for Result, Settings and Model**

Create `tests/test_model.py`:

```python
import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings

HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"
CAPTURED = "https://vocab.sentier.dev/products/co2-captured"


def test_result_defaults_to_empty_lists():
    result = Result(production=[Exchange(flow=Flow(iri=CAPTURED), amount=1.0, unit="kg")])
    assert result.technosphere == []
    assert result.biosphere == []
    assert result.provenance == {}


def test_result_default_lists_are_not_shared_between_instances():
    first = Result(production=[])
    second = Result(production=[])
    first.technosphere.append(Demand(flow=Flow(iri=HEAT), amount=1.0, unit="MJ"))
    assert second.technosphere == []


def test_settings_get_returns_default_for_missing_key():
    settings = Settings(values={"scenario": "base"})
    assert settings.get("scenario") == "base"
    assert settings.get("year") is None
    assert settings.get("year", 2030) == 2030


def test_settings_defaults_to_empty():
    assert Settings().get("anything") is None


def test_model_base_apply_raises_not_implemented():
    model = Model()
    with pytest.raises(NotImplementedError):
        model.apply(Demand(flow=Flow(iri=CAPTURED), amount=1.0, unit="kg"))


def test_model_subclass_declares_products_and_returns_a_result():
    class Trivial(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                biosphere=[Exchange(flow=Flow(iri=CO2), amount=0.1 * demand.amount, unit="kg")],
            )

    model = Trivial()
    result = model.apply(Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=10.0, unit="kg"))
    assert Trivial.produces == [CAPTURED]
    assert result.production[0].amount == 10.0
    assert result.biosphere[0].amount == pytest.approx(1.0)


def test_model_takes_settings_and_params_at_construction():
    class Trivial(Model):
        produces = [CAPTURED]

    settings = Settings(values={"scenario": "base"})
    model = Trivial(settings=settings, params="sentinel")
    assert model.settings is settings
    assert model.params == "sentinel"


def test_model_without_settings_gets_empty_settings():
    assert Model().settings.get("anything") is None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.core.result'`

- [ ] **Step 7: Write `trailrunner/core/result.py`**

```python
"""What a model run returned."""

from dataclasses import dataclass, field
from typing import Any

from trailrunner.core.flow import Demand, Exchange


@dataclass
class Result:
    """The answer to "given this demand, what happened?".

    ``production`` must cover the demand that triggered the run; the Runner
    checks this. ``technosphere`` demands are pushed onto the traversal queue.
    ``biosphere`` exchanges are accumulated into the inventory. ``provenance``
    records which parameter rows and fallbacks the model actually used.
    """

    production: list[Exchange]
    technosphere: list[Demand] = field(default_factory=list)
    biosphere: list[Exchange] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 8: Write `trailrunner/core/settings.py`**

```python
"""Run-wide knobs."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Settings:
    """One flat namespace for the whole run.

    Scenario names, a default year, model-specific switches. Anything that
    varies per technology belongs in that technology's ParameterSet instead.

    Frozen to prevent reassignment, but not hashable — ``values`` is a dict.
    """

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)
```

- [ ] **Step 9: Write `trailrunner/core/model.py`**

```python
"""The Model base class: Python code for one technology."""

from typing import Any

from trailrunner.core.flow import Demand
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings
from trailrunner.params.coverage import Coverage


class Model:
    """Base class for technology models.

    Subclasses declare which product IRIs they ``produces``, optionally
    restrict their validity with ``coverage``, and implement ``apply``.

    ``apply`` receives the *full* demand amount, never a unit demand, so that
    nonlinear behaviour is preserved: a plant at ten times the scale is not ten
    times the plant.
    """

    produces: list[str] = []
    coverage: Coverage | None = None
    params: Any = None

    def __init__(self, settings: Settings | None = None, params: Any = None) -> None:
        self.settings = settings if settings is not None else Settings()
        if params is not None:
            self.params = params

    def apply(self, demand: Demand) -> Result:
        raise NotImplementedError(
            f"{type(self).__name__} must implement apply(demand) -> Result"
        )
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS, 21 tests.

- [ ] **Step 11: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add Result, Settings, Coverage and Model base class"
```

---

### Task 3: Glossary

**Files:**
- Create: `trailrunner/orchestration/__init__.py`, `trailrunner/orchestration/glossary.py`
- Create: `tests/test_glossary.py`

**Interfaces:**
- Consumes: `Flow`, `Model`, `Coverage`, `AmbiguousProducer`.
- Produces: `Glossary(models: Iterable[Model] = ())` with
  `.register(model: Model) -> None` and `.resolve(flow: Flow) -> Model | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_glossary.py`:

```python
import pytest

from trailrunner.core.errors import AmbiguousProducer
from trailrunner.core.flow import Flow
from trailrunner.core.model import Model
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import Coverage

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"


class Capturer(Model):
    produces = [CAPTURED]


class SwissCapturer(Model):
    produces = [CAPTURED]
    coverage = Coverage(locations=frozenset({"CH"}))


class GermanCapturer(Model):
    produces = [CAPTURED]
    coverage = Coverage(locations=frozenset({"DE"}))


def test_resolve_returns_none_when_nothing_produces_the_flow():
    glossary = Glossary([Capturer()])
    assert glossary.resolve(Flow(iri=HEAT)) is None


def test_resolve_returns_the_single_producer():
    model = Capturer()
    glossary = Glossary([model])
    assert glossary.resolve(Flow(iri=CAPTURED)) is model


def test_coverage_disambiguates_two_producers_of_the_same_product():
    swiss, german = SwissCapturer(), GermanCapturer()
    glossary = Glossary([swiss, german])
    assert glossary.resolve(Flow(iri=CAPTURED, location="CH")) is swiss
    assert glossary.resolve(Flow(iri=CAPTURED, location="DE")) is german


def test_out_of_coverage_flow_has_no_producer():
    glossary = Glossary([SwissCapturer()])
    assert glossary.resolve(Flow(iri=CAPTURED, location="FR")) is None


def test_two_matching_producers_raise_and_name_the_candidates():
    glossary = Glossary([Capturer(), Capturer()])
    with pytest.raises(AmbiguousProducer) as excinfo:
        glossary.resolve(Flow(iri=CAPTURED))
    assert "Capturer" in str(excinfo.value)
    assert CAPTURED in str(excinfo.value)


def test_register_adds_a_model_after_construction():
    glossary = Glossary()
    model = Capturer()
    glossary.register(model)
    assert glossary.resolve(Flow(iri=CAPTURED)) is model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_glossary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.orchestration'`

- [ ] **Step 3: Write `trailrunner/orchestration/glossary.py`**

Create an empty `trailrunner/orchestration/__init__.py`, then:

```python
"""Who produces what."""

from collections.abc import Iterable

from trailrunner.core.errors import AmbiguousProducer
from trailrunner.core.flow import Flow
from trailrunner.core.model import Model


class Glossary:
    """Indexes model instances by the product IRIs they declare.

    Holds *instances*, not classes, because a model needs its settings and
    parameters before it can answer anything.
    """

    def __init__(self, models: Iterable[Model] = ()) -> None:
        self._models: list[Model] = list(models)

    def register(self, model: Model) -> None:
        self._models.append(model)

    def resolve(self, flow: Flow) -> Model | None:
        """Return the model that produces ``flow``.

        ``None`` means nobody does — the caller records a cutoff leaf.
        Two or more candidates is a data error, not something to resolve by
        silent precedence.
        """
        candidates = [
            model
            for model in self._models
            if flow.iri in model.produces
            and (model.coverage is None or model.coverage.covers(flow))
        ]
        if not candidates:
            return None
        if len(candidates) > 1:
            names = ", ".join(type(model).__name__ for model in candidates)
            raise AmbiguousProducer(
                f"{len(candidates)} models produce {flow.iri} "
                f"at location={flow.location!r} time={flow.time!r}: {names}"
            )
        return candidates[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_glossary.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add Glossary resolving product IRIs to models"
```

---

### Task 4: LocationHierarchy

**Files:**
- Create: `trailrunner/params/location.py`
- Create: `tests/test_location.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LocationHierarchy(parents: dict[str, str] | None = None, root: str = "GLO")`
  with `.chain(location: str | None) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_location.py`:

```python
from trailrunner.params.location import LocationHierarchy


def test_chain_walks_from_specific_to_root():
    hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
    assert hierarchy.chain("CH") == ["CH", "RER", "GLO"]


def test_chain_appends_the_root_for_unknown_locations():
    hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
    assert hierarchy.chain("NZ") == ["NZ", "GLO"]


def test_chain_of_the_root_is_just_the_root():
    hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
    assert hierarchy.chain("GLO") == ["GLO"]


def test_empty_hierarchy_falls_straight_back_to_root():
    assert LocationHierarchy().chain("CH") == ["CH", "GLO"]


def test_chain_of_none_is_none_meaning_ignore_the_location_column():
    assert LocationHierarchy().chain(None) == [None]


def test_cyclic_parents_do_not_loop_forever():
    hierarchy = LocationHierarchy({"A": "B", "B": "A"})
    assert hierarchy.chain("A") == ["A", "B", "GLO"]


def test_custom_root():
    hierarchy = LocationHierarchy({"CH": "RER"}, root="RoW")
    assert hierarchy.chain("CH") == ["CH", "RER", "RoW"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_location.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.params.location'`

- [ ] **Step 3: Write `trailrunner/params/location.py`**

```python
"""Location fallback: CH -> RER -> GLO."""


class LocationHierarchy:
    """A child-to-parent map used to widen a parameter lookup.

    ``chain`` always ends at ``root``, so every lookup has a last resort.
    """

    def __init__(self, parents: dict[str, str] | None = None, root: str = "GLO") -> None:
        self._parents = dict(parents or {})
        self._root = root

    def chain(self, location: str | None) -> list[str | None]:
        """Ordered candidates, most specific first.

        ``None`` means "no location was requested", which callers read as
        "ignore the location column entirely".
        """
        if location is None:
            return [None]
        chain: list[str | None] = []
        current: str | None = location
        while current is not None and current not in chain:
            chain.append(current)
            current = self._parents.get(current)
        if self._root not in chain:
            chain.append(self._root)
        return chain
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_location.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add LocationHierarchy for parameter fallback"
```

---

### Task 5: ParameterSet

This is the trailpack boundary: everything about reading parameters out of a
parquet file and telling the caller honestly how they were obtained.

**Files:**
- Create: `trailrunner/params/parameter_set.py`
- Create: `tests/conftest.py`, `tests/test_parameter_set.py`

**Interfaces:**
- Consumes: `LocationHierarchy`, `ParameterNotFound`.
- Produces:
  - `ParameterRow(values, units, iris, provenance)` supporting `row["col"]`, `row.col`, `row.unit_of("col")`, `row.iri_of("col")`.
  - `ParameterSet(rows, units, iris, hierarchy=None, location_column="location", time_column="time")`
  - `ParameterSet.from_parquet(path, hierarchy=None, location_column="location", time_column="time") -> ParameterSet`
  - `ParameterSet.at(location=None, time=None) -> ParameterRow`

- [ ] **Step 1: Write the fixture helper**

Create `tests/conftest.py`. This writes exactly the metadata layout trailpack
writes — Arrow schema key `b"datapackage.json"`, with per-field `unit.name`
and `rdfType` — so tests need no trailpack dependency:

```python
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

HEAT_DEMAND_IRI = "https://vocab.sentier.dev/parameters/heat-demand"
TEMPERATURE_IRI = "https://vocab.sentier.dev/parameters/air-temperature"
HUMIDITY_IRI = "https://vocab.sentier.dev/parameters/relative-humidity"


def write_parameter_parquet(path, rows, fields):
    """Write a trailpack-compatible parquet file.

    ``rows`` is a list of dicts. ``fields`` is a list of
    ``{"name", "type", "unit", "iri"}`` dicts; ``unit`` and ``iri`` may be None.
    """
    table = pa.Table.from_pylist(rows)
    datapackage = {
        "name": "test-parameters",
        "resources": [
            {
                "name": "parameters",
                "path": str(path),
                "fields": [
                    {
                        "name": field["name"],
                        "type": field["type"],
                        **({"unit": {"name": field["unit"]}} if field.get("unit") else {}),
                        **({"rdfType": field["iri"]} if field.get("iri") else {}),
                    }
                    for field in fields
                ],
            }
        ],
    }
    schema = table.schema.with_metadata(
        {"datapackage.json": json.dumps(datapackage).encode("utf-8")}
    )
    pq.write_table(table.cast(schema), path)
    return path


@pytest.fixture
def dac_parameter_file(tmp_path):
    """Two locations, two years each, so fallback and interpolation can be tested."""
    path = tmp_path / "dac_params.parquet"
    rows = [
        {"location": "CH", "time": 2020, "heat_demand": 6.0, "temperature": 9.0, "humidity": 0.75},
        {"location": "CH", "time": 2030, "heat_demand": 5.0, "temperature": 10.0, "humidity": 0.70},
        {"location": "RER", "time": 2020, "heat_demand": 6.6, "temperature": 11.0, "humidity": 0.68},
        {"location": "RER", "time": 2030, "heat_demand": 5.5, "temperature": 12.0, "humidity": 0.65},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "integer", "unit": "year", "iri": None},
        {"name": "heat_demand", "type": "number", "unit": "MJ", "iri": HEAT_DEMAND_IRI},
        {"name": "temperature", "type": "number", "unit": "degC", "iri": TEMPERATURE_IRI},
        {"name": "humidity", "type": "number", "unit": "dimensionless", "iri": HUMIDITY_IRI},
    ]
    write_parameter_parquet(path, rows, fields)
    return path
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_parameter_set.py`:

```python
import pytest

from trailrunner.core.errors import ParameterNotFound
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import HEAT_DEMAND_IRI

# FR must be in the map: chain("FR") with only {"CH": "RER"} would be
# ["FR", "GLO"] and never reach the RER rows.
HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


def test_exact_match_returns_the_row_untouched(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)
    assert row["heat_demand"] == 5.0
    assert row.temperature == 10.0
    assert row.provenance["location_used"] == "CH"
    assert row.provenance["location_fallback"] is False
    assert row.provenance["time_interpolated"] is False


def test_units_and_iris_come_from_the_embedded_datapackage(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)
    assert row.unit_of("heat_demand") == "MJ"
    assert row.iri_of("heat_demand") == HEAT_DEMAND_IRI
    assert row.unit_of("location") is None


def test_location_falls_back_up_the_hierarchy_and_says_so(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="FR", time=2030)
    assert row["heat_demand"] == 5.5
    assert row.provenance["location_requested"] == "FR"
    assert row.provenance["location_used"] == "RER"
    assert row.provenance["location_fallback"] is True


def test_time_is_interpolated_between_bracketing_rows(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2025)
    assert row["heat_demand"] == pytest.approx(5.5)
    assert row["temperature"] == pytest.approx(9.5)
    assert row.provenance["time_interpolated"] is True
    assert row.provenance["time_bracket"] == (2020, 2030)


def test_interpolated_row_keeps_non_numeric_columns_from_the_lower_row(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2025)
    assert row["location"] == "CH"


def test_time_outside_the_data_range_is_not_extrapolated(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    with pytest.raises(ParameterNotFound):
        params.at(location="CH", time=2100)


def test_unknown_location_exhausts_the_hierarchy_and_raises(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=LocationHierarchy())
    with pytest.raises(ParameterNotFound) as excinfo:
        params.at(location="NZ", time=2030)
    assert "NZ" in str(excinfo.value)


def test_omitting_location_ignores_the_location_column(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(time=2030)
    assert row["heat_demand"] == 5.0
    assert row.provenance["location_used"] is None


def test_omitting_time_returns_the_first_matching_row(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH")
    assert row["time"] == 2020
    assert row.provenance["time_interpolated"] is False


def test_unknown_column_raises_attribute_error(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)
    with pytest.raises(AttributeError):
        row.nonexistent_column
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_parameter_set.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.params.parameter_set'`

- [ ] **Step 4: Write `trailrunner/params/parameter_set.py`**

```python
"""Parameters out of a trailpack parquet file, with honest fallback."""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from trailrunner.core.errors import ParameterNotFound
from trailrunner.params.location import LocationHierarchy

DATAPACKAGE_KEY = b"datapackage.json"


@dataclass(frozen=True)
class ParameterRow:
    """One resolved set of parameter values, plus how it was obtained.

    Values are reachable as ``row["heat_demand"]`` or ``row.heat_demand``.
    """

    values: Mapping[str, Any]
    units: Mapping[str, str]
    iris: Mapping[str, str]
    provenance: Mapping[str, Any]

    def __getitem__(self, column: str) -> Any:
        return self.values[column]

    def __getattr__(self, column: str) -> Any:
        try:
            return object.__getattribute__(self, "values")[column]
        except KeyError:
            raise AttributeError(column) from None

    def unit_of(self, column: str) -> str | None:
        return self.units.get(column)

    def iri_of(self, column: str) -> str | None:
        return self.iris.get(column)


def _read_field_metadata(schema) -> tuple[dict[str, str], dict[str, str]]:
    """Pull per-column units and concept IRIs out of the embedded datapackage."""
    units: dict[str, str] = {}
    iris: dict[str, str] = {}
    raw = (schema.metadata or {}).get(DATAPACKAGE_KEY)
    if raw is None:
        return units, iris
    datapackage = json.loads(raw.decode("utf-8"))
    for resource in datapackage.get("resources", []):
        for field in resource.get("fields", []):
            name = field.get("name")
            if not name:
                continue
            unit = (field.get("unit") or {}).get("name")
            if unit:
                units[name] = unit
            iri = field.get("rdfType") or field.get("taxonomyUrl")
            if iri:
                iris[name] = iri
    return units, iris


class ParameterSet:
    """Row lookup by location and time, widening until something matches.

    Resolution order: exact ``(location, time)``; then the location hierarchy;
    then linear interpolation between bracketing years. Every widening step is
    written into the returned row's ``provenance`` so the report can state
    which parameters were actually used. Nothing is substituted silently, and
    nothing is extrapolated beyond the data.
    """

    def __init__(
        self,
        rows: Iterable[Mapping[str, Any]],
        units: Mapping[str, str] | None = None,
        iris: Mapping[str, str] | None = None,
        hierarchy: LocationHierarchy | None = None,
        location_column: str = "location",
        time_column: str = "time",
    ) -> None:
        self._rows = [dict(row) for row in rows]
        self._units = dict(units or {})
        self._iris = dict(iris or {})
        self._hierarchy = hierarchy or LocationHierarchy()
        self._location_column = location_column
        self._time_column = time_column

    @classmethod
    def from_parquet(
        cls,
        path: str | Path,
        hierarchy: LocationHierarchy | None = None,
        location_column: str = "location",
        time_column: str = "time",
    ) -> "ParameterSet":
        table = pq.read_table(path)
        units, iris = _read_field_metadata(table.schema)
        return cls(
            table.to_pylist(),
            units=units,
            iris=iris,
            hierarchy=hierarchy,
            location_column=location_column,
            time_column=time_column,
        )

    def at(self, location: str | None = None, time: int | None = None) -> ParameterRow:
        for candidate in self._hierarchy.chain(location):
            rows = self._rows_for_location(candidate)
            if not rows:
                continue
            resolved = self._row_for_time(rows, time)
            if resolved is None:
                continue
            values, time_provenance = resolved
            provenance = {
                "location_requested": location,
                "location_used": candidate,
                "location_fallback": candidate != location,
                "time_requested": time,
                **time_provenance,
            }
            return ParameterRow(values, self._units, self._iris, provenance)
        raise ParameterNotFound(
            f"no parameter row for location={location!r} time={time!r} "
            f"(tried {self._hierarchy.chain(location)})"
        )

    def _rows_for_location(self, candidate: str | None) -> list[dict[str, Any]]:
        if candidate is None:
            return list(self._rows)
        return [row for row in self._rows if row.get(self._location_column) == candidate]

    def _row_for_time(
        self, rows: list[dict[str, Any]], time: int | None
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if time is None:
            first = rows[0]
            return first, {"time_used": first.get(self._time_column), "time_interpolated": False}

        exact = [row for row in rows if row.get(self._time_column) == time]
        if exact:
            return exact[0], {"time_used": time, "time_interpolated": False}

        below = [r for r in rows if isinstance(r.get(self._time_column), Real) and r[self._time_column] < time]
        above = [r for r in rows if isinstance(r.get(self._time_column), Real) and r[self._time_column] > time]
        if not below or not above:
            return None

        lower = max(below, key=lambda r: r[self._time_column])
        upper = min(above, key=lambda r: r[self._time_column])
        return (
            self._interpolate(lower, upper, time),
            {
                "time_used": time,
                "time_interpolated": True,
                "time_bracket": (lower[self._time_column], upper[self._time_column]),
            },
        )

    def _interpolate(
        self, lower: dict[str, Any], upper: dict[str, Any], time: int
    ) -> dict[str, Any]:
        span = upper[self._time_column] - lower[self._time_column]
        fraction = (time - lower[self._time_column]) / span
        interpolated = dict(lower)
        for column, low_value in lower.items():
            if column == self._time_column:
                interpolated[column] = time
                continue
            high_value = upper.get(column)
            if isinstance(low_value, Real) and isinstance(high_value, Real):
                interpolated[column] = low_value + (high_value - low_value) * fraction
        return interpolated
```

Note on the interpolation guard: `None` is not a `Real`, so missing columns fall
through to the lower row's value. `bool`, however, **is** a `Real` — `bool`
subclasses `int`, which is registered under `numbers.Integral` ⊂ `numbers.Real`
— so it must be excluded explicitly, or a boolean column interpolates into a
meaningless float. The guard reads:

```python
if (
    isinstance(low_value, Real)
    and not isinstance(low_value, bool)
    and isinstance(high_value, Real)
    and not isinstance(high_value, bool)
):
```

Add a test that interpolates across a boolean column and asserts the result
keeps the lower row's boolean value unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_parameter_set.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 6: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add ParameterSet reading trailpack parquet with fallback provenance"
```

---

### Task 6: Runner

**Files:**
- Create: `trailrunner/orchestration/runner.py`
- Create: `tests/test_runner.py`

**Interfaces:**
- Consumes: `Glossary`, `Demand`, `Result`, `NoProducer`, `ValidationError`.
- Produces: `Runner(glossary: Glossary)` with
  `.apply(demand: Demand, model: Model | None = None) -> Result` and
  static `.validate(demand: Demand, result: Result, model: Model | None = None) -> None`
  (`model` is used only to name the offender in the error message).

  `model` is an optional argument so the Orchestrator, which already resolved
  the model to decide whether the demand is a cutoff leaf, does not pay for a
  second lookup.

- [ ] **Step 1: Write the failing test**

Create `tests/test_runner.py`:

```python
import pytest

from trailrunner.core.errors import NoProducer, ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.runner import Runner

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

DEMAND = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")


def make_runner(result: Result) -> Runner:
    class Stub(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return result

    return Runner(Glossary([Stub()]))


def good_result() -> Result:
    return Result(
        production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit="kg")],
        technosphere=[Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=5000.0, unit="MJ")],
        biosphere=[Exchange(flow=Flow(iri=CO2, location="CH", time=2030), amount=12.0, unit="kg")],
    )


def test_apply_resolves_the_model_and_returns_its_result():
    runner = make_runner(good_result())
    result = runner.apply(DEMAND)
    assert result.production[0].amount == 1000.0
    assert result.technosphere[0].unit == "MJ"


def test_apply_raises_when_nothing_produces_the_demand():
    runner = Runner(Glossary())
    with pytest.raises(NoProducer):
        runner.apply(DEMAND)


def test_apply_uses_a_model_passed_in_without_resolving():
    class Passed(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return good_result()

    runner = Runner(Glossary())
    assert runner.apply(DEMAND, model=Passed()).production[0].amount == 1000.0


def test_production_must_include_the_demanded_product():
    runner = make_runner(Result(production=[Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")]))
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert CAPTURED in str(excinfo.value)


def test_production_unit_must_match_the_demand_unit():
    runner = make_runner(
        Result(production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit="tonne")])
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert "tonne" in str(excinfo.value)


def test_production_amount_must_be_positive():
    runner = make_runner(Result(production=[Exchange(flow=DEMAND.flow, amount=0.0, unit="kg")]))
    with pytest.raises(ValidationError):
        runner.apply(DEMAND)


def test_every_exchange_must_carry_a_unit():
    runner = make_runner(
        Result(
            production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2), amount=12.0, unit="")],
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert CO2 in str(excinfo.value)


def test_a_model_returning_the_wrong_type_is_a_validation_error():
    class Broken(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand):
            return None

    runner = Runner(Glossary([Broken()]))
    with pytest.raises(ValidationError):
        runner.apply(DEMAND)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.orchestration.runner'`

- [ ] **Step 3: Write `trailrunner/orchestration/runner.py`**

```python
"""Calls a model and checks that it honoured its contract."""

from trailrunner.core.errors import NoProducer, ValidationError
from trailrunner.core.flow import Demand
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary


class Runner:
    """Synchronous. The single place where Result validation happens.

    It is a separate object so that a concurrent implementation can replace it
    behind the same interface without the Orchestrator changing.
    """

    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary

    def apply(self, demand: Demand, model: Model | None = None) -> Result:
        if model is None:
            model = self.glossary.resolve(demand.flow)
        if model is None:
            raise NoProducer(
                f"no model produces {demand.flow.iri} at "
                f"location={demand.flow.location!r} time={demand.flow.time!r}"
            )
        result = model.apply(demand)
        self.validate(demand, result, model=model)
        return result

    @staticmethod
    def validate(demand: Demand, result: Result, model: Model | None = None) -> None:
        origin = type(model).__name__ if model is not None else "model"

        if not isinstance(result, Result):
            raise ValidationError(f"{origin} returned {type(result).__name__}, expected Result")

        matching = [e for e in result.production if e.flow.iri == demand.flow.iri]
        if not matching:
            raise ValidationError(
                f"{origin} did not produce the demanded product {demand.flow.iri}; "
                f"produced {[e.flow.iri for e in result.production]}"
            )

        mismatched = [e.unit for e in matching if e.unit != demand.unit]
        if mismatched:
            raise ValidationError(
                f"{origin} produced {demand.flow.iri} in {mismatched[0]!r} "
                f"but the demand is in {demand.unit!r}"
            )

        for exchange in result.production:
            if exchange.amount <= 0:
                raise ValidationError(
                    f"{origin} produced a non-positive amount "
                    f"({exchange.amount}) of {exchange.flow.iri}"
                )

        for exchange in (*result.production, *result.technosphere, *result.biosphere):
            if not exchange.unit:
                raise ValidationError(f"{origin} returned {exchange.flow.iri} without a unit")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add Runner applying models and validating results"
```

---

### Task 7: Queue

**Files:**
- Create: `trailrunner/orchestration/queue.py`
- Create: `tests/test_queue.py`

**Interfaces:**
- Consumes: `Demand`.
- Produces:
  - `QueueItem(demand: Demand, depth: int = 0, parent: int | None = None, path: tuple[str, ...] = ())`
  - `Queue(priority: Callable[[Demand], float] | None = None)` with `.push(item)`, `.pop() -> QueueItem`, `len()`, truthiness.

  `path` is the tuple of flow IRIs already visited on the way to this item; the
  Orchestrator uses it to spot loops.

- [ ] **Step 1: Write the failing test**

Create `tests/test_queue.py`:

```python
import pytest

from trailrunner.core.flow import Demand, Flow
from trailrunner.orchestration.queue import Queue, QueueItem


def item(iri: str, amount: float = 1.0, depth: int = 0) -> QueueItem:
    return QueueItem(demand=Demand(flow=Flow(iri=iri), amount=amount, unit="kg"), depth=depth)


def test_default_queue_is_first_in_first_out():
    queue = Queue()
    queue.push(item("a"))
    queue.push(item("b"))
    queue.push(item("c"))
    assert [queue.pop().demand.flow.iri for _ in range(3)] == ["a", "b", "c"]


def test_queue_is_falsy_when_empty_and_reports_its_length():
    queue = Queue()
    assert not queue
    assert len(queue) == 0
    queue.push(item("a"))
    assert queue
    assert len(queue) == 1


def test_popping_an_empty_queue_raises():
    with pytest.raises(IndexError):
        Queue().pop()


def test_priority_callable_orders_pops_smallest_first():
    queue = Queue(priority=lambda demand: -demand.amount)
    queue.push(item("small", amount=1.0))
    queue.push(item("big", amount=100.0))
    queue.push(item("medium", amount=10.0))
    assert [queue.pop().demand.flow.iri for _ in range(3)] == ["big", "medium", "small"]


def test_priority_ties_are_broken_by_insertion_order():
    queue = Queue(priority=lambda demand: 0.0)
    queue.push(item("first"))
    queue.push(item("second"))
    assert [queue.pop().demand.flow.iri for _ in range(2)] == ["first", "second"]


def test_queue_item_carries_depth_parent_and_path():
    entry = QueueItem(
        demand=Demand(flow=Flow(iri="a"), amount=1.0, unit="kg"),
        depth=2,
        parent=7,
        path=("root", "a"),
    )
    assert (entry.depth, entry.parent, entry.path) == (2, 7, ("root", "a"))


def test_queue_item_defaults():
    entry = QueueItem(demand=Demand(flow=Flow(iri="a"), amount=1.0, unit="kg"))
    assert (entry.depth, entry.parent, entry.path) == (0, None, ())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_queue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.orchestration.queue'`

- [ ] **Step 3: Write `trailrunner/orchestration/queue.py`**

```python
"""What to traverse next."""

import heapq
import itertools
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from trailrunner.core.flow import Demand


@dataclass(frozen=True)
class QueueItem:
    """A demand waiting to be traversed, with where it came from.

    ``path`` holds the flow IRIs already visited on the way here, so the
    Orchestrator can flag a loop without maintaining separate bookkeeping.
    """

    demand: Demand
    depth: int = 0
    parent: int | None = None
    path: tuple[str, ...] = field(default=())


class Queue:
    """FIFO by default; a heap when given a priority callable.

    No priority function ships with v1: with an inventory-only result there is
    no score to rank by, and amounts in MJ, kg and kWh are not comparable. The
    seam exists so score-based ranking can drop in unchanged later.
    """

    def __init__(self, priority: Callable[[Demand], float] | None = None) -> None:
        self._priority = priority
        self._fifo: deque[QueueItem] = deque()
        self._heap: list[tuple[float, int, QueueItem]] = []
        self._counter = itertools.count()

    def push(self, item: QueueItem) -> None:
        if self._priority is None:
            self._fifo.append(item)
        else:
            heapq.heappush(
                self._heap, (self._priority(item.demand), next(self._counter), item)
            )

    def pop(self) -> QueueItem:
        if self._priority is None:
            if not self._fifo:
                raise IndexError("pop from an empty Queue")
            return self._fifo.popleft()
        if not self._heap:
            raise IndexError("pop from an empty Queue")
        return heapq.heappop(self._heap)[2]

    def __len__(self) -> int:
        return len(self._fifo) if self._priority is None else len(self._heap)

    def __bool__(self) -> bool:
        return len(self) > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_queue.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add Queue with FIFO default and pluggable priority"
```

---

### Task 8: Log

**Files:**
- Create: `trailrunner/orchestration/log.py`
- Create: `tests/test_log.py`

**Interfaces:**
- Consumes: `Demand`, `Result`, `Flow`.
- Produces:
  - `NodeRecord(id, demand, result, depth, parent)`
  - `UnresolvedRecord(demand, reason, depth, parent)`
  - `EdgeRecord(parent, child)`
  - `Log()` with `.write(demand, result, depth=0, parent=None) -> int`,
    `.unresolved(demand, reason, depth=0, parent=None) -> None`,
    `.warn(message, node=None) -> None`,
    attributes `.nodes`, `.edges`, `.unresolved_records`, `.warnings`,
    and `.to_parquet(path) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_log.py`:

```python
import pyarrow.parquet as pq

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


def a_demand(iri=CAPTURED, amount=1000.0, unit="kg") -> Demand:
    return Demand(flow=Flow(iri=iri, location="CH", time=2030), amount=amount, unit=unit)


def a_result(demand: Demand) -> Result:
    return Result(
        production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
        biosphere=[Exchange(flow=Flow(iri=CO2, location="CH", time=2030), amount=12.0, unit="kg")],
        provenance={"location_used": "RER", "location_fallback": True},
    )


def test_write_returns_increasing_node_ids():
    log = Log()
    demand = a_demand()
    assert log.write(demand, a_result(demand)) == 0
    assert log.write(demand, a_result(demand)) == 1


def test_written_node_keeps_demand_result_depth_and_parent():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand), depth=2, parent=0)
    node = log.nodes[node_id]
    assert node.demand is demand
    assert node.depth == 2
    assert node.parent == 0
    assert node.result.provenance["location_fallback"] is True


def test_write_records_an_edge_when_there_is_a_parent():
    log = Log()
    demand = a_demand()
    root = log.write(demand, a_result(demand))
    child = log.write(demand, a_result(demand), depth=1, parent=root)
    assert [(e.parent, e.child) for e in log.edges] == [(root, child)]


def test_root_node_creates_no_edge():
    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand))
    assert log.edges == []


def test_unresolved_demands_are_recorded_with_a_reason():
    log = Log()
    log.unresolved(a_demand(iri=HEAT, amount=5.0, unit="MJ"), reason="no_producer", depth=1, parent=0)
    record = log.unresolved_records[0]
    assert record.reason == "no_producer"
    assert record.demand.flow.iri == HEAT
    assert record.parent == 0


def test_warnings_are_collected():
    log = Log()
    log.warn("flow repeats on path", node=3)
    assert log.warnings == [("flow repeats on path", 3)]


def test_to_parquet_writes_one_row_per_biosphere_exchange(tmp_path):
    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand), depth=0, parent=None)
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    table = pq.read_table(path)
    assert table.num_rows == 1
    row = table.to_pylist()[0]
    assert row["node"] == 0
    assert row["flow_iri"] == CO2
    assert row["amount"] == 12.0
    assert row["unit"] == "kg"
    assert row["demand_iri"] == CAPTURED


def test_to_parquet_on_an_empty_log_writes_an_empty_table(tmp_path):
    path = tmp_path / "log.parquet"
    Log().to_parquet(path)
    assert pq.read_table(path).num_rows == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.orchestration.log'`

- [ ] **Step 3: Write `trailrunner/orchestration/log.py`**

```python
"""Append-only record of everything the traversal did."""

from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from trailrunner.core.flow import Demand
from trailrunner.core.result import Result

LOG_COLUMNS = (
    "node",
    "parent",
    "depth",
    "demand_iri",
    "demand_location",
    "demand_time",
    "demand_amount",
    "demand_unit",
    "flow_iri",
    "flow_location",
    "flow_time",
    "amount",
    "unit",
)


@dataclass
class NodeRecord:
    id: int
    demand: Demand
    result: Result
    depth: int
    parent: int | None


@dataclass
class UnresolvedRecord:
    demand: Demand
    reason: str
    depth: int
    parent: int | None


@dataclass
class EdgeRecord:
    parent: int
    child: int


@dataclass
class Log:
    """Nodes, edges, cutoff leaves and warnings, in the order they happened.

    The Report reads the graph structure back out of this.
    """

    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[EdgeRecord] = field(default_factory=list)
    unresolved_records: list[UnresolvedRecord] = field(default_factory=list)
    warnings: list[tuple[str, int | None]] = field(default_factory=list)

    def write(
        self, demand: Demand, result: Result, depth: int = 0, parent: int | None = None
    ) -> int:
        node_id = len(self.nodes)
        self.nodes.append(
            NodeRecord(id=node_id, demand=demand, result=result, depth=depth, parent=parent)
        )
        if parent is not None:
            self.edges.append(EdgeRecord(parent=parent, child=node_id))
        return node_id

    def unresolved(
        self, demand: Demand, reason: str, depth: int = 0, parent: int | None = None
    ) -> None:
        self.unresolved_records.append(
            UnresolvedRecord(demand=demand, reason=reason, depth=depth, parent=parent)
        )

    def warn(self, message: str, node: int | None = None) -> None:
        self.warnings.append((message, node))

    def to_parquet(self, path: str | Path) -> None:
        """Write one row per biosphere exchange, keyed to its node.

        Makes two runs diffable, and mirrors the parquet-in, parquet-out shape
        of the trailpack side.
        """
        rows = [
            {
                "node": node.id,
                "parent": node.parent,
                "depth": node.depth,
                "demand_iri": node.demand.flow.iri,
                "demand_location": node.demand.flow.location,
                "demand_time": node.demand.flow.time,
                "demand_amount": node.demand.amount,
                "demand_unit": node.demand.unit,
                "flow_iri": exchange.flow.iri,
                "flow_location": exchange.flow.location,
                "flow_time": exchange.flow.time,
                "amount": exchange.amount,
                "unit": exchange.unit,
            }
            for node in self.nodes
            for exchange in node.result.biosphere
        ]
        if rows:
            table = pa.Table.from_pylist(rows)
        else:
            table = pa.Table.from_pydict({column: [] for column in LOG_COLUMNS})
        pq.write_table(table, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_log.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add append-only Log with parquet export"
```

---

### Task 9: Report

**Files:**
- Create: `trailrunner/orchestration/report.py`
- Create: `tests/test_report.py`

**Interfaces:**
- Consumes: `Log`, `NodeRecord`, `UnresolvedRecord`, `Flow`.
- Produces: `Report` dataclass with fields `inventory: dict[tuple[Flow, str], float]`,
  `unresolved: list[UnresolvedRecord]`, `provenance: dict[int, dict]`,
  `nodes: list[NodeRecord]`, `edges: list[tuple[int, int]]`,
  `warnings: list[tuple[str, int | None]]`, `truncated: bool`;
  classmethod `Report.from_log(log, truncated=False) -> Report`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = Flow(iri="https://vocab.sentier.dev/flows/co2-fossil", location="CH", time=2030)
CH4 = Flow(iri="https://vocab.sentier.dev/flows/ch4-fossil", location="CH", time=2030)


def a_demand() -> Demand:
    return Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1.0, unit="kg")


def test_inventory_sums_the_same_flow_and_unit_across_nodes():
    log = Log()
    demand = a_demand()
    for amount in (12.0, 8.0):
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
                biosphere=[Exchange(flow=CO2, amount=amount, unit="kg")],
            ),
        )
    report = Report.from_log(log)
    assert report.inventory == {(CO2, "kg"): 20.0}


def test_inventory_keeps_different_flows_and_units_apart():
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[
                Exchange(flow=CO2, amount=12.0, unit="kg"),
                Exchange(flow=CH4, amount=0.3, unit="kg"),
                Exchange(flow=CO2, amount=5.0, unit="tonne"),
            ],
        ),
    )
    report = Report.from_log(log)
    assert report.inventory == {(CO2, "kg"): 12.0, (CH4, "kg"): 0.3, (CO2, "tonne"): 5.0}


def test_report_carries_unresolved_demands():
    log = Log()
    log.unresolved(
        Demand(flow=Flow(iri=HEAT), amount=5.0, unit="MJ"), reason="no_producer", depth=1
    )
    report = Report.from_log(log)
    assert len(report.unresolved) == 1
    assert report.unresolved[0].reason == "no_producer"


def test_provenance_is_keyed_by_node_id():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            provenance={"location_used": "RER", "location_fallback": True},
        ),
    )
    report = Report.from_log(log)
    assert report.provenance[node_id]["location_used"] == "RER"


def test_graph_structure_is_carried_through():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")])
    root = log.write(demand, result)
    child = log.write(demand, result, depth=1, parent=root)
    report = Report.from_log(log)
    assert [node.id for node in report.nodes] == [root, child]
    assert report.edges == [(root, child)]


def test_truncated_flag_defaults_to_false_and_is_settable():
    assert Report.from_log(Log()).truncated is False
    assert Report.from_log(Log(), truncated=True).truncated is True


def test_empty_log_gives_an_empty_report():
    report = Report.from_log(Log())
    assert report.inventory == {}
    assert report.unresolved == []
    assert report.nodes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.orchestration.report'`

- [ ] **Step 3: Write `trailrunner/orchestration/report.py`**

```python
"""What the caller gets back."""

from dataclasses import dataclass, field
from typing import Any

from trailrunner.core.flow import Flow
from trailrunner.orchestration.log import Log, NodeRecord, UnresolvedRecord


@dataclass
class Report:
    """Aggregated inventory plus everything needed to judge it.

    v1 stops at the inventory: no characterization, so no single score. The
    unresolved list and the provenance table are as much a part of the answer
    as the numbers are.
    """

    inventory: dict[tuple[Flow, str], float] = field(default_factory=dict)
    unresolved: list[UnresolvedRecord] = field(default_factory=list)
    provenance: dict[int, dict[str, Any]] = field(default_factory=dict)
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    warnings: list[tuple[str, int | None]] = field(default_factory=list)
    truncated: bool = False

    @classmethod
    def from_log(cls, log: Log, truncated: bool = False) -> "Report":
        inventory: dict[tuple[Flow, str], float] = {}
        provenance: dict[int, dict[str, Any]] = {}
        for node in log.nodes:
            if node.result.provenance:
                provenance[node.id] = dict(node.result.provenance)
            for exchange in node.result.biosphere:
                key = (exchange.flow, exchange.unit)
                inventory[key] = inventory.get(key, 0.0) + exchange.amount
        return cls(
            inventory=inventory,
            unresolved=list(log.unresolved_records),
            provenance=provenance,
            nodes=list(log.nodes),
            edges=[(edge.parent, edge.child) for edge in log.edges],
            warnings=list(log.warnings),
            truncated=truncated,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_report.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add Report aggregating inventory from the log"
```

---

### Task 10: Orchestrator

**Files:**
- Create: `trailrunner/orchestration/orchestrator.py`
- Modify: `trailrunner/__init__.py` (export the public API)
- Create: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `Glossary`, `Runner`, `Queue`, `QueueItem`, `Log`, `Report`, `Demand`.
- Produces: `Orchestrator(glossary, runner=None, max_depth=10, max_nodes=1000, priority=None)`
  with `.calculate(demand: Demand) -> Report`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator.py`:

```python
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

ROOT = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")


class Capturer(Model):
    """Needs 5 MJ of heat per kg captured; leaks 0.01 kg CO2 per kg."""

    produces = [CAPTURED]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(
                    flow=Flow(iri=HEAT, location=demand.flow.location, time=demand.flow.time),
                    amount=5.0 * demand.amount,
                    unit="MJ",
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                    amount=0.01 * demand.amount,
                    unit="kg",
                )
            ],
        )


class Boiler(Model):
    """Burns gas for heat; emits 0.06 kg CO2 per MJ."""

    produces = [HEAT]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(
                    flow=Flow(iri=GAS, location=demand.flow.location, time=demand.flow.time),
                    amount=0.02 * demand.amount,
                    unit="kg",
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                    amount=0.06 * demand.amount,
                    unit="kg",
                )
            ],
        )


def test_single_node_traversal_records_one_node_and_one_cutoff():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert len(report.nodes) == 1
    assert report.inventory == {(Flow(iri=CO2, location="CH", time=2030), "kg"): 10.0}
    assert [r.reason for r in report.unresolved] == ["no_producer"]
    assert report.unresolved[0].demand.flow.iri == HEAT


def test_two_level_traversal_accumulates_both_nodes():
    report = Orchestrator(Glossary([Capturer(), Boiler()])).calculate(ROOT)
    assert len(report.nodes) == 2
    # capture leak 10 kg + boiler 5000 MJ * 0.06 = 300 kg
    assert report.inventory[(Flow(iri=CO2, location="CH", time=2030), "kg")] == 310.0


def test_cutoff_leaf_names_the_parent_node():
    report = Orchestrator(Glossary([Capturer(), Boiler()])).calculate(ROOT)
    gas = [r for r in report.unresolved if r.demand.flow.iri == GAS][0]
    assert gas.parent == 1
    assert gas.depth == 2


def test_max_depth_truncates_and_is_reported():
    report = Orchestrator(Glossary([Capturer(), Boiler()]), max_depth=1).calculate(ROOT)
    assert len(report.nodes) == 1
    assert [r.reason for r in report.unresolved] == ["max_depth"]
    assert report.truncated is True


def test_untruncated_traversal_is_not_flagged():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert report.truncated is False


def test_max_nodes_stops_the_traversal():
    class SelfFeeder(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                technosphere=[Demand(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            )

    report = Orchestrator(Glossary([SelfFeeder()]), max_depth=100, max_nodes=5).calculate(ROOT)
    assert len(report.nodes) == 5
    assert report.truncated is True


def test_a_loop_is_warned_about():
    class SelfFeeder(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                technosphere=[Demand(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            )

    report = Orchestrator(Glossary([SelfFeeder()]), max_depth=3).calculate(ROOT)
    assert any(CAPTURED in message for message, _ in report.warnings)


def test_priority_callable_is_passed_through_to_the_queue():
    seen: list[str] = []

    def priority(demand: Demand) -> float:
        seen.append(demand.flow.iri)
        return -demand.amount

    Orchestrator(Glossary([Capturer(), Boiler()]), priority=priority).calculate(ROOT)
    assert HEAT in seen
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.orchestration.orchestrator'`

- [ ] **Step 3: Write `trailrunner/orchestration/orchestrator.py`**

```python
"""The traversal loop."""

from collections.abc import Callable

from trailrunner.core.flow import Demand
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.queue import Queue, QueueItem
from trailrunner.orchestration.report import Report
from trailrunner.orchestration.runner import Runner


class Orchestrator:
    """Walks demands outward through the supply chain.

    Every visit is its own node; nodes are never merged. A loop is therefore
    bounded by ``max_depth`` and ``max_nodes`` and flagged as a warning, rather
    than solved. A truncated tree with an honest unresolved list beats a
    converged number that would be wrong.
    """

    def __init__(
        self,
        glossary: Glossary,
        runner: Runner | None = None,
        max_depth: int = 10,
        max_nodes: int = 1000,
        priority: Callable[[Demand], float] | None = None,
    ) -> None:
        self.glossary = glossary
        self.runner = runner if runner is not None else Runner(glossary)
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.priority = priority

    def calculate(self, demand: Demand) -> Report:
        log = Log()
        queue = Queue(priority=self.priority)
        queue.push(QueueItem(demand=demand, depth=0, parent=None, path=()))
        truncated = False

        while queue:
            if len(log.nodes) >= self.max_nodes:
                truncated = True
                self._drain(queue, log, reason="max_nodes")
                break

            item = queue.pop()

            if item.depth >= self.max_depth:
                truncated = True
                log.unresolved(item.demand, reason="max_depth", depth=item.depth, parent=item.parent)
                continue

            model = self.glossary.resolve(item.demand.flow)
            if model is None:
                log.unresolved(
                    item.demand, reason="no_producer", depth=item.depth, parent=item.parent
                )
                continue

            result = self.runner.apply(item.demand, model=model)
            node_id = log.write(item.demand, result, depth=item.depth, parent=item.parent)

            if item.demand.flow.iri in item.path:
                log.warn(
                    f"{item.demand.flow.iri} repeats on its own supply chain path; "
                    "traversal is truncated, not converged",
                    node_id,
                )

            path = (*item.path, item.demand.flow.iri)
            for child in result.technosphere:
                queue.push(
                    QueueItem(demand=child, depth=item.depth + 1, parent=node_id, path=path)
                )

        return Report.from_log(log, truncated=truncated)

    @staticmethod
    def _drain(queue: Queue, log: Log, reason: str) -> None:
        while queue:
            item = queue.pop()
            log.unresolved(item.demand, reason=reason, depth=item.depth, parent=item.parent)
```

- [ ] **Step 4: Export the public API from `trailrunner/__init__.py`**

```python
"""Model-based supply chain traversal for life cycle inventories."""

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.orchestration.report import Report
from trailrunner.orchestration.runner import Runner
from trailrunner.params.coverage import Coverage
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

__version__ = "0.1.0"

__all__ = [
    "Coverage",
    "Demand",
    "Exchange",
    "Flow",
    "Glossary",
    "LocationHierarchy",
    "Model",
    "Orchestrator",
    "ParameterSet",
    "Report",
    "Result",
    "Runner",
    "Settings",
]
```

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS, 82 tests.

- [ ] **Step 6: Commit**

```bash
git add trailrunner tests
git commit -m "feat: add Orchestrator traversal loop and public API"
```

---

### Task 11: DirectAirCapture example and end-to-end test

**Files:**
- Create: `trailrunner/models/__init__.py`, `trailrunner/models/dac.py`
- Create: `tests/test_dac.py`
- Modify: `README.md` (add a usage example)

**Interfaces:**
- Consumes: everything built so far.
- Produces: `DirectAirCapture(Model)` with
  `produces = [CO2_CAPTURED]`, `coverage = Coverage(time_range=(2020, 2050))`,
  and module constants `CO2_CAPTURED`, `HEAT`, `ELECTRICITY`, `CO2_AIR`.

This is where the design either holds together or does not: real physics
(sorbent regeneration heat rising as air gets colder and drier), real
parameters from a parquet file, and a real multi-level traversal.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dac.py`:

```python
import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.models.dac import CO2_AIR, CO2_CAPTURED, ELECTRICITY, HEAT, DirectAirCapture
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet

HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


@pytest.fixture
def dac_params(tmp_path):
    path = tmp_path / "dac.parquet"
    rows = [
        {"location": "CH", "time": 2030, "heat_demand": 5.0, "electricity_demand": 0.4,
         "temperature": 10.0, "humidity": 0.70},
        {"location": "RER", "time": 2030, "heat_demand": 5.5, "electricity_demand": 0.45,
         "temperature": 12.0, "humidity": 0.65},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "integer", "unit": "year", "iri": None},
        {"name": "heat_demand", "type": "number", "unit": "MJ", "iri": "https://vocab.sentier.dev/parameters/heat-demand"},
        {"name": "electricity_demand", "type": "number", "unit": "kWh", "iri": "https://vocab.sentier.dev/parameters/electricity-demand"},
        {"name": "temperature", "type": "number", "unit": "degC", "iri": "https://vocab.sentier.dev/parameters/air-temperature"},
        {"name": "humidity", "type": "number", "unit": "dimensionless", "iri": "https://vocab.sentier.dev/parameters/relative-humidity"},
    ]
    write_parameter_parquet(path, rows, fields)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def demand(location="CH", time=2030, amount=1000.0):
    return Demand(flow=Flow(iri=CO2_CAPTURED, location=location, time=time), amount=amount, unit="kg")


def test_dac_produces_exactly_what_was_demanded(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    assert result.production[0].flow.iri == CO2_CAPTURED
    assert result.production[0].amount == 1000.0
    assert result.production[0].unit == "kg"


def test_dac_demands_heat_and_electricity_at_the_same_place_and_time(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert set(by_iri) == {HEAT, ELECTRICITY}
    assert by_iri[HEAT].unit == "MJ"
    assert by_iri[ELECTRICITY].unit == "kWh"
    for child in result.technosphere:
        assert child.flow.location == "CH"
        assert child.flow.time == 2030


def test_dac_takes_co2_from_air_as_a_negative_biosphere_flow(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    uptake = [e for e in result.biosphere if e.flow.iri == CO2_AIR][0]
    assert uptake.amount == -1000.0
    assert uptake.unit == "kg"


def test_ambient_penalty_is_one_at_the_reference_point():
    assert ambient_penalty(REFERENCE_TEMPERATURE, REFERENCE_HUMIDITY) == 1.0


def test_colder_and_drier_air_costs_more():
    assert ambient_penalty(5.0, 0.50) > 1.0


def test_warmer_and_wetter_air_costs_less():
    assert ambient_penalty(15.0, 0.90) < 1.0


def test_heat_demand_reflects_the_ambient_penalty(dac_params):
    """The whole reason models are code: this is not a fixed coefficient.

    Pin the exact amounts. Asserting only that the two differ would pass even
    if ambient_penalty ignored its inputs entirely, because the two fixture
    rows also carry different baseline heat_demand values.
    """
    swiss = DirectAirCapture(params=dac_params).apply(demand(location="CH"))
    european = DirectAirCapture(params=dac_params).apply(demand(location="RER"))
    swiss_heat = [d for d in swiss.technosphere if d.flow.iri == HEAT][0]
    european_heat = [d for d in european.technosphere if d.flow.iri == HEAT][0]
    assert swiss_heat.amount == pytest.approx(5000.0)     # 5.0 * 1.0   * 1000
    assert european_heat.amount == pytest.approx(5472.5)  # 5.5 * 0.995 * 1000


def test_dac_records_which_parameter_row_it_used(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand(location="FR"))
    assert result.provenance["location_used"] == "RER"
    assert result.provenance["location_fallback"] is True


def test_dac_is_out_of_coverage_before_2020(dac_params):
    glossary = Glossary([DirectAirCapture(params=dac_params)])
    assert glossary.resolve(Flow(iri=CO2_CAPTURED, location="CH", time=1990)) is None


def test_end_to_end_traversal_with_a_heat_model(dac_params):
    class Boiler(Model):
        produces = [HEAT]

        def apply(self, d: Demand) -> Result:
            return Result(
                production=[Exchange(flow=d.flow, amount=d.amount, unit=d.unit)],
                biosphere=[
                    Exchange(
                        flow=Flow(iri="https://vocab.sentier.dev/flows/co2-fossil",
                                  location=d.flow.location, time=d.flow.time),
                        amount=0.06 * d.amount,
                        unit="kg",
                    )
                ],
            )

    glossary = Glossary([DirectAirCapture(params=dac_params), Boiler()])
    report = Orchestrator(glossary).calculate(demand())

    assert len(report.nodes) == 2
    uptake = report.inventory[(Flow(iri=CO2_AIR, location="CH", time=2030), "kg")]
    assert uptake == -1000.0
    # electricity has no model: it is a cutoff leaf, not a silent zero
    assert [r.demand.flow.iri for r in report.unresolved] == [ELECTRICITY]
    assert report.truncated is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dac.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.models'`

- [ ] **Step 3: Write `trailrunner/models/dac.py`**

Create an empty `trailrunner/models/__init__.py`, then:

```python
"""Direct air capture: the worked example.

Sorbent regeneration heat is not a fixed coefficient. Colder, drier air means
less CO2 and less water reaching the sorbent per unit of air moved, so the heat
and fan work per kilogram captured go up. That dependency is the reason a model
is Python code rather than a row in a table.
"""

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.params.coverage import Coverage

CO2_CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
ELECTRICITY = "https://vocab.sentier.dev/products/electricity"
CO2_AIR = "https://vocab.sentier.dev/flows/co2-from-air"

REFERENCE_TEMPERATURE = 10.0  # degC, the temperature the parquet figures assume
REFERENCE_HUMIDITY = 0.70  # dimensionless, likewise
TEMPERATURE_SENSITIVITY = 0.01  # per degC below reference
HUMIDITY_SENSITIVITY = 0.30  # per unit of relative humidity below reference


def ambient_penalty(temperature: float, humidity: float) -> float:
    """Multiplier on heat and electricity demand for non-reference air.

    Colder or drier than the reference gives a value above 1.0; warmer or
    wetter gives one below. Deliberately a simple linear response: the point is
    that the dependency exists and lives in code, not that this particular
    curve is the right one.
    """
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    humidity_term = HUMIDITY_SENSITIVITY * (REFERENCE_HUMIDITY - humidity)
    return 1.0 + temperature_term + humidity_term


class DirectAirCapture(Model):
    """Captures CO2 from ambient air, given heat and electricity."""

    produces = [CO2_CAPTURED]
    coverage = Coverage(time_range=(2020, 2050))

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        penalty = ambient_penalty(row["temperature"], row["humidity"])

        heat = row["heat_demand"] * penalty * demand.amount
        electricity = row["electricity_demand"] * penalty * demand.amount
        upstream = Flow(iri=HEAT, location=demand.flow.location, time=demand.flow.time)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(flow=upstream, amount=heat, unit=row.unit_of("heat_demand")),
                Demand(
                    flow=Flow(
                        iri=ELECTRICITY,
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=electricity,
                    unit=row.unit_of("electricity_demand"),
                ),
            ],
            biosphere=[
                Exchange(
                    flow=Flow(
                        iri=CO2_AIR,
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=-demand.amount,
                    unit=demand.unit,
                )
            ],
            provenance=dict(row.provenance),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dac.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS, 89 tests.

- [ ] **Step 6: Add the usage example to `README.md`**

Append below the Status section:

````markdown
## Example

```python
from trailrunner import Demand, Flow, Glossary, LocationHierarchy, Orchestrator, ParameterSet
from trailrunner.models.dac import CO2_CAPTURED, DirectAirCapture

params = ParameterSet.from_parquet(
    "dac_params.parquet",
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
glossary = Glossary([DirectAirCapture(params=params)])

report = Orchestrator(glossary).calculate(
    Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")
)

for (flow, unit), amount in report.inventory.items():
    print(f"{amount:>12.2f} {unit}  {flow.iri}")

for record in report.unresolved:
    print(f"unresolved: {record.demand.flow.iri} ({record.reason})")
```

A demand nobody models is reported as unresolved, never silently treated as
zero. Every parameter fallback used along the way shows up in
`report.provenance`.
````

- [ ] **Step 7: Commit**

```bash
git add trailrunner tests README.md
git commit -m "feat: add DirectAirCapture example model and end-to-end test"
```

---

## Verification

After Task 11, the following must all hold. Run them and paste the output
before declaring the plan complete:

```bash
cd /Users/timodiepers/Documents/Coding/trailrunner
uv run pytest -v          # 89 passed
git log --oneline         # 12 commits (spec + 11 tasks), no attribution trailers
```

Per-task running totals, so a drift is caught early: 6, 21, 27, 34, 44, 52, 59,
67, 74, 82, 89.

Manual check: `git log --format='%B' | grep -ci claude` must print `0`.
