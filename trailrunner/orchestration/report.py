"""What the caller gets back."""

from dataclasses import dataclass, field
from typing import Any

from trailrunner.core.flow import Flow
from trailrunner.orchestration.log import Log, NodeRecord, UnresolvedRecord


def _short(iri: str) -> str:
    """The last path segment of an IRI, for a tree a human reads.

    The full IRI is in the records; a tree whose every line is 60 characters
    of vocabulary URL is a tree nobody reads.
    """
    return iri.rstrip("/").rsplit("/", 1)[-1]


def _where(flow: Flow) -> str:
    if flow.location is None and flow.time is None:
        return ""
    return f" @{flow.location or '-'}/{flow.time if flow.time is not None else '-'}"


@dataclass
class Report:
    """Aggregated inventory plus everything needed to judge it.

    A ``Report`` is the inventory and nothing else: it takes no position on
    how much any of it matters. ``trailrunner.assessment`` characterizes one
    into a score or a time-explicit curve, as a separate reading afterwards;
    nothing here knows that package exists, and nothing here changes if it is
    never imported.

    The unresolved list and the provenance table are as much a part of the
    answer as the numbers are.
    """

    inventory: dict[tuple[Flow, str], float] = field(default_factory=dict)
    unresolved: list[UnresolvedRecord] = field(default_factory=list)
    provenance: dict[int, dict[str, Any]] = field(default_factory=dict)
    resolutions: dict[int, dict[str, Any]] = field(default_factory=dict)
    """Per node: which tier answered its demand, and what was relaxed to get there."""
    proxies: dict[int, dict[str, Any]] = field(default_factory=dict)
    """The subset of ``resolutions`` that were not exact model matches.

    A number answered by a generalised demand or borrowed from the background
    is a different kind of number, and the report says which nodes those are
    without the reader having to filter.
    """
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    warnings: list[tuple[str, int | None]] = field(default_factory=list)
    truncated: bool = False

    @classmethod
    def from_log(cls, log: Log, truncated: bool = False) -> "Report":
        inventory: dict[tuple[Flow, str], float] = {}
        provenance: dict[int, dict[str, Any]] = {}
        resolutions: dict[int, dict[str, Any]] = {}
        proxies: dict[int, dict[str, Any]] = {}
        for node in log.nodes:
            if node.result.provenance:
                provenance[node.id] = dict(node.result.provenance)
            if node.resolution:
                resolutions[node.id] = dict(node.resolution)
                if node.resolution.get("tier", "model") != "model":
                    proxies[node.id] = dict(node.resolution)
            for exchange in node.result.biosphere:
                key = (exchange.flow, exchange.unit)
                inventory[key] = inventory.get(key, 0.0) + exchange.amount
        return cls(
            inventory=inventory,
            unresolved=list(log.unresolved_records),
            provenance=provenance,
            resolutions=resolutions,
            proxies=proxies,
            nodes=list(log.nodes),
            edges=[(edge.parent, edge.child) for edge in log.edges],
            warnings=list(log.warnings),
            truncated=truncated,
        )

    def _tag(self, node: NodeRecord) -> str:
        """How honestly this node was answered, in one bracket."""
        tier = node.resolution.get("tier", "model")
        if tier == "background":
            basis = node.resolution.get("basis")
            if basis == "unit_process":
                return "[background: unit_process, incomplete]"
            if basis == "cumulative":
                return "[background: cumulative]"
            return "[background]"
        if tier == "generalising":
            relaxations = node.resolution.get("relaxations") or []
            joined = "; ".join(str(relaxation) for relaxation in relaxations)
            return f"[proxy: {joined}]" if relaxations else "[proxy]"
        if tier == "model":
            return f"[model: {node.model}]" if node.model else "[model]"
        # An unrecognised tier must never read as an exact match: this is what
        # keeps tree() and proxies (anything whose tier isn't "model") in
        # agreement, even for a tier a later phase's provider chain invents.
        return f"[{tier}]"

    def tree(self, indent: str = "  ") -> str:
        """The traversal as indented text: the supply chain, and how each node
        was answered, in one screenful.

        Unresolved demands hang under the node that asked for them, because a
        cutoff is a property of the place in the chain where it happened.
        """
        children: dict[int | None, list[NodeRecord]] = {}
        for node in self.nodes:
            children.setdefault(node.parent, []).append(node)

        cutoffs: dict[int | None, list[UnresolvedRecord]] = {}
        for record in self.unresolved:
            cutoffs.setdefault(record.parent, []).append(record)

        lines: list[str] = []

        def line(depth: int, amount: float, unit: str, flow: Flow, tag: str) -> None:
            lines.append(f"{indent * depth}{amount:g} {unit} {_short(flow.iri)}{_where(flow)}  {tag}")

        def walk(node: NodeRecord, depth: int) -> None:
            line(depth, node.demand.amount, node.demand.unit, node.demand.flow, self._tag(node))
            for child in children.get(node.id, []):
                walk(child, depth + 1)
            for record in cutoffs.get(node.id, []):
                line(
                    depth + 1,
                    record.demand.amount,
                    record.demand.unit,
                    record.demand.flow,
                    f"[cutoff: {record.reason}]",
                )

        for root in children.get(None, []):
            walk(root, 0)
        for record in cutoffs.get(None, []):
            line(0, record.demand.amount, record.demand.unit, record.demand.flow,
                 f"[cutoff: {record.reason}]")
        return "\n".join(lines)

    def summary(self) -> str:
        """Everything needed to judge the numbers, in one block.

        Node and inventory counts come first, then the unresolved breakdown
        and the proxy count, then the truncation and warning flags — the
        numbers to check before trusting the inventory, in that order.
        """
        reasons: dict[str, int] = {}
        for record in self.unresolved:
            reasons[record.reason] = reasons.get(record.reason, 0) + 1

        entries = len(self.inventory)
        node_count = len(self.nodes)
        lines = [
            f"{node_count} {'node' if node_count == 1 else 'nodes'}, {entries} inventory "
            f"{'entry' if entries == 1 else 'entries'}",
        ]
        if reasons:
            breakdown = ", ".join(f"{reason}: {count}" for reason, count in sorted(reasons.items()))
            lines.append(f"{len(self.unresolved)} unresolved ({breakdown})")
        else:
            lines.append("0 unresolved")
        count = len(self.proxies)
        lines.append(f"{count} {'proxy' if count == 1 else 'proxies'}")
        if self.truncated:
            lines.append("traversal was truncated: max_depth or max_nodes was reached")
        if self.warnings:
            lines.append(f"{len(self.warnings)} warnings")
        return "\n".join(lines)
