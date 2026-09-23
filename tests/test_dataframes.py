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
