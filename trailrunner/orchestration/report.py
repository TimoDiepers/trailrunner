"""What the caller gets back."""

from dataclasses import dataclass, field
from typing import Any

from trailrunner.core.flow import Flow
from trailrunner.orchestration.log import Log, NodeRecord, UnresolvedRecord


@dataclass
class Report:
    """Aggregated inventory plus everything needed to judge it.

    v1 stops at the inventory: no characterization, so no single score. The
    unresolved list and the provenance table are as much a part of the answer
    as the numbers are.
    """

    inventory: dict[tuple[Flow, str], float] = field(default_factory=dict)
    unresolved: list[UnresolvedRecord] = field(default_factory=list)
    provenance: dict[int, dict[str, Any]] = field(default_factory=dict)
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    warnings: list[tuple[str, int | None]] = field(default_factory=list)
    truncated: bool = False

    @classmethod
    def from_log(cls, log: Log, truncated: bool = False) -> "Report":
        inventory: dict[tuple[Flow, str], float] = {}
        provenance: dict[int, dict[str, Any]] = {}
        for node in log.nodes:
            if node.result.provenance:
                provenance[node.id] = dict(node.result.provenance)
            for exchange in node.result.biosphere:
                key = (exchange.flow, exchange.unit)
                inventory[key] = inventory.get(key, 0.0) + exchange.amount
        return cls(
            inventory=inventory,
            unresolved=list(log.unresolved_records),
            provenance=provenance,
            nodes=list(log.nodes),
            edges=[(edge.parent, edge.child) for edge in log.edges],
            warnings=list(log.warnings),
            truncated=truncated,
        )
