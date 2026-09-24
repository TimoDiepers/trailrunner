"""What the caller gets back."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from trailrunner.core.flow import Flow
from trailrunner.orchestration.log import (
    ATTRIBUTION_KEY,
    Log,
    NodeRecord,
    UnresolvedRecord,
)


def _require_pandas():
    try:
        import pandas
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "pandas is needed for to_dataframe(); install it with "
            "`uv sync --extra viz` or `--extra dynamic`. The parquet log needs nothing."
        ) from exc
    return pandas


def _short(iri: str) -> str:
    """The last path segment of an IRI, for a tree a human reads.

    The full IRI is in the records; a tree whose every line is 60 characters
    of vocabulary URL is a tree nobody reads.
    """
    return iri.rstrip("/").rsplit("/", 1)[-1]


def _namer(labels: Any) -> "Callable[[str], str]":
    """Resolve ``tree()``'s ``labels`` argument to one IRI -> text function.

    A dict and a callable are both natural things to pass — the first is a
    cache read off disk, the second a lookup that can still miss — so both
    are accepted and neither is required to be total.
    """
    if labels is None:
        return _short
    lookup = labels.get if hasattr(labels, "get") else labels

    def name(iri: str) -> str:
        try:
            found = lookup(iri)
        except Exception:  # noqa: BLE001 — a label lookup must never break a tree
            found = None
        return found if found else _short(iri)

    return name


def _where(flow: Flow) -> str:
    where = ""
    if flow.location is not None or flow.time is not None:
        where = f" @{flow.location or '-'}/{flow.time if flow.time is not None else '-'}"
    if flow.context:
        where += f" ({flow.describe_context()})"
    return where


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
    """Per node: what the *model* recorded — the parameter rows it read, the
    fallbacks it took. The run's normative choices are not in here; they are
    in ``attribution``, because the model neither chose nor saw them."""
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
    attribution: dict[int, dict[str, Any]] = field(default_factory=dict)
    """Per node: the allocation rule applied and the shares computed."""
    attribution_settings: Any = None
    """The run's AttributionSettings, so the report states the choices that
    produced it without the reader having to know how it was called."""
    log: Any = None
    """The Log this Report was built from.

    Kept so a caller who only has the Report can still write the run out. The
    Report is a reading of the Log, not a replacement for it, and the parquet
    is the Log's job.
    """

    @classmethod
    def from_log(
        cls, log: Log, truncated: bool = False, attribution_settings: Any = None
    ) -> "Report":
        inventory: dict[tuple[Flow, str], float] = {}
        provenance: dict[int, dict[str, Any]] = {}
        resolutions: dict[int, dict[str, Any]] = {}
        proxies: dict[int, dict[str, Any]] = {}
        attribution: dict[int, dict[str, Any]] = {}
        for node in log.nodes:
            # The attribution record travels on the Result because that is
            # what the Runner had in hand, but it is the orchestrator's, not
            # the model's; it is reported beside provenance, never inside it.
            recorded = {
                key: value
                for key, value in node.result.provenance.items()
                if key != ATTRIBUTION_KEY
            }
            if recorded:
                provenance[node.id] = recorded
            if node.resolution:
                resolutions[node.id] = dict(node.resolution)
                if node.resolution.get("tier", "model") != "model":
                    proxies[node.id] = dict(node.resolution)
            if node.attribution:
                attribution[node.id] = dict(node.attribution)
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
            attribution=attribution,
            attribution_settings=attribution_settings,
            log=log,
        )

    def _tag(self, node: NodeRecord) -> str:
        """How honestly this node was answered, in one bracket.

        A borrow's incompleteness is read from the resolution's ``complete``
        key, not re-derived from ``basis``. ``summary()`` counts incomplete
        proxies from ``complete``; deriving the tag from ``basis`` instead
        meant a ``basis`` neither view recognised printed a bare
        ``[background]`` here while ``summary()`` said "1 incomplete" — two
        views of one node disagreeing, which is precisely what this tag
        exists to prevent.
        """
        tier = node.resolution.get("tier", "model")
        if tier == "background":
            basis = node.resolution.get("basis")
            label = f"background: {basis}" if basis else "background"
            if node.resolution.get("complete") is False:
                label += ", incomplete"
            return f"[{label}]"
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

    def tree(self, indent: str = "  ", labels: Any = None) -> str:
        """The traversal as indented text: the supply chain, and how each node
        was answered, in one screenful.

        Unresolved demands hang under the node that asked for them, because a
        cutoff is a property of the place in the chain where it happened.

        ``labels`` maps a flow's IRI to the name to print for it — a dict, or
        any callable taking an IRI. A flow is *keyed* on its IRI, which is
        what makes two models agree about a product at all; but an IRI is not
        a name, and the vocabulary that issues it also knows what it is
        called (``trailrunner.resolution.PystLabels``). Anything the mapping
        has no name for falls back to the IRI's last segment, so a partial
        mapping is useful and an empty one changes nothing.
        """
        name = _namer(labels)
        children: dict[int | None, list[NodeRecord]] = {}
        for node in self.nodes:
            children.setdefault(node.parent, []).append(node)

        cutoffs: dict[int | None, list[UnresolvedRecord]] = {}
        for record in self.unresolved:
            cutoffs.setdefault(record.parent, []).append(record)

        lines: list[str] = []

        def line(depth: int, amount: float, unit: str, flow: Flow, tag: str) -> None:
            lines.append(f"{indent * depth}{amount:g} {unit} {name(flow.iri)}{_where(flow)}  {tag}")

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

        The proxy line splits out incomplete borrows on their own: a
        ``unit_process`` borrow's upstream is missing, not merely deferred,
        and this is the one-line trust check where that has to be visible
        without a reader opening ``report.proxies`` or ``report.tree()``.

        Both lines also split out what happened on a **credit branch** — a
        negative demand, which under ``substitution`` is an avoided burden
        being traversed. The sign is the point: a forgone burden *understates*
        the impact, a forgone credit *overstates* it, and one bucket counting
        both tells the reader neither. Under any rule but ``substitution``
        nothing negative is ever demanded, so the clause simply never prints.
        """
        reasons: dict[str, int] = {}
        for record in self.unresolved:
            reasons[record.reason] = reasons.get(record.reason, 0) + 1
        credit_cutoffs = sum(1 for record in self.unresolved if record.demand.amount < 0)

        entries = len(self.inventory)
        node_count = len(self.nodes)
        lines = [
            f"{node_count} {'node' if node_count == 1 else 'nodes'}, {entries} inventory "
            f"{'entry' if entries == 1 else 'entries'}",
        ]
        if reasons:
            breakdown = ", ".join(f"{reason}: {count}" for reason, count in sorted(reasons.items()))
            if credit_cutoffs:
                breakdown += f", of which {credit_cutoffs} on a credit branch"
            lines.append(f"{len(self.unresolved)} unresolved ({breakdown})")
        else:
            lines.append("0 unresolved")
        count = len(self.proxies)
        incomplete = sum(
            1 for resolution in self.proxies.values() if resolution.get("complete") is False
        )
        amounts = {node.id: node.demand.amount for node in self.nodes}
        credit_proxies = sum(1 for node_id in self.proxies if amounts.get(node_id, 0.0) < 0)
        proxy_line = f"{count} {'proxy' if count == 1 else 'proxies'}"
        qualifiers = []
        if incomplete:
            qualifiers.append(f"{incomplete} incomplete")
        if credit_proxies:
            qualifiers.append(f"of which {credit_proxies} on a credit branch")
        if qualifiers:
            proxy_line += f" ({', '.join(qualifiers)})"
        lines.append(proxy_line)
        if self.attribution_settings is not None:
            lines.append(
                f"attribution: allocation={self.attribution_settings.allocation}, "
                f"capital={self.attribution_settings.capital}"
            )
        if self.truncated:
            lines.append("traversal was truncated: max_depth or max_nodes was reached")
        if self.warnings:
            lines.append(f"{len(self.warnings)} warnings")
        return "\n".join(lines)

    def to_dataframe(self):
        """One row per node, for anyone who wants to leave for pandas.

        pandas is not a core dependency; the parquet log is the
        dependency-free way out and stays the canonical one.
        """
        pandas = _require_pandas()
        return pandas.DataFrame(
            [
                {
                    "node": node.id,
                    "parent": node.parent,
                    "depth": node.depth,
                    "model": node.model,
                    "tier": node.resolution.get("tier", "model"),
                    "demand_iri": node.demand.flow.iri,
                    "location": node.demand.flow.location,
                    "time": node.demand.flow.time,
                    "amount": node.demand.amount,
                    "unit": node.demand.unit,
                }
                for node in self.nodes
            ]
        )
