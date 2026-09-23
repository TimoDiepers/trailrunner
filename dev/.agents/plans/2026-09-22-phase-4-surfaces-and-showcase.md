# Phase 4 — Surfaces and Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the result visible — a Sankey, a forcing curve, a contribution ranking, a one-line CLI — and assemble the seven-beat showcase page that presents the whole thing in five minutes without touching the network.

**Architecture:** `trailrunner/viz/` and `trailrunner/cli.py` are thin readers. They own no logic: everything they draw or print comes from a `Report` or an `Assessment` that already exists. The showcase is a docs page whose figures are pre-rendered by `dev/build_showcase_assets.py` from `examples/showcase.ipynb` and committed, so presenting needs no build, no network and no compute.

**Tech Stack:** Python >= 3.11, uv, plotly behind the `[viz]` extra, stdlib `argparse` for the CLI, pytest. Figures exported as static SVG.

**Spec:** `dev/.agents/specs/2026-09-22-trailrunner-v2-design.md` §4 and §5

## Global Constraints

- Python `>= 3.11`. `plotly` and `kaleido` (for static export) live behind the
  `[viz]` extra and are lazily imported. The CLI adds **no** dependency.
- **Nothing in the showcase path touches the network at presentation time.**
  Figures are committed SVGs; the PyST cache is the committed
  `examples/pyst_cache.json`; the background pack is the committed parquet.
- Viz and CLI own no computation. If a number is needed that the `Report` or
  `Assessment` does not already carry, it is added there, not computed here.
- Every figure must be legible in both light and dark docs themes: no
  hard-coded white backgrounds, no colour as the only carrier of meaning.
- All tooling runs through `uv`. Repo root is
  `/Users/timodiepers/Documents/Coding/trailrunner`.
- Work on branch `feat/phase-4-surfaces`, branched from `feat/phase-3-attribution`.
- Commit after every task, with no attribution trailer and no tooling references.

## File Structure

| File | Responsibility |
|---|---|
| `trailrunner/viz/__init__.py` | public surface: `sankey`, `curve`, `contributions` |
| `trailrunner/viz/figures.py` | the three figure builders |
| `trailrunner/cli.py` | `trailrunner run` |
| `examples/showcase.ipynb` | the seven beats as runnable code |
| `dev/build_showcase_assets.py` | executes the notebook, writes the SVGs |
| `docs/showcase.md` | the page presented on stage |
| `docs/assets/showcase/*.svg` | committed figures |
| `tests/test_viz.py` | figure structure, not pixels |
| `tests/test_cli.py` | exit code, output, written parquet |

---

### Task 1: `trailrunner/viz`

**Files:**
- Create: `trailrunner/viz/__init__.py`, `trailrunner/viz/figures.py`
- Modify: `pyproject.toml`
- Test: `tests/test_viz.py` (create)

**Interfaces:**
- Consumes: `Report.nodes`, `.edges`, `.unresolved`, `.resolutions`;
  `Assessment.cumulative_by_node`, `.by_flow`; `DynamicAssessment.curve`.
- Produces:
  `sankey(report: Report, assessment: Assessment | None = None) -> go.Figure`;
  `curve(dynamic: DynamicAssessment) -> go.Figure`;
  `contributions(assessment: Assessment, top: int = 10, by: str = "flow", labels: Mapping[int, str] | None = None) -> go.Figure`;
  `save(figure, path: str | Path) -> None`.

Tests assert on figure **structure** — trace counts, labels, node ordering —
never on rendered pixels. A pixel test on a plotting library is a test of the
plotting library.

- [ ] **Step 1: Add the extra**

In `pyproject.toml`, under `[project.optional-dependencies]`:

```toml
viz = [
  "plotly>=5.20",
  # Static export for the showcase figures; the interactive figures work
  # without it.
  "kaleido>=0.2",
  "pandas>=2",
]
```

Run: `uv sync --extra dev --extra viz --extra dynamic`

- [ ] **Step 2: Write the failing tests**

Create `tests/test_viz.py`:

```python
import pytest

pytest.importorskip("plotly")

from trailrunner.assessment import Method, assess  # noqa: E402
from trailrunner.core.flow import Demand, Exchange, Flow  # noqa: E402
from trailrunner.core.result import Result  # noqa: E402
from trailrunner.orchestration.log import Log  # noqa: E402
from trailrunner.orchestration.report import Report  # noqa: E402
from trailrunner.viz import contributions, sankey, save  # noqa: E402

from .conftest import CO2_IRI  # noqa: E402

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"


def two_level_report() -> Report:
    log = Log()
    root_demand = Demand(flow=Flow(iri=CAPTURED, location="GLO"), amount=1000.0, unit="kg")
    heat_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=5000.0, unit="MJ")
    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            technosphere=[heat_demand],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=10.0, unit="kg")],
        ),
        model="DirectAirCapture",
        resolution={"tier": "model", "model": "DirectAirCapture"},
    )
    log.write(
        heat_demand,
        Result(production=[Exchange(flow=heat_demand.flow, amount=5000.0, unit="MJ")]),
        depth=1,
        parent=root,
        model="GasBoiler",
        resolution={"tier": "background", "kind": "linear_background", "dataset": "heat, gas"},
    )
    return Report.from_log(log)


def test_sankey_has_one_node_per_traversal_node():
    figure = sankey(two_level_report())
    labels = figure.data[0].node.label
    assert any("co2-captured" in label for label in labels)
    assert any("heat" in label for label in labels)


def test_sankey_links_parent_to_child():
    figure = sankey(two_level_report())
    assert list(figure.data[0].link.source) == [0]
    assert list(figure.data[0].link.target) == [1]


def test_sankey_marks_a_background_node_differently_from_a_modelled_one():
    figure = sankey(two_level_report())
    colours = list(figure.data[0].node.color)
    assert colours[0] != colours[1]


def test_sankey_widths_follow_the_assessment_when_given(method_parquet_file):
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    figure = sankey(report, assessment=assessment)
    assert list(figure.data[0].link.value) == [
        pytest.approx(assessment.cumulative_by_node[1])
    ]


def test_contributions_ranks_and_truncates(method_parquet_file):
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    figure = contributions(assessment, top=1)
    assert len(figure.data[0].x) == 1


def test_contributions_can_rank_by_node(method_parquet_file):
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    figure = contributions(assessment, by="node")
    assert figure.layout.xaxis.title.text


def test_node_bars_use_the_labels_the_caller_supplies(method_parquet_file):
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    labels = {node.id: node.model for node in report.nodes}
    figure = contributions(assessment, by="node", labels=labels)
    assert "DirectAirCapture" in list(figure.data[0].x)


def test_an_unknown_ranking_axis_is_rejected(method_parquet_file):
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    with pytest.raises(ValueError, match="continent"):
        contributions(assessment, by="continent")


def test_save_writes_a_file(tmp_path):
    pytest.importorskip("kaleido")
    path = tmp_path / "figure.svg"
    save(sankey(two_level_report()), path)
    assert path.exists() and path.stat().st_size > 0


def test_figures_set_no_opaque_background():
    """The docs render in light and dark; a white canvas is a bug in one of them."""
    figure = sankey(two_level_report())
    assert figure.layout.paper_bgcolor in (None, "rgba(0,0,0,0)")
```

Add a `tests/test_viz_curve.py` with one test for `curve`, gated on the
`[dynamic]` extra:

```python
import pytest

pytest.importorskip("plotly")
pytest.importorskip("dynamic_characterization")

from trailrunner.assessment import assess_dynamic  # noqa: E402
from trailrunner.core.flow import Demand, Exchange, Flow  # noqa: E402
from trailrunner.core.result import Result  # noqa: E402
from trailrunner.orchestration.log import Log  # noqa: E402
from trailrunner.orchestration.report import Report  # noqa: E402
from trailrunner.viz import curve  # noqa: E402

from .conftest import CO2_IRI  # noqa: E402

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"


def test_curve_draws_the_series_and_its_cumulative_integral():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1.0, unit="kg")
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[
                Exchange(flow=Flow(iri=CO2_IRI, location="CH", time=2030), amount=10.0, unit="kg")
            ],
        ),
        model="DirectAirCapture",
    )
    figure = curve(assess_dynamic(Report.from_log(log), horizon=20))
    assert len(figure.data) == 2
    # The marginal axis is W/m2; the cumulative one is its integral.
    assert figure.layout.yaxis.title.text.startswith("W/m2")
    assert figure.layout.yaxis2.title.text.startswith("W")
    assert figure.layout.yaxis2.title.text != figure.layout.yaxis.title.text


def test_the_bars_are_one_per_year_not_one_per_emission():
    """Two emissions in the same year make one bar, not two overlapping ones."""
    log = Log()
    for year in (2030, 2030):
        demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=year), amount=1.0, unit="kg")
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
                biosphere=[
                    Exchange(flow=Flow(iri=CO2_IRI, location="CH", time=year), amount=5.0, unit="kg")
                ],
            ),
            model="DirectAirCapture",
        )
    figure = curve(assess_dynamic(Report.from_log(log), horizon=10))
    dates = list(figure.data[0].x)
    assert len(dates) == len(set(dates))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_viz.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.viz'`.

- [ ] **Step 4: Implement**

Create `trailrunner/viz/figures.py`:

```python
"""Pictures of a result. No arithmetic lives here.

Every number these functions draw comes from a Report or an Assessment that
already computed it. If a figure needs something neither carries, that thing
belongs in the Report or the Assessment — a plot that computes its own numbers
is a second implementation nobody tests.
"""

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
    """Name, model, and the tier that answered — in the text, not only the colour.

    Colour must never be the sole carrier of meaning: a reader in a
    colour-blind palette, a greyscale print or a dark theme still has to see
    which nodes were borrowed or generalised.
    """
    iri = node.demand.flow.iri.rstrip("/").rsplit("/", 1)[-1]
    tier = node.resolution.get("tier", "model")
    return f"{iri} ({node.model or 'unknown'}) [{tier}]"


def _layout(figure, title: str, xaxis: str = "", yaxis: str = "") -> None:
    """Transparent canvas so the docs' light and dark themes both work."""
    figure.update_layout(
        title=title,
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    if xaxis:
        figure.update_xaxes(title_text=xaxis)
    if yaxis:
        figure.update_yaxes(title_text=yaxis)


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

    Two traces on one axis: the per-year response, and the running total that
    is the number a static LCA would have given at the end of the horizon.
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
    # Set each axis explicitly. `update_yaxes` with no selector touches EVERY
    # y-axis, so a shared helper would clobber yaxis2's title back to yaxis's.
    figure.update_layout(
        xaxis=dict(title="year"),
        yaxis=dict(title=dynamic.unit),
        yaxis2=dict(overlaying="y", side="right", title=dynamic.cumulative_unit),
    )
    _layout(
        figure,
        f"{dynamic.metric} over {dynamic.horizon} years",
        xaxis="year",
        yaxis=dynamic.unit,
    )
    return figure


def contributions(assessment, top: int = 10, by: str = "flow", labels=None):
    """The ranked contributors, by elementary flow or by node.

    ``labels`` maps node id to a name; the caller holds the Report and passes
    ``{node.id: node.model}``. The Assessment keys by id because it is a
    reading of the Report, not a second copy of the graph.
    """
    go = _plotly()
    if by == "flow":
        pairs = [
            (flow.iri.rstrip("/").rsplit("/", 1)[-1], value)
            for (flow, _unit), value in assessment.by_flow.items()
        ]
        axis = "elementary flow"
    elif by == "node":
        # An Assessment keys its node contributions by id, not by name: it is a
        # reading of the Report, not a copy of it. The caller holds the Report
        # and passes the labels, rather than the Assessment carrying a second
        # copy of the graph that could drift from the first.
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
```

Create `trailrunner/viz/__init__.py` exporting `contributions`, `curve`,
`sankey`, `save` and `TIER_COLOURS`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_viz.py tests/test_viz_curve.py -v`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Add the pandas exits**

Spec §4 asks for `report.to_dataframe()` and `assessment.to_dataframe()`.
pandas is not a core dependency, so both import it lazily and say which extra
provides it. The parquet log stays the dependency-free way out.

Write the failing tests, in `tests/test_dataframes.py`:

```python
import pytest

pytest.importorskip("pandas")

from trailrunner.assessment import Method, assess  # noqa: E402
from trailrunner.orchestration.report import Report  # noqa: E402

from .test_viz import two_level_report  # noqa: E402


def test_report_to_dataframe_has_one_row_per_node():
    frame = two_level_report().to_dataframe()
    assert len(frame) == 2
    assert {"node", "model", "tier", "demand_iri", "amount", "unit"} <= set(frame.columns)


def test_report_to_dataframe_names_the_tier_that_answered():
    frame = two_level_report().to_dataframe()
    assert set(frame["tier"]) == {"model", "background"}


def test_assessment_to_dataframe_has_one_row_per_characterized_flow(method_parquet_file):
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    frame = assessment.to_dataframe()
    assert {"flow_iri", "unit", "score"} <= set(frame.columns)
    assert len(frame) == len(assessment.by_flow)


def test_report_and_assessment_frames_join_on_flow_and_unit(method_parquet_file):
    """The inventory amount lives on the Report; the score on the Assessment.
    Keeping them apart is the one-way arrow; joining them is the caller's job,
    and it has to be possible."""
    report = two_level_report()
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    scores = assessment.to_dataframe()
    assert {"flow_iri", "unit"} <= set(scores.columns)
```

Run: `uv run pytest tests/test_dataframes.py -v` — expect FAIL with
`AttributeError: 'Report' object has no attribute 'to_dataframe'`.

Implement, on `Report`:

```python
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
```

and on `Assessment`:

```python
    def to_dataframe(self):
        """One row per characterized flow, score descending."""
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
```

with, in each module:

```python
def _require_pandas():
    try:
        import pandas
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "pandas is needed for to_dataframe(); install it with "
            "`uv sync --extra viz` or `--extra dynamic`. The parquet log needs nothing."
        ) from exc
    return pandas
```

The assessment frame carries the **score** per flow, not the inventory amount.
The amount belongs to the `Report`, and an `Assessment` is a reading of a
Report rather than a copy of one — widening `by_flow` to carry both would put
the same number in two places that can drift. A caller who wants both joins
the two frames on `(flow_iri, unit)`; say so in the docstring.

Run: `uv run pytest tests/test_dataframes.py -v` — expect PASS.

- [ ] **Step 7: Commit**

```bash
git add trailrunner/viz trailrunner/orchestration/report.py trailrunner/assessment/static.py pyproject.toml uv.lock tests/test_viz.py tests/test_viz_curve.py tests/test_dataframes.py
git commit -m "feat(viz): draw the traversal, the curve and the contributions

Three figures, no arithmetic: everything drawn comes from a Report or an
Assessment that already computed it. Sankey nodes are coloured by tier,
so a reader sees which parts of the chain were modelled and which were
borrowed before looking at any number. Transparent canvases, because the
docs render in both themes."
```

---

### Task 2: The `trailrunner run` CLI

**Files:**
- Create: `trailrunner/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py` (create)

**Interfaces:**
- Consumes: everything public from phases 0–3.
- Produces: `main(argv: list[str] | None = None) -> int`; console script
  `trailrunner = "trailrunner.cli:main"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import textwrap

import pytest

from trailrunner.cli import main

HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


@pytest.fixture
def models_file(tmp_path):
    """A module the CLI loads by path, exposing one model."""
    path = tmp_path / "mymodels.py"
    path.write_text(
        textwrap.dedent(
            f'''
            from trailrunner import Demand, Exchange, Flow, Model, Result

            HEAT = "{HEAT}"
            CO2 = "{CO2}"


            class Boiler(Model):
                produces = [HEAT]

                def apply(self, demand):
                    return Result(
                        production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                        biosphere=[Exchange(
                            flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                            amount=0.05 * demand.amount, unit="kg")],
                    )

            MODELS = [Boiler()]
            '''
        )
    )
    return path


def test_a_run_exits_zero_and_prints_the_summary(models_file, capsys):
    code = main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--location", "CH", "--year", "2030", "--models", str(models_file),
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "1 nodes" in out


def test_the_tree_is_printed(models_file, capsys):
    main(["run", HEAT, "--amount", "100", "--unit", "MJ", "--models", str(models_file)])
    assert "[model: Boiler]" in capsys.readouterr().out


def test_the_log_is_written_when_asked(models_file, tmp_path):
    out = tmp_path / "log.parquet"
    main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--models", str(models_file), "--out", str(out),
    ])
    assert out.exists()


def test_an_unresolved_demand_is_reported_not_fatal(models_file, capsys):
    code = main([
        "run", "https://vocab.sentier.dev/products/unobtainium",
        "--amount", "1", "--unit", "kg", "--models", str(models_file),
    ])
    assert code == 0
    assert "no_model_found" in capsys.readouterr().out


def test_a_missing_models_file_exits_nonzero_with_a_message(capsys):
    code = main(["run", HEAT, "--amount", "1", "--unit", "MJ", "--models", "/nope.py"])
    assert code == 2
    assert "nope.py" in capsys.readouterr().err


def test_the_allocation_flag_reaches_the_settings(models_file, capsys):
    main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--models", str(models_file), "--allocation", "economic",
    ])
    assert "allocation=economic" in capsys.readouterr().out


def test_an_unknown_allocation_is_rejected_before_anything_runs(models_file, capsys):
    code = main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--models", str(models_file), "--allocation", "vibes",
    ])
    assert code == 2
    assert "vibes" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trailrunner.cli'`.

- [ ] **Step 3: Implement**

Create `trailrunner/cli.py`:

```python
"""One command, so a run can be shown without a notebook.

Deliberately stdlib-only argparse: a CLI is a convenience, and a convenience
that adds a dependency to every install is not one.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from trailrunner.core.flow import Demand, Flow
from trailrunner.core.settings import AttributionSettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator


def load_models(path: Path) -> list:
    """Import a .py file by path and return its ``MODELS`` list."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"cannot import models from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    models = getattr(module, "MODELS", None)
    if models is None:
        raise AttributeError(f"{path} defines no MODELS list")
    return list(models)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trailrunner", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="traverse a demand and report")
    run.add_argument("iri", help="product IRI to demand")
    run.add_argument("--amount", type=float, required=True)
    run.add_argument("--unit", required=True)
    run.add_argument("--location", default=None)
    run.add_argument("--year", type=int, default=None)
    run.add_argument("--models", required=True, help="a .py file exposing MODELS")
    run.add_argument("--method", default=None, help="a method parquet; prints a score")
    run.add_argument("--dynamic", default=None, help="a dynamic metric, e.g. radiative_forcing")
    run.add_argument("--horizon", type=int, default=100)
    run.add_argument("--allocation", default="none")
    run.add_argument("--capital", default="per_output")
    run.add_argument("--max-depth", type=int, default=10)
    run.add_argument("--max-nodes", type=int, default=1000)
    run.add_argument("--out", default=None, help="write the parquet log here")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = Settings(
            attribution=AttributionSettings(allocation=args.allocation, capital=args.capital)
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        models = load_models(Path(args.models))
    except (FileNotFoundError, AttributeError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    demand = Demand(
        flow=Flow(iri=args.iri, location=args.location, time=args.year),
        amount=args.amount,
        unit=args.unit,
    )
    orchestrator = Orchestrator(
        Glossary(models),
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        settings=settings,
    )
    report = orchestrator.calculate(demand)

    print(report.summary())
    print()
    print(report.tree())

    if args.method:
        from trailrunner.assessment import Method, assess

        assessment = assess(report, Method.from_parquet(args.method))
        print()
        print(assessment.summary())

    if args.dynamic:
        from trailrunner.assessment import assess_dynamic

        dynamic = assess_dynamic(report, metric=args.dynamic, horizon=args.horizon)
        print()
        # cumulative_unit, not unit: total is the integral of the series, and
        # for radiative forcing those are different dimensions.
        print(
            f"{dynamic.metric} over {dynamic.horizon} years: "
            f"{dynamic.total:g} {dynamic.cumulative_unit}"
        )
        # The gaps travel with the number, the same way the static path's do.
        print(dynamic.summary())

    if args.out:
        report.log.to_parquet(args.out)
        print(f"\nwrote {args.out}")
    return 0
```

`report.log` does not exist yet: `to_parquet` belongs to the `Log`, and
`Orchestrator.calculate` currently drops the Log once the Report is built. Add
the reference before running the tests — in `trailrunner/orchestration/report.py`:

```python
    log: Any = None
    """The Log this Report was built from.

    Kept so a caller who only has the Report can still write the run out. The
    Report is a reading of the Log, not a replacement for it, and the parquet
    is the Log's job.
    """
```

and set it in `from_log` by passing `log=log` to the `cls(...)` call.

Add the console script to `pyproject.toml`:

```toml
[project.scripts]
trailrunner = "trailrunner.cli:main"
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS, all seven.

Add one test for the new field to `tests/test_report.py`:

```python
def test_the_report_keeps_its_log():
    log = Log()
    assert Report.from_log(log).log is log
```

- [ ] **Step 5: Try it by hand**

Run:
```bash
uv run trailrunner run https://vocab.sentier.dev/products/co2-captured \
    --amount 1000 --unit kg --location CH --year 2030 \
    --models examples/showcase_models.py
```
Create `examples/showcase_models.py` exposing `MODELS` — the DAC, electricity
and pipeline transport models wired to the example parquet files — since the
showcase notebook needs exactly the same list. Expected: a summary, a tree, and
a non-zero exit only if something raised.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trailrunner/cli.py trailrunner/orchestration/report.py examples/showcase_models.py pyproject.toml tests/test_cli.py
git commit -m "feat(cli): add trailrunner run

One command that traverses a demand, prints the summary and the tree,
optionally characterizes it and optionally writes the parquet log.
Stdlib argparse only: a convenience that adds a dependency to every
install is not one.

The Report now keeps a reference to its Log, so a caller can write the
run out without having built the Log itself."
```

---

### Task 3: The showcase

**Files:**
- Create: `examples/showcase.ipynb`, `dev/build_showcase_assets.py`, `docs/showcase.md`
- Create: `docs/assets/showcase/*.svg` (generated, committed)
- Modify: `zensical.toml`, `.github/workflows/*.yml`, `README.md`

**Interfaces:**
- Consumes: everything. This task adds no library code.
- Produces: a page that reads correctly to a stranger and cues a speaker
  through seven beats in five minutes.

- [ ] **Step 0: Give the models real vocabulary IRIs**

Beat 4 of the showcase claims the product dimension generalises a demand up
`skos:broader`. It cannot, as things stand: the IRIs the shipped models use are
**invented, not vocabulary concepts**. Verified against the live service —
`GET /api/v1/concepts/https%3A%2F%2Fvocab.sentier.dev%2Fproducts%2Felectricity`
returns **404**, as do `products/heat`, `products/natural-gas` and
`products/co2-captured`. The relationships endpoint still answers `200 []` for
them, which is why nothing noticed.

`dev/warm_pyst_cache.py` now prints this loudly and refuses to cache them, so
the examples ship **no** `pyst_cache.json` until this is fixed.

Real concepts do exist and do have parents — `fi_17100 → fi_1710 → fi_171` in
the BONSAI scheme, verified live and traversable by the multi-level walk. So:

1. Search the vocabulary (`/api/v1/concepts/search/?query=...`) for concepts
   matching the products the showcase models produce — heat, electricity,
   natural gas, and the captured-CO2 product if one exists.
2. Repoint the models at the IRIs the vocabulary actually has, updating the
   background pack's `product_iri` values and any test constant that names one.
3. Re-run `dev/warm_pyst_cache.py` with `PYST_AUTH_TOKEN` set and commit the
   cache it produces. It must be non-empty, and the script must print no
   `THE VOCABULARY HAS NO SUCH CONCEPT` block.
4. If a product genuinely has no vocabulary concept, **say so in the showcase**
   rather than implying the dimension applies to it. A beat that demonstrates a
   capability on a product it cannot actually apply to is the one thing this
   page must not do.

Until this step is done, beat 4 demonstrates nothing, and the offline-run
constraint in this plan's Global Constraints cannot be met.

- [ ] **Step 1: Write the notebook**

Create `examples/showcase.ipynb` with one section per beat, in this order,
using `examples/showcase_models.py`, the committed `examples/pyst_cache.json`
and `examples/background_pack.parquet` so it runs offline:

1. **A matrix row is a fixed coefficient.** Show a two-line "classic" inventory
   dict and state what it cannot express: a dependency on where and when.
2. **The process is the code.** Show `DirectAirCapture.apply` and run the same
   demand at two ambient conditions, printing the two different heat demands.
3. **The walk.** Run the root demand through the Orchestrator with tier 1 only;
   print `report.tree()` and `report.summary()`. The cutoffs are visible and
   that is the point.
4. **When nothing matches.** Add the generalising and background tiers; rerun;
   print the tree again beside `report.proxies`. Say out loud that the PyST
   lookups come from the committed cache.
5. **Value judgements are flags.** Run the same demand under
   `allocation="economic"` and `allocation="substitution"`; print both scores
   and `report.attribution`.
6. **Time.** `assess_dynamic(report, "radiative_forcing", horizon=100)`; plot
   `viz.curve`. Point at the construction pulse in the build years against the
   capture years after it.
7. **The record.** `report.summary()` and `log.to_parquet`; state that the run
   is reproducible from the committed parquet and cache alone.

Every cell must run top to bottom with `uv run --extra examples --extra viz
--extra dynamic jupyter nbconvert --execute`.

- [ ] **Step 2: Write the asset builder**

Create `dev/build_showcase_assets.py`: executes `examples/showcase.ipynb` with
`nbclient`, pulls the figures out of the executed notebook by cell tag
(`figure:sankey`, `figure:curve`, `figure:contributions`), and writes them to
`docs/assets/showcase/` as SVG via `trailrunner.viz.save`. Print each path it
wrote.

Run: `uv run --extra examples --extra viz --extra dynamic python dev/build_showcase_assets.py`
Expected: three SVGs in `docs/assets/showcase/`.

- [ ] **Step 3: Write the page**

Create `docs/showcase.md`: the seven beats, each as a section with its heading,
the code that produces it, the real output (pasted, not re-executed), the
committed figure where there is one, and a single bolded punchline sentence.
Target reading time five minutes; if a section needs more than about 120 words
of prose, it is doing too much.

Each section ends with a collapsed presenter note:

```markdown
??? note "Presenter note (45s)"
    Say: the coefficient cannot depend on where and when. Show the two heat
    numbers. Do not explain the sorbent chemistry.
```

The page's opening states the demand being traced — 1000 kg CO₂ captured,
Switzerland, 2030 — and its closing gives the two links a listener will want:
the notebook and the installation page.

- [ ] **Step 4: Put it in the nav and the README**

In `zensical.toml`, add `{ "5-minute tour" = "showcase.md" }` to the `Home`
nav section, directly after `{ Overview = "index.md" }`.

In `README.md`, add one line under the intro linking to the showcase page.

- [ ] **Step 5: Keep it honest in CI**

Add a job to the existing GitHub Actions workflow that executes the notebook:

```yaml
  showcase:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --extra dev --extra examples --extra viz --extra dynamic
      - name: Execute the showcase notebook
        # No PYST_AUTH_TOKEN here on purpose: the showcase must run from the
        # committed cache alone, which is exactly what it has to do on stage.
        run: uv run jupyter nbconvert --execute --to notebook --stdout examples/showcase.ipynb > /dev/null
```

- [ ] **Step 6: Rehearse against the clock**

Read the page aloud, timing each beat against the table in the spec. Cut
whatever overruns — the cut goes in the page, not in the delivery. Beats 1, 2
and 6 are the ones that survive if time is lost, so verify the page still makes
its argument when only those three are read.

- [ ] **Step 7: Build, verify and commit**

Run:
```bash
uv run pytest -q
uv sync --extra docs && uv run zensical build
```
Expected: both pass, no broken links.

```bash
git add examples/showcase.ipynb dev/build_showcase_assets.py docs zensical.toml README.md .github
git commit -m "docs: add the five-minute showcase

Seven beats on one demand -- 1000 kg CO2 captured, CH, 2030 -- from a
fixed coefficient to a time-resolved forcing curve. Figures are
pre-rendered and committed, PyST comes from the committed cache, and CI
executes the notebook with no token, so the page is exactly as
reproducible as it claims to be."
```

---

## Verification

Phase 4 is done when:

- [ ] `uv run pytest -q` passes with `--extra viz --extra dynamic`.
- [ ] `uv run trailrunner run <iri> --amount 1000 --unit kg --models examples/showcase_models.py`
      prints a summary and a tree and exits 0.
- [ ] `examples/showcase.ipynb` executes top to bottom with **no network
      access** and no `PYST_AUTH_TOKEN` set.
- [ ] `docs/showcase.md` renders with its three figures in both light and dark
      themes.
- [ ] Reading the page aloud takes five minutes or less.
- [ ] The repo contains no PyST token:
      `git grep -n "ns_" -- . ':!uv.lock'` returns nothing.
