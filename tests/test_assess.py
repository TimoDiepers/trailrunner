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


def branching_report() -> Report:
    """Root emits 10 kg CO2 and has *two* children, each characterized on its
    own: one emits 2 kg CH4, the other 5 kg CO2. Every other fixture in this
    file is a linear chain (root -> one child), which cannot catch a
    cumulative walk that overwrites a running total instead of accumulating
    into it -- with one child, `total = cumulative(child)` and
    `total += cumulative(child)` give the same answer. This is the one
    fixture where they diverge."""
    log = Log()
    root_demand = Demand(flow=Flow(iri=CAPTURED, location="GLO"), amount=1000.0, unit="kg")
    child_a_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=5000.0, unit="MJ")
    child_b_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=2000.0, unit="MJ")
    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=10.0, unit="kg")],
        ),
        model="DirectAirCapture",
    )
    log.write(
        child_a_demand,
        Result(
            production=[Exchange(flow=child_a_demand.flow, amount=5000.0, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CH4_IRI, location="GLO"), amount=2.0, unit="kg")],
        ),
        depth=1,
        parent=root,
        model="GasBoiler",
    )
    log.write(
        child_b_demand,
        Result(
            production=[Exchange(flow=child_b_demand.flow, amount=2000.0, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=5.0, unit="kg")],
        ),
        depth=1,
        parent=root,
        model="ElectricHeater",
    )
    return Report.from_log(log)


def test_a_roots_cumulative_contribution_accumulates_across_every_child(method_parquet_file):
    """Guards against a cumulative walk that overwrites the running total with
    the last child's contribution instead of summing across siblings -- a bug
    every other fixture here, being a single-child chain, is structurally
    unable to catch."""
    assessment = assess(branching_report(), Method.from_parquet(method_parquet_file))
    direct_root = 10.0 * 1.0
    child_a = 2.0 * 29.8
    child_b = 5.0 * 1.0
    assert assessment.cumulative_by_node[0] == direct_root + child_a + child_b
    assert assessment.cumulative_by_node[1] == child_a
    assert assessment.cumulative_by_node[2] == child_b


def node_with_only_an_uncharacterized_emission() -> Report:
    """Root emits 10 kg CO2; its child emits only 1 kg of a flow the method
    has no factor for; its other child emits nothing at all."""
    log = Log()
    root_demand = Demand(flow=Flow(iri=CAPTURED, location="GLO"), amount=1000.0, unit="kg")
    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=10.0, unit="kg")],
        ),
        model="DirectAirCapture",
    )
    sox_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=5000.0, unit="MJ")
    log.write(
        sox_demand,
        Result(
            production=[Exchange(flow=sox_demand.flow, amount=5000.0, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=SOX, location="GLO"), amount=1.0, unit="kg")],
        ),
        depth=1,
        parent=root,
        model="SmellyBoiler",
    )
    clean_demand = Demand(flow=Flow(iri=HEAT, location="GLO"), amount=2000.0, unit="MJ")
    log.write(
        clean_demand,
        Result(production=[Exchange(flow=clean_demand.flow, amount=2000.0, unit="MJ")]),
        depth=1,
        parent=root,
        model="CleanBoiler",
    )
    return Report.from_log(log)


def test_an_uncharacterized_node_is_distinguishable_from_a_silent_one(method_parquet_file):
    """Both score 0.0 in ``direct_by_node``. Without a per-node record of what
    was left out, "the method had nothing to say about this node's only
    emission" and "this node emitted nothing" are the same number."""
    assessment = assess(
        node_with_only_an_uncharacterized_emission(), Method.from_parquet(method_parquet_file)
    )
    assert assessment.direct_by_node[1] == 0.0
    assert assessment.direct_by_node[2] == 0.0
    assert assessment.uncharacterized_by_node[1] == [
        (Flow(iri=SOX, location="GLO"), "kg", 1.0)
    ]
    assert 2 not in assessment.uncharacterized_by_node


def test_a_characterized_node_has_no_uncharacterized_entry(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert 0 not in assessment.uncharacterized_by_node
    assert assessment.uncharacterized_by_node[1] == [
        (Flow(iri=SOX, location="GLO"), "kg", 1.0)
    ]


def test_the_inventorys_own_gaps_reach_the_assessment(method_parquet_file):
    """A consumer handed only an ``Assessment`` must be able to tell a complete
    traversal's score from one that hit ``max_nodes`` halfway down."""
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="GLO"), amount=1000.0, unit="kg")
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="GLO"), amount=10.0, unit="kg")],
        ),
        model="DirectAirCapture",
    )
    log.unresolved(
        Demand(flow=Flow(iri=HEAT, location="GLO"), amount=5.0, unit="MJ"),
        reason="max_depth",
        parent=0,
    )
    report = Report.from_log(log, truncated=True)
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    assert assessment.truncated is True
    assert assessment.unresolved == len(report.unresolved) == 1
    assert assessment.proxies == len(report.proxies)


def test_the_summary_carries_the_score_the_method_and_the_caveats(method_parquet_file):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    summary = assessment.summary()
    assert "kg CO2eq" in summary
    assert assessment.method in summary
    assert "1 uncharacterized flow" in summary
    assert "0 unresolved" in summary
    assert "truncated" not in summary


def test_the_summary_says_so_when_the_traversal_was_truncated(method_parquet_file):
    report = two_level_report()
    report.truncated = True
    assessment = assess(report, Method.from_parquet(method_parquet_file))
    assert "truncated" in assessment.summary()


def test_the_summary_is_returned_not_printed(method_parquet_file, capsys):
    assessment = assess(two_level_report(), Method.from_parquet(method_parquet_file))
    assert isinstance(assessment.summary(), str)
    assert capsys.readouterr().out == ""
