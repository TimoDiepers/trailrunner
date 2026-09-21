"""Append-only record of everything the traversal did."""

from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from trailrunner.core.flow import Demand
from trailrunner.core.result import Result

LOG_COLUMNS = (
    "node",
    "parent",
    "depth",
    "demand_iri",
    "demand_location",
    "demand_time",
    "demand_amount",
    "demand_unit",
    "flow_iri",
    "flow_location",
    "flow_time",
    "amount",
    "unit",
)


@dataclass
class NodeRecord:
    id: int
    demand: Demand
    result: Result
    depth: int
    parent: int | None


@dataclass
class UnresolvedRecord:
    demand: Demand
    reason: str
    depth: int
    parent: int | None


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
        self, demand: Demand, result: Result, depth: int = 0, parent: int | None = None
    ) -> int:
        node_id = len(self.nodes)
        self.nodes.append(
            NodeRecord(id=node_id, demand=demand, result=result, depth=depth, parent=parent)
        )
        if parent is not None:
            self.edges.append(EdgeRecord(parent=parent, child=node_id))
        return node_id

    def unresolved(
        self, demand: Demand, reason: str, depth: int = 0, parent: int | None = None
    ) -> None:
        self.unresolved_records.append(
            UnresolvedRecord(demand=demand, reason=reason, depth=depth, parent=parent)
        )

    def warn(self, message: str, node: int | None = None) -> None:
        self.warnings.append((message, node))

    def to_parquet(self, path: str | Path) -> None:
        """Write one row per biosphere exchange, keyed to its node.

        Makes two runs diffable, and mirrors the parquet-in, parquet-out shape
        of the trailpack side.
        """
        rows = [
            {
                "node": node.id,
                "parent": node.parent,
                "depth": node.depth,
                "demand_iri": node.demand.flow.iri,
                "demand_location": node.demand.flow.location,
                "demand_time": node.demand.flow.time,
                "demand_amount": node.demand.amount,
                "demand_unit": node.demand.unit,
                "flow_iri": exchange.flow.iri,
                "flow_location": exchange.flow.location,
                "flow_time": exchange.flow.time,
                "amount": exchange.amount,
                "unit": exchange.unit,
            }
            for node in self.nodes
            for exchange in node.result.biosphere
        ]
        if rows:
            table = pa.Table.from_pylist(rows)
        else:
            table = pa.Table.from_pydict({column: [] for column in LOG_COLUMNS})
        pq.write_table(table, path)
