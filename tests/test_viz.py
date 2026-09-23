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
