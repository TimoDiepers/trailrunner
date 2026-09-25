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

from trailrunner.core.errors import (
    DuplicateFactor,
    MissingColumns,
    MissingTimeStandard,
    MissingUnit,
    UnknownUnit,
)
from trailrunner.core.flow import Flow
from trailrunner.core.time import GYEAR, contains, interval
from trailrunner.core.units import VOCAB, UnitCatalog, default_catalog
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import (
    DATAPACKAGE_KEY,
    _read_field_metadata,
    read_time_standards,
)


@dataclass(frozen=True)
class CharacterizationFactor:
    """One CF and how it was found."""

    value: float
    unit: str
    provenance: Mapping[str, Any]


class Method:
    """Characterization factors indexed by (flow IRI, flow unit, location).

    ``time`` is read if the column is present, in the method's
    ``time_standard``, and a row answers a flow whose time lies inside the
    row's period: a method whose factors change by year says so per row, and
    its 2030 row answers a flow dated 2030-06-15. There is no interpolation
    between CFs, because a CF is a modelling convention rather than a measured
    quantity, and interpolating between two conventions produces neither.

    Lookup precedence is **location first, time second**: the outer loop walks
    the location chain and the inner loop tries ``flow.time`` then ``None``.
    So a ``CH`` row with no year beats a ``GLO`` row written for exactly the
    year asked for. A method states its factors where they hold; a regional
    convention that did not bother to date itself is still that region's
    convention, and reaching past it to the global table would substitute a
    different method's opinion for this one's.

    One deliberate divergence from ``ParameterSet``, which this class
    otherwise mirrors: ``ParameterSet`` reads ``location=None`` as "no
    location was requested, so every row is a candidate", and hands back
    whichever row comes first. ``Method`` reads it as "match rows whose
    location is null", then falls through to the hierarchy root. That is
    stricter, and on purpose: silently answering an unlocated flow with the
    first regional CF in file order would make the score depend on row order
    in the parquet.

    Units are vocabulary IRIs, checked at construction: a row whose
    ``flow_unit`` (or a ``cf`` column whose declared unit) is not one the
    catalog confirms is refused rather than kept. A method file still written
    with ``flow_unit: "kg"`` would otherwise match nothing a model emits --
    every flow of that kind goes uncharacterized and the score is silently
    ``0`` -- so the refusal happens here, at authoring time, instead of
    surfacing later as a suspiciously small score.
    """

    def __init__(
        self,
        rows: list[dict[str, Any]],
        unit: str,
        name: str,
        hierarchy: LocationHierarchy | None = None,
        source: str | None = None,
        units: UnitCatalog | None = None,
        time_standard: str | None = None,
    ) -> None:
        self.unit = unit
        self._time_standard = time_standard
        self.name = name
        self.source = source
        self._hierarchy = hierarchy if hierarchy is not None else LocationHierarchy()
        self._units = units if units is not None else default_catalog()
        self._check_unit(unit, source)
        # (flow_iri, flow_unit, location) -> [(time, cf, interval), ...]. Time
        # lives in a list rather than the key so ``_candidate_units`` can
        # enumerate every unit a flow has a CF in without also enumerating
        # every year. ``interval`` is the row's time pre-parsed at
        # construction, so ``_match`` never re-parses it per lookup.
        self._rows: dict[tuple[str, str, str | None], list[tuple[Any, float, Any]]] = {}
        self._flow_units: dict[str, set[str]] = {}
        seen: set[tuple[str, str, str | None, Any]] = set()
        for row in rows:
            try:
                iri, flow_unit = row["flow_iri"], row["flow_unit"]
                location, time = row.get("location"), row.get("time")
                value = row["cf"]
            except KeyError as exc:
                raise self._layout_error(source) from exc
            self._check_unit(flow_unit, source)
            computed_interval = None
            if time is not None:
                if time_standard is None:
                    raise MissingTimeStandard(
                        f"{source or 'the method rows'} carry times in 'time' but no "
                        f"time standard; declare one (e.g. {GYEAR})"
                    )
                # Parsed once here, not mid-assessment: a bad row fails
                # immediately, with the file and column named, and ``_match``
                # reuses the result instead of re-parsing it on every lookup.
                try:
                    computed_interval = interval(time, time_standard)
                except ValueError as error:
                    raise ValueError(
                        f"{source or 'the method rows'}: column 'time' has {time!r} "
                        f"({error}); times are strings in the declared standard, e.g. "
                        "'2030' — cast the column to string"
                    ) from None
            key = (iri, flow_unit, location, time)
            if key in seen:
                # Last-wins would put a number in the score that appears in no
                # message anywhere. Two CFs for one key is a data error, the
                # same way two models producing one product is.
                raise DuplicateFactor(
                    f"two characterization factors for "
                    f"(flow_iri={key[0]!r}, flow_unit={key[1]!r}, location={key[2]!r}, "
                    f"time={key[3]!r}) in {source or name}; a method file states "
                    "each factor once"
                )
            seen.add(key)
            self._rows.setdefault((iri, flow_unit, location), []).append(
                (time, value, computed_interval)
            )
            self._flow_units.setdefault(iri, set()).add(flow_unit)

    def _check_unit(self, unit: str, source: str | None) -> None:
        if self._units.known(unit) is True:
            return
        raise UnknownUnit(
            f"{source or 'the method rows'} names {unit!r}, which is not a unit "
            f"the vocabulary confirms; units are vocabulary IRIs such as KG "
            f"({VOCAB}KiloGM)"
        )

    @staticmethod
    def _layout_error(source: str | None) -> MissingColumns:
        return MissingColumns(
            f"{source or 'the method rows'} is not a method file: a method needs "
            "the columns 'flow_iri' (string), 'flow_unit' (string) and 'cf' "
            "(number), plus the optional 'location' (string) and 'time' "
            "(string, with a timeStandard); the 'cf' column must declare its "
            "unit in the embedded datapackage metadata"
        )

    @classmethod
    def from_parquet(
        cls,
        path: str | Path,
        hierarchy: LocationHierarchy | None = None,
        units: UnitCatalog | None = None,
    ) -> "Method":
        table = pq.read_table(path)
        missing = [
            column
            for column in ("flow_iri", "flow_unit", "cf")
            if column not in table.schema.names
        ]
        if missing:
            raise MissingColumns(
                f"{path} is missing the column{'s' if len(missing) > 1 else ''} "
                f"{', '.join(repr(column) for column in missing)}; a method needs "
                "'flow_iri' (string), 'flow_unit' (string) and 'cf' (number), plus "
                "the optional 'location' (string) and 'time' (string, with a "
                "timeStandard), and the "
                f"'cf' column must declare its unit (found: "
                f"{', '.join(table.schema.names) or 'no columns at all'})"
            )
        column_units, _ = _read_field_metadata(table.schema)
        if not column_units.get("cf"):
            raise MissingUnit(
                f"column 'cf' has no unit declared in {path}; the method's score "
                "unit is read from it"
            )
        time_standard = read_time_standards(table.schema).get("time")
        if "time" in table.schema.names and time_standard is None:
            raise MissingTimeStandard(
                f"column 'time' in {path} declares no time standard; add "
                f'"timeStandard": "{GYEAR}" (or another registered standard) to its '
                "field in the embedded datapackage, and make sure the column holds "
                "strings (e.g. '2030'), not integers"
            )
        raw = (table.schema.metadata or {}).get(DATAPACKAGE_KEY)
        name = "method"
        if raw is not None:
            name = json.loads(raw).get("name", name)
        return cls(
            rows=table.to_pylist(),
            unit=column_units["cf"],
            name=name,
            hierarchy=hierarchy,
            source=str(path),
            units=units,
            time_standard=time_standard,
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

        Precedence: location first (as before), then the flow's own unit
        before any other unit of its kind, then time. A factor stated per kg
        scores a flow in tonnes by the exact multiplier, and says which unit
        it was stated in (``unit_used``).
        """
        for location in self._locations(flow):
            for row_unit, scale in self._candidate_units(flow.iri, unit):
                value, time_used = self._match(
                    self._rows.get((flow.iri, row_unit, location), ()), flow
                )
                if value is None:
                    continue
                return CharacterizationFactor(
                    value=value * scale,
                    unit=self.unit,
                    provenance={
                        "location_requested": flow.location,
                        "location_used": location,
                        # Nothing was substituted if nothing was asked for.
                        "location_fallback": flow.location is not None
                        and location != flow.location,
                        "time_used": time_used,
                        "unit_used": row_unit,
                        "method": self.name,
                    },
                )
        return None

    def _candidate_units(self, iri: str, unit: str):
        """``unit`` itself first, then any other unit of its kind the flow has a CF in.

        The requested unit always wins over a converted one: an exact row for
        grams beats scaling the flow's kilogram row, because the method author
        who bothered to write the exact row meant it to be used as written.
        """
        yield unit, 1.0
        for row_unit in sorted(self._flow_units.get(iri, ())):
            if row_unit != unit and self._units.convertible(unit, row_unit):
                yield row_unit, self._units.factor(unit, row_unit)

    def _match(self, entries, flow: Flow) -> tuple[float | None, Any]:
        """A row whose period contains the flow's time, then an undated row."""
        if flow.time is not None:
            asked = interval(flow.time, flow.time_standard)
            for time, value, row_interval in entries:
                if time is not None and contains(row_interval, asked):
                    return value, time
        for time, value, _ in entries:
            if time is None:
                return value, None
        return None, None
