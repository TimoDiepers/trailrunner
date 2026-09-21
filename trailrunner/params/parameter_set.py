"""Parameters out of a trailpack parquet file, with honest fallback."""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyarrow.parquet as pq

from trailrunner.core.errors import MissingUnit, ParameterNotFound
from trailrunner.params.location import LocationHierarchy

DATAPACKAGE_KEY = b"datapackage.json"

_REQUIRED = object()
"""Sentinel: ``unit_of`` raises unless the caller passes an explicit default."""


@dataclass(frozen=True)
class ParameterRow:
    """One resolved set of parameter values, plus how it was obtained.

    Values are reachable as ``row["heat_demand"]`` or ``row.heat_demand``.

    The row owns its ``values`` and sees ``units`` and ``iris`` through
    read-only views, so nothing done to a row can reach back into the
    ParameterSet that produced it.
    """

    values: Mapping[str, Any]
    units: Mapping[str, str]
    iris: Mapping[str, str]
    provenance: Mapping[str, Any]
    source: str | None = None
    """Where these values came from, so a complaint can name the file."""

    def __getitem__(self, column: str) -> Any:
        return self.values[column]

    def __getattr__(self, column: str) -> Any:
        try:
            return object.__getattribute__(self, "values")[column]
        except KeyError:
            raise AttributeError(column) from None

    def unit_of(self, column: str, default: Any = _REQUIRED) -> Any:
        """The unit declared for ``column``, raising when there is none.

        Strict by default because the caller is almost always building an
        ``Exchange``, whose ``unit`` is a ``str``: handing back ``None`` there
        type-checks, travels into the model's Result and only fails later, in
        the Runner, with a message blaming the model for what is really a gap
        in the parquet's metadata. Pass ``default=`` to ask without asserting.
        """
        unit = self.units.get(column)
        if unit is not None:
            return unit
        if default is not _REQUIRED:
            return default
        where = self.source or "this ParameterSet"
        known = ", ".join(sorted(self.units)) or "none"
        raise MissingUnit(
            f"column {column!r} has no unit declared in {where} "
            f"(columns with units: {known})"
        )

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
        source: str | None = None,
    ) -> None:
        self._rows = [dict(row) for row in rows]
        self._units = dict(units or {})
        self._iris = dict(iris or {})
        self._hierarchy = hierarchy or LocationHierarchy()
        self._location_column = location_column
        self._time_column = time_column
        self._source = source

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
            source=str(path),
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
            # The location of the row actually taken, not the candidate that
            # was searched for: with no location requested every row is a
            # candidate and the first one wins, and the provenance has to name
            # it. Reporting ``None`` there while handing back the CH row is
            # precisely the silent precedence this design refuses.
            location_used = values.get(self._location_column, candidate)
            provenance = {
                "location_requested": location,
                "location_used": location_used,
                # Nothing was substituted if nothing was asked for.
                "location_fallback": location is not None and location_used != location,
                "time_requested": time,
                **time_provenance,
            }
            # dict() and read-only views: ParameterRow advertises immutability,
            # and these mappings are the ParameterSet's own live state. One
            # ``row.values[k] = ...`` would otherwise corrupt every later
            # lookup in the run.
            return ParameterRow(
                dict(values),
                MappingProxyType(self._units),
                MappingProxyType(self._iris),
                provenance,
                self._source,
            )
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
            # bool is a numbers.Real (bool subclasses int, int is Integral,
            # Integral is Real), so it must be excluded explicitly here or a
            # boolean column gets averaged into a meaningless float instead
            # of falling through to the lower row's value below.
            if (
                isinstance(low_value, Real)
                and not isinstance(low_value, bool)
                and isinstance(high_value, Real)
                and not isinstance(high_value, bool)
            ):
                interpolated[column] = low_value + (high_value - low_value) * fraction
        return interpolated
