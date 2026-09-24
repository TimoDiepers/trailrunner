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
SQUARE_METRE = VOCAB + "M2"
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
