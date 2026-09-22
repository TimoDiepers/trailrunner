# Phase 0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the four load-bearing seams every later phase needs — co-product properties on `Exchange`, typed normative settings, a Log that records *how* each node was answered, and a Report you can read as text.

**Architecture:** Nothing new is traversed and nothing new is computed. `Exchange` gains a hashable `properties` tuple; `Settings` gains two closed typed fields beside its open `values` mapping; `Log.write` learns a `model` name and a `resolution` mapping, which `Report` surfaces as `resolutions` and `proxies`; `Report` gains `summary()` and `tree()` built from records it already holds.

**Tech Stack:** Python >= 3.11, uv, pyarrow (only runtime dependency), pytest, stdlib dataclasses.

**Spec:** `dev/.agents/specs/2026-09-22-trailrunner-v2-design.md`

## Global Constraints

- Python `>= 3.11`. Use `X | None` unions, not `Optional[X]`.
- Runtime dependency: `pyarrow` only. No pandas, no Brightway, no pydantic in
  anything this phase touches.
- All tooling runs through `uv`: `uv run pytest`, `uv add`, `uv sync`. Never
  `pip`, never `conda`.
- Every value crossing a component boundary carries an explicit unit string.
  Unit compatibility is **string equality** — no conversion.
- `Flow` is an aggregation key and `QueueItem` is a frozen dataclass, so
  **every field added to `Exchange` must be hashable.** No dicts, no lists.
- Repo root is `/Users/timodiepers/Documents/Coding/trailrunner`. Paths are
  relative to it.
- Work on branch `feat/phase-0-foundations`, branched from `design/trailrunner-v2`.
- Commit after every task. End each commit message with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, matching this repo's
  existing history.
- Backwards compatibility is required: every existing test in `tests/` must
  still pass untouched after each task. New fields are added with defaults.

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/core/flow.py` | add `Property`; add `Exchange.properties` and `Exchange.get_property` |
| `trailrunner/core/settings.py` | add `AttributionSettings`, `ProxySettings`; add the two typed fields to `Settings` |
| `trailrunner/orchestration/log.py` | `NodeRecord.model`, `NodeRecord.resolution`, widened parquet schema |
| `trailrunner/orchestration/orchestrator.py` | pass the model name into `log.write` |
| `trailrunner/orchestration/report.py` | `resolutions`, `proxies`, `summary()`, `tree()` |
| `trailrunner/__init__.py` | export `Property`, `AttributionSettings`, `ProxySettings` |
| `tests/test_flow.py` | properties and hashability |
| `tests/test_settings.py` | **new** — typed settings and their validation |
| `tests/test_log.py` | model name, resolution records, parquet round-trip |
| `tests/test_report.py` | `resolutions`, `proxies` |
| `tests/test_report_text.py` | **new** — `summary()` and `tree()` |

---

### Task 1: `Property` and `Exchange.properties`

**Files:**
- Modify: `trailrunner/core/flow.py`
- Modify: `trailrunner/__init__.py`
- Test: `tests/test_flow.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Property(name: str, value: float, unit: str)` — frozen;
  `Exchange(flow, amount, unit, properties: tuple[Property, ...] = ())`;
  `Exchange.get_property(name: str) -> Property | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_flow.py`:

```python
from trailrunner.core.flow import Property


def test_exchange_defaults_to_no_properties():
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")
    assert exchange.properties == ()


def test_exchange_carries_properties_and_stays_hashable():
    mass = Property(name="mass", value=2.5, unit="kg")
    price = Property(name="price", value=18.0, unit="EUR")
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass, price))
    # Hashability is the whole reason properties is a tuple: Flow is an
    # aggregation key and QueueItem is a frozen dataclass holding a Demand.
    assert hash(exchange) == hash(
        Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass, price))
    )


def test_get_property_finds_by_name():
    mass = Property(name="mass", value=2.5, unit="kg")
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass,))
    assert exchange.get_property("mass") is mass


def test_get_property_returns_none_when_absent():
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")
    assert exchange.get_property("mass") is None


def test_properties_do_not_affect_the_flow_aggregation_key():
    mass = Property(name="mass", value=2.5, unit="kg")
    with_property = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass,))
    without = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")
    assert with_property.flow == without.flow
```

`HEAT` is already defined at the top of `tests/test_flow.py`; if it is not,
add `HEAT = "https://vocab.sentier.dev/products/heat"` beside the other IRI
constants there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_flow.py -v`
Expected: FAIL — `ImportError: cannot import name 'Property'`.

- [ ] **Step 3: Implement**

In `trailrunner/core/flow.py`, add above `Exchange`:

```python
@dataclass(frozen=True)
class Property:
    """A quantified attribute of an exchange, used to partition co-production.

    Mass, price, energy content: whatever the allocation rule divides by. The
    unit travels with the value because a partition over ``price`` in EUR and
    one in USD are not the same partition.
    """

    name: str
    value: float
    unit: str
```

and extend `Exchange`:

```python
@dataclass(frozen=True)
class Exchange:
    """A quantified flow. The unit lives here, not on the Flow."""

    flow: Flow
    amount: float
    unit: str

    properties: tuple[Property, ...] = ()
    """Attributes an allocation rule may partition on.

    A tuple rather than a mapping so that ``Exchange`` stays hashable: ``Flow``
    is an aggregation key and ``QueueItem`` is a frozen dataclass holding a
    ``Demand``, so a dict here would make the hashability of both depend on
    which fields happen to be populated.
    """

    def get_property(self, name: str) -> Property | None:
        """The property called ``name``, or ``None``.

        Deliberately lenient: the caller that *requires* a property is the
        allocation rule in the Runner, and it raises a message naming the model
        and the co-product, which is far more useful than a KeyError here.
        """
        for candidate in self.properties:
            if candidate.name == name:
                return candidate
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_flow.py -v`
Expected: PASS.

- [ ] **Step 5: Export and run the whole suite**

In `trailrunner/__init__.py`, add `Property` to the `from trailrunner.core.flow import ...`
line and to `__all__` (alphabetically, between `ParameterSet` and `Report`).

Run: `uv run pytest -q`
Expected: PASS — every pre-existing test still green, because `properties`
defaults to `()`.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/core/flow.py trailrunner/__init__.py tests/test_flow.py
git commit -m "feat(core): give Exchange hashable co-product properties

Allocation rules need something to partition on. A tuple of frozen
Property records rather than a mapping, because Flow is an aggregation
key and QueueItem is a frozen dataclass holding a Demand.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Typed attribution and proxy settings

**Files:**
- Modify: `trailrunner/core/settings.py`
- Modify: `trailrunner/__init__.py`
- Test: `tests/test_settings.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  `AttributionSettings(allocation: str = "none", capital: str = "per_output", reuse: str = "first_life")`,
  validating against `ALLOCATION_RULES`, `CAPITAL_RULES`, `REUSE_RULES`;
  `ProxySettings(order: tuple[str, ...] = ("time", "location", "product"), max_steps: dict[str, int] = {"time": 1, "location": 3, "product": 2}, time_tolerance: int = 5)`,
  validating against `PROXY_DIMENSIONS`;
  `Settings(values: dict, attribution: AttributionSettings, proxy: ProxySettings)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings.py`:

```python
import pytest

from trailrunner.core.settings import AttributionSettings, ProxySettings, Settings


def test_settings_defaults_are_the_conservative_ones():
    settings = Settings()
    assert settings.attribution.allocation == "none"
    assert settings.attribution.capital == "per_output"
    assert settings.attribution.reuse == "first_life"
    assert settings.proxy.order == ("time", "location", "product")
    assert settings.proxy.time_tolerance == 5


def test_values_mapping_still_works_alongside_the_typed_fields():
    settings = Settings(values={"scenario": "SSP2"})
    assert settings.get("scenario") == "SSP2"
    assert settings.get("missing") is None


def test_unknown_allocation_rule_is_rejected_at_construction():
    with pytest.raises(ValueError, match="economical"):
        AttributionSettings(allocation="economical")


def test_unknown_capital_rule_is_rejected_at_construction():
    with pytest.raises(ValueError, match="per_decade"):
        AttributionSettings(capital="per_decade")


def test_every_documented_allocation_rule_is_accepted():
    for rule in ("none", "mass", "economic", "energy", "substitution"):
        assert AttributionSettings(allocation=rule).allocation == rule


def test_unknown_proxy_dimension_is_rejected():
    with pytest.raises(ValueError, match="colour"):
        ProxySettings(order=("time", "colour"))


def test_repeated_proxy_dimension_is_rejected():
    with pytest.raises(ValueError, match="once"):
        ProxySettings(order=("time", "time", "location"))


def test_proxy_order_may_be_a_subset():
    settings = ProxySettings(order=("location",))
    assert settings.order == ("location",)


def test_steps_allowed_reads_max_steps_with_a_zero_default():
    settings = ProxySettings(max_steps={"location": 2})
    assert settings.steps_allowed("location") == 2
    assert settings.steps_allowed("product") == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'AttributionSettings'`.

- [ ] **Step 3: Implement**

Replace the body of `trailrunner/core/settings.py` with:

```python
"""Run-wide knobs, including the run's normative choices."""

from dataclasses import dataclass, field
from typing import Any

ALLOCATION_RULES = frozenset({"none", "mass", "economic", "energy", "substitution"})
CAPITAL_RULES = frozenset({"per_output", "per_year", "first_life"})
REUSE_RULES = frozenset({"first_life", "shared"})
PROXY_DIMENSIONS = ("time", "location", "product")


def _check(value: str, allowed, label: str) -> None:
    if value not in allowed:
        raise ValueError(
            f"{value!r} is not a known {label}; allowed: {', '.join(sorted(allowed))}"
        )


@dataclass(frozen=True)
class AttributionSettings:
    """The run's normative choices, closed and typed.

    Closed rather than free-form keys because these are value judgements, and a
    typo must not silently select a different ethics. An unknown value is
    rejected where it is written, not where it is read.
    """

    allocation: str = "none"
    """How co-production is handled: none | mass | economic | energy | substitution."""

    capital: str = "per_output"
    """How a long-lived asset's construction is attributed: per_output | per_year | first_life."""

    reuse: str = "first_life"
    """Whether initial production falls entirely on the first life, or is shared."""

    def __post_init__(self) -> None:
        _check(self.allocation, ALLOCATION_RULES, "allocation rule")
        _check(self.capital, CAPITAL_RULES, "capital rule")
        _check(self.reuse, REUSE_RULES, "reuse rule")


@dataclass(frozen=True)
class ProxySettings:
    """How far, and in which order, a demand may be generalised to find a model.

    The order is the practitioner's preference hierarchy, not the library's:
    relaxing the year and relaxing the product are different concessions, and
    which one is acceptable first is a modelling decision.
    """

    order: tuple[str, ...] = PROXY_DIMENSIONS
    max_steps: dict[str, int] = field(
        default_factory=lambda: {"time": 1, "location": 3, "product": 2}
    )
    time_tolerance: int = 5
    """Years. How far a demand's year may be moved to meet a model's coverage."""

    def __post_init__(self) -> None:
        for dimension in self.order:
            _check(dimension, PROXY_DIMENSIONS, "proxy dimension")
        if len(set(self.order)) != len(self.order):
            raise ValueError(f"each proxy dimension may appear only once in {self.order}")

    def steps_allowed(self, dimension: str) -> int:
        """Budget for ``dimension``. Absent means zero: no accidental relaxation."""
        return self.max_steps.get(dimension, 0)


@dataclass(frozen=True)
class Settings:
    """One flat namespace for the whole run, plus two closed typed fields.

    ``values`` stays the open namespace a model may read keys from. Anything
    that varies per process belongs in that process's ParameterSet instead.

    Frozen to prevent reassignment, but not hashable — ``values`` is a dict.
    """

    values: dict[str, Any] = field(default_factory=dict)
    attribution: AttributionSettings = AttributionSettings()
    proxy: ProxySettings = ProxySettings()

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Export and run the whole suite**

In `trailrunner/__init__.py`, import `AttributionSettings` and `ProxySettings`
from `trailrunner.core.settings` beside `Settings`, and add both to `__all__`.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/core/settings.py trailrunner/__init__.py tests/test_settings.py
git commit -m "feat(core): type the run's normative choices

Allocation, capital attribution and reuse are value judgements, so they
get closed typed fields validated at construction rather than free-form
keys in the values mapping. ProxySettings carries the practitioner's
generalisation preference order and its budgets.

Nothing reads them yet; the Runner enforces attribution in phase 3 and
the resolution chain reads proxy in phase 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The Log records how each node was answered

**Files:**
- Modify: `trailrunner/orchestration/log.py`
- Modify: `trailrunner/orchestration/orchestrator.py`
- Modify: `trailrunner/orchestration/report.py`
- Test: `tests/test_log.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: `NodeRecord.model: str | None`, `NodeRecord.resolution: dict[str, Any]`;
  `Log.write(demand, result, depth=0, parent=None, model=None, resolution=None) -> int`;
  `Report.resolutions: dict[int, dict]`, `Report.proxies: dict[int, dict]`.
  Phase 2's providers fill `resolution`; the agreed keys are
  `{"tier": "model" | "generalising" | "background", "relaxations": [...], "model": str}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_log.py`:

```python
def test_write_records_the_model_name():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand), model="DirectAirCapture")
    assert log.nodes[node_id].model == "DirectAirCapture"


def test_model_and_resolution_default_to_none_and_empty():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand))
    assert log.nodes[node_id].model is None
    assert log.nodes[node_id].resolution == {}


def test_write_records_how_the_demand_was_resolved():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        a_result(demand),
        model="GridElectricity",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    assert log.nodes[node_id].resolution["tier"] == "generalising"


def test_parquet_carries_the_model_and_one_row_per_resolution_key(tmp_path):
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        a_result(demand),
        model="GridElectricity",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    path = tmp_path / "log.parquet"
    log.to_parquet(path)

    rows = pq.read_table(path).to_pylist()
    resolution_rows = [row for row in rows if row["kind"] == "resolution"]
    assert {row["key"] for row in resolution_rows} == {"tier", "relaxations"}
    assert all(row["model"] == "GridElectricity" for row in rows)
```

`a_demand()` and `a_result(demand)` already exist in `tests/test_log.py`; if a
helper of a different name is there, reuse that one rather than adding another.
`pq` is already imported in that file.

Append to `tests/test_report.py`:

```python
def test_report_carries_resolutions_by_node():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")])
    node_id = log.write(demand, result, model="DirectAirCapture", resolution={"tier": "model"})
    report = Report.from_log(log)
    assert report.resolutions[node_id] == {"tier": "model"}


def test_proxies_hold_only_the_nodes_that_were_not_exact_matches():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")])
    exact = log.write(demand, result, model="DirectAirCapture", resolution={"tier": "model"})
    relaxed = log.write(
        demand,
        result,
        model="GridElectricity",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    borrowed = log.write(demand, result, resolution={"tier": "background"})

    report = Report.from_log(log)
    assert set(report.proxies) == {relaxed, borrowed}
    assert exact not in report.proxies


def test_nodes_without_a_resolution_are_not_proxies():
    log = Log()
    demand = a_demand()
    log.write(demand, Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")]))
    assert Report.from_log(log).proxies == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_log.py tests/test_report.py -v`
Expected: FAIL — `TypeError: write() got an unexpected keyword argument 'model'`.

- [ ] **Step 3: Implement the Log changes**

In `trailrunner/orchestration/log.py`:

Add `("model", pa.string())` to `LOG_SCHEMA`, immediately after `("kind", pa.string())`.

Extend `NodeRecord`:

```python
@dataclass
class NodeRecord:
    id: int
    demand: Demand
    result: Result
    depth: int
    parent: int | None
    model: str | None = None
    """Class name of the model that answered, for the tree and the report."""
    resolution: dict[str, Any] = field(default_factory=dict)
    """How this demand was matched: which tier answered and what was relaxed.

    Empty in phase 0 — the Orchestrator fills ``tier`` and ``model`` once the
    resolution chain exists. Kept here rather than in ``Result.provenance``
    because provenance is the *model's* record of the parameters it used, and
    resolution is the *orchestrator's* record of how that model was chosen.
    """
```

Add `from typing import Any` to the imports.

Change `Log.write`:

```python
    def write(
        self,
        demand: Demand,
        result: Result,
        depth: int = 0,
        parent: int | None = None,
        model: str | None = None,
        resolution: dict[str, Any] | None = None,
    ) -> int:
        node_id = len(self.nodes)
        self.nodes.append(
            NodeRecord(
                id=node_id,
                demand=demand,
                result=result,
                depth=depth,
                parent=parent,
                model=model,
                resolution=dict(resolution or {}),
            )
        )
        if parent is not None:
            self.edges.append(EdgeRecord(parent=parent, child=node_id))
        return node_id
```

In `to_parquet`, add `"model": node.model` to the `base` dict, and after the
provenance loop add:

```python
            for key, value in node.resolution.items():
                rows.append(
                    {
                        **base,
                        "kind": "resolution",
                        "key": str(key),
                        "value": None if value is None else str(value),
                    }
                )
```

- [ ] **Step 4: Implement the Orchestrator and Report changes**

In `trailrunner/orchestration/orchestrator.py`, change the `log.write` call to:

```python
            node_id = log.write(
                item.demand,
                result,
                depth=item.depth,
                parent=item.parent,
                model=type(model).__name__,
                resolution={"tier": "model", "model": type(model).__name__},
            )
```

In `trailrunner/orchestration/report.py`, add two fields to `Report`:

```python
    resolutions: dict[int, dict[str, Any]] = field(default_factory=dict)
    """Per node: which tier answered its demand, and what was relaxed to get there."""
    proxies: dict[int, dict[str, Any]] = field(default_factory=dict)
    """The subset of ``resolutions`` that were not exact model matches.

    A number answered by a generalised demand or borrowed from the background
    is a different kind of number, and the report says which nodes those are
    without the reader having to filter.
    """
```

and fill them in `from_log`, inside the existing `for node in log.nodes:` loop:

```python
            if node.resolution:
                resolutions[node.id] = dict(node.resolution)
                if node.resolution.get("tier", "model") != "model":
                    proxies[node.id] = dict(node.resolution)
```

declaring `resolutions: dict[int, dict[str, Any]] = {}` and
`proxies: dict[int, dict[str, Any]] = {}` beside `inventory` and `provenance`,
and passing both to the `cls(...)` call.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q`
Expected: PASS, all of it. The existing orchestrator and log tests are
unaffected: every new parameter has a default.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/orchestration/log.py trailrunner/orchestration/orchestrator.py trailrunner/orchestration/report.py tests/test_log.py tests/test_report.py
git commit -m "feat(log): record which model answered, and how it was chosen

A node now carries the model's name and a resolution mapping saying
which tier matched it and what was relaxed to get there. The Report
surfaces it as resolutions, and as proxies for the nodes that were not
exact matches. Phase 2's provider chain fills it; today every node is
tier 'model'.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `report.summary()` and `report.tree()`

**Files:**
- Modify: `trailrunner/orchestration/report.py`
- Test: `tests/test_report_text.py` (create)

**Interfaces:**
- Consumes: `Report.resolutions`, `Report.proxies`, `NodeRecord.model` from Task 3.
- Produces: `Report.summary() -> str`, `Report.tree() -> str`.

Both return a string rather than printing, so they are testable and so a
caller can put them in a file. Tests assert on *contents*, never on alignment.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_report_text.py`:

```python
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = Flow(iri="https://vocab.sentier.dev/flows/co2-fossil", location="CH", time=2030)


def built_report() -> Report:
    """Root -> heat -> an unresolved gas demand, with one biosphere flow."""
    log = Log()
    root_demand = Demand(
        flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg"
    )
    heat_demand = Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=5000.0, unit="MJ")
    gas_demand = Demand(flow=Flow(iri=GAS, location="CH", time=2030), amount=125.0, unit="kg")

    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            technosphere=[heat_demand],
            biosphere=[Exchange(flow=CO2, amount=12.0, unit="kg")],
        ),
        model="DirectAirCapture",
        resolution={"tier": "model", "model": "DirectAirCapture"},
    )
    log.write(
        heat_demand,
        Result(production=[Exchange(flow=heat_demand.flow, amount=5000.0, unit="MJ")]),
        depth=1,
        parent=root,
        model="GasBoiler",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    log.unresolved(gas_demand, reason="no_model_found", depth=2, parent=1)
    return Report.from_log(log)


def test_tree_shows_every_node_in_traversal_order():
    tree = built_report().tree()
    assert tree.index("co2-captured") < tree.index("heat") < tree.index("natural-gas")


def test_tree_tags_an_exact_match_with_its_model():
    assert "[model: DirectAirCapture]" in built_report().tree()


def test_tree_tags_a_generalised_node_with_what_was_relaxed():
    tree = built_report().tree()
    assert "[proxy: location: CH -> RER]" in tree


def test_tree_tags_an_unresolved_demand_with_its_reason():
    assert "[cutoff: no_model_found]" in built_report().tree()


def test_tree_indents_children_under_their_parent():
    lines = {
        line.strip().split()[2]: len(line) - len(line.lstrip())
        for line in built_report().tree().splitlines()
    }
    assert lines["co2-captured"] < lines["heat"] < lines["natural-gas"]


def test_tree_shows_the_amount_and_unit_of_each_demand():
    tree = built_report().tree()
    assert "1000" in tree and "kg" in tree
    assert "5000" in tree and "MJ" in tree


def test_summary_counts_nodes_and_inventory_entries():
    summary = built_report().summary()
    assert "2 nodes" in summary
    assert "1 inventory entry" in summary


def test_summary_breaks_unresolved_down_by_reason():
    assert "no_model_found: 1" in built_report().summary()


def test_summary_reports_proxies_and_attribution():
    summary = built_report().summary()
    assert "1 proxy" in summary


def test_summary_says_when_the_traversal_was_truncated():
    log = Log()
    assert "truncated" in Report.from_log(log, truncated=True).summary()
    assert "truncated" not in Report.from_log(log).summary()


def test_summary_of_an_empty_report_does_not_crash():
    assert "0 nodes" in Report.from_log(Log()).summary()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_report_text.py -v`
Expected: FAIL — `AttributeError: 'Report' object has no attribute 'tree'`.

- [ ] **Step 3: Implement**

Add to `trailrunner/orchestration/report.py`, at module level:

```python
def _short(iri: str) -> str:
    """The last path segment of an IRI, for a tree a human reads.

    The full IRI is in the records; a tree whose every line is 60 characters
    of vocabulary URL is a tree nobody reads.
    """
    return iri.rstrip("/").rsplit("/", 1)[-1]


def _where(flow: Flow) -> str:
    if flow.location is None and flow.time is None:
        return ""
    return f" @{flow.location or '-'}/{flow.time if flow.time is not None else '-'}"
```

and these methods on `Report`:

```python
    def _tag(self, node: NodeRecord) -> str:
        """How honestly this node was answered, in one bracket."""
        tier = node.resolution.get("tier", "model")
        if tier == "background":
            return "[background]"
        if tier == "generalising":
            relaxations = node.resolution.get("relaxations") or []
            return f"[proxy: {'; '.join(relaxations)}]" if relaxations else "[proxy]"
        return f"[model: {node.model}]" if node.model else "[model]"

    def tree(self, indent: str = "  ") -> str:
        """The traversal as indented text: the supply chain, and how each node
        was answered, in one screenful.

        Unresolved demands hang under the node that asked for them, because a
        cutoff is a property of the place in the chain where it happened.
        """
        children: dict[int | None, list[NodeRecord]] = {}
        for node in self.nodes:
            children.setdefault(node.parent, []).append(node)

        cutoffs: dict[int | None, list[UnresolvedRecord]] = {}
        for record in self.unresolved:
            cutoffs.setdefault(record.parent, []).append(record)

        lines: list[str] = []

        def line(depth: int, amount: float, unit: str, flow: Flow, tag: str) -> None:
            lines.append(f"{indent * depth}{amount:g} {unit} {_short(flow.iri)}{_where(flow)}  {tag}")

        def walk(node: NodeRecord, depth: int) -> None:
            line(depth, node.demand.amount, node.demand.unit, node.demand.flow, self._tag(node))
            for child in children.get(node.id, []):
                walk(child, depth + 1)
            for record in cutoffs.get(node.id, []):
                line(
                    depth + 1,
                    record.demand.amount,
                    record.demand.unit,
                    record.demand.flow,
                    f"[cutoff: {record.reason}]",
                )

        for root in children.get(None, []):
            walk(root, 0)
        for record in cutoffs.get(None, []):
            line(0, record.demand.amount, record.demand.unit, record.demand.flow,
                 f"[cutoff: {record.reason}]")
        return "\n".join(lines)

    def summary(self) -> str:
        """Everything needed to judge the numbers, in one block.

        The cutoffs and the proxies come before the inventory size on purpose:
        what the traversal could not answer is part of the answer.
        """
        reasons: dict[str, int] = {}
        for record in self.unresolved:
            reasons[record.reason] = reasons.get(record.reason, 0) + 1

        entries = len(self.inventory)
        lines = [
            f"{len(self.nodes)} nodes, {entries} inventory "
            f"{'entry' if entries == 1 else 'entries'}",
        ]
        if reasons:
            breakdown = ", ".join(f"{reason}: {count}" for reason, count in sorted(reasons.items()))
            lines.append(f"{len(self.unresolved)} unresolved ({breakdown})")
        else:
            lines.append("0 unresolved")
        count = len(self.proxies)
        lines.append(f"{count} {'proxy' if count == 1 else 'proxies'}")
        if self.truncated:
            lines.append("traversal was truncated: max_depth or max_nodes was reached")
        if self.warnings:
            lines.append(f"{len(self.warnings)} warnings")
        return "\n".join(lines)
```

Add `NodeRecord` and `UnresolvedRecord` to the existing import from
`trailrunner.orchestration.log` if either is missing, and `Flow` is already
imported.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_report_text.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite and the README test**

Run: `uv run pytest -q`
Expected: PASS, including `tests/test_readme.py`, which executes the README's
code blocks.

- [ ] **Step 6: Document and commit**

Add a short section to `docs/content/reports.md` showing `report.summary()` and
`report.tree()` with the output of the DAC example, and add one line to the
README's example block after the existing `for record in report.unresolved:`
loop:

```python
print(report.tree())
```

Verify the README still runs: `uv run pytest tests/test_readme.py -v`

```bash
git add trailrunner/orchestration/report.py tests/test_report_text.py docs/content/reports.md README.md
git commit -m "feat(report): add summary() and tree()

One screenful showing the supply chain and how honestly each node was
answered: exact model, proxy with what was relaxed, borrowed background,
or cutoff with its reason. Both return strings rather than printing, so
they are testable and can be written to a file.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification

Phase 0 is done when:

- [ ] `uv run pytest -q` passes, including every pre-existing test unmodified.
- [ ] `Exchange` is still hashable with properties populated, and `Flow` is
      unchanged as an aggregation key.
- [ ] `AttributionSettings("economical")` raises `ValueError` naming the typo.
- [ ] `report.tree()` on `examples/dac.ipynb`'s report shows the DAC node, its
      heat and electricity children, and the cutoff leaves with their reasons.
- [ ] `log.to_parquet()` output contains a `model` column and `kind="resolution"`
      rows.
- [ ] Nothing imports `trailrunner.assessment` — it does not exist yet.
