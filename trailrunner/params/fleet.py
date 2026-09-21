"""The plants that actually exist, with the years they were actually built.

``ParameterSet`` answers "what is the number here and now", and one row wins.
A fleet is the other shape: *every* plant running in the demanded year is part
of the answer, because each was built in its own year and its construction
belongs in that year, not in the year it captures anything.

Nothing here decides how construction is amortized — that is the model's job.
This resolves which plants are running, how much capacity they add up to, and
when they were built.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyarrow.parquet as pq

from trailrunner.core.errors import MissingUnit, ParameterNotFound
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import _read_field_metadata

_REQUIRED = object()
"""Sentinel: ``unit_of`` raises unless the caller passes an explicit default."""


@dataclass(frozen=True)
class FleetSelection:
    """The plants running at one place and time, and what they add up to.

    ``plants`` are the rows themselves, so a model can read any column it put
    in the table. The two summaries it will always want — the capacity to
    divide by and the capacity-weighted mean build year — are computed here so
    that every model computes them the same way.
    """

    plants: Sequence[Mapping[str, Any]]
    total_capacity: float
    mean_build_year: float
    provenance: Mapping[str, Any]
    units: Mapping[str, str]
    source: str | None = None

    def unit_of(self, column: str, default: Any = _REQUIRED) -> Any:
        """The unit declared for ``column``. Strict, for the same reason
        :meth:`ParameterRow.unit_of` is: the caller is building an Exchange."""
        unit = self.units.get(column)
        if unit is not None:
            return unit
        if default is not _REQUIRED:
            return default
        where = self.source or "this Fleet"
        known = ", ".join(sorted(self.units)) or "none"
        raise MissingUnit(
            f"column {column!r} has no unit declared in {where} "
            f"(columns with units: {known})"
        )


class Fleet:
    """A table of built plants, selected by where and when they operate.

    A plant is running in ``time`` when ``build_year <= time < build_year +
    lifetime``. The window is half-open at the top so the year a plant retires
    is not also a year it produces: a twenty-year plant built in 2005 is gone
    by 2025, not still running in it.

    The location hierarchy widens exactly as it does for a ParameterSet — but
    the answer is every plant at the first location that has any, never a mix
    of two levels, because a fleet that pooled the Swiss plants with the
    European ones would double-count the Swiss ones.
    """

    def __init__(
        self,
        rows: Iterable[Mapping[str, Any]],
        units: Mapping[str, str] | None = None,
        iris: Mapping[str, str] | None = None,
        hierarchy: LocationHierarchy | None = None,
        location_column: str = "location",
        build_year_column: str = "build_year",
        capacity_column: str = "capacity",
        lifetime_column: str = "lifetime",
        identifier_column: str = "plant",
        source: str | None = None,
    ) -> None:
        self._rows = [dict(row) for row in rows]
        self._units = dict(units or {})
        self._iris = dict(iris or {})
        self._hierarchy = hierarchy or LocationHierarchy()
        self._location_column = location_column
        self._build_year_column = build_year_column
        self._capacity_column = capacity_column
        self._lifetime_column = lifetime_column
        self._identifier_column = identifier_column
        self._source = source

    @classmethod
    def from_parquet(
        cls,
        path: str | Path,
        hierarchy: LocationHierarchy | None = None,
        **columns: str,
    ) -> "Fleet":
        table = pq.read_table(path)
        units, iris = _read_field_metadata(table.schema)
        return cls(
            table.to_pylist(),
            units=units,
            iris=iris,
            hierarchy=hierarchy,
            source=str(path),
            **columns,
        )

    @property
    def capacity_column(self) -> str:
        """The column a model divides by — it needs the name to ask for its unit."""
        return self._capacity_column

    @property
    def lifetime_column(self) -> str:
        return self._lifetime_column

    def operating(
        self, location: str | None = None, time: int | None = None
    ) -> FleetSelection:
        """Every plant running at ``location`` in ``time``.

        ``time=None`` means the year is not a criterion, matching what it means
        in a ParameterSet lookup: take the whole fleet at that location.
        """
        for candidate in self._hierarchy.chain(location):
            plants = [
                row
                for row in self._rows_for_location(candidate)
                if self._is_running(row, time)
            ]
            if not plants:
                continue
            total_capacity = sum(float(row[self._capacity_column]) for row in plants)
            location_used = plants[0].get(self._location_column, candidate)
            provenance = {
                "location_requested": location,
                "location_used": location_used,
                "location_fallback": location is not None and location_used != location,
                "time_requested": time,
                "plants": [row.get(self._identifier_column) for row in plants],
                "total_capacity": total_capacity,
                "mean_build_year": self._mean_build_year(plants, total_capacity),
            }
            return FleetSelection(
                plants=tuple(dict(row) for row in plants),
                total_capacity=total_capacity,
                mean_build_year=provenance["mean_build_year"],
                provenance=provenance,
                units=MappingProxyType(self._units),
                source=self._source,
            )
        raise ParameterNotFound(
            f"no plant operating at location={location!r} time={time!r} "
            f"(tried {self._hierarchy.chain(location)})"
        )

    def _rows_for_location(self, candidate: str | None) -> list[dict[str, Any]]:
        if candidate is None:
            return list(self._rows)
        return [row for row in self._rows if row.get(self._location_column) == candidate]

    def _is_running(self, row: Mapping[str, Any], time: int | None) -> bool:
        if time is None:
            return True
        built = row.get(self._build_year_column)
        if not isinstance(built, Real):
            return False
        lifetime = row.get(self._lifetime_column)
        if not isinstance(lifetime, Real):
            # No lifetime is "still running": a table that does not say when a
            # plant retires has not said that it has.
            return built <= time
        return built <= time < built + lifetime

    def _mean_build_year(
        self, plants: Sequence[Mapping[str, Any]], total_capacity: float
    ) -> float:
        """Capacity-weighted, because a 40 MW plant is not one vote like a 4 MW one.

        Falls back to the unweighted mean when the fleet has no capacity at
        all, which is the only reading left when nothing can be weighted.
        """
        years = [float(row[self._build_year_column]) for row in plants]
        if total_capacity <= 0:
            return sum(years) / len(years)
        weighted = sum(
            float(row[self._build_year_column]) * float(row[self._capacity_column])
            for row in plants
        )
        return weighted / total_capacity
