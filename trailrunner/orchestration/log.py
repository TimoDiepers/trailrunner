"""Append-only record of everything the traversal did."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from trailrunner.core.flow import Demand, Flow
from trailrunner.core.result import Result
from trailrunner.core.time import interval

LOG_SCHEMA = pa.schema(
    [
        # Which kind of record this row is: "biosphere" (one per biosphere
        # exchange), "node" (a node that emitted none, so it does not vanish),
        # "unresolved" (a cutoff leaf), "provenance" (one per key a node
        # recorded), "resolution" (one per key of how a node's demand was
        # matched) or "attribution" (one per key of the normative choice
        # applied to it). One flat table rather than six files, because the
        # point is to diff two runs with a single read.
        ("kind", pa.string()),
        ("model", pa.string()),
        ("node", pa.int64()),
        ("parent", pa.int64()),
        ("depth", pa.int64()),
        ("demand_iri", pa.string()),
        ("demand_location", pa.string()),
        ("demand_time", pa.string()),
        ("demand_time_standard", pa.string()),
        ("demand_time_start", pa.timestamp("us", tz="UTC")),
        ("demand_time_end", pa.timestamp("us", tz="UTC")),
        ("demand_context", pa.string()),
        ("demand_amount", pa.float64()),
        ("demand_unit", pa.string()),
        ("flow_iri", pa.string()),
        ("flow_location", pa.string()),
        ("flow_time", pa.string()),
        ("flow_time_standard", pa.string()),
        ("flow_time_start", pa.timestamp("us", tz="UTC")),
        ("flow_time_end", pa.timestamp("us", tz="UTC")),
        ("flow_context", pa.string()),
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


ATTRIBUTION_KEY = "attribution"
"""The one provenance key the orchestration layer writes and owns.

``allocate`` and ``substitute`` leave their record on the Result because that
is the object the Runner has in hand. It is lifted out here rather than left
among the model's own keys -- see ``NodeRecord.attribution``.
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

    attribution: dict[str, Any] = field(default_factory=dict)
    """The run's normative choice as applied to this node: the allocation rule,
    the property partitioned on, the share, the co-products credited.

    Its own field, beside ``resolution``, on the same split. ``allocate`` and
    ``substitute`` write it into ``Result.provenance`` because that is the
    object in the Runner's hand, but it is not the model's record: the model
    never chose the rule and cannot see it. Leaving it there put a key nothing
    modelled into every node of ``report.provenance``, which is documented as
    what the model recorded. Lifted here, all three views stay true to their
    own definition.
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


def _flatten(base: dict, kind: str, record: dict) -> list[dict]:
    """One row per leaf of ``record``, never a Python repr in a cell.

    A list becomes "<singular>.0", "<singular>.1", ... (``relaxations`` ->
    ``relaxation.0``, ``co_products`` -> ``co_product.0``) and a nested dict
    becomes "<key>.<subkey>". Both for the same reason: a value stringified
    whole lands as a repr the reader has to parse back out, which with one
    relaxation is ugly and with a whole attribution record -- rule, property,
    share and every credited co-product in one cell -- is unusable. The run is
    supposed to be reproducible from the committed parquet, and a column a
    reader cannot filter on is not.
    """
    rows: list[dict] = []
    for key, value in record.items():
        if isinstance(value, list):
            singular = key[:-1] if key.endswith("s") else key
            for index, item in enumerate(value):
                rows.append(
                    {
                        **base,
                        "kind": kind,
                        "key": f"{singular}.{index}",
                        "value": None if item is None else str(item),
                    }
                )
        elif isinstance(value, dict):
            for subkey, item in value.items():
                rows.append(
                    {
                        **base,
                        "kind": kind,
                        "key": f"{key}.{subkey}",
                        "value": None if item is None else str(item),
                    }
                )
        else:
            rows.append(
                {
                    **base,
                    "kind": kind,
                    "key": str(key),
                    "value": None if value is None else str(value),
                }
            )
    return rows


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
                attribution=dict(result.provenance.get(ATTRIBUTION_KEY) or {}),
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
        """Write the whole log — nodes, biosphere exchanges, cutoff leaves,
        provenance, resolution and attribution — one row each, tagged by
        ``kind``.

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
                **_identity("demand", node.demand.flow),
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
                        **_identity("flow", exchange.flow),
                        "amount": exchange.amount,
                        "unit": exchange.unit,
                    }
                )
            if not node.result.biosphere:
                # A node that emitted nothing still ran, and still has a place
                # in the graph; without this row it would vanish from the file.
                rows.append({**base, "kind": "node"})
            for key, value in node.result.provenance.items():
                if key == ATTRIBUTION_KEY:
                    # Written below, flattened, under its own kind: it is the
                    # orchestrator's record, not the model's, and a nested
                    # dict in one cell is exactly the Python repr the
                    # resolution branch flattens to avoid.
                    continue
                rows.append(
                    {
                        **base,
                        "kind": "provenance",
                        "key": str(key),
                        "value": None if value is None else str(value),
                    }
                )
            rows.extend(_flatten(base, "resolution", node.resolution))
            rows.extend(_flatten(base, ATTRIBUTION_KEY, node.attribution))

        for record in self.unresolved_records:
            rows.append(
                {
                    "kind": "unresolved",
                    "parent": record.parent,
                    "depth": record.depth,
                    "demand_iri": record.demand.flow.iri,
                    "demand_location": record.demand.flow.location,
                    **_identity("demand", record.demand.flow),
                    "demand_amount": record.demand.amount,
                    "demand_unit": record.demand.unit,
                    "reason": record.reason,
                    "detail": record.detail,
                }
            )

        pq.write_table(pa.Table.from_pylist(rows, schema=LOG_SCHEMA), path)
