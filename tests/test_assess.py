from trailrunner.assessment import Method, assess
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

from .conftest import CH4_IRI, CO2_IRI

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
SOX = "https://vocab.sentier.dev/flows/sox"


def two_level_report() -> Report:
    """Root emits 10 kg CO2; its child emits 2 kg CH4 and 1 kg of an
    uncharacterized flow."""
    log = Log()
    root_demand = Demand(flow=Flow(iri=CAPTURED, location="GLO"), amount=1000.0, unit="kg")
    child_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=5000.0, unit="MJ")
    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=10.0, unit="kg")],
        ),
        model="DirectAirCapture",
    )
    log.write(
        child_demand,
        Result(
            production=[Exchange(flow=child_demand.flow, amount=5000.0, unit="MJ")],
            biosphere=[
                Exchange(flow=Flow(iri=CH4_IRI, location="GLO"), amount=2.0, unit="kg"),
                Exchange(flow=Flow(iri=SOX, location="GLO"), amount=1.0, unit="kg"),
            ],
        ),
        depth=1,
        parent=root,
        model="GasBoiler",
    )
    return Report.from_log(log)


def test_score_is_the_sum_of_inventory_times_factors(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.score == 10.0 * 1.0 + 2.0 * 29.8


def test_score_carries_the_methods_unit(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.unit == "kg CO2eq"


def test_contributions_are_reported_per_flow(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.by_flow[(Flow(iri=CO2_IRI, location="GLO"), "kg")] == 10.0


def test_a_flow_with_no_factor_is_reported_not_zeroed(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert [(flow.iri, unit, amount) for flow, unit, amount in assessment.uncharacterized] == [
        (SOX, "kg", 1.0)
    ]


def test_direct_contributions_are_per_node(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.direct_by_node[0] == 10.0
    assert assessment.direct_by_node[1] == 2.0 * 29.8


def test_cumulative_contribution_of_the_root_is_the_whole_score(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert assessment.cumulative_by_node[0] == assessment.score
    assert assessment.cumulative_by_node[1] == 2.0 * 29.8


def test_provenance_records_the_factor_lookups(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    key = (Flow(iri=CO2_IRI, location="GLO"), "kg")
    assert assessment.provenance[key]["method"]


def test_an_empty_report_assesses_to_zero(method_parquet_file):
    assessment = assess(Report.from_log(Log()), Method.from_parquet(method_parquet_file))
    assert assessment.score == 0.0
    assert assessment.uncharacterized == []
