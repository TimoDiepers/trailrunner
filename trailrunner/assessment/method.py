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

from trailrunner.core.errors import DuplicateFactor, MissingColumns, MissingUnit
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
        self._rows: dict[tuple[str, str, str | None, int | None], float] = {}
        for row in rows:
            try:
                key = (
                    row["flow_iri"],
                    row["flow_unit"],
                    row.get("location"),
                    row.get("time"),
                )
            except KeyError as exc:
                raise self._layout_error(source) from exc
            if key in self._rows:
                # Last-wins would put a number in the score that appears in no
                # message anywhere. Two CFs for one key is a data error, the
                # same way two models producing one product is.
                raise DuplicateFactor(
                    f"two characterization factors for "
                    f"(flow_iri={key[0]!r}, flow_unit={key[1]!r}, location={key[2]!r}, "
                    f"time={key[3]!r}) in {source or name}; a method file states "
                    "each factor once"
                )
            self._rows[key] = row["cf"]

    @staticmethod
    def _layout_error(source: str | None) -> MissingColumns:
        return MissingColumns(
            f"{source or 'the method rows'} is not a method file: a method needs "
            "the columns 'flow_iri' (string), 'flow_unit' (string) and 'cf' "
            "(number), plus the optional 'location' (string) and 'time' "
            "(integer); the 'cf' column must declare its unit in the embedded "
            "datapackage metadata"
        )

    @classmethod
    def from_parquet(
        cls, path: str | Path, hierarchy: LocationHierarchy | None = None
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
                "the optional 'location' (string) and 'time' (integer), and the "
                f"'cf' column must declare its unit (found: "
                f"{', '.join(table.schema.names) or 'no columns at all'})"
            )
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
                            "location_requested": flow.location,
                            "location_used": location,
                            # Nothing was substituted if nothing was asked for.
                            "location_fallback": flow.location is not None
                            and location != flow.location,
                            "time_used": time,
                            "method": self.name,
                        },
                    )
        return None
