---
icon: lucide/chart-network
tags:
  - concepts
---

# Figures

`trailrunner.viz` draws a `Report` or an assessment with [plotly](https://plotly.com/python/).
It needs the `viz` extra:

```bash
uv sync --extra viz
```

plotly is imported only when a figure is drawn, so `import trailrunner` keeps working with
pyarrow alone. **The figures do no arithmetic.** Every number they draw comes from a
`Report`, `Assessment` or `DynamicAssessment` that already computed it, so a figure can't
disagree with the objects it shows.

Each function returns a `plotly.graph_objects.Figure`. Show it in a notebook, call
`.show()`, or save it. The figures below are from the [5-minute tour](../showcase.md),
built by `dev/build_showcase_assets.py` from `examples/showcase.ipynb`.

## `sankey`

The traversal as a flow diagram, with nodes coloured by the tier that answered them:

```python
from trailrunner import viz

viz.sankey(report)                          # every link width 1: the shape of the chain
viz.sankey(report, assessment=assessment)   # link width = the child's cumulative score
```

![Supply chain traversal as a Sankey diagram](../assets/showcase/sankey.svg)

Each node's label also names its model and tier in text, so the figure still reads in
greyscale. The colours are in `viz.TIER_COLOURS` (`model` teal, `generalising` amber,
`background` grey).

!!! warning "Width is magnitude, not sign"

    A Sankey ribbon can't be negative, so a [substitution credit](attribution.md#who-may-answer-a-credit)
    draws exactly as wide as a burden of the same size. Read signs from
    `assessment.cumulative_by_node` or the contributions chart.

## `contributions`

The top contributors to a static [`Assessment`](assessment.md#assess), by elementary flow or
by node, ranked by absolute value:

```python
viz.contributions(assessment, top=10)             # by flow
viz.contributions(
    assessment,
    by="node",
    labels={node.id: node.model for node in report.nodes},
)
```

![Contribution to the GWP100 score by node](../assets/showcase/contributions.svg)

An `Assessment` keys nodes by id and doesn't copy the graph, so pass `labels` to name them.
Without it the bars read `node 0`, `node 1`, and so on.

## `curve`

A [`DynamicAssessment`](assessment.md#assess_dynamic-a-time-explicit-reading) as two
traces on two axes: the per-year values as bars (summed over emissions landing in the same
year) and the running total as a line.

```python
from trailrunner.assessment import assess_dynamic

dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
viz.curve(dynamic)
```

![Marginal and cumulative radiative forcing over 100 years](../assets/showcase/curve.svg)

The two traces have different units (W/m² in a year against W·yr/m² accumulated), so each
has its own axis, labelled with `dynamic.unit` and `dynamic.cumulative_unit`.

## Saving

```python
viz.save(figure, "figures/sankey.svg")
```

writes a static image with kaleido (part of the `viz` extra), creating the directory if
needed. The format follows the extension. Figures have a transparent background so they
work on light and dark pages alike.

For interactive HTML, use plotly directly: `figure.write_html("sankey.html")`.
