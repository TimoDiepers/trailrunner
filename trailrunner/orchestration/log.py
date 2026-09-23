"""Append-only record of everything the traversal did."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from trailrunner.core.flow import Demand
from trailrunner.core.result import Result

LOG_SCHEMA = pa.schema(
    [
        # Which kind of record this row is: "biosphere" (one per biosphere
        # exchange), "node" (a node that emitted none, so it does not vanish),
        # "unresolved" (a cutoff leaf), "provenance" (one per key a node
        # recorded) or "resolution" (one per key of how a node's demand was
        # matched). One flat table rather than five files, because the point
        # is to diff two runs with a single read.
        ("kind", pa.string()),
        ("model", pa.string()),
        ("node", pa.int64()),
        ("parent", pa.int64()),
        ("depth", pa.int64()),
        ("demand_iri", pa.string()),
        ("demand_location", pa.string()),
        ("demand_time", pa.int64()),
        ("demand_amount", pa.float64()),
        ("demand_unit", pa.string()),
        ("flow_iri", pa.string()),
        ("flow_location", pa.string()),
        ("flow_time", pa.int64()),
        ("amount", pa.float64()),
        ("unit", pa.string()),
        ("reason", pa.string()),
        ("detail", pa.string()),
        ("key", pa.string()),
        ("value", pa.string()),
    ]
)
"""One explicit schema for every row kind, used by both the populated and the
empty branch of :meth:`Log.to_parquet`.

Declaring it here rather than inferring it from the rows is what lets an empty
log concatenate with a populated one: inferred columns of an empty table are
pyarrow ``null``-typed and will not merge with ``int64`` or ``string``.
"""


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

    Every node carries at least ``{"tier": "model"}`` today. A later phase's
    provider chain widens this to ``"generalising"`` or ``"background"``,
    along with the ``relaxations`` that got there. Kept here rather than in
    ``Result.provenance`` because provenance is the *model's* record of the
    parameters it used, and resolution is the *orchestrator's* record of how
    that model was chosen.
    """


@dataclass
class UnresolvedRecord:
    demand: Demand
    reason: str
    depth: int
    parent: int | None
    detail: str | None = None
    """Free text qualifying ``reason`` — for ``coverage_excluded``, the models
    that declare the product but whose coverage rejected this flow."""


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

    def unresolved(
        self,
        demand: Demand,
        reason: str,
        depth: int = 0,
        parent: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.unresolved_records.append(
            UnresolvedRecord(
                demand=demand, reason=reason, depth=depth, parent=parent, detail=detail
            )
        )

    def warn(self, message: str, node: int | None = None) -> None:
        self.warnings.append((message, node))

    def to_parquet(self, path: str | Path) -> None:
        """Write the whole log — nodes, biosphere exchanges, cutoff leaves and
        provenance — one row each, tagged by ``kind``.

        Everything the Log holds goes out, because the unresolved list and the
        provenance are as much a part of the answer as the numbers are: two
        runs that differ only in which cutoffs they hit or which parameter
        fallbacks they took must differ on disk too. Mirrors the parquet-in,
        parquet-out shape of the trailpack side.
        """
        rows: list[dict] = []
        for node in self.nodes:
            base = {
                "node": node.id,
                "parent": node.parent,
                "depth": node.depth,
                "demand_iri": node.demand.flow.iri,
                "demand_location": node.demand.flow.location,
                "demand_time": node.demand.flow.time,
                "demand_amount": node.demand.amount,
                "demand_unit": node.demand.unit,
                "model": node.model,
            }
            for exchange in node.result.biosphere:
                rows.append(
                    {
                        **base,
                        "kind": "biosphere",
                        "flow_iri": exchange.flow.iri,
                        "flow_location": exchange.flow.location,
                        "flow_time": exchange.flow.time,
                        "amount": exchange.amount,
                        "unit": exchange.unit,
                    }
                )
            if not node.result.biosphere:
                # A node that emitted nothing still ran, and still has a place
                # in the graph; without this row it would vanish from the file.
                rows.append({**base, "kind": "node"})
            for key, value in node.result.provenance.items():
                rows.append(
                    {
                        **base,
                        "kind": "provenance",
                        "key": str(key),
                        "value": None if value is None else str(value),
                    }
                )
            for key, value in node.resolution.items():
                if isinstance(value, list):
                    # One row per item, keyed "<singular>.0", "<singular>.1",
                    # ... (e.g. "relaxations" -> "relaxation.0") -- a list
                    # stringified whole lands as a Python repr a reader has to
                    # parse back out. With one relaxation that is ugly; with
                    # several (a node can carry more than one, in this
                    # phase) it is unusable.
                    singular = key[:-1] if key.endswith("s") else key
                    for index, item in enumerate(value):
                        rows.append(
                            {
                                **base,
                                "kind": "resolution",
                                "key": f"{singular}.{index}",
                                "value": None if item is None else str(item),
                            }
                        )
                else:
                    rows.append(
                        {
                            **base,
                            "kind": "resolution",
                            "key": str(key),
                            "value": None if value is None else str(value),
                        }
                    )

        for record in self.unresolved_records:
            rows.append(
                {
                    "kind": "unresolved",
                    "parent": record.parent,
                    "depth": record.depth,
                    "demand_iri": record.demand.flow.iri,
                    "demand_location": record.demand.flow.location,
                    "demand_time": record.demand.flow.time,
                    "demand_amount": record.demand.amount,
                    "demand_unit": record.demand.unit,
                    "reason": record.reason,
                    "detail": record.detail,
                }
            )

        pq.write_table(pa.Table.from_pylist(rows, schema=LOG_SCHEMA), path)
