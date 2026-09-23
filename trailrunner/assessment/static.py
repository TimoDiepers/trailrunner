"""Inventory times factors, and where the number came from."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from trailrunner.assessment.method import Method
from trailrunner.core.flow import Flow
from trailrunner.orchestration.report import Report


@dataclass
class Assessment:
    """A characterized inventory, plus what could not be characterized.

    ``uncharacterized`` is as much a part of the answer as ``score`` is, for
    the same reason ``report.unresolved`` is: the alternative is a number that
    silently omits whatever the method did not cover.
    """

    score: float = 0.0
    unit: str = ""
    method: str = ""
    by_flow: dict[tuple[Flow, str], float] = field(default_factory=dict)
    direct_by_node: dict[int, float] = field(default_factory=dict)
    cumulative_by_node: dict[int, float] = field(default_factory=dict)
    uncharacterized: list[tuple[Flow, str, float]] = field(default_factory=list)
    provenance: dict[tuple[Flow, str], Mapping[str, Any]] = field(default_factory=dict)


def assess(report: Report, method: Method) -> Assessment:
    """Characterize a finished Report.

    Reads the Report; never touches the traversal. The Orchestrator does not
    know this function exists, which is what keeps the Queue free of scores.
    """
    assessment = Assessment(unit=method.unit, method=method.name)

    for (flow, unit), amount in report.inventory.items():
        factor = method.factor(flow, unit)
        if factor is None:
            assessment.uncharacterized.append((flow, unit, amount))
            continue
        contribution = amount * factor.value
        assessment.score += contribution
        assessment.by_flow[(flow, unit)] = assessment.by_flow.get((flow, unit), 0.0) + contribution
        assessment.provenance[(flow, unit)] = factor.provenance

    for node in report.nodes:
        total = 0.0
        for exchange in node.result.biosphere:
            factor = method.factor(exchange.flow, exchange.unit)
            if factor is not None:
                total += exchange.amount * factor.value
        assessment.direct_by_node[node.id] = total

    children: dict[int, list[int]] = {}
    for parent, child in report.edges:
        children.setdefault(parent, []).append(child)

    def cumulative(node_id: int) -> float:
        if node_id in assessment.cumulative_by_node:
            return assessment.cumulative_by_node[node_id]
        total = assessment.direct_by_node.get(node_id, 0.0)
        for child in children.get(node_id, []):
            total += cumulative(child)
        assessment.cumulative_by_node[node_id] = total
        return total

    # Deepest first, so the memo is warm and the recursion never goes deeper
    # than the traversal already did.
    for node in sorted(report.nodes, key=lambda n: n.depth, reverse=True):
        cumulative(node.id)

    return assessment
