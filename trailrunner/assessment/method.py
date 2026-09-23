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
                            # Nothing was substituted if nothing was asked for.
                            "location_fallback": flow.location is not None
                            and location != flow.location,
                            "time_used": time,
                            "method": self.name,
                        },
                    )
        return None
