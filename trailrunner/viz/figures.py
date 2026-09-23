"""Pictures of a result. No arithmetic lives here.

Every number these functions draw comes from a Report or an Assessment that
already computed it. If a figure needs something neither carries, that thing
belongs in the Report or the Assessment — a plot that computes its own numbers
is a second implementation nobody tests.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Colour by tier, not by magnitude: a reader needs to see which parts of the
# chain were modelled and which were borrowed before they look at any number.
TIER_COLOURS = {
    "model": "#0b7285",
    "generalising": "#f59f00",
    "background": "#868e96",
}
TRANSPARENT = "rgba(0,0,0,0)"


def _plotly():
    try:
        import plotly.graph_objects as go
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "plotly is needed to draw figures; install it with `uv sync --extra viz`"
        ) from exc
    return go


def _label(node) -> str:
    """The node's name, its model, and the tier that answered it.

    The tier also sets the node's colour, but colour is never the only
    carrier of meaning: a reader using a greyscale printout or a screen
    reader still sees which nodes were modelled and which were borrowed or
    generalised, spelled out here in text.
    """
    iri = node.demand.flow.iri.rstrip("/").rsplit("/", 1)[-1]
    tier = node.resolution.get("tier", "model")
    return f"{iri} ({node.model or 'unknown'}) [{tier}]"


def _layout(figure, title: str, xaxis: str = "", yaxis: str = "") -> None:
    """Transparent canvas so the docs' light and dark themes both work.

    Sets ``xaxis``/``yaxis`` (the primary pair) through explicit dicts on
    ``update_layout`` rather than ``update_xaxes``/``update_yaxes``: those
    default to touching *every* axis of their kind, including a secondary
    ``yaxis2`` a figure may have added for its own, differently-labelled,
    quantity — and a shared helper clobbering a caller's own axis title is
    the last thing a shared helper should do.
    """
    updates: dict[str, Any] = dict(
        title=title,
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    if xaxis:
        updates["xaxis"] = dict(title=dict(text=xaxis))
    if yaxis:
        updates["yaxis"] = dict(title=dict(text=yaxis))
    figure.update_layout(**updates)


def sankey(report, assessment: Any | None = None):
    """The traversal as a flow diagram, coloured by how each node was answered.

    Link width is the child's cumulative contribution when an assessment is
    given, and 1.0 otherwise — an unweighted diagram still shows the shape of
    the chain, which is most of what it is for.
    """
    go = _plotly()
    index = {node.id: position for position, node in enumerate(report.nodes)}
    labels = [_label(node) for node in report.nodes]
    colours = [
        TIER_COLOURS.get(node.resolution.get("tier", "model"), TIER_COLOURS["model"])
        for node in report.nodes
    ]

    sources, targets, values = [], [], []
    for parent, child in report.edges:
        sources.append(index[parent])
        targets.append(index[child])
        values.append(
            abs(assessment.cumulative_by_node.get(child, 0.0)) if assessment else 1.0
        )

    figure = go.Figure(
        go.Sankey(
            node=dict(label=labels, color=colours, pad=18, thickness=14),
            link=dict(source=sources, target=targets, value=values),
        )
    )
    _layout(figure, "Supply chain traversal")
    return figure


def curve(dynamic):
    """The characterized time series and its cumulative integral.

    Two traces, on two axes: the per-year response, and the running total
    that is the number a static LCA would have given at the end of the
    horizon. They are different dimensions — W/m2 in a year against W*yr/m2
    accumulated — so they get different axes rather than a shared one that
    mislabels whichever trace it does not belong to.
    """
    go = _plotly()
    # series has one row per (emission, year) pair, so plotting it raw draws
    # overlapping bars whenever two emissions land in the same year. Sum per
    # year first: the bar is what happened that year, from every emission.
    marginal = dynamic.series.groupby("date", as_index=False)["amount"].sum()

    figure = go.Figure()
    figure.add_trace(
        go.Bar(x=marginal["date"], y=marginal["amount"], name=f"{dynamic.metric}, per year")
    )
    figure.add_trace(
        go.Scatter(
            x=dynamic.curve["date"],
            y=dynamic.curve["amount"],
            name=f"cumulative ({dynamic.cumulative_unit})",
            mode="lines",
            yaxis="y2",
        )
    )
    # Two axes, because the marginal and the cumulative are different
    # dimensions: W/m2 in a year against W*yr/m2 accumulated. One axis for both
    # is the mislabel this phase's predecessor had to fix.
    figure.update_layout(
        yaxis2=dict(overlaying="y", side="right", title=dict(text=dynamic.cumulative_unit))
    )
    _layout(
        figure,
        f"{dynamic.metric} over {dynamic.horizon} years",
        xaxis="year",
        yaxis=dynamic.unit,
    )
    return figure


def contributions(
    assessment,
    top: int = 10,
    by: str = "flow",
    labels: Mapping[int, str] | None = None,
):
    """The ranked contributors, by elementary flow or by node.

    ``labels`` names the nodes when ``by="node"``: an ``Assessment`` keys its
    node contributions by id, not by name — it is a reading of the Report,
    not a copy of it. The caller holds the Report and passes the names
    (typically ``{node.id: node.model for node in report.nodes}``), rather
    than the Assessment carrying a second copy of the graph that could drift
    from the first.
    """
    go = _plotly()
    if by == "flow":
        pairs = [
            (flow.iri.rstrip("/").rsplit("/", 1)[-1], value)
            for (flow, _unit), value in assessment.by_flow.items()
        ]
        axis = "elementary flow"
    elif by == "node":
        names = labels or {}
        pairs = [
            (names.get(node, f"node {node}"), value)
            for node, value in assessment.direct_by_node.items()
        ]
        axis = "node"
    else:
        raise ValueError(f"{by!r} is not a ranking axis; use 'flow' or 'node'")

    pairs.sort(key=lambda pair: abs(pair[1]), reverse=True)
    pairs = pairs[:top]
    figure = go.Figure(go.Bar(x=[name for name, _ in pairs], y=[value for _, value in pairs]))
    _layout(figure, f"Contributions by {axis}", xaxis=axis, yaxis=assessment.unit)
    return figure


def save(figure, path: str | Path) -> None:
    """Write a static figure for the docs. Needs kaleido, from the viz extra."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    figure.write_image(str(path))
