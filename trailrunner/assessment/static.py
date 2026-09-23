"""Inventory times factors, and where the number came from."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from trailrunner.assessment.method import Method
from trailrunner.core.flow import Flow
from trailrunner.orchestration.report import Report


def _require_pandas():
    try:
        import pandas
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "pandas is needed for to_dataframe(); install it with "
            "`uv sync --extra viz` or `--extra dynamic`. The parquet log needs nothing."
        ) from exc
    return pandas


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
    uncharacterized_by_node: dict[int, list[tuple[Flow, str, float]]] = field(
        default_factory=dict
    )
    """Per node: the exchanges of that node the method had no factor for.

    Without this, ``direct_by_node`` is the one place the module's own rule
    breaks down: a node whose only emission has no CF scores ``0.0``, which
    reads exactly like a node that emitted nothing. ``uncharacterized`` alone
    cannot fix that, because it carries a ``Flow``, not a node id, and the two
    cannot be joined after the fact.
    """
    provenance: dict[tuple[Flow, str], Mapping[str, Any]] = field(default_factory=dict)

    truncated: bool = False
    """``report.truncated``, carried through.

    A consumer handed only an ``Assessment`` would otherwise have no way to
    tell a complete traversal's score from one that hit ``max_nodes`` halfway
    down the chain — two very different claims that look identical as floats.
    """
    unresolved: int = 0
    """How many demands the traversal could not resolve (``len(report.unresolved)``)."""
    proxies: int = 0
    """How many nodes were answered by something other than an exact model match."""

    def summary(self) -> str:
        """Score, method, and every reason to distrust the score, in one block.

        The same shape as ``Report.summary()``, and for the same reason: the
        caveats belong in front of a reader who did not know to go looking for
        them. Returns the block rather than printing it.
        """
        lines = [
            f"{self.score:g} {self.unit}".strip(),
            f"method: {self.method}",
        ]
        count = len(self.uncharacterized)
        if count:
            nodes = len(self.uncharacterized_by_node)
            lines.append(
                f"{count} uncharacterized "
                f"{'flow' if count == 1 else 'flows'} on "
                f"{nodes} {'node' if nodes == 1 else 'nodes'} "
                "(not in the score, and not zero)"
            )
        else:
            lines.append("0 uncharacterized flows")
        lines.append(f"{self.unresolved} unresolved")
        lines.append(f"{self.proxies} {'proxy' if self.proxies == 1 else 'proxies'}")
        if self.truncated:
            lines.append("traversal was truncated: max_depth or max_nodes was reached")
        return "\n".join(lines)

    def to_dataframe(self):
        """One row per characterized flow, score descending.

        Carries the **score**, not the inventory amount: the amount belongs
        to the ``Report``, and an ``Assessment`` is a reading of a Report
        rather than a copy of one — widening ``by_flow`` to carry both would
        put the same number in two places that can drift. A caller who wants
        both joins this frame with ``Report.to_dataframe()`` on
        ``(flow_iri, unit)``.
        """
        pandas = _require_pandas()
        frame = pandas.DataFrame(
            [
                {
                    "flow_iri": flow.iri,
                    "location": flow.location,
                    "time": flow.time,
                    "unit": unit,
                    "score": score,
                }
                for (flow, unit), score in self.by_flow.items()
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values("score", ascending=False, key=abs).reset_index(drop=True)


def assess(report: Report, method: Method) -> Assessment:
    """Characterize a finished Report.

    Reads the Report; never touches the traversal. The Orchestrator does not
    know this function exists, which is what keeps the Queue free of scores.
    """
    assessment = Assessment(
        unit=method.unit,
        method=method.name,
        truncated=report.truncated,
        unresolved=len(report.unresolved),
        proxies=len(report.proxies),
    )

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
            if factor is None:
                # Both the node and the flow are in hand here and nowhere
                # else, so this is the only place the two can be joined.
                assessment.uncharacterized_by_node.setdefault(node.id, []).append(
                    (exchange.flow, exchange.unit, exchange.amount)
                )
                continue
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
