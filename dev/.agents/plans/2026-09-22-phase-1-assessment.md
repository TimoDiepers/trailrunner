# Phase 1 — Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a finished `Report` into a score — a static one from a parquet method file, and a time-explicit one from `dynamic_characterization` — without the traversal ever learning that assessment exists.

**Architecture:** A new top-level package `trailrunner/assessment/`. `Method` reads characterization factors from a trailpack-style parquet with the same fallback-and-provenance discipline as `ParameterSet`. `assess(report, method)` multiplies the inventory and walks `report.edges` for cumulative per-node contributions. `assess_dynamic(report, ...)` reshapes the already-time-stamped inventory into the four-column DataFrame `dynamic_characterization.characterize()` wants and calls it. The dependency arrow points one way: `assessment` imports `orchestration.report`; `orchestration` never imports `assessment`.

**Tech Stack:** Python >= 3.11, uv, pyarrow for `Method` and `assess`; `dynamic_characterization` >= 1.4 and pandas behind the `[dynamic]` extra for `assess_dynamic`; pytest.

**Spec:** `dev/.agents/specs/2026-09-22-trailrunner-v2-design.md` §1

## Global Constraints

- Python `>= 3.11` for everything in this phase's core path. `assess_dynamic`
  runs only where `dynamic_characterization` installs (>= 3.12); it is behind
  an extra and lazily imported, never at module import time.
- `Method` and `assess` import **pyarrow only**. A test that exercises them
  must pass in an environment with no pandas.
- Unit compatibility is **string equality**, here as everywhere. A CF declared
  for `kg` does not characterize an inventory entry in `tonne`; that entry is
  reported as uncharacterized. No conversion, ever.
- **A flow with no CF is never zero.** It goes into `Assessment.uncharacterized`.
  This mirrors `report.unresolved` and is the reason this module exists in the
  shape it does.
- All tooling runs through `uv`. Never `pip`.
- Repo root is `/Users/timodiepers/Documents/Coding/trailrunner`.
- Work on branch `feat/phase-1-assessment`, branched from `feat/phase-0-foundations`.
- Commit after every task, ending each message with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Phase 0 must be merged or present: this plan assumes `Report.resolutions`
  and `Report.proxies` exist, though only Task 2 touches them.

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/assessment/__init__.py` | public surface: `Method`, `assess`, `assess_dynamic`, `Assessment`, `DynamicAssessment` |
| `trailrunner/assessment/method.py` | `Method`, `CharacterizationFactor` — parquet CFs with location fallback |
| `trailrunner/assessment/static.py` | `assess`, `Assessment` |
| `trailrunner/assessment/dynamic.py` | `assess_dynamic`, `DynamicAssessment`, the IRI→function table |
| `dev/convert_brightway_method.py` | offline: a bw2data method → the parquet format |
| `tests/test_method.py` | CF lookup, fallback, missing metadata |
| `tests/test_assess.py` | score, by_flow, by_node, uncharacterized |
| `tests/test_assess_dynamic.py` | DataFrame shape, dates, curve, missing-extra error |
| `tests/conftest.py` | `method_parquet_file` fixture |

---

### Task 1: `Method` — characterization factors from parquet

**Files:**
- Create: `trailrunner/assessment/__init__.py`, `trailrunner/assessment/method.py`
- Modify: `trailrunner/params/location.py` (add the `root` property)
- Modify: `tests/conftest.py`
- Test: `tests/test_method.py` (create)

**Interfaces:**
- Consumes: `trailrunner.params.location.LocationHierarchy`,
  `trailrunner.params.parameter_set._read_field_metadata`,
  `trailrunner.core.flow.Flow`, `trailrunner.core.errors.MissingUnit`.
- Produces:
  `Method.from_parquet(path, hierarchy: LocationHierarchy | None = None) -> Method`;
  `Method.name: str`, `Method.unit: str`;
  `Method.factor(flow: Flow, unit: str) -> CharacterizationFactor | None`;
  `CharacterizationFactor(value: float, unit: str, provenance: Mapping[str, Any])`.

The method parquet has columns `flow_iri` (string), `flow_unit` (string),
`cf` (number), and optionally `location` (string) and `time` (int64). The
score's unit is the `cf` column's declared unit in the embedded
`datapackage.json`; the method's name is the datapackage's `name`.

- [ ] **Step 1: Add the fixture**

Append to `tests/conftest.py`:

```python
CO2_IRI = "https://vocab.sentier.dev/flows/co2-fossil"
CH4_IRI = "https://vocab.sentier.dev/flows/ch4-fossil"


def write_method_parquet(path, rows, fields):
    """Write a method parquet with the same embedded metadata trailpack writes."""
    return write_parameter_parquet(path, rows, fields)


@pytest.fixture
def method_parquet_file(tmp_path):
    """GWP100-shaped: a global CO2 factor, a regional CH4 one, both per kg."""
    path = tmp_path / "gwp100.parquet"
    rows = [
        {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.0},
        {"flow_iri": CH4_IRI, "flow_unit": "kg", "location": "GLO", "cf": 29.8},
        {"flow_iri": CH4_IRI, "flow_unit": "kg", "location": "RER", "cf": 27.0},
    ]
    fields = [
        {"name": "flow_iri", "type": "string", "unit": None, "iri": None},
        {"name": "flow_unit", "type": "string", "unit": None, "iri": None},
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "cf", "type": "number", "unit": "kg CO2eq", "iri": None},
    ]
    write_method_parquet(path, rows, fields)
    return path
```

`write_parameter_parquet` names the datapackage `test-parameters`; that is the
name `Method.name` will report in tests, which is fine — the name is metadata,
not behaviour.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_method.py`:

```python
import pytest

from trailrunner.assessment import Method
from trailrunner.core.errors import MissingUnit
from trailrunner.core.flow import Flow
from trailrunner.params.location import LocationHierarchy

from .conftest import CH4_IRI, CO2_IRI, write_method_parquet


def test_exact_factor_is_found(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    factor = method.factor(Flow(iri=CO2_IRI, location="GLO"), "kg")
    assert factor.value == 1.0


def test_score_unit_comes_from_the_cf_column_metadata(method_parquet_file):
    assert Method.from_parquet(method_parquet_file).unit == "kg CO2eq"


def test_location_falls_back_up_the_hierarchy(method_parquet_file):
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="CH"), "kg")
    assert factor.value == 27.0
    assert factor.provenance["location_used"] == "RER"
    assert factor.provenance["location_fallback"] is True


def test_exact_location_is_preferred_over_the_fallback(method_parquet_file):
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="RER"), "kg")
    assert factor.value == 27.0
    assert factor.provenance["location_fallback"] is False


def test_a_flow_with_no_factor_returns_none(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    assert method.factor(Flow(iri="https://vocab.sentier.dev/flows/sox"), "kg") is None


def test_a_factor_for_a_different_unit_does_not_match(method_parquet_file):
    """String equality, no conversion: a CF per kg says nothing about tonnes."""
    method = Method.from_parquet(method_parquet_file)
    assert method.factor(Flow(iri=CO2_IRI, location="GLO"), "tonne") is None


def test_a_flow_without_a_location_matches_the_root_row(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    factor = method.factor(Flow(iri=CO2_IRI), "kg")
    assert factor.value == 1.0
    # Nothing was asked for, so nothing was substituted.
    assert factor.provenance["location_fallback"] is False


def test_a_cf_column_without_a_declared_unit_raises(tmp_path):
    path = tmp_path / "unitless.parquet"
    write_method_parquet(
        path,
        [{"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.0}],
        [
            {"name": "flow_iri", "type": "string", "unit": None, "iri": None},
            {"name": "flow_unit", "type": "string", "unit": None, "iri": None},
            {"name": "location", "type": "string", "unit": None, "iri": None},
            {"name": "cf", "type": "number", "unit": None, "iri": None},
        ],
    )
    with pytest.raises(MissingUnit, match="cf"):
        Method.from_parquet(path)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_method.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.assessment'`.

- [ ] **Step 4: Implement**

Create `trailrunner/assessment/method.py`:

```python
"""Characterization factors out of a parquet file, with honest fallback.

Deliberately the same shape as ``ParameterSet``: same embedded datapackage
metadata, same location hierarchy, same rule that a fallback is recorded
rather than assumed. A method file is parameters that happen to be CFs.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from trailrunner.core.errors import MissingUnit
from trailrunner.core.flow import Flow
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import DATAPACKAGE_KEY, _read_field_metadata


@dataclass(frozen=True)
class CharacterizationFactor:
    """One CF and how it was found."""

    value: float
    unit: str
    provenance: Mapping[str, Any]


class Method:
    """Characterization factors indexed by (flow IRI, flow unit, location).

    ``time`` is read if the column is present, and matched exactly: a method
    whose factors change by year says so per row. There is no interpolation
    between CFs, because a CF is a modelling convention rather than a measured
    quantity, and interpolating between two conventions produces neither.
    """

    def __init__(
        self,
        rows: list[dict[str, Any]],
        unit: str,
        name: str,
        hierarchy: LocationHierarchy | None = None,
        source: str | None = None,
    ) -> None:
        self.unit = unit
        self.name = name
        self.source = source
        self._hierarchy = hierarchy if hierarchy is not None else LocationHierarchy()
        self._rows: dict[tuple[str, str, str | None, int | None], float] = {
            (row["flow_iri"], row["flow_unit"], row.get("location"), row.get("time")): row["cf"]
            for row in rows
        }

    @classmethod
    def from_parquet(
        cls, path: str | Path, hierarchy: LocationHierarchy | None = None
    ) -> "Method":
        table = pq.read_table(path)
        units, _ = _read_field_metadata(table.schema)
        if not units.get("cf"):
            raise MissingUnit(
                f"column 'cf' has no unit declared in {path}; the method's score "
                "unit is read from it"
            )
        raw = (table.schema.metadata or {}).get(DATAPACKAGE_KEY)
        name = "method"
        if raw is not None:
            name = json.loads(raw).get("name", name)
        return cls(
            rows=table.to_pylist(),
            unit=units["cf"],
            name=name,
            hierarchy=hierarchy,
            source=str(path),
        )

    def _locations(self, flow: Flow) -> list[str | None]:
        """Candidate locations, most specific first, always ending at the root.

        ``LocationHierarchy.chain(None)`` is ``[None]`` — "no location was
        requested". A method file still normally states its factors at the
        root, so the root is appended: a global CF answers a flow that named
        no location.
        """
        chain = list(self._hierarchy.chain(flow.location))
        if self._hierarchy.root not in chain:
            chain.append(self._hierarchy.root)
        return chain

    def factor(self, flow: Flow, unit: str) -> CharacterizationFactor | None:
        """The CF for this flow in this unit, or ``None``.

        ``None`` is not zero. The caller records it as uncharacterized, which
        is the whole point: a flow nobody characterized is a gap in the method,
        not an absence of impact.
        """
        for location in self._locations(flow):
            for time in (flow.time, None):
                value = self._rows.get((flow.iri, unit, location, time))
                if value is not None:
                    return CharacterizationFactor(
                        value=value,
                        unit=self.unit,
                        provenance={
                            "location_used": location,
                            # Nothing was substituted if nothing was asked for: a
                            # flow that named no location is answered by the
                            # method's global row, which is the right answer
                            # rather than a concession. Same rule, same wording,
                            # as ParameterSet.at().
                            "location_fallback": flow.location is not None
                            and location != flow.location,
                            "time_used": time,
                            "method": self.name,
                        },
                    )
        return None
```

`Method._locations` needs the hierarchy's root, which `LocationHierarchy` keeps
private. Add a read-only accessor to `trailrunner/params/location.py`, beside
`chain`:

```python
    @property
    def root(self) -> str:
        """The last resort every chain ends at. Read-only: changing it mid-run
        would silently change which fallback rows match."""
        return self._root
```

Create `trailrunner/assessment/__init__.py`:

```python
"""Characterization: a finished Report in, a score or a curve out.

This package imports from ``orchestration.report``; ``orchestration`` never
imports from here. The inventory is a complete, valid deliverable on its own,
and characterization is a separate reading of it.
"""

from trailrunner.assessment.method import CharacterizationFactor, Method

__all__ = ["CharacterizationFactor", "Method"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_method.py -v`
Expected: PASS.

All eight tests must pass. `test_a_flow_without_a_location_matches_the_root_row`
is the one that exercises `_locations`' root append; if it fails, the
`LocationHierarchy.root` property from Step 4 is missing.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/assessment trailrunner/params/location.py tests/test_method.py tests/conftest.py
git commit -m "feat(assessment): read characterization factors from parquet

Same shape as ParameterSet: embedded datapackage metadata, the same
location hierarchy, the same rule that a fallback is recorded rather
than assumed. A missing CF returns None, never zero -- the caller
reports it as uncharacterized.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `assess` — the static score

**Files:**
- Create: `trailrunner/assessment/static.py`
- Modify: `trailrunner/assessment/__init__.py`
- Test: `tests/test_assess.py` (create)

**Interfaces:**
- Consumes: `Method`, `CharacterizationFactor` from Task 1;
  `Report.inventory`, `Report.nodes`, `Report.edges`.
- Produces:
  `assess(report: Report, method: Method) -> Assessment`;
  `Assessment.score: float`, `.unit: str`, `.by_flow: dict[tuple[Flow, str], float]`,
  `.direct_by_node: dict[int, float]`, `.cumulative_by_node: dict[int, float]`,
  `.uncharacterized: list[tuple[Flow, str, float]]`, `.provenance: dict[tuple[Flow, str], Mapping]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_assess.py`:

```python
from trailrunner.assessment import Method, assess
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

from .conftest import CH4_IRI, CO2_IRI

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
SOX = "https://vocab.sentier.dev/flows/sox"


def two_level_report() -> Report:
    """Root emits 10 kg CO2; its child emits 2 kg CH4 and 1 kg of an
    uncharacterized flow."""
    log = Log()
    root_demand = Demand(flow=Flow(iri=CAPTURED, location="GLO"), amount=1000.0, unit="kg")
    child_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=5000.0, unit="MJ")
    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=10.0, unit="kg")],
        ),
        model="DirectAirCapture",
    )
    log.write(
        child_demand,
        Result(
            production=[Exchange(flow=child_demand.flow, amount=5000.0, unit="MJ")],
            biosphere=[
                Exchange(flow=Flow(iri=CH4_IRI, location="GLO"), amount=2.0, unit="kg"),
                Exchange(flow=Flow(iri=SOX, location="GLO"), amount=1.0, unit="kg"),
            ],
        ),
        depth=1,
        parent=root,
        model="GasBoiler",
    )
    return Report.from_log(log)


def test_score_is_the_sum_of_inventory_times_factors(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.score == 10.0 * 1.0 + 2.0 * 29.8


def test_score_carries_the_methods_unit(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.unit == "kg CO2eq"


def test_contributions_are_reported_per_flow(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.by_flow[(Flow(iri=CO2_IRI, location="GLO"), "kg")] == 10.0


def test_a_flow_with_no_factor_is_reported_not_zeroed(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert [(flow.iri, unit, amount) for flow, unit, amount in assessment.uncharacterized] == [
        (SOX, "kg", 1.0)
    ]


def test_direct_contributions_are_per_node(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.direct_by_node[0] == 10.0
    assert assessment.direct_by_node[1] == 2.0 * 29.8


def test_cumulative_contribution_of_the_root_is_the_whole_score(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.cumulative_by_node[0] == assessment.score
    assert assessment.cumulative_by_node[1] == 2.0 * 29.8


def test_provenance_records_the_factor_lookups(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    key = (Flow(iri=CO2_IRI, location="GLO"), "kg")
    assert assessment.provenance[key]["method"]


def test_an_empty_report_assesses_to_zero(method_parquet_file):
    assessment = assess(Report.from_log(Log()), Method.from_parquet(method_parquet_file))
    assert assessment.score == 0.0
    assert assessment.uncharacterized == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_assess.py -v`
Expected: FAIL — `ImportError: cannot import name 'assess'`.

- [ ] **Step 3: Implement**

Create `trailrunner/assessment/static.py`:

```python
"""Inventory times factors, and where the number came from."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from trailrunner.assessment.method import Method
from trailrunner.core.flow import Flow
from trailrunner.orchestration.report import Report


@dataclass
class Assessment:
    """A characterized inventory, plus what could not be characterized.

    ``uncharacterized`` is as much a part of the answer as ``score`` is, for
    the same reason ``report.unresolved`` is: the alternative is a number that
    silently omits whatever the method did not cover.
    """

    score: float = 0.0
    unit: str = ""
    method: str = ""
    by_flow: dict[tuple[Flow, str], float] = field(default_factory=dict)
    direct_by_node: dict[int, float] = field(default_factory=dict)
    cumulative_by_node: dict[int, float] = field(default_factory=dict)
    uncharacterized: list[tuple[Flow, str, float]] = field(default_factory=list)
    provenance: dict[tuple[Flow, str], Mapping[str, Any]] = field(default_factory=dict)


def assess(report: Report, method: Method) -> Assessment:
    """Characterize a finished Report.

    Reads the Report; never touches the traversal. The Orchestrator does not
    know this function exists, which is what keeps the Queue free of scores.
    """
    assessment = Assessment(unit=method.unit, method=method.name)

    for (flow, unit), amount in report.inventory.items():
        factor = method.factor(flow, unit)
        if factor is None:
            assessment.uncharacterized.append((flow, unit, amount))
            continue
        contribution = amount * factor.value
        assessment.score += contribution
        assessment.by_flow[(flow, unit)] = assessment.by_flow.get((flow, unit), 0.0) + contribution
        assessment.provenance[(flow, unit)] = factor.provenance

    for node in report.nodes:
        total = 0.0
        for exchange in node.result.biosphere:
            factor = method.factor(exchange.flow, exchange.unit)
            if factor is not None:
                total += exchange.amount * factor.value
        assessment.direct_by_node[node.id] = total

    children: dict[int, list[int]] = {}
    for parent, child in report.edges:
        children.setdefault(parent, []).append(child)

    def cumulative(node_id: int) -> float:
        if node_id in assessment.cumulative_by_node:
            return assessment.cumulative_by_node[node_id]
        total = assessment.direct_by_node.get(node_id, 0.0)
        for child in children.get(node_id, []):
            total += cumulative(child)
        assessment.cumulative_by_node[node_id] = total
        return total

    # Deepest first, so the memo is warm and the recursion never goes deeper
    # than the traversal already did.
    for node in sorted(report.nodes, key=lambda n: n.depth, reverse=True):
        cumulative(node.id)

    return assessment
```

Add to `trailrunner/assessment/__init__.py`:

```python
from trailrunner.assessment.static import Assessment, assess
```

and extend `__all__` with `"Assessment"` and `"assess"`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_assess.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the one-way dependency holds**

Run:
```bash
grep -rn "assessment" trailrunner/orchestration/ trailrunner/core/ trailrunner/params/
```
Expected: no output. If anything matches, the arrow has been reversed and must
be undone — `orchestration` importing `assessment` is the one thing this
phase's architecture forbids.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/assessment tests/test_assess.py
git commit -m "feat(assessment): add the static score

Inventory times factors, with per-flow and per-node contributions and a
cumulative-by-subtree walk over the report's edges. Flows the method
does not cover are listed, not zeroed.

The dependency arrow points one way: assessment reads orchestration,
never the reverse, so the Queue stays free of scores.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `assess_dynamic` — the time-explicit curve

**Files:**
- Create: `trailrunner/assessment/dynamic.py`
- Modify: `trailrunner/assessment/__init__.py`, `pyproject.toml`
- Test: `tests/test_assess_dynamic.py` (create)

**Interfaces:**
- Consumes: `Report.nodes` (for the per-node `activity` label), `Report.inventory`.
- Produces:
  `assess_dynamic(report, metric="radiative_forcing", horizon=100, fixed_time_horizon=False, functions=None) -> DynamicAssessment`;
  `DynamicAssessment.series` (a DataFrame with `date`, `amount`, `flow`, `activity`),
  `.curve` (a DataFrame with `date`, `amount` — the cumulative integral),
  `.total: float`, `.metric: str`, `.unit: str`, `.uncharacterized: list[str]`;
  `default_functions() -> dict[str, Callable]` — IRI → characterization function.
  A function rather than a module-level dict: building the table imports
  `dynamic_characterization.ipcc_ar6`, and doing that at module scope would
  break this module's own lazy-import rule and the pyarrow-only static path;
  `inventory_dataframe(report) -> pd.DataFrame`.

`dynamic_characterization.characterize()` takes a DataFrame with exactly the
columns `date`, `amount`, `flow`, `activity`. `flow` is used only as a dict
key into `characterization_functions`, so the flow **IRI string** goes there
directly — no integer ids, no Brightway.

- [ ] **Step 1: Add the extra**

In `pyproject.toml`, under `[project.optional-dependencies]`, add:

```toml
dynamic = [
  # dynamic_characterization requires >=3.12, so the marker has to match it,
  # the same way the examples extra matches trailpack's floor.
  "dynamic_characterization>=1.4; python_version >= '3.12'",
  "pandas>=2",
]
```

Run: `uv sync --extra dev --extra dynamic`
Expected: resolves and installs. Confirm with
`uv run python -c "import dynamic_characterization; print(dynamic_characterization.__version__)"`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_assess_dynamic.py`:

```python
import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

from .conftest import CO2_IRI

pytest.importorskip("dynamic_characterization")

from trailrunner.assessment import assess_dynamic, inventory_dataframe  # noqa: E402

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"


def report_with(emissions) -> Report:
    """One node per (year, amount) pair, each emitting fossil CO2 that year."""
    log = Log()
    for year, amount in emissions:
        demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=year), amount=1.0, unit="kg")
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
                biosphere=[
                    Exchange(flow=Flow(iri=CO2_IRI, location="CH", time=year), amount=amount, unit="kg")
                ],
            ),
            model="DirectAirCapture",
        )
    return Report.from_log(log)


def test_inventory_dataframe_has_the_four_columns_the_library_wants():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert list(frame.columns) == ["date", "amount", "flow", "activity"]


def test_a_year_becomes_the_first_of_january():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert str(frame["date"].iloc[0])[:10] == "2030-01-01"


def test_the_flow_column_carries_the_iri():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert frame["flow"].iloc[0] == CO2_IRI


def test_the_activity_column_names_the_model():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert frame["activity"].iloc[0] == "DirectAirCapture"


def test_exchanges_without_a_time_are_left_out_and_reported():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=1.0, unit="kg")
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="CH"), amount=5.0, unit="kg")],
        ),
        model="Undated",
    )
    assessment = assess_dynamic(Report.from_log(log))
    assert assessment.undated == [(CO2_IRI, "kg", 5.0)]
    assert len(assessment.series) == 0


def test_radiative_forcing_series_spans_the_horizon():
    assessment = assess_dynamic(report_with([(2030, 10.0)]), horizon=20)
    years = assessment.series["date"].dt.year
    assert years.min() == 2030
    assert years.max() == 2030 + 19


def test_the_curve_is_the_cumulative_integral_of_the_series():
    assessment = assess_dynamic(report_with([(2030, 10.0)]), horizon=20)
    assert assessment.curve["amount"].iloc[-1] == pytest.approx(
        assessment.series["amount"].sum()
    )
    assert assessment.total == pytest.approx(assessment.curve["amount"].iloc[-1])


def test_twice_the_emission_is_twice_the_forcing():
    one = assess_dynamic(report_with([(2030, 10.0)]), horizon=20).total
    two = assess_dynamic(report_with([(2030, 20.0)]), horizon=20).total
    assert two == pytest.approx(2 * one)


def test_an_emission_ten_years_later_is_characterized_over_its_own_horizon():
    """The default is the conventional convention: the horizon starts at the
    emission, not at the functional unit."""
    assessment = assess_dynamic(report_with([(2030, 10.0), (2040, 10.0)]), horizon=20)
    assert assessment.series["date"].dt.year.max() == 2059


def test_an_unknown_flow_is_reported_rather_than_silently_dropped():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1.0, unit="kg")
    unknown = "https://vocab.sentier.dev/flows/unobtainium"
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=unknown, location="CH", time=2030), amount=1.0, unit="kg")],
        ),
        model="Mystery",
    )
    assessment = assess_dynamic(Report.from_log(log))
    assert unknown in assessment.uncharacterized


def test_an_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="cheeseburgers"):
        assess_dynamic(report_with([(2030, 10.0)]), metric="cheeseburgers")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_assess_dynamic.py -v`
Expected: FAIL — `ImportError: cannot import name 'assess_dynamic'`.

- [ ] **Step 4: Implement**

Create `trailrunner/assessment/dynamic.py`:

```python
"""Time-explicit characterization.

Every ``Exchange`` already carries ``flow.time``, so the inventory *is* a time
series. This module reshapes it into the four columns
``dynamic_characterization.characterize()`` expects and hands it over. That is
the whole trick, and it is only available because the traversal keeps the year
each emission happens in rather than summing it away.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trailrunner.orchestration.report import Report

CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"
CO2_BIOGENIC_UPTAKE = "https://vocab.sentier.dev/flows/co2-uptake"
CH4_FOSSIL = "https://vocab.sentier.dev/flows/ch4-fossil"
N2O = "https://vocab.sentier.dev/flows/n2o"
CO = "https://vocab.sentier.dev/flows/co"

METRICS = ("radiative_forcing", "GWP", "pGWP", "pGTP", "prospective_radiative_forcing")

METRIC_UNITS = {
    "radiative_forcing": "W/m2",
    "prospective_radiative_forcing": "W/m2",
    "GWP": "kg CO2eq",
    "pGWP": "kg CO2eq",
    "pGTP": "kg CO2eq",
}


def _require(module: str):
    """Import an extra's module, or say which extra is missing.

    Imported here rather than at module top so that ``trailrunner.assessment``
    keeps working with pyarrow alone.
    """
    try:
        return __import__(module, fromlist=["_"])
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            f"{module} is needed for dynamic assessment; install it with "
            "`uv sync --extra dynamic`"
        ) from exc


def default_functions() -> dict[str, Callable]:
    """IRI -> IPCC AR6 characterization function.

    A declared table rather than a lookup through a background database: the
    flows are identified by vocabulary IRI, and the mapping from an IRI to the
    physics of that gas is a fact about the gas, not about anyone's database.
    """
    ipcc = _require("dynamic_characterization.ipcc_ar6")
    return {
        CO2_FOSSIL: ipcc.characterize_co2,
        CO2_BIOGENIC_UPTAKE: ipcc.characterize_co2_uptake,
        CH4_FOSSIL: ipcc.characterize_ch4,
        N2O: ipcc.characterize_n2o,
        CO: ipcc.characterize_co,
    }


@dataclass
class DynamicAssessment:
    """A characterized time series, its cumulative curve, and what was left out."""

    series: Any = None
    """DataFrame: date, amount, flow, activity — the characterized inventory."""
    curve: Any = None
    """DataFrame: date, amount — the cumulative integral of ``series``."""
    total: float = 0.0
    metric: str = "radiative_forcing"
    unit: str = ""
    horizon: int = 100
    uncharacterized: list[str] = field(default_factory=list)
    """Flow IRIs with no characterization function. Reported, never zeroed."""
    undated: list[tuple[str, str, float]] = field(default_factory=list)
    """(IRI, unit, amount) for exchanges with no ``time``. A dynamic assessment
    cannot place them on the axis, so it says so instead of assuming a year."""


def inventory_dataframe(report: Report) -> Any:
    """The report's biosphere exchanges as the four columns the library wants.

    ``Flow.time`` is a year and ``characterize`` wants a timestamp, so year Y
    becomes ``datetime(Y, 1, 1)``. That is an assumption, not a fact — a finer
    ``Flow.time`` would change it — and it lives in this one function so the
    change would be one edit.
    """
    pandas = _require("pandas")
    rows = []
    for node in report.nodes:
        activity = node.model or f"node {node.id}"
        for exchange in node.result.biosphere:
            if exchange.flow.time is None:
                continue
            rows.append(
                {
                    "date": datetime(exchange.flow.time, 1, 1),
                    "amount": exchange.amount,
                    "flow": exchange.flow.iri,
                    "activity": activity,
                }
            )
    frame = pandas.DataFrame(rows, columns=["date", "amount", "flow", "activity"])
    return frame.astype({"date": "datetime64[s]", "amount": "float64"})


def assess_dynamic(
    report: Report,
    metric: str = "radiative_forcing",
    horizon: int = 100,
    fixed_time_horizon: bool = False,
    functions: Mapping[str, Callable] | None = None,
) -> DynamicAssessment:
    """Characterize the time-stamped inventory over ``horizon`` years.

    ``fixed_time_horizon=False`` is the conventional convention: each emission
    is characterized over its own horizon. ``True`` is Levasseur: every horizon
    ends at the same date, so an earlier emission is counted for longer. Both
    are exposed because neither is the obviously right one.
    """
    if metric not in METRICS:
        raise ValueError(f"{metric!r} is not a known metric; allowed: {', '.join(METRICS)}")

    pandas = _require("pandas")
    characterization = _require("dynamic_characterization")

    table = functions if functions is not None else default_functions()

    assessment = DynamicAssessment(
        metric=metric, unit=METRIC_UNITS[metric], horizon=horizon
    )
    for node in report.nodes:
        for exchange in node.result.biosphere:
            if exchange.flow.time is None:
                assessment.undated.append((exchange.flow.iri, exchange.unit, exchange.amount))
            elif exchange.flow.iri not in table:
                if exchange.flow.iri not in assessment.uncharacterized:
                    assessment.uncharacterized.append(exchange.flow.iri)

    frame = inventory_dataframe(report)
    if frame.empty:
        assessment.series = frame
        assessment.curve = pandas.DataFrame(columns=["date", "amount"])
        return assessment

    series = characterization.characterize(
        frame,
        metric=metric,
        characterization_functions=dict(table),
        time_horizon=horizon,
        fixed_time_horizon=fixed_time_horizon,
    )
    assessment.series = series

    if len(series):
        curve = series.groupby("date", as_index=False)["amount"].sum().sort_values("date")
        curve["amount"] = curve["amount"].cumsum()
        assessment.curve = curve.reset_index(drop=True)
        assessment.total = float(assessment.curve["amount"].iloc[-1])
    else:
        assessment.curve = pandas.DataFrame(columns=["date", "amount"])
    return assessment
```

Add to `trailrunner/assessment/__init__.py`:

```python
from trailrunner.assessment.dynamic import (
    DynamicAssessment,
    assess_dynamic,
    default_functions,
    inventory_dataframe,
)
```

and extend `__all__` accordingly. These imports are safe at package import
time: `dynamic.py`'s own imports are pyarrow-free, and `pandas` and
`dynamic_characterization` are only fetched inside `_require`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_assess_dynamic.py -v`
Expected: PASS.

If `test_radiative_forcing_series_spans_the_horizon` reports a maximum year of
`2030 + 20` rather than `2030 + 19`, the library's offsets are inclusive of the
final year; change the assertion to match the library rather than reshaping the
data, and note it in the docstring.

- [ ] **Step 6: Prove the core path still needs nothing**

Run:
```bash
uv run python -c "
import sys
sys.modules['pandas'] = None
from trailrunner.assessment import Method, assess
print('static path imports without pandas')
"
```
Expected: prints the message. If it raises, a top-level pandas import has crept
into `static.py` or `method.py`.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add trailrunner/assessment tests/test_assess_dynamic.py pyproject.toml uv.lock
git commit -m "feat(assessment): add time-explicit characterization

Every Exchange already carries flow.time, so the inventory is already a
time series; this reshapes it into the four columns
dynamic_characterization wants and hands it over. Radiative forcing and
GWP, conventional or Levasseur horizons, IRI-keyed IPCC AR6 functions,
no Brightway.

Flows with no function, and exchanges with no year, are reported rather
than dropped. Behind the [dynamic] extra, lazily imported, so the static
path still installs with pyarrow alone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Brightway method converter and documentation

**Files:**
- Create: `dev/convert_brightway_method.py`
- Create: `docs/content/assessment.md`
- Create: `docs/api/assessment.md`
- Modify: `zensical.toml`, `pyproject.toml`, `README.md`

**Interfaces:**
- Consumes: `Method`'s parquet layout from Task 1.
- Produces: a command-line script, run by hand, that writes a method parquet
  from a Brightway method. Nothing imports it at runtime.

- [ ] **Step 1: Add the extra**

In `pyproject.toml`, under `[project.optional-dependencies]`:

```toml
brightway = [
  # Offline only: dev/convert_brightway_method.py writes a method parquet from
  # an existing Brightway project. trailrunner itself never imports bw2data.
  "bw2data>=4.0; python_version >= '3.12'",
]
```

- [ ] **Step 2: Write the converter**

Create `dev/convert_brightway_method.py`:

```python
"""Write a trailrunner method parquet from a Brightway LCIA method.

Run by hand, once, per method. trailrunner never imports bw2data: the point of
the parquet is that the method travels with the study rather than living in
someone's local project directory.

    uv run --extra brightway python dev/convert_brightway_method.py \
        --project ecoinvent-3.10 \
        --method "EF v3.1" "climate change" "global warming potential (GWP100)" \
        --iri-prefix https://vocab.sentier.dev/flows/ \
        --out gwp100.parquet

Flow identity is the hard part and is deliberately dumb here: each Brightway
biosphere flow becomes `<iri-prefix><slugified name>`. Check the output against
the IRIs your models actually emit before trusting a number that comes out of
it -- a CF attached to an IRI nothing emits is silently no CF at all, which the
Assessment will tell you about in `uncharacterized`.
"""

import argparse
import json
import re

import pyarrow as pa
import pyarrow.parquet as pq


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--method", required=True, nargs="+")
    parser.add_argument("--iri-prefix", default="https://vocab.sentier.dev/flows/")
    parser.add_argument("--unit", default=None, help="score unit; read from the method if omitted")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import bw2data as bd

    bd.projects.set_current(args.project)
    method = bd.Method(tuple(args.method))
    metadata = method.metadata
    unit = args.unit or metadata.get("unit", "unit")

    rows = []
    for key, cf in method.load():
        flow = bd.get_node(key=key) if not isinstance(key, int) else bd.get_node(id=key)
        rows.append(
            {
                "flow_iri": f"{args.iri_prefix}{slug(flow['name'])}",
                "flow_unit": flow.get("unit", "kg"),
                "location": "GLO",
                "cf": float(cf),
            }
        )

    table = pa.Table.from_pylist(rows)
    datapackage = {
        "name": " | ".join(args.method),
        "resources": [
            {
                "name": "method",
                "path": args.out,
                "schema": {
                    "fields": [
                        {"name": "flow_iri", "type": "string"},
                        {"name": "flow_unit", "type": "string"},
                        {"name": "location", "type": "string"},
                        {"name": "cf", "type": "number", "unit": {"name": unit}},
                    ]
                },
            }
        ],
    }
    schema = table.schema.with_metadata(
        {"datapackage.json": json.dumps(datapackage).encode("utf-8")}
    )
    pq.write_table(table.cast(schema), args.out)
    print(f"wrote {len(rows)} factors to {args.out} (unit: {unit})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the converter's output is readable by `Method`**

There is no Brightway project in CI, so test the round trip by hand with a
fake: run

```bash
uv run python - <<'PY'
import json, pyarrow as pa, pyarrow.parquet as pq
from trailrunner.assessment import Method
from trailrunner.core.flow import Flow

rows = [{"flow_iri": "https://vocab.sentier.dev/flows/co2-fossil",
         "flow_unit": "kg", "location": "GLO", "cf": 1.0}]
table = pa.Table.from_pylist(rows)
dp = {"name": "EF v3.1 | climate change", "resources": [{"name": "method", "path": "m.parquet",
      "schema": {"fields": [{"name": "flow_iri", "type": "string"},
                            {"name": "flow_unit", "type": "string"},
                            {"name": "location", "type": "string"},
                            {"name": "cf", "type": "number", "unit": {"name": "kg CO2eq"}}]}}]}
pq.write_table(table.cast(table.schema.with_metadata(
    {"datapackage.json": json.dumps(dp).encode()})), "/tmp/m.parquet")

method = Method.from_parquet("/tmp/m.parquet")
print(method.name, method.unit,
      method.factor(Flow(iri="https://vocab.sentier.dev/flows/co2-fossil", location="GLO"), "kg").value)
PY
```
Expected: `EF v3.1 | climate change kg CO2eq 1.0`.

- [ ] **Step 4: Write the documentation page**

Create `docs/content/assessment.md` covering, in this order: why assessment is
a separate module and not part of the traversal; the method parquet layout with
the four columns; `assess()` and reading `uncharacterized`; `assess_dynamic()`
with a worked radiative-forcing example and its plot; the two horizon
conventions and why both are exposed; and the `dev/convert_brightway_method.py`
escape hatch with its flow-matching caveat stated plainly.

While you are in `docs/content/`, fix a stale claim Phase 0 left behind: the
"Writing the log to parquet" section of `docs/content/reports.md` still says
"four files" and lists four row kinds, but the log has written five since
Phase 0 added `kind="resolution"`. Correct the count and add the missing kind.
(Found by Phase 0's final review; deliberately left out of that phase's fix
wave to keep its scope closed.)

Create `docs/api/assessment.md` following the pattern of the existing
`docs/api/report.md`, with `mkdocstrings` directives for
`trailrunner.assessment.method`, `trailrunner.assessment.static` and
`trailrunner.assessment.dynamic`.

In `zensical.toml`, add `{ Assessment = "content/assessment.md" }` to the
`"User Guide"` nav after `{ "Reading a Report" = "content/reports.md" }`, and
`{ Assessment = "api/assessment.md" }` to the API nav after
`{ Report = "api/report.md" }`.

In `README.md`, replace the Status line
`Early development. Inventory only — no impact characterization yet.` with a
sentence saying inventory plus static and time-explicit characterization, and
add a short code block showing `assess(report, Method.from_parquet(...)).score`.

- [ ] **Step 5: Verify the docs build and the README still runs**

Run: `uv run pytest tests/test_readme.py -v`
Expected: PASS. If the new README block needs a method file that does not
exist, guard it the way the existing README example is guarded in
`tests/test_readme.py`, rather than weakening the test.

Run: `uv sync --extra docs && uv run zensical build`
Expected: builds with no broken-link validation errors.

- [ ] **Step 6: Commit**

```bash
git add dev/convert_brightway_method.py docs zensical.toml pyproject.toml README.md
git commit -m "docs(assessment): document the module, add the Brightway converter

A hand-run script turns a bw2data method into the parquet format, with
its flow-matching caveat stated rather than buried: a CF attached to an
IRI nothing emits is no CF at all, and the Assessment says so in
uncharacterized.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification

Phase 1 is done when:

- [ ] `uv run pytest -q` passes with `--extra dynamic` installed.
- [ ] `grep -rn "assessment" trailrunner/orchestration/ trailrunner/core/ trailrunner/params/`
      returns nothing.
- [ ] `Method` and `assess` import and run in an environment without pandas.
- [ ] A DAC report assessed against a GWP100 method gives a score whose
      `uncharacterized` list is empty for the flows the DAC model emits.
- [ ] `assess_dynamic(report).curve` plotted against year shows the construction
      pulse before the capture years — the picture beat 6 of the showcase needs.
