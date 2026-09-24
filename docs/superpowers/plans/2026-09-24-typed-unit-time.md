# Typed Units and Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every unit a sentier vocabulary IRI (with exact, logged conversion within a quantity kind) and every time a string in a declared, registered time standard (XSD by default), across the core, models, data files, CLI and showcase.

**Architecture:** A `UnitCatalog` in `trailrunner/core/units.py` reads QUDT facts (quantity kind, multiplier, UCUM symbol) from the vocabulary, cached offline in a bundled JSON; the Runner rejects non-vocab units, `ModelProvider` converts a demand into a unit the model declares in `Coverage.units`, and `Coverage`/tier 2 convert context conditions. A time-standard registry in `trailrunner/core/time.py` turns `(time, time_standard)` into a UTC interval; coverage, parameter rows, methods and relaxation all compare intervals (containment first, then nearest period / midpoint interpolation).

**Tech Stack:** Python ≥ 3.11, stdlib (`urllib`, `datetime`, `re`, `json`), pyarrow, pytest. Run everything with `uv run`.

**Spec:** `docs/superpowers/specs/2026-09-24-typed-unit-time-design.md`

## Global Constraints

- Work in the worktree `/Users/timodiepers/Documents/Coding/trailrunner/.claude/worktrees/typed-unit-time`, branch `feat/typed-unit-time`. Never `cd` to the main checkout.
- Test command: `uv run pytest -q` (whole suite must be green at the end of every task).
- Commits: Conventional Commits. **No** `Co-Authored-By` or "Generated with" footer (repo owner's rule).
- Unit IRIs live under `https://vocab.sentier.dev/units/unit/`. **Strict**: only IRIs the vocabulary has. Never invent a vocab IRI.
- `Exchange.unit` and context-condition units (`Property` in `Flow.context`, `ContextRange.unit`, the unit in `context_tolerance`) are strict. Allocation `Exchange.properties` units stay free text (the vocab has no currencies). Parameter-file ratio columns (`MJ/tkm`, `kg/Nm3`) may keep free-text units; only columns read through `unit_of` must declare IRIs.
- Temperature units are never converted (vocab has no `conversionOffset` for `DEG_C`).
- Pressure is always Pa (`PA`); the vocab has no `BAR`.
- Time standards are XSD datatype IRIs: `http://www.w3.org/2001/XMLSchema#gYear`, `#gYearMonth`, `#date`, `#dateTime`. `dateTime` requires a timezone. Intervals are half-open UTC `[start, end)`; a `dateTime` is zero width.
- A coarser declaration covers a finer demand (containment), at tier 1 — not a relaxation.
- Unit conversion is **not** a proxy relaxation: no budget, no entry in `ProxySettings.order`, tier unchanged; recorded under the resolution key `"conversion"` as `unit: t -> kg ×1000`.
- `ProxySettings.time_tolerance` is years (float), default 5.
- Code style: match the surrounding code — long explanatory docstrings stating *why*, `frozen=True` dataclasses, tuples not lists/dicts on hashable types.
- Layering (enforced by `tests/test_architecture.py`): `core`, `params`, `orchestration` never import `assessment`.

## Review Focus

1. **°C vs K**: `DEG_C` and `K` share a quantity kind and multiplier 1 in the vocab, with no offset. A catalog that converts by multiplier would silently read 10 °C as 10 K. Expected: `convertible(DEG_C, K) is False`. Pinned in Task 1.
2. **An instant exactly at a period boundary**: `2031-01-01T00:00:00Z` is not inside gYear `2030`, and `2030-12-31T23:59:59Z` is. Expected: containment is half-open. Pinned in Task 8.
3. **Offline run, vocab unit not in the bundled cache**: expected is a `ValidationError` that says the unit is unknown *or not cached* and how to warm the cache, not a crash and not a pass. Pinned in Task 6.
4. **A demand in a unit of another quantity kind** (m³ of something whose model declares kg): expected is an unresolved leaf with reason `unit_mismatch`, not a `ValidationError` from inside the model and not a silent answer. Pinned in Task 3.
5. **Old habits**: `Flow(iri=..., time=2030)` (an int) must raise `TypeError` naming `in_year(2030)`, not produce a flow that fails later. `ParameterSet.at(time=2030)` likewise. Pinned in Task 9.
6. **Leap years in interpolation**: 2025 between rows 2020 (leap) and 2030 must interpolate at exactly 0.5, as today. Pinned in Task 9.

---

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/core/units.py` (new) | Unit IRI constants, `UnitInfo`, `UnitCatalog`, `default_catalog()`, `symbol()` |
| `trailrunner/core/units.json` (new) | Bundled offline cache of QUDT facts for the constants |
| `trailrunner/core/time.py` (new) | Time-standard registry, parsers, `interval`, `TimeRange`, `in_year`, `year_range`, `when`, `year_of`, `infer_standard`, `decimal_year`, `midpoint_year`, `contains` |
| `dev/warm_unit_cache.py` (new) | Refreshes `units.json` from the live vocabulary |
| `trailrunner/core/errors.py` | + `UnknownUnit`, `MissingTimeStandard` |
| `trailrunner/core/flow.py` | `Flow.time: str`, `Flow.time_standard`, validation; context display via `symbol` |
| `trailrunner/params/coverage.py` | `Coverage.units`, `TimeRange` time ranges, context conversion |
| `trailrunner/params/parameter_set.py` | Time standard metadata, containment, midpoint interpolation |
| `trailrunner/core/settings.py` | `context_tolerance` gains a unit; `time_tolerance` float |
| `trailrunner/resolution/models.py` | Unit conversion in `ModelProvider.offer`, `unit_mismatch` explain |
| `trailrunner/resolution/generalising.py` | Carries conversion; context candidates in units; time candidates by interval |
| `trailrunner/orchestration/runner.py` | Strict unit validation |
| `trailrunner/orchestration/orchestrator.py` | Passes a `UnitCatalog` to Runner and ModelProvider |
| `trailrunner/orchestration/report.py` | Conversion in the tag; unit symbols in the tree |
| `trailrunner/orchestration/log.py` | String time columns, standard/start/end, context columns |
| `trailrunner/assessment/method.py`, `static.py`, `dynamic.py` | Unit conversion for CFs; time containment; IRI metric units; interval dates |
| `trailrunner/models/*.py` | Constants, `Coverage.units`, `when(...)`, pipeline t + distance |
| `trailrunner/cli.py` | `--unit` resolution, `--time`/`--time-standard`, `--context` |
| `dev/build_showcase_params.py`, `dev/build_background_pack.py` | Regenerate example parquets with IRIs and time standards |
| `examples/*.ipynb`, `docs/*.md`, `docs/content/**` | Showcase/pitch/guide |

---

### Task 1: Unit catalog

**Files:**
- Create: `trailrunner/core/units.py`
- Create: `trailrunner/core/units.json`
- Create: `dev/warm_unit_cache.py`
- Modify: `trailrunner/core/errors.py` (append `UnknownUnit`)
- Test: `tests/test_units.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - constants `VOCAB, KG, GRAM, TONNE, J, MJ, KWH, M3, PA, KILOMETRE, METRE, YEAR, TONNE_PER_YEAR, DEG_C, KELVIN, NUM, UNITLESS, PERCENT, W_PER_M2` (all `str`)
  - `@dataclass(frozen=True) class UnitInfo(iri: str, quantity_kind: str | None, multiplier: float | None, offset: float = 0.0, symbol: str | None = None)`
  - `parse_unit_payload(iri: str, payload: Any) -> UnitInfo | None`
  - `class UnitCatalog(cache_path: str | Path | None = None, client: Any | None = None)` with `info(iri) -> UnitInfo | None`, `known(iri) -> bool | None`, `convertible(a, b) -> bool`, `factor(a, b) -> float`, `convert(amount, a, b) -> float`, `try_convert(amount, a, b) -> float | None`, `symbol(iri) -> str`, `resolve(text) -> str`, `save() -> None`, `unknown_iris: frozenset[str]`
  - `default_catalog() -> UnitCatalog` (bundled, offline, memoised), `symbol(iri: str) -> str`
  - `errors.UnknownUnit(TrailrunnerError, ValueError)`

- [ ] **Step 1: Add the error class**

Append to `trailrunner/core/errors.py`:

```python
class UnknownUnit(TrailrunnerError, ValueError):
    """A unit the vocabulary does not have, or that nothing could confirm.

    A ``ValueError`` too, because it is raised where a value is read -- a CLI
    argument, a unit written in a notebook -- and callers catching the broad
    class for bad input should catch this one.
    """
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_units.py`:

```python
import json
import urllib.error

import pytest

from trailrunner.core.errors import UnknownUnit
from trailrunner.core.units import (
    DEG_C,
    KELVIN,
    KG,
    KILOMETRE,
    KWH,
    M3,
    METRE,
    MJ,
    NUM,
    TONNE,
    VOCAB,
    UnitCatalog,
    UnitInfo,
    default_catalog,
    parse_unit_payload,
    symbol,
)

QUDT = "http://qudt.org/schema/qudt/"
SKOS_NOTATION = "http://www.w3.org/2004/02/skos/core#notation"


def payload(iri, kind, multiplier, ucum):
    """The shape GET /api/v1/concepts/<iri> answers with (trimmed)."""
    return [
        {
            "@id": iri,
            QUDT + "hasQuantityKind": [{"@id": f"https://vocab.sentier.dev/units/quantity-kind/{kind}"}],
            QUDT + "conversionMultiplier": [
                {"@type": "http://www.w3.org/2001/XMLSchema#decimal", "@value": str(multiplier)}
            ],
            SKOS_NOTATION: [{"@type": QUDT + "ucumCode", "@value": ucum}],
        }
    ]


class StubClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def concept_payload(self, iri):
        self.calls.append(iri)
        if iri not in self.payloads:
            raise urllib.error.HTTPError(iri, 404, "Not Found", {}, None)
        return self.payloads[iri]


def test_parse_reads_kind_multiplier_and_ucum_symbol():
    info = parse_unit_payload(MJ, payload(MJ, "Energy", 1000000.0, "MJ"))
    assert info == UnitInfo(
        iri=MJ,
        quantity_kind="https://vocab.sentier.dev/units/quantity-kind/Energy",
        multiplier=1000000.0,
        offset=0.0,
        symbol="MJ",
    )


def test_parse_rejects_a_non_object():
    assert parse_unit_payload(MJ, "nope") is None
    assert parse_unit_payload(MJ, []) is None


def test_bundled_catalog_knows_the_constants_offline():
    catalog = default_catalog()
    for iri in (KG, TONNE, MJ, KWH, M3, KILOMETRE, NUM):
        assert catalog.known(iri) is True, iri


def test_mass_converts_by_multiplier():
    catalog = default_catalog()
    assert catalog.convertible(TONNE, KG)
    assert catalog.factor(TONNE, KG) == pytest.approx(1000.0)
    assert catalog.convert(2.5, TONNE, KG) == pytest.approx(2500.0)
    assert catalog.convert(3.6, MJ, KWH) == pytest.approx(1.0)


def test_different_kinds_do_not_convert():
    catalog = default_catalog()
    assert not catalog.convertible(M3, KG)
    assert catalog.try_convert(1.0, M3, KG) is None
    with pytest.raises(ValueError):
        catalog.factor(M3, KG)


def test_temperature_never_converts_even_though_the_vocab_says_it_could():
    # Review focus 1: the vocab gives DEG_C and K the same kind and
    # multiplier 1 with no conversionOffset, so 10 degC would become 10 K.
    catalog = default_catalog()
    assert not catalog.convertible(DEG_C, KELVIN)
    assert catalog.convertible(DEG_C, DEG_C)


def test_a_non_vocab_string_is_known_false():
    assert default_catalog().known("kg") is False
    assert default_catalog().known("https://example.org/units/kg") is False


def test_a_miss_asks_the_client_and_caches_to_disk(tmp_path):
    grams = VOCAB + "GM-TEST"
    client = StubClient({grams: payload(grams, "Mass", 0.001, "g")})
    cache = tmp_path / "units.json"
    catalog = UnitCatalog(cache_path=cache, client=client)
    assert catalog.convert(1000.0, grams, KG) == pytest.approx(1.0)
    assert json.loads(cache.read_text())[grams]["symbol"] == "g"
    # A second catalog reads the file; no client needed.
    assert UnitCatalog(cache_path=cache).known(grams) is True


def test_a_404_is_unknown_and_not_cached(tmp_path):
    missing = VOCAB + "BAR"
    cache = tmp_path / "units.json"
    catalog = UnitCatalog(cache_path=cache, client=StubClient({}))
    assert catalog.known(missing) is False
    assert missing in catalog.unknown_iris
    assert not cache.exists() or missing not in json.loads(cache.read_text())


def test_offline_miss_is_undetermined():
    assert UnitCatalog().known(VOCAB + "LB") is None


def test_symbol_prefers_the_display_override_then_ucum_then_last_segment():
    assert symbol(KG) == "kg"
    assert symbol(TONNE) == "t"
    assert symbol(KWH) == "kWh"
    assert symbol(VOCAB + "NOT-CACHED") == "NOT-CACHED"
    assert symbol("W·yr/m2") == "W·yr/m2"  # not an IRI: shown as written


def test_resolve_accepts_iri_id_and_symbol():
    catalog = default_catalog()
    assert catalog.resolve(KG) == KG
    assert catalog.resolve("KiloGM") == KG
    assert catalog.resolve("kg") == KG
    assert catalog.resolve("t") == TONNE


def test_resolve_refuses_what_it_cannot_confirm():
    with pytest.raises(UnknownUnit, match="tkm"):
        default_catalog().resolve("tkm")
    with pytest.raises(UnknownUnit):
        default_catalog().resolve("https://example.org/kg")


def test_a_damaged_cache_is_ignored(tmp_path):
    cache = tmp_path / "units.json"
    cache.write_text("{not json")
    assert UnitCatalog(cache_path=cache).known(KG) is True  # bundled still loads


def test_metre_and_kilometre_convert():
    assert default_catalog().convert(1500.0, METRE, KILOMETRE) == pytest.approx(1.5)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_units.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.core.units'`

- [ ] **Step 4: Write the bundled cache**

Create `trailrunner/core/units.json` with exactly these facts (fetched from the live vocabulary on 2026-09-24; `dev/warm_unit_cache.py` regenerates it):

```json
{
  "https://vocab.sentier.dev/units/unit/DEG_C": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Temperature", "symbol": "Cel"},
  "https://vocab.sentier.dev/units/unit/GM": {"multiplier": 0.001, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Mass", "symbol": "g"},
  "https://vocab.sentier.dev/units/unit/J": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Energy", "symbol": "J"},
  "https://vocab.sentier.dev/units/unit/K": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Temperature", "symbol": "K"},
  "https://vocab.sentier.dev/units/unit/KiloGM": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Mass", "symbol": "kg"},
  "https://vocab.sentier.dev/units/unit/KiloM": {"multiplier": 1000.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Length", "symbol": "km"},
  "https://vocab.sentier.dev/units/unit/KiloW-HR": {"multiplier": 3600000.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Energy", "symbol": "kW.h"},
  "https://vocab.sentier.dev/units/unit/M": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Length", "symbol": "m"},
  "https://vocab.sentier.dev/units/unit/M3": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Volume", "symbol": "m3"},
  "https://vocab.sentier.dev/units/unit/MegaJ": {"multiplier": 1000000.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Energy", "symbol": "MJ"},
  "https://vocab.sentier.dev/units/unit/NUM": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Population", "symbol": "{#}"},
  "https://vocab.sentier.dev/units/unit/PA": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Pressure", "symbol": "Pa"},
  "https://vocab.sentier.dev/units/unit/PERCENT": {"multiplier": 0.01, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/DimensionlessRatio", "symbol": "%"},
  "https://vocab.sentier.dev/units/unit/TONNE": {"multiplier": 1000.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Mass", "symbol": "t"},
  "https://vocab.sentier.dev/units/unit/TONNE-PER-YR": {"multiplier": 3.168808781402895e-05, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/MassPerTime", "symbol": "t.a-1"},
  "https://vocab.sentier.dev/units/unit/UNITLESS": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/LogOctanolWaterPartitionCoefficient", "symbol": null},
  "https://vocab.sentier.dev/units/unit/W-PER-M2": {"multiplier": 1.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Irradiance", "symbol": "W.m-2"},
  "https://vocab.sentier.dev/units/unit/YR": {"multiplier": 31557600.0, "offset": 0.0, "quantity_kind": "https://vocab.sentier.dev/units/quantity-kind/Time", "symbol": "a"}
}
```

Hatchling ships non-Python files inside the package directory, so no `pyproject.toml` change is needed. Verify after Step 5 with `uv build --wheel && unzip -l dist/*.whl | grep units.json`, then `rm -rf dist`.

- [ ] **Step 5: Implement `trailrunner/core/units.py`**

```python
"""Units as vocabulary IRIs, and the one catalog that knows how they relate.

A unit used to be whatever string a model author typed: ``"kg"`` here,
``"Nm3"`` there, ``"kg CO2eq"`` somewhere else. Two models meaning the same
unit could fail to compose, and nothing knew that a tonne is a thousand
kilograms. A unit is now a concept IRI from the sentier vocabulary's units
scheme (QUDT-derived), and ``UnitCatalog`` reads what the vocabulary says
about it: its quantity kind (what it may be converted into), its multiplier
to the SI base, and its UCUM symbol (what a person reads).

**Offline first, for the same reason as ``PystTaxonomy``.** The facts for
every constant below ship in ``units.json`` beside this module, so a run with
no network validates and converts exactly what an online one does. A catalog
given a ``client`` asks the vocabulary about anything else and caches the
answer; one without a client answers "not determined" for it, and the Runner
refuses a unit it cannot confirm rather than guessing.

This module talks to the network only through the client it is handed
(``trailrunner.resolution.pyst.PystHttpClient`` has the ``concept_payload``
method it needs); ``core`` itself never opens a connection.
"""

import json
import urllib.error
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from trailrunner.core.errors import UnknownUnit

VOCAB = "https://vocab.sentier.dev/units/unit/"

KG = VOCAB + "KiloGM"
GRAM = VOCAB + "GM"
TONNE = VOCAB + "TONNE"
J = VOCAB + "J"
MJ = VOCAB + "MegaJ"
KWH = VOCAB + "KiloW-HR"
M3 = VOCAB + "M3"
PA = VOCAB + "PA"
"""Pressure. The vocabulary has no plain ``BAR`` (nor kPa, MPa, hPa, atm)."""
KILOMETRE = VOCAB + "KiloM"
METRE = VOCAB + "M"
YEAR = VOCAB + "YR"
TONNE_PER_YEAR = VOCAB + "TONNE-PER-YR"
DEG_C = VOCAB + "DEG_C"
KELVIN = VOCAB + "K"
NUM = VOCAB + "NUM"
"""A count of items: a plant, a pipeline, a vehicle."""
UNITLESS = VOCAB + "UNITLESS"
PERCENT = VOCAB + "PERCENT"
W_PER_M2 = VOCAB + "W-PER-M2"

QUDT = "http://qudt.org/schema/qudt/"
SKOS_NOTATION = "http://www.w3.org/2004/02/skos/core#notation"
UCUM_CODE = QUDT + "ucumCode"
BUNDLED = Path(__file__).with_name("units.json")

NEVER_CONVERTED_KINDS = frozenset(
    {"https://vocab.sentier.dev/units/quantity-kind/Temperature"}
)
"""Quantity kinds whose units compare equal only to themselves.

Temperature, because the vocabulary gives ``DEG_C`` and ``K`` the same kind
and a multiplier of 1 **without** a ``conversionOffset``: converting by
multiplier alone would read 10 degC as 10 K. Refusing is honest; guessing an
offset the vocabulary does not state is not.
"""

_DISPLAY = {
    KWH: "kWh",
    NUM: "unit",
    DEG_C: "°C",
    TONNE_PER_YEAR: "t/yr",
    W_PER_M2: "W/m2",
    YEAR: "yr",
}
"""Where the UCUM code is correct but reads badly in a tree (``kW.h``, ``{#}``)."""


@dataclass(frozen=True)
class UnitInfo:
    """What the vocabulary says about one unit."""

    iri: str
    quantity_kind: str | None
    multiplier: float | None
    """Factor to the SI base unit of the quantity kind."""
    offset: float = 0.0
    symbol: str | None = None
    """UCUM code, as the vocabulary gives it."""


def _first(payload: dict, key: str) -> Any:
    values = payload.get(key) or []
    return values[0] if values else None


def parse_unit_payload(iri: str, payload: Any) -> UnitInfo | None:
    """Read a unit's facts out of ``GET /api/v1/concepts/<iri>``.

    The service answers the concept either as the object or a one-item list
    of it, keyed by full predicate URIs. Anything that is not a concept object
    is ``None``: a display-and-conversion path does not guess at a shape.
    """
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return None
    kind = _first(payload, QUDT + "hasQuantityKind")
    multiplier = _first(payload, QUDT + "conversionMultiplier")
    offset = _first(payload, QUDT + "conversionOffset")
    symbol = None
    for notation in payload.get(SKOS_NOTATION, []):
        if isinstance(notation, dict) and notation.get("@type") == UCUM_CODE:
            symbol = notation.get("@value")
            break
    return UnitInfo(
        iri=iri,
        quantity_kind=kind.get("@id") if isinstance(kind, dict) else None,
        multiplier=float(multiplier["@value"]) if isinstance(multiplier, dict) else None,
        offset=float(offset["@value"]) if isinstance(offset, dict) else 0.0,
        symbol=symbol,
    )


def _load(path: Path) -> dict[str, UnitInfo]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # A damaged cache costs a lookup, never the run.
        return {}
    return {iri: UnitInfo(iri=iri, **entry) for iri, entry in raw.items() if isinstance(entry, dict)}


class UnitCatalog:
    """Unit facts, bundled first, then ``cache_path``, then the client.

    ``cache_path`` is where facts learned from the client are written, so a
    study can commit them beside its other caches. Without one, nothing is
    written and the bundled file is never touched.
    """

    def __init__(self, cache_path: str | Path | None = None, client: Any | None = None) -> None:
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self.client = client
        self._info: dict[str, UnitInfo] = _load(BUNDLED)
        if self.cache_path is not None:
            self._info.update(_load(self.cache_path))
        self._unknown: set[str] = set()

    def save(self) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        serialised = {
            iri: {key: value for key, value in asdict(info).items() if key != "iri"}
            for iri, info in self._info.items()
        }
        self.cache_path.write_text(json.dumps(serialised, indent=2, sort_keys=True))

    def info(self, iri: str) -> UnitInfo | None:
        if iri in self._info:
            return self._info[iri]
        if iri in self._unknown or self.client is None or not iri.startswith(VOCAB):
            return None
        try:
            payload = self.client.concept_payload(iri)
        except urllib.error.HTTPError as error:
            # HTTPError before OSError: it is one. Only a 404 is an answer.
            if error.code == 404:
                self._unknown.add(iri)
            return None
        except (OSError, json.JSONDecodeError):
            return None
        info = parse_unit_payload(iri, payload)
        if info is None:
            return None
        self._info[iri] = info
        self.save()
        return info

    def known(self, iri: str) -> bool | None:
        """``True`` if the vocabulary has it, ``False`` if not, ``None`` if nobody could say.

        Anything that is not an IRI under the units scheme is ``False``
        without asking: strictness is the whole point.
        """
        if not isinstance(iri, str) or not iri.startswith(VOCAB):
            return False
        if self.info(iri) is not None:
            return True
        if iri in self._unknown:
            return False
        return None

    @property
    def unknown_iris(self) -> frozenset[str]:
        return frozenset(self._unknown)

    def convertible(self, source: str, target: str) -> bool:
        if source == target:
            return True
        a, b = self.info(source), self.info(target)
        if a is None or b is None:
            return False
        if a.quantity_kind is None or a.quantity_kind != b.quantity_kind:
            return False
        if a.quantity_kind in NEVER_CONVERTED_KINDS:
            return False
        if a.multiplier is None or b.multiplier is None:
            return False
        return a.offset == 0.0 and b.offset == 0.0

    def factor(self, source: str, target: str) -> float:
        """Multiply an amount in ``source`` by this to get it in ``target``."""
        if source == target:
            return 1.0
        if not self.convertible(source, target):
            raise ValueError(f"cannot convert {source!r} to {target!r}")
        return self._info[source].multiplier / self._info[target].multiplier

    def convert(self, amount: float, source: str, target: str) -> float:
        return amount * self.factor(source, target)

    def try_convert(self, amount: float, source: str, target: str) -> float | None:
        if not self.convertible(source, target):
            return None
        return self.convert(amount, source, target)

    def symbol(self, iri: str) -> str:
        """What a person reads: an override, the UCUM code, or the IRI's last segment.

        A string that is not an IRI is returned as written -- a display label
        such as a cumulative metric's ``W·yr/m2`` is not a unit to look up.
        """
        if not isinstance(iri, str) or not iri.startswith("http"):
            return str(iri)
        if iri in _DISPLAY:
            return _DISPLAY[iri]
        info = self._info.get(iri)
        if info is not None and info.symbol and not info.symbol.startswith("{"):
            return info.symbol
        return iri.rstrip("/").rsplit("/", 1)[-1]

    def resolve(self, text: str) -> str:
        """A unit IRI from an IRI, a vocabulary id (``KiloGM``) or a symbol (``kg``).

        Symbols are matched against what the catalog already knows -- the
        bundled units and anything cached -- and an ambiguous one is refused
        rather than picked.
        """
        if text.startswith("http"):
            if self.known(text) is True:
                return text
            raise UnknownUnit(f"{text!r} is not a unit of the vocabulary ({VOCAB})")
        candidate = VOCAB + text
        if self.info(candidate) is not None:
            return candidate
        matches = sorted(
            iri
            for iri, info in self._info.items()
            if text in (info.symbol, _DISPLAY.get(iri))
        )
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise UnknownUnit(f"{text!r} is ambiguous: {', '.join(matches)}; pass the IRI")
        raise UnknownUnit(
            f"{text!r} is not a unit IRI, a vocabulary id or the symbol of a known "
            f"unit; units come from {VOCAB} (e.g. {KG})"
        )


@lru_cache(maxsize=1)
def default_catalog() -> UnitCatalog:
    """The bundled, offline catalog. Shared: it never writes and never asks."""
    return UnitCatalog()


def symbol(iri: str) -> str:
    """``default_catalog().symbol(iri)``, for display code that has no catalog."""
    return default_catalog().symbol(iri)
```

- [ ] **Step 6: Add the cache-warming script**

Create `dev/warm_unit_cache.py`:

```python
"""Refresh ``trailrunner/core/units.json`` from the live vocabulary.

Asks the vocabulary about every unit constant in ``trailrunner.core.units``
and writes what it answers into the bundled cache. Prints any constant the
vocabulary does not have: that is an invented IRI, and it has to go.

    uv run python dev/warm_unit_cache.py
"""

import sys

from trailrunner.core import units
from trailrunner.core.units import BUNDLED, VOCAB, UnitCatalog
from trailrunner.resolution.pyst import default_client


def main() -> int:
    constants = sorted(
        value for name, value in vars(units).items()
        if name.isupper() and isinstance(value, str) and value.startswith(VOCAB) and value != VOCAB
    )
    # Start empty so a stale entry cannot survive a refresh.
    BUNDLED.write_text("{}")
    catalog = UnitCatalog(cache_path=BUNDLED, client=default_client())
    for iri in constants:
        catalog.info(iri)
    catalog.save()
    for iri in sorted(catalog.unknown_iris):
        print(f"NOT IN THE VOCABULARY: {iri}", file=sys.stderr)
    return 1 if catalog.unknown_iris else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_units.py -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add trailrunner/core/units.py trailrunner/core/units.json trailrunner/core/errors.py dev/warm_unit_cache.py tests/test_units.py
git commit -m "feat: add a unit catalog backed by the sentier units vocabulary"
```

---

### Task 2: Unit IRIs everywhere (mechanical migration + display)

**Files:**
- Modify: every `trailrunner/**/*.py`, `tests/*.py`, `examples/showcase_models.py`, `dev/build_showcase_params.py` that writes a unit string (via codemod)
- Modify: `trailrunner/models/natural_gas.py` (`MJ`, `NM3` constants), `trailrunner/models/electricity.py` (`ELECTRICITY_UNIT`)
- Modify: `trailrunner/core/flow.py` (`describe_context`), `trailrunner/orchestration/report.py` (tree line)
- Modify: `trailrunner/assessment/dynamic.py` (`default_functions` keys, `METRIC_UNITS`)
- Modify: `tests/test_cli.py` (embedded model source), `docs/content/writing_a_model.md` (executed by `tests/test_writing_a_model.py`)
- Regenerate: `examples/*_params.parquet` via `dev/build_showcase_params.py`

**Interfaces:**
- Consumes: Task 1 constants and `symbol`.
- Produces: every unit that reaches an `Exchange` is an IRI, except `"tkm"` (Task 5), `"bar"`/`"psi"` (Task 4) and allocation property units (stay free text). `Report.tree()` and `Flow.describe_context()` print `symbol(unit)`.

- [ ] **Step 1: Write the codemod**

Create `dev/_codemod_units.py` (deleted in Step 9):

```python
"""One-off: replace unit string literals with trailrunner.core.units constants."""

import re
import sys
from pathlib import Path

MAP = {
    "kg": "KG",
    "MJ": "MJ",
    "kWh": "KWH",
    "tonne": "TONNE",
    "Nm3": "M3",
    "unit": "NUM",
    "kg CO2eq": "KG",
    "kg CO2-eq": "KG",
    "year": "YEAR",
    "dimensionless": "UNITLESS",
    "degC": "DEG_C",
}
PATTERNS = [
    # unit="kg"  (keyword argument)
    (re.compile(r'\bunit="([^"]+)"'), lambda c: f"unit={c}"),
    # "unit": "kg"  (field descriptor dicts)
    (re.compile(r'"unit": "([^"]+)"'), lambda c: f'"unit": {c}'),
    # "flow_unit": "kg" / "product_unit": "kg"  (method and pack rows)
    (re.compile(r'"(flow_unit|product_unit)": "([^"]+)"'), None),
]


def migrate(path: Path) -> None:
    source = path.read_text()
    used: set[str] = set()

    def keyword(match):
        constant = MAP.get(match.group(1))
        if constant is None:
            return match.group(0)
        used.add(constant)
        return f"unit={constant}"

    def field(match):
        constant = MAP.get(match.group(1))
        if constant is None:
            return match.group(0)
        used.add(constant)
        return f'"unit": {constant}'

    def row(match):
        constant = MAP.get(match.group(2))
        if constant is None:
            return match.group(0)
        used.add(constant)
        return f'"{match.group(1)}": {constant}'

    source = PATTERNS[0][0].sub(keyword, source)
    source = PATTERNS[1][0].sub(field, source)
    source = PATTERNS[2][0].sub(row, source)
    if not used:
        return
    line = f"from trailrunner.core.units import {', '.join(sorted(used))}\n"
    lines = source.splitlines(keepends=True)
    last_import = max(
        (i for i, text in enumerate(lines) if text.startswith(("import ", "from "))),
        default=None,
    )
    if last_import is None:
        lines.insert(0, line)
    else:
        # Walk past a parenthesised import that spans several lines.
        end = last_import
        if lines[end].rstrip().endswith("("):
            while not lines[end].strip().startswith(")"):
                end += 1
        lines.insert(end + 1, line)
    path.write_text("".join(lines))
    print(f"{path}: {', '.join(sorted(used))}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        migrate(Path(name))
```

- [ ] **Step 2: Run the codemod**

```bash
uv run python dev/_codemod_units.py $(git ls-files 'trailrunner/*.py' 'trailrunner/**/*.py' 'tests/*.py' examples/showcase_models.py dev/build_showcase_params.py | grep -v 'trailrunner/core/units.py')
```

Expected: one line per touched file. Then `git diff --stat` and read the diff of `trailrunner/` in full.

- [ ] **Step 3: Fix what the codemod cannot**

1. `trailrunner/models/natural_gas.py`: delete the module constants `MJ = "MJ"` and `NM3 = "Nm3"` with their docstrings; import `MJ, M3` from `trailrunner.core.units`; replace every `NM3` with `M3` and every `volume_nm3` stays (it is a variable name). Keep the two `demand.unit != …` guards for now (Task 3 removes them); their messages use `symbol(...)`: `f"... only {symbol(MJ)} can be read that way"`.
2. `trailrunner/models/electricity.py`: `ELECTRICITY_UNIT = KWH` (import `KWH`), keep its docstring; in messages use `symbol(ELECTRICITY_UNIT)`.
3. `trailrunner/assessment/dynamic.py`: in `default_functions()` replace every key `(X, "kg")` with `(X, KG)`; set
   ```python
   METRIC_UNITS = {
       "radiative_forcing": W_PER_M2,
       "prospective_radiative_forcing": W_PER_M2,
       "GWP": KG,
       "pGWP": KG,
       "pGTP": KG,
   }
   CUMULATIVE_METRIC_UNITS = {
       # No vocabulary unit for W·yr/m2: a display label for a cumulative
       # result, never an exchange unit, so it stays a label.
       "radiative_forcing": "W·yr/m2",
       "prospective_radiative_forcing": "W·yr/m2",
       "GWP": KG,
       "pGWP": KG,
       "pGTP": KG,
   }
   ```
   Update the docstring sentence "kg CO2eq per year" to say the GWP metrics are in kg of CO2-equivalent, the equivalence belonging to the metric, not the unit.
4. `trailrunner/cli.py`: print `symbol(dynamic.cumulative_unit)` instead of the raw unit.
5. `trailrunner/assessment/static.py`: in the summary line use `symbol(self.unit)`.
6. `trailrunner/core/flow.py`, `describe_context`:
   ```python
   return ", ".join(
       f"{entry.name}={entry.value:g} {symbol(entry.unit)}" for entry in self.context
   )
   ```
   with `from trailrunner.core.units import symbol`.
7. `trailrunner/orchestration/report.py`, the `line(...)` helper inside `tree()`:
   ```python
   lines.append(f"{indent * depth}{amount:g} {symbol(unit)} {name(flow.iri)}{_where(flow)}  {tag}")
   ```
   Check `summary()` and any other f-string in `report.py` printing a unit; route each through `symbol`.
8. `tests/test_cli.py`, fixture `models_file`: the embedded module text now contains `unit=KG` — add `from trailrunner.core.units import KG` to the embedded source's imports. Its CLI invocations keep `--unit kg`. In `trailrunner/cli.py` build the demand with `unit=default_catalog().resolve(args.unit)` so `kg` becomes the IRI; Task 11 replaces this line with proper error handling.
9. `docs/content/writing_a_model.md`: every code block `unit="kWh"`/`"kg"`/`"MJ"` becomes the constant, and each block that uses one imports it: `from trailrunner.core.units import KG, KWH, MJ`.
10. `dev/build_showcase_params.py`: in `_write`, a field unit that is an IRI is written as-is (no change needed: it is a string). The `TIME_FIELD` unit `"year"` becomes `YEAR` (codemod did it); ratio units (`"kg/Nm3"`, `"MJ/tkm"`, …) stay text. Map `"kg"` in `co2_factor` etc. is already `KG`.

- [ ] **Step 4: Regenerate the example parameter files**

Run: `uv run python dev/build_showcase_params.py`
Expected: it rewrites the eight `examples/*_params.parquet`. Check one:

```bash
uv run python -c "import pyarrow.parquet as pq; print(pq.read_table('examples/cement_params.parquet').schema.metadata[b'datapackage.json'][:400])"
```
Expected: `"unit": {"name": "https://vocab.sentier.dev/units/unit/KiloGM"}` (or `MegaJ`, `KiloW-HR`) on the columns models read through `unit_of`.

- [ ] **Step 5: Add a regression test for display**

Append to `tests/test_report_text.py`:

```python
def test_tree_prints_unit_symbols_not_iris():
    from trailrunner.core.flow import Demand, Flow
    from trailrunner.core.units import KWH
    from trailrunner.orchestration.log import Log
    from trailrunner.orchestration.report import Report
    from trailrunner.core.result import Result
    from trailrunner.core.flow import Exchange

    log = Log()
    demand = Demand(flow=Flow(iri="https://example.org/power"), amount=2.0, unit=KWH)
    log.write(demand, Result(production=[Exchange(flow=demand.flow, amount=2.0, unit=KWH)]),
              depth=0, parent=None, model="Plant", resolution={"tier": "model"})
    tree = Report.from_log(log).tree()
    assert "2 kWh power" in tree
    assert "units/unit" not in tree
```

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. Failures here are expected to be string assertions on printed units (e.g. a test asserting `"kg CO2eq"` in a summary now sees `"kg"`); update each expected string to what `symbol()` prints. Do not change library behaviour to satisfy an old string.

- [ ] **Step 7: Check nothing unit-shaped was missed**

Run: `git grep -nE 'unit="[^"]+"|"(flow_|product_)?unit": "[^"]+"' -- trailrunner tests examples/showcase_models.py`
Expected: only `"tkm"`, `"bar"`, `"psi"`, `"EUR"` (allocation property), `""` (empty-unit tests), and ratio-column descriptors in `dev/`/tests fixtures that no `unit_of` reads. Anything else: migrate it.

- [ ] **Step 8: Run the suite again**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
rm dev/_codemod_units.py
git add -A
git commit -m "refactor: write units as vocabulary IRIs and print their symbols"
```

---

### Task 3: Exact unit conversion at tier 1

**Files:**
- Modify: `trailrunner/params/coverage.py` (`Coverage.units`)
- Modify: `trailrunner/resolution/models.py` (conversion, `unit_mismatch`)
- Modify: `trailrunner/resolution/generalising.py` (carry the inner conversion)
- Modify: `trailrunner/orchestration/report.py` (`_tag`)
- Modify: `trailrunner/orchestration/orchestrator.py`, `trailrunner/orchestration/runner.py` (accept `units`)
- Modify: `trailrunner/models/natural_gas.py`, `trailrunner/models/electricity.py`, `trailrunner/models/cement.py` (guards → `Coverage.units`)
- Test: `tests/test_unit_conversion.py` (new), existing `tests/test_natural_gas.py`, `tests/test_electricity.py`

**Interfaces:**
- Consumes: `UnitCatalog.convertible/factor/symbol`, `default_catalog()`.
- Produces:
  - `Coverage.units: frozenset[str] | None = None`
  - `ModelProvider(glossary: Glossary, units: UnitCatalog | None = None)`; `ModelProvider.units: UnitCatalog`
  - resolution key `"conversion"`: `str`, e.g. `"unit: t -> kg ×1000"`
  - `ModelProvider.explain` may return `("unit_mismatch", detail)`
  - `Runner(glossary=None, settings=None, units: UnitCatalog | None = None)`; `Orchestrator(..., units: UnitCatalog | None = None)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_unit_conversion.py`:

```python
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.units import KG, M3, MJ, TONNE
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.coverage import Coverage
from trailrunner.resolution.chain import ResolutionChain
from trailrunner.resolution.generalising import GeneralisingProvider, StaticTaxonomy
from trailrunner.resolution.models import ModelProvider

CEMENT = "https://example.org/cement"
BINDER = "https://example.org/binder"
CO2 = "https://example.org/co2"


class PerKilogram(Model):
    """Emits 0.5 kg CO2 per kg -- only right if it is really handed kilograms."""

    produces = [CEMENT]
    coverage = Coverage(units=frozenset({KG}))

    def apply(self, demand):
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            biosphere=[Exchange(flow=Flow(iri=CO2), amount=0.5 * demand.amount, unit=KG)],
        )


def test_a_tonne_demand_reaches_a_kilogram_model_as_kilograms():
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=2.0, unit=TONNE)
    )
    assert report.inventory[(Flow(iri=CO2), KG)] == 1000.0
    node = report.nodes[0]
    assert node.demand.unit == TONNE  # the log keeps what was asked
    assert node.resolution["tier"] == "model"
    assert node.resolution["conversion"] == "unit: t -> kg ×1000"
    assert report.proxies == {}  # a conversion concedes nothing


def test_the_tree_shows_the_conversion():
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=2.0, unit=TONNE)
    )
    assert "[model: PerKilogram; unit: t -> kg ×1000]" in report.tree()


def test_the_demanded_unit_is_used_as_is_when_declared():
    offer = ModelProvider(Glossary([PerKilogram()])).offer(
        Demand(flow=Flow(iri=CEMENT), amount=5.0, unit=KG)
    )
    assert offer.demand.amount == 5.0
    assert "conversion" not in offer.resolution


def test_a_model_without_declared_units_takes_any_unit():
    class Anything(PerKilogram):
        coverage = None

    offer = ModelProvider(Glossary([Anything()])).offer(
        Demand(flow=Flow(iri=CEMENT), amount=5.0, unit=MJ)
    )
    assert offer.demand.unit == MJ


def test_another_quantity_kind_is_a_unit_mismatch_not_a_crash():
    # Review focus 4.
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=1.0, unit=M3)
    )
    assert report.nodes == []
    [record] = report.unresolved
    assert record.reason == "unit_mismatch"
    assert "PerKilogram" in record.detail and "m3" in record.detail and "kg" in record.detail


def test_a_generalised_demand_is_converted_too():
    class BinderPerKg(PerKilogram):
        produces = [BINDER]

    chain = ResolutionChain(
        [
            ModelProvider(Glossary([BinderPerKg()])),
            GeneralisingProvider(
                ModelProvider(Glossary([BinderPerKg()])),
                taxonomy=StaticTaxonomy({CEMENT: [BINDER]}),
            ),
        ]
    )
    report = Orchestrator(chain).calculate(Demand(flow=Flow(iri=CEMENT), amount=1.0, unit=TONNE))
    node = report.nodes[0]
    assert node.resolution["tier"] == "generalising"
    assert node.resolution["conversion"] == "unit: t -> kg ×1000"
    assert report.inventory[(Flow(iri=CO2), KG)] == 500.0
    assert "unit: t -> kg ×1000" in report.tree()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_unit_conversion.py -q`
Expected: FAIL — `TypeError: Coverage.__init__() got an unexpected keyword argument 'units'`.

- [ ] **Step 3: Add `Coverage.units`**

In `trailrunner/params/coverage.py`, add the field after `context`, and extend the class docstring:

```python
    units: frozenset[str] | None = None
    """Unit IRIs the model answers in; ``None`` means any unit, passed through.

    Not a restriction on *whether* the model answers but on *what it is
    handed*: a demand in another unit of the same quantity kind is converted
    exactly before ``apply`` sees it (``ModelProvider``), and one of another
    kind is not answered at all. ``covers`` does not read this field, because
    a unit is on the demand, not on the flow.
    """
```

- [ ] **Step 4: Convert in `ModelProvider`**

Replace `trailrunner/resolution/models.py`'s class body with:

```python
class ModelProvider:
    """A Provider over a Glossary: exact product IRI, within coverage.

    Also where a demand meets the unit its model reasons in. A model that
    declares ``Coverage.units`` is handed the demand in one of them: converted
    exactly when the quantity kind matches (1 t becomes 1000 kg), refused when
    it does not. The conversion is recorded under ``"conversion"`` and is not
    a proxy -- it loses nothing -- so the tier stays ``"model"``.
    """

    def __init__(self, glossary: Glossary, units: UnitCatalog | None = None) -> None:
        self.glossary = glossary
        self.units = units if units is not None else default_catalog()

    def offer(self, demand: Demand, exclude: Sequence[Model] = ()) -> Offer | None:
        model = self.glossary.resolve(demand.flow, exclude=exclude)
        if model is None:
            return None
        answered, conversion = self._in_model_unit(demand, model)
        if answered is None:
            return None
        resolution = {
            "model": type(model).__name__,
            # ``asked`` and ``answered`` are identical here, and said anyway:
            # they are the two keys a reader compares across tiers, and one
            # that is present only when it differs is a key whose absence has
            # to be interpreted. See ``chain``'s module docstring.
            "asked": describe(demand),
            "answered": describe(answered),
        }
        if conversion is not None:
            resolution["conversion"] = conversion
        return Offer(model=model, demand=answered, tier="model", resolution=resolution)

    def _in_model_unit(self, demand: Demand, model: Model) -> tuple[Demand | None, str | None]:
        accepted = model.coverage.units if model.coverage is not None else None
        if accepted is None or demand.unit in accepted:
            return demand, None
        for target in sorted(accepted):
            if self.units.convertible(demand.unit, target):
                factor = self.units.factor(demand.unit, target)
                converted = replace(demand, amount=demand.amount * factor, unit=target)
                note = (
                    f"unit: {self.units.symbol(demand.unit)} -> "
                    f"{self.units.symbol(target)} ×{factor:g}"
                )
                return converted, note
        return None, None

    def explain(self, demand: Demand, exclude: Sequence[Model] = ()) -> tuple[str, str] | None:
        """A unit mismatch, a coverage miss, or nothing.

        (Keep the existing paragraph about ``exclude`` here.)

        A unit mismatch is checked first because it is the more specific
        answer: the model covers this flow and would answer it, in a unit the
        demand cannot be converted into.
        """
        model = self.glossary.resolve(demand.flow, exclude=exclude)
        if model is not None:
            accepted = sorted(model.coverage.units)  # non-None, or offer() would have answered
            return (
                "unit_mismatch",
                f"{type(model).__name__} answers {demand.flow.iri} in "
                f"{', '.join(self.units.symbol(unit) for unit in accepted)} but the demand is in "
                f"{self.units.symbol(demand.unit)}, a different quantity",
            )
        near_misses = self.glossary.declared_models(demand.flow, exclude=exclude)
        if not near_misses:
            return None
        names = ", ".join(type(model).__name__ for model in near_misses)
        context = f" context={demand.flow.describe_context()!r}" if demand.flow.context else ""
        return (
            "coverage_excluded",
            f"{names} declares this product but its coverage does not cover "
            f"location={demand.flow.location!r} time={demand.flow.time!r}{context}",
        )
```

Imports at top: `from dataclasses import replace` and `from trailrunner.core.units import UnitCatalog, default_catalog`.

- [ ] **Step 5: Carry the conversion through tier 2**

In `GeneralisingProvider.offer`, replace the `return Offer(...)` with:

```python
                resolution = {
                    "model": type(inner_offer.model).__name__,
                    "relaxations": notes,
                    "asked": describe(demand),
                    "answered": describe(candidate),
                }
                conversion = inner_offer.resolution.get("conversion")
                if conversion is not None:
                    resolution["conversion"] = conversion
                return Offer(
                    model=inner_offer.model,
                    # The inner offer's demand, not the candidate: it is the
                    # candidate already converted into the model's unit.
                    demand=inner_offer.demand,
                    tier="generalising",
                    resolution=resolution,
                )
```

- [ ] **Step 6: Show it in the tag**

In `Report._tag`, compute once at the top:

```python
        conversion = node.resolution.get("conversion")
        suffix = f"; {conversion}" if conversion else ""
```

and use it: generalising → `f"[proxy: {joined}{suffix}]" if relaxations else f"[proxy{suffix}]"`; model → `f"[model: {node.model}{suffix}]" if node.model else f"[model{suffix}]"`. Background is unchanged.

- [ ] **Step 7: Thread a catalog through Orchestrator and Runner**

- `Runner.__init__(self, glossary=None, settings=None, units: UnitCatalog | None = None)`: store `self.units = units if units is not None else default_catalog()` (Task 6 uses it).
- `Orchestrator.__init__(..., settings=None, units: UnitCatalog | None = None)`: build the default chain as `ResolutionChain([ModelProvider(resolver, units=units)])` and the default runner as `Runner(self.glossary, settings=self.settings, units=units)`.

- [ ] **Step 8: Replace the hand-written guards with declarations**

- `NaturalGasSupply.coverage = Coverage(time_range=..., context=..., units=frozenset({MJ}))`; delete the `if demand.unit != MJ: raise ...` block and move its explanation into the `MJ`-related docstring: "Energy content is MJ/Nm3, so the model is handed MJ: ``Coverage.units`` converts a kWh demand and refuses a kg one."
- `NaturalGasExtraction.coverage = Coverage(time_range=..., units=frozenset({M3}))`; delete its guard.
- `GasPower.coverage = Coverage(time_range=..., units=frozenset({ELECTRICITY_UNIT}))`; delete its guard.
- `CementPlant.coverage = Coverage(time_range=(2026, 2050), units=frozenset({KG}))` and `MeteredCementPlant.coverage = Coverage(time_range=(2018, 2025), units=frozenset({KG}))` — both compute per kg (`clinker_factor * demand.amount`, `REFERENCE_OUTPUT = 1000.0 # kg`).
- Remove now-unused `ValidationError` imports.

- [ ] **Step 9: Update the tests that expected the guards to raise**

In `tests/test_natural_gas.py`, replace `test_supply_rejects_a_unit_its_energy_content_cannot_read` and `test_extraction_rejects_a_unit_its_factors_cannot_read` (fixtures `supply`, `extraction`; helpers `gas(...)`, `wellhead(...)` already in the file) with:

```python
def test_supply_refuses_a_mass_demand_as_a_unit_mismatch(supply):
    provider = ModelProvider(Glossary([supply]))
    assert provider.offer(gas(unit=KG)) is None
    reason, detail = provider.explain(gas(unit=KG))
    assert reason == "unit_mismatch"
    assert "NaturalGasSupply" in detail


def test_supply_is_handed_mj_for_a_kwh_demand(supply):
    offer = ModelProvider(Glossary([supply])).offer(gas(amount=1.0, unit=KWH))
    assert offer.demand.unit == MJ
    assert offer.demand.amount == pytest.approx(3.6)


def test_extraction_refuses_a_mass_demand_as_a_unit_mismatch(extraction):
    provider = ModelProvider(Glossary([extraction]))
    assert provider.offer(wellhead(unit=KG, time=2020)) is None
    assert provider.explain(wellhead(unit=KG, time=2020))[0] == "unit_mismatch"
```

Imports: `ModelProvider` from `trailrunner.resolution.models`, `KG, KWH, MJ` from `trailrunner.core.units`. Then run `uv run pytest -q 2>&1 | grep FAILED` and handle `tests/test_electricity.py`'s wrong-unit test for `GasPower` the same way (offer `None`, explain `unit_mismatch`).

- [ ] **Step 10: Run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: convert a demand exactly into the unit its model declares"
```

---

### Task 4: Context conditions in any unit of their kind; pressure in Pa

**Files:**
- Modify: `trailrunner/params/coverage.py` (`ContextRange` docstring, `Coverage.covers`)
- Modify: `trailrunner/core/settings.py` (`context_tolerance` 3-tuple)
- Modify: `trailrunner/resolution/generalising.py` (`_context_candidates`)
- Modify: `trailrunner/models/natural_gas.py` (`DELIVERY_PRESSURE_PA`), `trailrunner/models/cement.py` (`burner_pressure` in Pa)
- Test: `tests/test_coverage.py`, `tests/test_generalising.py`, `tests/test_settings.py`, `tests/test_cement.py`

**Interfaces:**
- Consumes: `UnitCatalog.try_convert`, `default_catalog`, `symbol`, `PA`, `KILOMETRE`, `METRE`.
- Produces:
  - `Coverage.covers(flow: Flow, units: UnitCatalog | None = None) -> bool`
  - `ProxySettings.context_tolerance: dict[str, tuple[float, float, str]]` — `(below, above, unit IRI)`
  - `trailrunner.models.natural_gas.DELIVERY_PRESSURE_PA = 5e5`; `CementPlant(burner_pressure=<Pa>)`

- [ ] **Step 1: Write the failing tests**

In `tests/test_coverage.py`, replace the `"bar"`/`"psi"` tests with:

```python
from trailrunner.core.units import KG, KILOMETRE, METRE, PA


def test_context_is_matched_in_the_declared_unit():
    coverage = Coverage(context=(ContextRange("pressure", PA, 5e5, 5e5),))
    assert coverage.covers(Flow(iri="gas", context=(Property("pressure", 5e5, PA),)))
    assert not coverage.covers(Flow(iri="gas", context=(Property("pressure", 4e5, PA),)))


def test_context_in_another_unit_of_the_same_kind_is_converted():
    coverage = Coverage(context=(ContextRange("distance", KILOMETRE, 0.0, 2000.0),))
    assert coverage.covers(Flow(iri="t", context=(Property("distance", 1.5e6, METRE),)))
    assert not coverage.covers(Flow(iri="t", context=(Property("distance", 2.5e6, METRE),)))


def test_context_of_another_kind_is_not_covered():
    coverage = Coverage(context=(ContextRange("pressure", PA, 0.0, 1e6),))
    assert not coverage.covers(Flow(iri="gas", context=(Property("pressure", 4.0, KG),)))
```

Keep the existing tests for "a flow naming no condition is covered" and "minimum above maximum raises", rewritten with `PA`.

In `tests/test_settings.py`:

```python
def test_context_tolerance_carries_its_unit():
    settings = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})
    assert settings.context_tolerance["pressure"][2] == PA


@pytest.mark.parametrize("bounds", [(0.0, 1.0), (-1.0, 1.0, PA), (0.0, 1.0, 5)])
def test_context_tolerance_rejects_bad_bounds(bounds):
    with pytest.raises(ValueError, match="context tolerance"):
        ProxySettings(context_tolerance={"pressure": bounds})
```

In `tests/test_generalising.py` (block starting at `GAS = ...`, around line 505), rewrite in Pa:

```python
class FiveBarGas(Model):
    produces = [GAS]
    coverage = Coverage(context=(ContextRange("pressure", PA, 5e5, 5e5),))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def gas_at(pascal, unit=PA):
    return Demand(
        flow=Flow(iri=GAS, location="CH", time=2030, context=(Property("pressure", pascal, unit),)),
        amount=10.0,
        unit=MJ,
    )


PRESSURE_UP_TO_ONE_BAR_HIGHER = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})
```

Every call `gas_at(4.0)` becomes `gas_at(4e5)` (6.0 → 6e5, 3.0 → 3e5, 60.0 → 60.0); expected values `Property("pressure", 5e5, PA)`; notes `"context: pressure 400000 Pa -> 500000 Pa"`; `asked`/`answered` suffixes `"[pressure=4e+05 Pa]"` / `"[pressure=5e+05 Pa]"`. Replace `test_context_in_another_unit_is_not_relaxed` with:

```python
def test_context_in_another_quantity_kind_is_not_relaxed():
    settings = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})
    assert provider([FiveBarGas()], settings=settings).offer(gas_at(4.0, unit=KG)) is None


HAUL = "https://vocab.sentier.dev/products/haul"


class TenKilometreHaul(Model):
    produces = [HAUL]
    coverage = Coverage(context=(ContextRange("distance", KILOMETRE, 10.0, 10.0),))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def test_context_tolerance_in_another_unit_than_the_ask():
    settings = ProxySettings(context_tolerance={"distance": (0.0, 1.0, KILOMETRE)})
    asked = Demand(
        flow=Flow(iri=HAUL, context=(Property("distance", 9500.0, METRE),)),
        amount=1.0,
        unit=TONNE,
    )
    offer = provider([TenKilometreHaul()], settings=settings).offer(asked)
    assert offer.demand.flow.get_context("distance") == Property("distance", 10000.0, METRE)
    assert offer.resolution["relaxations"] == ["context: distance 9500 m -> 10000 m"]
```

Imports: `KG, KILOMETRE, METRE, MJ, PA, TONNE` from `trailrunner.core.units`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_coverage.py tests/test_settings.py tests/test_generalising.py -q`
Expected: FAIL (conversion not implemented; 2-tuples accepted).

- [ ] **Step 3: Convert in `Coverage.covers`**

```python
    def covers(self, flow: Flow, units: UnitCatalog | None = None) -> bool:
        catalog = units if units is not None else default_catalog()
        # (location and time checks unchanged)
        for declared in self.context:
            asked = flow.get_context(declared.name)
            if asked is None:
                continue
            value = catalog.try_convert(asked.value, asked.unit, declared.unit)
            if value is None:
                return False
            if not declared.minimum <= value <= declared.maximum:
                return False
        return True
```

Replace the `ContextRange` docstring's last paragraph with: "The unit is a vocabulary IRI. A flow asking in another unit of the same quantity kind is converted exactly before it is compared (4e5 Pa and a range in Pa; 1500 m against a range in km); one asking in another kind is not covered. Converting used to be refused here because a unit was a string and converting it meant guessing; with the catalog it does not."

- [ ] **Step 4: `context_tolerance` gains a unit**

In `ProxySettings`:

```python
    context_tolerance: dict[str, tuple[float, float, str]] = field(default_factory=dict)
    """Per context condition, how far ``(below, above, unit)`` the asked value may move.

    (keep the safe-side paragraph, now with) ... so pressure wants
    ``(0.0, 1e5, PA)``, not ``1e5`` either way. The unit says what the two
    numbers are in, because a condition may be asked in any unit of its kind:
    "1 above" means nothing until it says 1 of what.
    """
```

Validation in `__post_init__`:

```python
        for name, bounds in self.context_tolerance.items():
            if (
                len(bounds) != 3
                or not isinstance(bounds[2], str)
                or any(not isinstance(bound, (int, float)) or bound < 0 for bound in bounds[:2])
            ):
                raise ValueError(
                    f"{bounds!r} is not a valid context tolerance for {name!r}; "
                    "must be (below, above, unit) with both bounds >= 0"
                )
```

- [ ] **Step 5: Work in the tolerance's unit in `_context_candidates`**

```python
        catalog = self.inner.units
        found: dict[tuple[str, float], tuple[float, Property]] = {}
        for asked in demand.flow.context:
            tolerance = self.settings.context_tolerance.get(asked.name)
            if tolerance is None:
                continue
            below, above, unit = tolerance
            asked_value = catalog.try_convert(asked.value, asked.unit, unit)
            if asked_value is None:
                continue
            for model in self.inner.glossary.declared_models(demand.flow):
                if model.coverage is None:
                    continue
                declared = model.coverage.context_range(asked.name)
                if declared is None:
                    continue
                low = catalog.try_convert(declared.minimum, declared.unit, unit)
                high = catalog.try_convert(declared.maximum, declared.unit, unit)
                if low is None or high is None:
                    continue
                value = min(max(asked_value, low), high)
                shift = value - asked_value
                if shift == 0 or not -below <= shift <= above:
                    continue
                # Written back in the unit the demander asked in.
                snapped = catalog.convert(value, unit, asked.unit)
                found.setdefault((asked.name, snapped), (abs(shift), asked))
        ranked = sorted(found.items(), key=lambda item: (item[1][0], item[0]))
        for step, ((name, value), (_distance, asked)) in enumerate(islice(ranked, budget), 1):
            context = tuple(
                replace(entry, value=value) if entry.name == name else entry
                for entry in demand.flow.context
            )
            flow = replace(demand.flow, context=context)
            shown = symbol(asked.unit)
            note = f"context: {name} {asked.value:g} {shown} -> {value:g} {shown}"
            yield replace(demand, flow=flow), note, step
```

Update the docstring sentence "A condition with no tolerance, or declared by a model in another unit, is not moved at all" → "…or declared in a unit of another quantity kind…". Import `symbol`.

- [ ] **Step 6: Pressure in Pa in the models**

- `natural_gas.py`: rename `DELIVERY_PRESSURE_BAR = 5.0` → `DELIVERY_PRESSURE_PA = 5e5` ("5 bar: a medium-pressure distribution grid, in Pa because that is the vocabulary's pressure unit"); coverage `ContextRange("pressure", PA, DELIVERY_PRESSURE_PA, DELIVERY_PRESSURE_PA)`.
- `cement.py`: `burner_pressure` docstring "(Pa)"; `_gas` writes `Property("pressure", self.burner_pressure, PA)`.
- `tests/test_cement.py:101`: `CementPlant(..., burner_pressure=4e5)` and `(Property("pressure", 4e5, PA),)`.

- [ ] **Step 7: Run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: compare and relax context conditions across units of one kind"
```

---

### Task 5: Pipeline transport in tonnes over a distance

**Files:**
- Modify: `trailrunner/models/natural_gas_pipeline_transport.py`
- Modify: `trailrunner/models/natural_gas.py` (`NaturalGasSupply` transport demand)
- Modify: `dev/build_showcase_params.py` (unit docs of pipeline ratio columns unchanged; nothing else)
- Modify: `dev/build_background_pack.py`, regenerate `examples/background_pack.parquet`
- Modify: `dev/reverse-engineering of BAFU pipeline transport datasets/validate_pipeline_model.py` (if it builds `Demand`s)
- Test: `tests/test_natural_gas_pipeline_transport.py`, `tests/test_natural_gas.py`, `tests/test_background.py`

**Interfaces:**
- Consumes: `TONNE`, `KILOMETRE`, `M3`, `MJ`, `KG`, `NUM`, `Coverage.units`, `default_catalog().try_convert`.
- Produces:
  - `natural_gas_pipeline_transport.DISTANCE = "distance"`
  - `NaturalGasOffshorePipelineTransport` answers `TONNE` with context `Property(DISTANCE, km, KILOMETRE)`; `coverage.units = frozenset({TONNE})`
  - lorry demand: `FREIGHT_LORRY` in `TONNE`, same `distance` context
  - `NaturalGasSupply` provenance keys `transport_tonnes`, `transport_km` (replacing `transport_tkm`)

- [ ] **Step 1: Write the failing tests**

In `tests/test_natural_gas_pipeline_transport.py`, replace the `demand` helper and add tests:

```python
from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Property
from trailrunner.core.units import KILOMETRE, METRE, TONNE
from trailrunner.models.natural_gas_pipeline_transport import DISTANCE, FREIGHT_LORRY


def demand(location="DZ", amount=1.0, km=1.0, unit=KILOMETRE):
    """1 t over 1 km is the old 1 tkm functional unit, number for number."""
    return Demand(
        flow=Flow(iri=TRANSPORT, location=location, time=2025,
                  context=(Property(DISTANCE, km, unit),)),
        amount=amount,
        unit=TONNE,
    )


def test_tonnes_times_distance_is_the_old_tkm(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    one_tkm = model.apply(demand(amount=1.0, km=1.0))
    ten_t_100_km = model.apply(demand(amount=10.0, km=100.0))
    turbine = lambda r: next(e for e in r.technosphere if e.flow.iri == NATURAL_GAS_BURNED_IN_GAS_TURBINE)
    assert turbine(ten_t_100_km).amount == pytest.approx(1000 * turbine(one_tkm).amount)


def test_distance_in_metres_is_the_same_distance(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    in_km = model.apply(demand(km=2.0))
    in_m = model.apply(demand(km=2000.0, unit=METRE))
    assert [e.amount for e in in_m.biosphere] == pytest.approx([e.amount for e in in_km.biosphere])


def test_a_demand_without_a_distance_is_refused(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    bare = Demand(flow=Flow(iri=TRANSPORT, location="DZ", time=2025), amount=1.0, unit=TONNE)
    with pytest.raises(ValidationError, match="distance"):
        model.apply(bare)


def test_the_lorry_leg_travels_the_same_distance(pipeline_params):
    result = NaturalGasOffshorePipelineTransport(params=pipeline_params).apply(demand(amount=3.0, km=50.0))
    lorry = next(e for e in result.technosphere if e.flow.iri == FREIGHT_LORRY)
    assert lorry.unit == TONNE
    assert lorry.flow.get_context(DISTANCE) == Property(DISTANCE, 50.0, KILOMETRE)
    assert lorry.amount == pytest.approx(HIGH["lorry_factor"] * 3.0)
```

Keep every existing numeric test; they now call `demand(...)` with the defaults (1 t, 1 km), so their expected values are unchanged. Update `leaked_volume_nm3_per_tkm` references if you rename it (don't: the per-tkm rate is still what the parameter is).

In `tests/test_natural_gas.py`, replace `test_supply_converts_volume_to_tonne_kilometres` and `test_a_further_origin_means_more_transport_for_the_same_energy`:

```python
def test_supply_demands_tonnes_over_the_route(supply):
    result = supply.apply(gas())
    transport = [d for d in result.technosphere if d.flow.iri == TRANSPORT][0]
    # 68.75 m3 * 0.735 kg/m3 = 50.53 kg = 0.05053 t, over 1000 km.
    assert transport.amount == pytest.approx(2475.0 / 36.0 * 0.735 / 1000)
    assert transport.unit == TONNE
    assert transport.flow.get_context(DISTANCE) == Property(DISTANCE, 1000.0, KILOMETRE)
    assert result.provenance["transport_km"] == 1000.0


def test_a_further_origin_means_more_transport_for_the_same_energy(supply):
    danish = supply.apply(gas(location="DK")).provenance
    european = supply.apply(gas(location="RER")).provenance
    assert european["origin"] == "RU"
    assert european["transport_tonnes"] * european["transport_km"] == pytest.approx(
        4 * danish["transport_tonnes"] * danish["transport_km"]
    )
```

and in `test_supply_converts_energy_to_wellhead_volume` the unit assertion is `volume.unit == M3`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_natural_gas_pipeline_transport.py tests/test_natural_gas.py -q`
Expected: FAIL (`ImportError: cannot import name 'DISTANCE'`).

- [ ] **Step 3: Remodel the pipeline model**

Module docstring: replace the first paragraph's opening with "The functional unit is 1 t of gas transported, over the distance the demand states in its context (``distance``, any length unit): 1 t over 1 km is the ecoinvent dataset's 1 tkm, number for number. The route length is the demander's to state -- ``NaturalGasSupply`` knows it per consumer -- and the per-tkm parameters below are applied to tonnes × km." Then:

```python
DISTANCE = "distance"
"""The context condition carrying how far the gas travels."""


class NaturalGasOffshorePipelineTransport(Model):
    """Transports tonnes of natural gas over a stated distance by offshore pipeline."""

    produces = [TRANSPORT]
    coverage = Coverage(locations=DOCUMENTED_LOCATIONS, units=frozenset({TONNE}))

    # supports unchanged

    def apply(self, demand: Demand) -> Result:
        distance = demand.flow.get_context(DISTANCE)
        if distance is None:
            raise ValidationError(
                f"{type(self).__name__} moves tonnes of gas over a distance, and the "
                f"demand for {demand.flow.iri} states none; add "
                f"Property({DISTANCE!r}, <km>, KILOMETRE) to the flow's context"
            )
        km = default_catalog().try_convert(distance.value, distance.unit, KILOMETRE)
        if km is None:
            raise ValidationError(
                f"{type(self).__name__} was given a distance in "
                f"{symbol(distance.unit)}, which is not a length"
            )
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        tkm = demand.amount * km
        location, time = demand.flow.location, demand.flow.time

        def flow(iri: str) -> Flow:
            return Flow(iri=iri, location=location, time=time)

        leaked_nm3 = leaked_volume_nm3_per_tkm(row["leakage_rate_per_1000km"], row["gas_density_kg_per_nm3"]) * tkm

        technosphere = [
            Demand(flow=flow(PIPELINE_INFRASTRUCTURE), amount=row["infra_factor"] * tkm, unit=NUM),
            Demand(flow=flow(NATURAL_GAS_AT_PRODUCTION), amount=leaked_nm3, unit=M3),
            Demand(
                flow=flow(NATURAL_GAS_BURNED_IN_GAS_TURBINE),
                amount=row["gas_turbine_mj_per_tkm"] * tkm,
                unit=MJ,
            ),
            # lorry_factor is lorry tkm per pipeline tkm, so the same distance
            # carries lorry_factor × tonnes.
            Demand(
                flow=replace(flow(FREIGHT_LORRY), context=(distance,)),
                amount=row["lorry_factor"] * demand.amount,
                unit=TONNE,
            ),
            Demand(
                flow=flow(MINERAL_OIL_DISPOSAL),
                amount=row["mineral_oil_disposal_factor"] * tkm,
                unit=KG,
            ),
        ]

        biosphere = [
            Exchange(flow=flow(iri), amount=leaked_nm3 * row[column], unit=KG)
            for iri, column in _COMPOSITION_FLOWS
            if row[column] is not None
        ]
        biosphere.append(Exchange(flow=flow(HALON_1211), amount=row["halon1211_rate_kg_per_tkm"] * tkm, unit=KG))
        biosphere.append(Exchange(flow=flow(HFC_23), amount=row["hfc23_rate_kg_per_tkm"] * tkm, unit=KG))

        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=technosphere,
            biosphere=biosphere,
            provenance=dict(row.provenance)
            | {"tier": row["tier"], "leaked_volume_nm3": leaked_nm3, "tkm": tkm},
        )
```

Imports: `from dataclasses import replace`, `ValidationError`, `from trailrunner.core.units import KG, KILOMETRE, M3, MJ, NUM, TONNE, default_catalog, symbol`.

- [ ] **Step 4: The supply demands tonnes over its route**

In `NaturalGasSupply.apply`:

```python
        volume_m3 = demand.amount / float(row["energy_content_mj_per_nm3"])
        tonnes = volume_m3 * float(row["gas_density_kg_per_nm3"]) / KG_PER_TONNE
        km = float(row["transport_distance_km"])
        ...
                Demand(
                    flow=Flow(
                        iri=TRANSPORT,
                        context=(Property(DISTANCE, km, KILOMETRE),),
                        **there,
                    ),
                    amount=tonnes,
                    unit=TONNE,
                ),
        ...
            provenance=dict(row.provenance)
            | {"origin": origin, "volume_m3": volume_m3, "transport_tonnes": tonnes, "transport_km": km},
```

Rename the local `volume_nm3` → `volume_m3` and the provenance key accordingly (the reference state is documented on the parameter column, not the unit). Update the module docstring sentence "Nm3 become tkm of pipeline through a density and a route length" → "m³ (at normal conditions) become tonnes, carried over the route length the supply states as the transport demand's ``distance``".

- [ ] **Step 5: Drop the unused tkm datasets from the background pack**

In `dev/build_background_pack.py`: remove the two dataset entries for `transport-freight-rail` and `transport-natural-gas-pipeline-long-distance` from the dataset list (lines ~218–229), with a comment: "tkm datasets are not expressible with vocabulary units (no tonne-kilometre), and nothing demands them." Map EcoSpold unit strings to IRIs where rows are built (around lines 483–489):

```python
ECOSPOLD_UNITS = {"kg": KG, "MJ": MJ, "kWh": KWH, "m3": M3}
"""EcoSpold 1 unit strings -> vocabulary IRIs. A unit outside this map fails the build."""
...
"product_unit": ECOSPOLD_UNITS[identity["unit"]],
...
"flow_unit": ECOSPOLD_UNITS[expected_unit],
```

Run: `uv run python dev/build_background_pack.py`
Expected: writes `examples/background_pack.parquet`; then
`uv run python -c "import pyarrow.parquet as pq,collections; t=pq.read_table('examples/background_pack.parquet').to_pylist(); print(collections.Counter(r['product_unit'] for r in t))"` shows only IRIs.

- [ ] **Step 6: Update the BAFU validation script if it builds demands**

Before touching the model (do this first in the task, before Step 3), record the script's current output:
`uv run python "dev/reverse-engineering of BAFU pipeline transport datasets/validate_pipeline_model.py" > /tmp/claude-bafu-before.txt 2>&1; echo $?`

Now run `grep -n "Demand(\|tkm" "dev/reverse-engineering of BAFU pipeline transport datasets/validate_pipeline_model.py"`. For every `Demand(... unit="tkm")`, build `Demand(flow=Flow(..., context=(Property(DISTANCE, 1.0, KILOMETRE),)), amount=1.0, unit=TONNE)`. Run it again into `/tmp/claude-bafu-after.txt` and `diff` the two files. Expected: identical numbers (1 t over 1 km is 1 tkm). If the script could not run before (missing inputs), say so in the task report and rely on the unit tests.

- [ ] **Step 7: Run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: model pipeline transport as tonnes over a stated distance"
```

---

### Task 6: The Runner refuses units the vocabulary does not have

**Files:**
- Modify: `trailrunner/orchestration/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `Runner.units` (Task 3), `UnitCatalog.known`, `VOCAB`, `KG`.
- Produces: `Runner.validate(demand, result, model=None, units: UnitCatalog | None = None)` raises `ValidationError` for any exchange unit or context-condition unit that is not a confirmed vocabulary unit.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_runner.py`:

```python
from trailrunner.core.flow import Property
from trailrunner.core.units import KG, PA, VOCAB, UnitCatalog


def _result(unit=KG, context=()):
    flow = Flow(iri="https://example.org/p")
    return (
        Demand(flow=flow, amount=1.0, unit=KG),
        Result(
            production=[Exchange(flow=flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri="https://example.org/e", context=context), amount=1.0, unit=unit)],
        ),
    )


def test_a_free_text_unit_is_refused():
    demand, result = _result(unit="kg")
    with pytest.raises(ValidationError, match="not a unit of the vocabulary"):
        Runner.validate(demand, result)


def test_a_context_unit_is_checked_too():
    demand, result = _result(context=(Property("pressure", 4.0, "bar"),))
    with pytest.raises(ValidationError, match="pressure"):
        Runner.validate(demand, result)


def test_a_demand_in_free_text_is_refused():
    flow = Flow(iri="https://example.org/p")
    demand = Demand(flow=flow, amount=1.0, unit="tkm")
    result = Result(production=[Exchange(flow=flow, amount=1.0, unit="tkm")])
    with pytest.raises(ValidationError, match="tkm"):
        Runner.validate(demand, result)


def test_an_uncached_vocab_unit_offline_says_how_to_fix_it():
    # Review focus 3.
    demand, result = _result(unit=VOCAB + "LB")
    with pytest.raises(ValidationError, match="warm_unit_cache"):
        Runner.validate(demand, result, units=UnitCatalog())


def test_vocab_units_pass():
    demand, result = _result(context=(Property("pressure", 4e5, PA),))
    Runner.validate(demand, result)
```

(Match the file's existing imports for `Demand`, `Exchange`, `Flow`, `Result`, `Runner`, `ValidationError`, `pytest`.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_runner.py -q`
Expected: the four refusal tests FAIL (nothing raised).

- [ ] **Step 3: Implement**

In `Runner.apply`: `self.validate(demand, result, model=model, units=self.units)`.

In `validate`, change the signature and add, before the "One pass over every exchange" loop:

```python
        catalog = units if units is not None else default_catalog()

        def check(unit: str, where: str) -> None:
            known = catalog.known(unit)
            if known is True:
                return
            hint = (
                "; it may simply not be cached -- run dev/warm_unit_cache.py, or "
                "pass Orchestrator(units=UnitCatalog(client=default_client()))"
                if known is None
                else ""
            )
            raise ValidationError(
                f"{origin} {where} in {unit!r}, which is not a unit of the "
                f"vocabulary ({VOCAB}); units are IRIs such as {KG}{hint}"
            )

        check(demand.unit, f"was asked for {demand.flow.iri}")
        for entry in demand.flow.context:
            check(entry.unit, f"was asked for {demand.flow.iri} with {entry.name!r}")
```

and inside the loop, right after the empty-unit check:

```python
            check(exchange.unit, f"returned {exchange.flow.iri}")
            for entry in exchange.flow.context:
                check(entry.unit, f"returned {exchange.flow.iri} with {entry.name!r}")
```

Extend the docstring: "Five rules … every exchange carries a unit, and that unit — and every context condition's — is a vocabulary unit; …". Imports: `from trailrunner.core.units import KG, VOCAB, UnitCatalog, default_catalog`.

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q`
Expected: PASS. A failure now means a unit string survived Tasks 2–5: fix the source of the string (a test fixture or model), never loosen `check`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: refuse exchange and context units the vocabulary does not have"
```

---

### Task 7: Characterization factors across units of one kind

**Files:**
- Modify: `trailrunner/assessment/method.py`
- Modify: `trailrunner/assessment/static.py` (pass nothing new; `assess` uses `method.factor`)
- Test: `tests/test_method.py`

**Interfaces:**
- Consumes: `UnitCatalog.convertible/factor`, `default_catalog`.
- Produces: `Method(rows, unit, name, hierarchy=None, source=None, units: UnitCatalog | None = None)`; `Method.from_parquet(path, hierarchy=None, units=None)`; `factor()` provenance gains `"unit_used"`. Internal storage: `self._rows: dict[tuple[str, str, str | None], list[tuple[int | None, float]]]` and `self._flow_units: dict[str, set[str]]` (Task 9 changes the time element to `str | None`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_method.py`:

```python
from trailrunner.core.units import GRAM, KG, TONNE, M3


def _method(rows):
    return Method(rows=rows, unit=KG, name="gwp")


def test_a_factor_per_kg_scores_a_flow_in_tonnes():
    method = _method([{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0}])
    cf = method.factor(Flow(iri=CO2_IRI), TONNE)
    assert cf.value == pytest.approx(1000.0)
    assert cf.provenance["unit_used"] == KG


def test_an_exact_unit_row_wins_over_a_convertible_one():
    method = _method([
        {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0},
        {"flow_iri": CO2_IRI, "flow_unit": GRAM, "location": "GLO", "cf": 0.002},
    ])
    assert method.factor(Flow(iri=CO2_IRI), GRAM).value == pytest.approx(0.002)


def test_another_kind_stays_uncharacterized():
    method = _method([{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0}])
    assert method.factor(Flow(iri=CO2_IRI), M3) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_method.py -q`
Expected: the tonne test FAILS (`None`).

- [ ] **Step 3: Implement**

`__init__` gains `units: UnitCatalog | None = None` → `self._units = units if units is not None else default_catalog()`. Storage:

```python
        self._rows: dict[tuple[str, str, str | None], list[tuple[Any, float]]] = {}
        self._flow_units: dict[str, set[str]] = {}
        seen: set[tuple] = set()
        for row in rows:
            try:
                iri, unit = row["flow_iri"], row["flow_unit"]
                location, time = row.get("location"), row.get("time")
                value = row["cf"]
            except KeyError as exc:
                raise self._layout_error(source) from exc
            key = (iri, unit, location, time)
            if key in seen:
                raise DuplicateFactor(...)  # message unchanged, uses key[0..3]
            seen.add(key)
            self._rows.setdefault((iri, unit, location), []).append((time, value))
            self._flow_units.setdefault(iri, set()).add(unit)
```

`from_parquet(cls, path, hierarchy=None, units=None)` passes `units=units`.

`factor`:

```python
    def factor(self, flow: Flow, unit: str) -> CharacterizationFactor | None:
        """(keep the None-is-not-zero paragraph)

        Precedence: location first (as before), then the flow's own unit
        before any other unit of its kind, then time. A factor stated per kg
        scores a flow in tonnes by the exact multiplier, and says which unit
        it was stated in (``unit_used``).
        """
        for location in self._locations(flow):
            for row_unit, scale in self._candidate_units(flow.iri, unit):
                value, time_used = self._match(self._rows.get((flow.iri, row_unit, location), ()), flow)
                if value is None:
                    continue
                return CharacterizationFactor(
                    value=value * scale,
                    unit=self.unit,
                    provenance={
                        "location_requested": flow.location,
                        "location_used": location,
                        "location_fallback": flow.location is not None and location != flow.location,
                        "time_used": time_used,
                        "unit_used": row_unit,
                        "method": self.name,
                    },
                )
        return None

    def _candidate_units(self, iri: str, unit: str):
        yield unit, 1.0
        for row_unit in sorted(self._flow_units.get(iri, ())):
            if row_unit != unit and self._units.convertible(unit, row_unit):
                yield row_unit, self._units.factor(unit, row_unit)

    @staticmethod
    def _match(entries, flow: Flow) -> tuple[float | None, Any]:
        """The flow's own year first, then an undated row."""
        for wanted in (flow.time, None):
            for time, value in entries:
                if time == wanted:
                    return value, time
        return None, None
```

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: apply a characterization factor across units of one kind"
```

---

### Task 8: Time standards

**Files:**
- Create: `trailrunner/core/time.py`
- Test: `tests/test_time.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `XSD`, `GYEAR`, `GYEAR_MONTH`, `DATE`, `DATETIME` (str)
  - `Interval = tuple[datetime, datetime]`
  - `register_time_standard(iri: str, parser: Callable[[str], Interval]) -> None`, `is_registered(iri) -> bool`
  - `interval(time: str, standard: str) -> Interval`
  - `contains(outer: Interval, inner: Interval) -> bool`
  - `decimal_year(moment: datetime) -> float`, `midpoint_year(span: Interval) -> float`
  - `in_year(year: int) -> dict[str, str]` → `{"time": "2030", "time_standard": GYEAR}`
  - `when(flow) -> dict[str, str | None]` → `{"time": flow.time, "time_standard": flow.time_standard}`
  - `year_of(flow) -> int | None`
  - `@dataclass(frozen=True) class TimeRange(start: str, end: str, standard: str = GYEAR)` with `bounds() -> Interval`, `contains(time: str, standard: str) -> bool`, `edges() -> tuple[str, str]`
  - `year_range(first: int, last: int) -> TimeRange`
  - `infer_standard(text: str) -> str`
  - `short(standard: str) -> str` (`"xsd:gYear"`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_time.py`:

```python
from datetime import UTC, datetime

import pytest

from trailrunner.core.time import (
    DATE,
    DATETIME,
    GYEAR,
    GYEAR_MONTH,
    TimeRange,
    contains,
    decimal_year,
    in_year,
    infer_standard,
    interval,
    midpoint_year,
    register_time_standard,
    year_range,
)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "standard", "expected"),
    [
        ("2030", GYEAR, (utc(2030, 1, 1), utc(2031, 1, 1))),
        ("2030-12", GYEAR_MONTH, (utc(2030, 12, 1), utc(2031, 1, 1))),
        ("2030-02", GYEAR_MONTH, (utc(2030, 2, 1), utc(2030, 3, 1))),
        ("2030-06-15", DATE, (utc(2030, 6, 15), utc(2030, 6, 16))),
        ("2030-06-15T08:00:00Z", DATETIME, (utc(2030, 6, 15, 8), utc(2030, 6, 15, 8))),
        ("2030-06-15T10:00:00+02:00", DATETIME, (utc(2030, 6, 15, 8), utc(2030, 6, 15, 8))),
    ],
)
def test_shipped_standards(value, standard, expected):
    assert interval(value, standard) == expected


@pytest.mark.parametrize(
    ("value", "standard"),
    [
        ("30", GYEAR),
        ("2030-13", GYEAR_MONTH),
        ("2030-02-30", DATE),
        ("2030-06-15T08:00:00", DATETIME),  # no timezone
        ("2030", DATETIME),
    ],
)
def test_malformed_values_are_refused(value, standard):
    with pytest.raises(ValueError):
        interval(value, standard)


def test_an_unregistered_standard_is_refused_by_name():
    with pytest.raises(ValueError, match="register_time_standard"):
        interval("FY2030", "https://example.org/fiscal-year")


def test_a_registered_standard_is_used():
    fiscal = "https://example.org/fiscal-year-test"
    register_time_standard(
        fiscal,
        lambda text: (utc(int(text[2:]) - 1, 7, 1), utc(int(text[2:]), 7, 1)),
    )
    assert interval("FY2030", fiscal) == (utc(2029, 7, 1), utc(2030, 7, 1))


def test_containment_is_half_open():
    # Review focus 2.
    year = interval("2030", GYEAR)
    assert contains(year, interval("2030-06-15", DATE))
    assert contains(year, interval("2030-12-31T23:59:59Z", DATETIME))
    assert not contains(year, interval("2031-01-01T00:00:00Z", DATETIME))
    assert not contains(interval("2030-06-15", DATE), year)


def test_decimal_years_make_year_midpoints_exact_even_across_leap_years():
    # Review focus 6: this is what keeps interpolation identical to the int-year days.
    assert midpoint_year(interval("2020", GYEAR)) == 2020.5
    assert midpoint_year(interval("2025", GYEAR)) == 2025.5
    assert decimal_year(utc(2024, 1, 1)) == 2024.0


def test_in_year():
    assert in_year(2030) == {"time": "2030", "time_standard": GYEAR}


def test_time_range_contains_finer_times():
    window = year_range(2026, 2050)
    assert window == TimeRange("2026", "2050", GYEAR)
    assert window.contains("2050-12-31", DATE)
    assert not window.contains("2051-01-01", DATE)
    assert not window.contains("2025", GYEAR)


def test_time_range_refuses_an_empty_window():
    with pytest.raises(ValueError):
        TimeRange("2050", "2026", GYEAR)


@pytest.mark.parametrize(
    ("text", "standard"),
    [("2030", GYEAR), ("2030-06", GYEAR_MONTH), ("2030-06-15", DATE), ("2030-06-15T08:00Z", DATETIME)],
)
def test_infer_standard(text, standard):
    assert infer_standard(text) == standard


def test_infer_standard_refuses_the_unrecognisable():
    with pytest.raises(ValueError):
        infer_standard("next year")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_time.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.core.time'`.

- [ ] **Step 3: Implement `trailrunner/core/time.py`**

```python
"""When a flow is: a string in a declared time standard, read as an interval.

``Flow.time`` used to be an ``int`` year, so a demand for a day or an instant
could not be stated at all. A time is now a string plus the IRI of the
standard it is written in -- by default the XSD datatypes, so ``"2030"`` in
``xsd:gYear``, ``"2030-06-15"`` in ``xsd:date``, ``"2030-06-15T08:00:00Z"``
in ``xsd:dateTime`` -- and a registry turns the pair into a half-open UTC
interval. Every comparison the library makes goes through that interval,
never through the string: a model declared for a year covers any day in it,
because the day lies inside the year.

More standards can be registered (a fiscal year, an ISO week): a parser is
all a standard needs to be.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

XSD = "http://www.w3.org/2001/XMLSchema#"
GYEAR = XSD + "gYear"
GYEAR_MONTH = XSD + "gYearMonth"
DATE = XSD + "date"
DATETIME = XSD + "dateTime"

Interval = tuple[datetime, datetime]
"""Half-open ``[start, end)``, timezone-aware UTC. An instant has start == end."""

_PARSERS: dict[str, Callable[[str], Interval]] = {}


def short(standard: str) -> str:
    return "xsd:" + standard[len(XSD):] if standard.startswith(XSD) else standard


def register_time_standard(iri: str, parser: Callable[[str], Interval]) -> None:
    """Teach the library a time standard: ``parser`` maps a value to its interval.

    The parser raises ``ValueError`` for a value it cannot read, and returns
    timezone-aware UTC datetimes.
    """
    _PARSERS[iri] = parser


def is_registered(iri: str) -> bool:
    return iri in _PARSERS


def interval(time: str, standard: str) -> Interval:
    parser = _PARSERS.get(standard)
    if parser is None:
        known = ", ".join(sorted(short(iri) for iri in _PARSERS))
        raise ValueError(
            f"{standard!r} is not a registered time standard (known: {known}); "
            "register one with trailrunner.core.time.register_time_standard()"
        )
    if not isinstance(time, str):
        raise ValueError(f"a time is a string, got {time!r}")
    try:
        return parser(time)
    except ValueError as error:
        raise ValueError(f"{time!r} is not a valid {short(standard)} value: {error}") from None


def _year(text: str) -> Interval:
    if not re.fullmatch(r"\d{4}", text):
        raise ValueError("expected YYYY")
    year = int(text)
    return datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)


def _year_month(text: str) -> Interval:
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if not match:
        raise ValueError("expected YYYY-MM")
    year, month = int(match[1]), int(match[2])
    if not 1 <= month <= 12:
        raise ValueError("month out of range")
    end = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
    return datetime(year, month, 1, tzinfo=UTC), end


def _date(text: str) -> Interval:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("expected YYYY-MM-DD")
    day = date.fromisoformat(text)
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _datetime(text: str) -> Interval:
    if "T" not in text:
        raise ValueError("expected YYYY-MM-DDThh:mm:ss with a timezone")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError("a dateTime must carry a timezone, e.g. 'Z' or '+01:00'")
    moment = moment.astimezone(UTC)
    return moment, moment


register_time_standard(GYEAR, _year)
register_time_standard(GYEAR_MONTH, _year_month)
register_time_standard(DATE, _date)
register_time_standard(DATETIME, _datetime)


def contains(outer: Interval, inner: Interval) -> bool:
    """Whether ``inner`` lies inside ``outer``; an instant at ``outer``'s end does not."""
    return outer[0] <= inner[0] and inner[1] <= outer[1] and inner[0] < outer[1]


def decimal_year(moment: datetime) -> float:
    """2030-01-01 is 2030.0; the fraction counts this year's own length.

    Counting in the year's own length, not in days, is what makes a gYear's
    midpoint exactly ``Y + 0.5`` whether or not ``Y`` is a leap year -- and so
    what keeps interpolating between year rows exactly as it was when a time
    was an int.
    """
    start = datetime(moment.year, 1, 1, tzinfo=UTC)
    length = (datetime(moment.year + 1, 1, 1, tzinfo=UTC) - start).total_seconds()
    return moment.year + (moment - start).total_seconds() / length


def midpoint_year(span: Interval) -> float:
    return (decimal_year(span[0]) + decimal_year(span[1])) / 2


def in_year(year: int) -> dict[str, str]:
    """``Flow(iri=..., **in_year(2030))`` -- the common case, spelled once."""
    return {"time": str(year), "time_standard": GYEAR}


def when(flow: Any) -> dict[str, str | None]:
    """A flow's time and standard, to pass on: ``Flow(iri=..., **when(demand.flow))``."""
    return {"time": flow.time, "time_standard": flow.time_standard}


def year_of(flow: Any) -> int | None:
    """The calendar year a flow's time starts in, for code that counts in years (fleets)."""
    if flow.time is None:
        return None
    return interval(flow.time, flow.time_standard)[0].year


@dataclass(frozen=True)
class TimeRange:
    """A model's validity in time: from the start of ``start`` to the end of ``end``.

    Both ends inclusive, as ``time_range=(2026, 2050)`` was: ``year_range(2026,
    2050)`` covers every day of 2050.
    """

    start: str
    end: str
    standard: str = GYEAR

    def __post_init__(self) -> None:
        low, high = self.bounds()
        if high <= low:
            raise ValueError(f"time range {self.start!r}..{self.end!r} is empty")

    def bounds(self) -> Interval:
        return interval(self.start, self.standard)[0], interval(self.end, self.standard)[1]

    def contains(self, time: str, standard: str) -> bool:
        return contains(self.bounds(), interval(time, standard))

    def edges(self) -> tuple[str, str]:
        return self.start, self.end


def year_range(first: int, last: int) -> TimeRange:
    return TimeRange(str(first), str(last), GYEAR)


def infer_standard(text: str) -> str:
    """The XSD standard a value's lexical form implies; for the CLI, which prints it."""
    if re.fullmatch(r"\d{4}", text):
        return GYEAR
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return GYEAR_MONTH
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return DATE
    if "T" in text:
        return DATETIME
    raise ValueError(
        f"cannot tell which standard {text!r} is in; pass --time-standard with an IRI"
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_time.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trailrunner/core/time.py tests/test_time.py
git commit -m "feat: add a registry of time standards read as UTC intervals"
```

---

### Task 9: `Flow.time` becomes a string in a declared standard

This is the switch-over: every reader of `flow.time` changes in one commit, because a half-switched codebase compares `"2030"` with `2030`.

**Files:**
- Modify: `trailrunner/core/flow.py`, `trailrunner/core/errors.py` (+ `MissingTimeStandard`)
- Modify: `trailrunner/params/coverage.py`, `trailrunner/params/parameter_set.py`
- Modify: `trailrunner/resolution/generalising.py` (`_time_candidates`), `trailrunner/core/settings.py` (`time_tolerance: float`)
- Modify: `trailrunner/assessment/method.py` (`_match`, time standard), `trailrunner/assessment/dynamic.py` (dates)
- Modify: `trailrunner/orchestration/log.py` (time columns → string)
- Modify: every model in `trailrunner/models/`, `trailrunner/resolution/background.py`, `examples/showcase_models.py`, `docs/content/writing_a_model.md`
- Modify: `tests/conftest.py` (`time_standard` field key), all tests (codemod)
- Modify: `dev/build_showcase_params.py`; regenerate `examples/*_params.parquet`
- Test: `tests/test_flow.py`, `tests/test_parameter_set.py`, `tests/test_coverage.py`, `tests/test_generalising.py`, `tests/test_method.py`

**Interfaces:**
- Consumes: Task 8 in full.
- Produces:
  - `Flow(iri, location=None, time: str | None = None, time_standard: str | None = None, context=())`
  - `Coverage.time_range: TimeRange | None`
  - `ParameterSet(rows, units=None, iris=None, hierarchy=None, location_column="location", time_column="time", source=None, time_standard: str | None = None)`; `ParameterSet.at(location=None, time: str | None = None, time_standard: str | None = None)`
  - `trailrunner.params.parameter_set.read_time_standards(schema) -> dict[str, str]`
  - `Method(..., time_standard: str | None = None)`
  - `ProxySettings.time_tolerance: float = 5.0`
  - `errors.MissingTimeStandard(TrailrunnerError)`

- [ ] **Step 1: Write the failing tests**

`tests/test_flow.py`:

```python
from trailrunner.core.time import DATE, GYEAR, in_year


def test_time_is_a_string_in_a_standard():
    flow = Flow(iri="x", **in_year(2030))
    assert (flow.time, flow.time_standard) == ("2030", GYEAR)


def test_an_int_year_is_refused_with_the_fix():
    # Review focus 5.
    with pytest.raises(TypeError, match=r"in_year\(2030\)"):
        Flow(iri="x", time=2030)


def test_time_and_standard_come_together():
    with pytest.raises(ValueError, match="time_standard"):
        Flow(iri="x", time="2030")
    with pytest.raises(ValueError, match="time_standard"):
        Flow(iri="x", time_standard=GYEAR)


def test_a_value_that_does_not_parse_is_refused():
    with pytest.raises(ValueError, match="xsd:date"):
        Flow(iri="x", time="2030-02-30", time_standard=DATE)
```

`tests/test_parameter_set.py` (add; fixtures written with the updated conftest, see Step 3):

```python
from trailrunner.core.errors import MissingTimeStandard
from trailrunner.core.time import DATE, GYEAR, in_year

ROWS = [
    {"location": "CH", "time": "2020", "x": 1.0},
    {"location": "CH", "time": "2030", "x": 3.0},
]


def test_a_day_is_answered_by_its_year_row():
    params = ParameterSet(ROWS, time_standard=GYEAR)
    row = params.at(location="CH", time="2030-06-15", time_standard=DATE)
    assert row["x"] == 3.0
    assert row.provenance["time_used"] == "2030"
    assert row.provenance["time_interpolated"] is False


def test_interpolation_between_years_is_unchanged_across_leap_years():
    params = ParameterSet(ROWS, time_standard=GYEAR)
    row = params.at(location="CH", **in_year(2025))
    assert row["x"] == pytest.approx(2.0)
    assert row.provenance["time_bracket"] == ("2020", "2030")


def test_int_time_is_refused():
    with pytest.raises(TypeError, match="in_year"):
        ParameterSet(ROWS, time_standard=GYEAR).at(location="CH", time=2030)


def test_rows_with_time_need_a_standard():
    with pytest.raises(MissingTimeStandard):
        ParameterSet(ROWS)


def test_a_file_without_a_time_standard_is_refused(tmp_path):
    path = tmp_path / "p.parquet"
    write_parameter_parquet(path, ROWS, [
        {"name": "location", "type": "string"},
        {"name": "time", "type": "string"},
        {"name": "x", "type": "number"},
    ])
    with pytest.raises(MissingTimeStandard, match="timeStandard"):
        ParameterSet.from_parquet(path)
```

`tests/test_coverage.py`:

```python
from trailrunner.core.time import DATE, GYEAR, year_range


def test_a_year_range_covers_a_day_in_it():
    coverage = Coverage(time_range=year_range(2026, 2050))
    assert coverage.covers(Flow(iri="c", time="2050-12-31", time_standard=DATE))
    assert not coverage.covers(Flow(iri="c", time="2025", time_standard=GYEAR))
```

`tests/test_generalising.py` (add):

```python
def test_a_day_outside_coverage_snaps_to_the_nearest_covered_year():
    # DatedBoiler covers 2035..2050; a demand dated the last day of 2034
    # is about half a year from 2035's midpoint.
    demand = Demand(flow=Flow(iri=HEAT, time="2034-12-31", time_standard=DATE), amount=1.0, unit=MJ)
    offer = provider([DatedBoiler()]).offer(demand)
    assert (offer.demand.flow.time, offer.demand.flow.time_standard) == ("2035", GYEAR)
    assert offer.resolution["relaxations"] == ["time: 2034-12-31 -> 2035"]


def test_a_year_snaps_exactly_as_it_did_with_int_years():
    demand = Demand(flow=Flow(iri=HEAT, **in_year(2034)), amount=1.0, unit=MJ)
    offer = provider([DatedBoiler()]).offer(demand)
    assert offer.resolution["relaxations"] == ["time: 2034 -> 2035"]
```

(`DatedBoiler` is at the top of the file; after the Step 7 codemod its coverage reads `year_range(2035, 2050)`. Imports: `DATE, GYEAR, in_year` from `trailrunner.core.time`, `MJ` from `trailrunner.core.units`.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_flow.py tests/test_parameter_set.py tests/test_coverage.py tests/test_time.py -q`
Expected: FAIL.

- [ ] **Step 3: Core changes**

`trailrunner/core/errors.py`:

```python
class MissingTimeStandard(TrailrunnerError):
    """Times in a file or table with no standard saying how to read them."""
```

`trailrunner/core/flow.py` — replace the `time` field and add validation:

```python
    time: str | None = None
    """When, as written in ``time_standard``: ``"2030"``, ``"2030-06-15"``.

    ``None`` means the flow is not time-specific. Compared only through its
    interval (``trailrunner.core.time.interval``), never as a string.
    """

    time_standard: str | None = None
    """The IRI of the standard ``time`` is written in (``xsd:gYear`` …).

    Set exactly when ``time`` is. ``Flow(iri=..., **in_year(2030))`` sets both.
    """

    # context unchanged

    def __post_init__(self) -> None:
        if self.time is not None and not isinstance(self.time, str):
            raise TypeError(
                f"Flow.time is a string in a declared standard, not {self.time!r}; "
                f"write Flow(iri=..., **in_year({self.time}))"
            )
        if (self.time is None) != (self.time_standard is None):
            raise ValueError("Flow.time and Flow.time_standard are set together or not at all")
        if self.time is not None:
            interval(self.time, self.time_standard)  # raises ValueError naming the standard
```

Import `from trailrunner.core.time import interval`.

`trailrunner/params/coverage.py`: `time_range: TimeRange | None = None`; in `covers`:

```python
        if self.time_range is not None:
            if flow.time is None:
                return False
            if not self.time_range.contains(flow.time, flow.time_standard):
                return False
```

Docstring: "A coarser range covers a finer time: ``year_range(2026, 2050)`` covers ``2050-12-31``."

`trailrunner/core/settings.py`: `time_tolerance: float = 5.0` — "Years, measured between period midpoints. How far a demand's time may be moved to meet a model's coverage."

- [ ] **Step 4: `ParameterSet` reads intervals**

```python
TIME_STANDARD_KEY = "timeStandard"


def read_time_standards(schema) -> dict[str, str]:
    """Per-column time standards (``"timeStandard"`` on a field) from the datapackage."""
    raw = (schema.metadata or {}).get(DATAPACKAGE_KEY)
    if raw is None:
        return {}
    standards = {}
    for resource in json.loads(raw.decode("utf-8")).get("resources", []):
        container = resource.get("schema") or resource
        for field in container.get("fields", []):
            if field.get("name") and field.get(TIME_STANDARD_KEY):
                standards[field["name"]] = field[TIME_STANDARD_KEY]
    return standards
```

In `ParameterSet.__init__` add `time_standard: str | None = None`, store it, and after storing rows:

```python
        dated = [row[time_column] for row in self._rows if row.get(time_column) is not None]
        if dated and time_standard is None:
            raise MissingTimeStandard(
                f"{source or 'these rows'} carry times in {time_column!r} but no time "
                f"standard; declare one (e.g. {GYEAR})"
            )
        for value in dated:
            interval(value, time_standard)  # a bad row fails here, not mid-traversal
```

`from_parquet`:

```python
        standards = read_time_standards(table.schema)
        standard = standards.get(time_column)
        if time_column in table.schema.names and standard is None:
            raise MissingTimeStandard(
                f"column {time_column!r} in {path} declares no time standard; add "
                f'"timeStandard": "{GYEAR}" (or another registered standard) to its '
                "field in the embedded datapackage"
            )
        return cls(..., time_standard=standard)
```

`at`:

```python
    def at(
        self,
        location: str | None = None,
        time: str | None = None,
        time_standard: str | None = None,
    ) -> ParameterRow:
        if time is not None and not isinstance(time, str):
            raise TypeError(
                f"ParameterSet.at(time=...) takes a string in a standard, not {time!r}; "
                f"write params.at(location=..., **in_year({time})) or **when(demand.flow)"
            )
        if (time is None) != (time_standard is None):
            raise ValueError("time and time_standard are passed together or not at all")
        # loop unchanged, but call self._row_for_time(rows, time, time_standard)
        # and the ParameterNotFound message names time and time_standard.
```

`_row_for_time` and `_interpolate`:

```python
    def _row_for_time(self, rows, time, standard):
        if time is None:
            first = rows[0]
            return first, {"time_used": first.get(self._time_column), "time_interpolated": False}

        asked = interval(time, standard)
        dated = [row for row in rows if row.get(self._time_column) is not None]
        for row in dated:
            if contains(interval(row[self._time_column], self._time_standard), asked):
                return row, {"time_used": row[self._time_column], "time_interpolated": False}

        here = midpoint_year(asked)
        placed = [
            (midpoint_year(interval(row[self._time_column], self._time_standard)), row)
            for row in dated
        ]
        below = [pair for pair in placed if pair[0] < here]
        above = [pair for pair in placed if pair[0] > here]
        if not below or not above:
            return None
        lower = max(below, key=lambda pair: pair[0])
        upper = min(above, key=lambda pair: pair[0])
        fraction = (here - lower[0]) / (upper[0] - lower[0])
        return (
            self._interpolate(lower[1], upper[1], time, fraction),
            {
                "time_used": time,
                "time_interpolated": True,
                "time_bracket": (lower[1][self._time_column], upper[1][self._time_column]),
            },
        )

    def _interpolate(self, lower, upper, time, fraction):
        interpolated = dict(lower)
        for column, low_value in lower.items():
            if column == self._time_column:
                interpolated[column] = time
                continue
            # (the bool-excluding numeric branch unchanged, using `fraction`)
```

Update the class docstring: "then the location hierarchy; then linear interpolation between the bracketing rows, placed at their periods' midpoints in decimal years (so year rows interpolate exactly as integer years did). A row whose period contains the asked time answers it directly."

Imports: `MissingTimeStandard`, `from trailrunner.core.time import GYEAR, contains, interval, midpoint_year`.

`tests/conftest.py`, `write_parameter_parquet`: in the field descriptor add
`**({"timeStandard": field["time_standard"]} if field.get("time_standard") else {}),`.

- [ ] **Step 5: Relax time by intervals**

Replace `_time_candidates`:

```python
    def _time_candidates(self, demand: Demand, budget: int) -> Iterator[tuple[Demand, str, int]]:
        """Snap to the nearest period a declaring model covers, within tolerance.

        Asks the registry rather than guessing: the only periods worth trying
        are the edges of ranges some model actually declares -- the nearer
        edge of each. Distance is between period midpoints in decimal years,
        which for year data is exactly the old ``abs(year - original)``.
        """
        original = demand.flow
        if original.time is None:
            return
        here = midpoint_year(interval(original.time, original.time_standard))
        found: dict[tuple[str, str], float] = {}
        for model in self.inner.glossary.declared_models(original):
            window = getattr(model.coverage, "time_range", None) if model.coverage else None
            if window is None:
                continue
            distance, value = min(
                (abs(midpoint_year(interval(edge, window.standard)) - here), edge)
                for edge in window.edges()
            )
            key = (value, window.standard)
            if distance > self.settings.time_tolerance or key == (original.time, original.time_standard):
                continue
            found[key] = min(found.get(key, distance), distance)
        ranked = sorted(found.items(), key=lambda item: (item[1], item[0]))
        for step, ((value, standard), _distance) in enumerate(islice(ranked, budget), 1):
            flow = replace(original, time=value, time_standard=standard)
            yield replace(demand, flow=flow), f"time: {original.time} -> {value}", step
```

Imports: `from trailrunner.core.time import interval, midpoint_year`.

- [ ] **Step 6: Methods, dynamic, log**

`method.py`: `__init__` gains `time_standard: str | None = None` (validate like `ParameterSet`: dated rows need it, raise `MissingTimeStandard`); `from_parquet` reads `read_time_standards(table.schema).get("time")` and refuses a `time` column without one. `_match` becomes:

```python
    def _match(self, entries, flow: Flow) -> tuple[float | None, Any]:
        """A row whose period contains the flow's time, then an undated row."""
        if flow.time is not None:
            asked = interval(flow.time, flow.time_standard)
            for time, value in entries:
                if time is not None and contains(interval(time, self._time_standard), asked):
                    return value, time
        for time, value in entries:
            if time is None:
                return value, None
        return None, None
```

(it is no longer a staticmethod). Update `_layout_error`'s text: "'time' (string, with a timeStandard)".

`dynamic.py`: add

```python
def _date(flow: Flow) -> datetime:
    """Where on the axis an exchange sits: the start of its period, as naive UTC.

    A year becomes 1 January, exactly as when time was an int; a finer time
    lands where it says.
    """
    return interval(flow.time, flow.time_standard)[0].replace(tzinfo=None)
```

and replace both `datetime(exchange.flow.time, 1, 1)` with `_date(exchange.flow)`. Fix the `inventory_dataframe` docstring ("``Flow.time`` is a year and…" → "an exchange is placed at the start of its period").

`log.py`: `("demand_time", pa.string())`, `("flow_time", pa.string())`.

- [ ] **Step 7: Migrate callers with a codemod**

Create `dev/_codemod_time.py` (deleted in Step 11):

```python
"""One-off: int years -> strings in a standard."""

import re
import sys
from pathlib import Path

RULES = [
    (re.compile(r"\btime=(demand|d|item\.demand|record\.demand)\.flow\.time\b"), r"**when(\1.flow)", "when"),
    (re.compile(r"\btime=flow\.time\b"), r"**when(flow)", "when"),
    (re.compile(r"\btime_range=\((\d{4}),\s*(\d{4})\)"), r"time_range=year_range(\1, \2)", "year_range"),
    (re.compile(r"\btime=(\d{4})\b"), r"**in_year(\1)", "in_year"),
    (re.compile(r'"time": (\d{4})\b'), r'"time": "\1"', None),
    (re.compile(r'\{"name": "time", "type": "integer", "unit": YEAR'), '{"name": "time", "type": "string", "time_standard": GYEAR', "GYEAR"),
]


def migrate(path: Path) -> None:
    lines = path.read_text().splitlines(keepends=True)
    used: set[str] = set()
    for index, line in enumerate(lines):
        if "operating(" in line or "demand_year=" in line:
            continue  # fleets and amortize count in int years: migrated by hand
        for pattern, replacement, name in RULES:
            new = pattern.sub(replacement, line)
            if new != line and name:
                used.add(name)
            line = new
        lines[index] = line
    source = "".join(lines)
    if used:
        imports = f"from trailrunner.core.time import {', '.join(sorted(used))}\n"
        at = max(i for i, text in enumerate(lines) if text.startswith(("import ", "from ")))
        end = at
        if lines[end].rstrip().endswith("("):
            while not lines[end].strip().startswith(")"):
                end += 1
        lines.insert(end + 1, imports)
        source = "".join(lines)
    path.write_text(source)
    if used:
        print(f"{path}: {', '.join(sorted(used))}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        migrate(Path(name))
```

Run:

```bash
uv run python dev/_codemod_time.py $(git ls-files 'trailrunner/models/*.py' trailrunner/resolution/background.py 'tests/*.py' examples/showcase_models.py dev/build_showcase_params.py)
```

- [ ] **Step 8: Hand-migrate what the codemod skips**

1. Fleets and capital (`cement.py`, `dac.py`, and tests in `tests/test_fleet.py`, `tests/test_cement.py`, `tests/test_dac.py`, `tests/test_capital.py`):
   - `self.fleet.operating(location=demand.flow.location, time=year_of(demand.flow))`
   - `amortize(..., demand_year=year_of(demand.flow), ...)`
   - construction flows: `Flow(iri=CEMENT_KILN, location=..., **in_year(build_year))` (same in `dac.py`).
   - Fleet's own API keeps `time: int | None`; tests calling `fleet.operating(time=2030)` stay as they are.
2. Remaining variable-year call sites the codemod leaves: `git grep -nE "\btime=[a-z_]+\b" -- trailrunner tests examples | grep -v "time_standard\|time_range\|time_tolerance\|time_column\|time_horizon"`. Each `time=year` becomes `**in_year(year)`; each `time=time` inside a `Flow(...)` or `.at(...)` becomes `time=time, time_standard=<the standard in scope>` or `**in_year(time)` when `time` is an int loop variable. Read each.
3. `natural_gas_pipeline_transport.py`: `location, time = ...` → build flows with `Flow(iri=iri, location=location, **when(demand.flow))`.
4. `resolution/background.py:205`: `flow=Flow(iri=iri, location=demand.flow.location, **when(demand.flow))`.
5. Assertions comparing times: `git grep -nE "\.time == [0-9]{4}|time_used.*[0-9]{4}|time_requested" -- tests` → compare with strings (`== "2030"`).
6. `tests/test_method.py`'s `YEAR` field helper: the time field gets `"time_standard": GYEAR`; method row times become strings.
7. `docs/content/writing_a_model.md`: `here = dict(location=demand.flow.location, **when(demand.flow))`; `Coverage(time_range=year_range(2020, 2050))`; `self.params.at(location=demand.flow.location, **when(demand.flow))`; imports `from trailrunner.core.time import when, year_range`. In the prose at line ~165: "`time_range` includes both ends, and covers any finer time inside them: `year_range(2020, 2050)` answers a demand dated `2050-12-31`."
8. `dev/build_showcase_params.py`: `TIME_FIELD = {"name": "time", "type": "string", "time_standard": GYEAR, "iri": None}`; in `_write`, emit `"timeStandard"` for fields that have `time_standard` (same line as conftest), and write `"time": str(row["time"])` for every row.

- [ ] **Step 9: Regenerate example parameter files**

Run: `uv run python dev/build_showcase_params.py`
Expected: files rewritten; `uv run python -c "from trailrunner import ParameterSet; print(ParameterSet.from_parquet('examples/cement_params.parquet').at(location='DK', time='2030', time_standard='http://www.w3.org/2001/XMLSchema#gYear').provenance)"` prints `time_used: '2030'`.

- [ ] **Step 10: Run the suite until green**

Run: `uv run pytest -q`
Expected: PASS. Remaining failures are call sites that still pass an int (the `TypeError` names the fix) or tests asserting int times; fix each at the source.

- [ ] **Step 11: Commit**

```bash
rm dev/_codemod_time.py
git add -A
git commit -m "feat!: state a flow's time as a string in a declared time standard"
```

---

### Task 10: The log records the standard, the interval and the context

**Files:**
- Modify: `trailrunner/orchestration/log.py`
- Test: `tests/test_log.py`

**Interfaces:**
- Consumes: `interval`.
- Produces: `LOG_SCHEMA` gains `demand_time_standard`, `demand_time_start`, `demand_time_end`, `demand_context`, `flow_time_standard`, `flow_time_start`, `flow_time_end`, `flow_context` (starts/ends `pa.timestamp("us", tz="UTC")`, others `pa.string()`).

- [ ] **Step 1: Write the failing test**

```python
def test_the_parquet_carries_time_standard_interval_and_context(tmp_path):
    from datetime import UTC, datetime
    import pyarrow.parquet as pq
    from trailrunner.core.flow import Property
    from trailrunner.core.time import DATE
    from trailrunner.core.units import KG, PA

    flow = Flow(iri="https://example.org/gas", time="2030-06-15", time_standard=DATE,
                context=(Property("pressure", 4e5, PA),))
    log = Log()
    demand = Demand(flow=flow, amount=1.0, unit=KG)
    log.write(demand, Result(production=[Exchange(flow=flow, amount=1.0, unit=KG)],
                             biosphere=[Exchange(flow=flow, amount=2.0, unit=KG)]),
              depth=0, parent=None, model="M", resolution={"tier": "model"})
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    row = [r for r in pq.read_table(path).to_pylist() if r["kind"] == "biosphere"][0]
    assert row["demand_time"] == "2030-06-15"
    assert row["demand_time_standard"] == DATE
    assert row["demand_time_start"] == datetime(2030, 6, 15, tzinfo=UTC)
    assert row["demand_time_end"] == datetime(2030, 6, 16, tzinfo=UTC)
    assert row["demand_context"] == "pressure=4e+05 Pa"
    assert row["flow_time_start"] == datetime(2030, 6, 15, tzinfo=UTC)
    assert row["flow_context"] == "pressure=4e+05 Pa"
```

(Match `Log.write`'s real signature.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_log.py -q`
Expected: FAIL — `KeyError: 'demand_time_standard'`.

- [ ] **Step 3: Implement**

Add to the schema, after the existing `demand_time` and `flow_time` columns:

```python
        ("demand_time_standard", pa.string()),
        ("demand_time_start", pa.timestamp("us", tz="UTC")),
        ("demand_time_end", pa.timestamp("us", tz="UTC")),
        ("demand_context", pa.string()),
        ...
        ("flow_time_standard", pa.string()),
        ("flow_time_start", pa.timestamp("us", tz="UTC")),
        ("flow_time_end", pa.timestamp("us", tz="UTC")),
        ("flow_context", pa.string()),
```

and a helper:

```python
def _identity(prefix: str, flow: Flow) -> dict:
    """Time as written, its standard, its interval, and the context: a node's whole identity.

    The interval is there so the file can be filtered by date without
    re-implementing the time standards; the context so that two nodes for gas
    at different pressures are not two identical rows.
    """
    start = end = None
    if flow.time is not None:
        start, end = interval(flow.time, flow.time_standard)
    return {
        f"{prefix}_time": flow.time,
        f"{prefix}_time_standard": flow.time_standard,
        f"{prefix}_time_start": start,
        f"{prefix}_time_end": end,
        f"{prefix}_context": flow.describe_context() or None,
    }
```

Use `**_identity("demand", node.demand.flow)` in `base` (replacing `"demand_time": ...`), `**_identity("flow", exchange.flow)` in biosphere rows (replacing `"flow_time": ...`), and `**_identity("demand", record.demand.flow)` in unresolved rows.

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: log each flow's time standard, interval and context"
```

---

### Task 11: CLI

**Files:**
- Modify: `trailrunner/cli.py`
- Test: `tests/test_cli.py`
- Modify: `docs/content/getting_started/cli.md`

**Interfaces:**
- Consumes: `UnitCatalog.resolve`, `UnknownUnit`, `infer_standard`, `short`, `Property`.
- Produces: `trailrunner run IRI --amount A --unit U [--time T] [--time-standard IRI] [--context "NAME=VALUE UNIT"]...`; `--year` removed; exit code 2 with a message for a bad unit/time/context.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py` (reusing `models_file`):

```python
@pytest.mark.parametrize("unit", ["kg", "KiloGM", "https://vocab.sentier.dev/units/unit/KiloGM"])
def test_unit_accepts_symbol_id_and_iri(models_file, capsys, unit):
    assert main(["run", HEAT, "--amount", "1", "--unit", unit, "--models", str(models_file)]) == 0


def test_an_unknown_unit_exits_2(models_file, capsys):
    assert main(["run", HEAT, "--amount", "1", "--unit", "tkm", "--models", str(models_file)]) == 2
    assert "tkm" in capsys.readouterr().err


def test_time_standard_is_inferred_and_said(models_file, capsys):
    assert main(["run", HEAT, "--amount", "1", "--unit", "kg", "--time", "2030-06-15",
                 "--models", str(models_file)]) == 0
    assert "time 2030-06-15 read as xsd:date" in capsys.readouterr().out


def test_a_bad_time_exits_2(models_file, capsys):
    assert main(["run", HEAT, "--amount", "1", "--unit", "kg", "--time", "2030-02-30",
                 "--models", str(models_file)]) == 2


def test_context_is_parsed(models_file, capsys):
    assert main(["run", HEAT, "--amount", "1", "--unit", "kg",
                 "--context", "pressure=4e5 Pa", "--models", str(models_file)]) == 0
    assert "pressure=4e+05 Pa" in capsys.readouterr().out


def test_a_malformed_context_exits_2(models_file, capsys):
    assert main(["run", HEAT, "--amount", "1", "--unit", "kg",
                 "--context", "pressure 4", "--models", str(models_file)]) == 2


def test_year_is_gone(models_file):
    with pytest.raises(SystemExit):
        main(["run", HEAT, "--amount", "1", "--unit", "kg", "--year", "2030", "--models", str(models_file)])
```

Replace existing `--year 2030` usages in this file with `--time 2030`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Arguments:

```python
    run.add_argument("--unit", required=True, help="a unit IRI, vocabulary id (KiloGM) or symbol (kg)")
    run.add_argument("--location", default=None)
    run.add_argument("--time", default=None, help="2030, 2030-06, 2030-06-15 or 2030-06-15T08:00:00Z")
    run.add_argument(
        "--time-standard", default=None,
        help="the IRI --time is written in; inferred from its form when omitted",
    )
    run.add_argument(
        "--context", action="append", default=[], metavar="NAME=VALUE UNIT",
        help='a condition on the demand, e.g. "pressure=4e5 Pa"; repeatable',
    )
```

In `main`, before building the demand:

```python
    catalog = UnitCatalog()
    try:
        unit = catalog.resolve(args.unit)
        standard = None
        if args.time is not None:
            standard = args.time_standard or infer_standard(args.time)
        context = tuple(_condition(text, catalog) for text in args.context)
        flow = Flow(
            iri=args.iri, location=args.location,
            time=args.time, time_standard=standard, context=context,
        )
    except (UnknownUnit, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if standard is not None:
        # Inferred or not, the reading is printed: a time is never read silently.
        print(f"time {args.time} read as {short(standard)}")
    demand = Demand(flow=flow, amount=args.amount, unit=unit)
```

and the helper:

```python
def _condition(text: str, catalog: UnitCatalog) -> Property:
    """``"pressure=4e5 Pa"`` -> ``Property("pressure", 400000.0, PA)``."""
    name, separator, rest = text.partition("=")
    parts = rest.split(None, 1)
    if not separator or not name.strip() or len(parts) != 2:
        raise ValueError(f'{text!r} is not a condition; write "NAME=VALUE UNIT", e.g. "pressure=4e5 Pa"')
    return Property(name.strip(), float(parts[0]), catalog.resolve(parts[1].strip()))
```

Remove the Task 2 stop-gap `default_catalog().resolve(args.unit)` line. Imports: `Property`, `UnitCatalog`, `UnknownUnit`, `infer_standard`, `short`. Also print the context in the summary: the demand's root line in `report.tree()` already shows `(pressure=4e+05 Pa)` via `_where`.

- [ ] **Step 4: Update the CLI page**

In `docs/content/getting_started/cli.md`, replace `--year` with `--time`, document `--time-standard`, `--context`, and that `--unit` takes an IRI, a vocabulary id or a symbol. Example: `trailrunner run <CEMENT> --amount 1 --unit t --location DK --time 2030-06-15 --models examples/showcase_models.py`.

- [ ] **Step 5: Run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(cli): resolve units, read times in a standard, accept context"
```

---

### Task 12: Showcase, pitches and guides

**Files:**
- Modify: `examples/showcase.ipynb`, `examples/dac.ipynb`, `examples/coproduction.ipynb`
- Regenerate: `docs/showcase.md` and example pages via `docs/convert_notebooks.py`; `docs/assets/showcase/*.svg` via `dev/build_showcase_assets.py`
- Modify: `docs/pitch.md`, `docs/pitch-5min.md`, `docs/content/concepts.md`, `docs/content/resolution.md`, `docs/content/parameters.md`, `docs/content/writing_a_model.md` (prose), `docs/api/*.md` if they reference removed names
- Modify: `README.md` if it shows a `Flow`/`Demand`

**Interfaces:**
- Consumes: everything above.
- Produces: the tour demands **1 t** of cement in DK on **2030-06-15** (`DATE`); `CementPlant` answers in kg, and the tree reads `[model: CementPlant; unit: t -> kg ×1000]`. Pressure is 4e5 Pa asked and 5e5 Pa delivered, with `ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})`.

- [ ] **Step 1: Migrate the notebooks' code cells**

Edit the cells (NotebookEdit, or a short `nbformat` script — never hand-edit notebook JSON by string replacement). In `examples/showcase.ipynb`:

```python
DEMAND = Demand(
    flow=Flow(iri=CEMENT, location="DK", time="2030-06-15", time_standard=DATE),
    amount=1.0,
    unit=TONNE,
)
```

`CementPlant(params=cement_params, fleet=fleet, burner_pressure=4e5)`, `PROXY = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})`, fleet units `{"capacity": TONNE_PER_YEAR, "lifetime": YEAR}` with capacity values ×0.001 (they were kg/year), every other `unit="kg"` → `unit=KG`, `time=year` → `**in_year(year)`, `params.at(location=location, time=year)` → `params.at(location=location, **in_year(year))`, the dynamic-assessment cell's `unit="kg CO2-eq"` → `unit=KG`. Imports: `from trailrunner.core.units import KG, PA, TONNE, TONNE_PER_YEAR, YEAR` and `from trailrunner.core.time import DATE, in_year`. Add one markdown cell right after the first tree, in the voice of the surrounding cells:

> The demand is **1 t** of cement on **15 June 2030**. `CementPlant` reasons in kilograms and its parameters are per year: it answers the day because the day lies inside 2030, and it is handed 1000 kg because a tonne is exactly that — `unit: t -> kg ×1000`, written on the node, costing nothing. A conversion is not a proxy.

Do the same mechanical migration in `examples/dac.ipynb` and `examples/coproduction.ipynb`.

- [ ] **Step 2: Execute the notebooks**

Run: `uv run --extra examples --extra viz --extra dynamic jupyter nbconvert --to notebook --execute --inplace examples/showcase.ipynb examples/dac.ipynb examples/coproduction.ipynb`
Expected: all three execute without error. Read the showcase's printed tree: the root line shows `1 t` and `[model: CementPlant; unit: t -> kg ×1000]`; the gas line shows `pressure=4e+05 Pa` and `[proxy: context: pressure 400000 Pa -> 500000 Pa]`.

- [ ] **Step 3: Regenerate the docs pages and figures**

Run: `uv run --extra docs python docs/convert_notebooks.py && uv run --extra viz python dev/build_showcase_assets.py`
Expected: `docs/showcase.md` and `docs/content/examples/*.md` rewritten; SVGs rewritten.

- [ ] **Step 4: Update the pitches by hand**

Both `docs/pitch.md` and `docs/pitch-5min.md`:
- `row = params.at(location="DK", time=2030)` → `row = params.at(location="DK", **in_year(2030))`.
- The context-fallback section: "The kiln burners want gas at **4e5 Pa** (4 bar)… delivers **5e5 Pa**…", `ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})  # (below, above, unit)`, and the printed lines copied verbatim from the executed notebook output.
- Add a short section before "Finding fallback models" (pitch.md) / within the cement chain (pitch-5min.md): **"A unit falls back exactly"** — the demand in t, the model in kg, the tagged tree line from the notebook output, and one sentence: "Same quantity, different unit: converted by the vocabulary's own multiplier, logged on the node, and not counted as a concession."
- Every `@DK/2030` in quoted tree output and mermaid labels that comes from the root demand becomes `@DK/2030-06-15`; copy from the notebook output rather than retyping.

- [ ] **Step 5: Update the guides**

- `docs/content/concepts.md`: the Flow section says a unit is a vocabulary IRI (`https://vocab.sentier.dev/units/`) and a time is a string plus a time standard IRI; list the four shipped standards and `register_time_standard`.
- `docs/content/resolution.md`: a "Units" subsection (conversion at tier 1, `Coverage.units`, `unit_mismatch`), context tolerance with a unit, time relaxation by period midpoint and containment.
- `docs/content/parameters.md`: `timeStandard` on the time field; containment and midpoint interpolation; `unit_of` returns an IRI.
- `README.md`: migrate any code sample.

Run: `git grep -nE 'time=[0-9]{4}|unit="(kg|MJ|kWh|tkm|Nm3)"|--year|\bbar\b' -- docs README.md examples ':!docs/superpowers'`
Expected: no hits except prose that deliberately mentions bar next to Pa.

- [ ] **Step 6: Build the docs**

Run: `uv run --extra docs zensical build`
Expected: builds without warnings about missing references.

- [ ] **Step 7: Run the suite**

Run: `uv run pytest -q`
Expected: PASS (`tests/test_writing_a_model.py` executes the guide's code).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "docs: show unit conversion, dated demands and Pa in the tour and pitches"
```

---

### Task 13: Whole-branch verification

**Files:** none new.

- [ ] **Step 1: Full suite**

Run: `uv run pytest -q`
Expected: PASS, zero skips added by this branch.

- [ ] **Step 2: CLI end to end**

Run: `uv run trailrunner run https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440 --amount 1 --unit t --location DK --time 2030-06-15 --models examples/showcase_models.py`
Expected: first line `time 2030-06-15 read as xsd:date`; tree root `1 t … @DK/2030-06-15  [model: CementPlant; unit: t -> kg ×1000]`; exit 0.

- [ ] **Step 3: Strictness sweep**

Run: `git grep -nE 'unit="[^"]*"|"unit": "[^"]*"' -- trailrunner examples/showcase_models.py`
Expected: no hits (allocation properties in tests are the only free-text units, and none are in `trailrunner/`).

Run: `git grep -n "time: int" -- trailrunner`
Expected: only `params/fleet.py` (fleets count in years by design).

- [ ] **Step 4: Spec cross-check**

Open the spec and tick each section against a commit: §1 units (Tasks 1–7), §2 time (Tasks 8–10), §3 CLI (Task 11), §4 showcase (Task 12), §5 testing (every task), open point "breaking change" (documented in guides, Task 12). Anything unticked is a missing task: stop and report it.

- [ ] **Step 5: Hand off**

Use superpowers:finishing-a-development-branch.
