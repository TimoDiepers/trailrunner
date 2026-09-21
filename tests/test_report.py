from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = Flow(iri="https://vocab.sentier.dev/flows/co2-fossil", location="CH", time=2030)
CH4 = Flow(iri="https://vocab.sentier.dev/flows/ch4-fossil", location="CH", time=2030)


def a_demand() -> Demand:
    return Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1.0, unit="kg")


def test_inventory_sums_the_same_flow_and_unit_across_nodes():
    log = Log()
    demand = a_demand()
    for amount in (12.0, 8.0):
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
                biosphere=[Exchange(flow=CO2, amount=amount, unit="kg")],
            ),
        )
    report = Report.from_log(log)
    assert report.inventory == {(CO2, "kg"): 20.0}


def test_inventory_keeps_different_flows_and_units_apart():
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[
                Exchange(flow=CO2, amount=12.0, unit="kg"),
                Exchange(flow=CH4, amount=0.3, unit="kg"),
                Exchange(flow=CO2, amount=5.0, unit="tonne"),
            ],
        ),
    )
    report = Report.from_log(log)
    assert report.inventory == {(CO2, "kg"): 12.0, (CH4, "kg"): 0.3, (CO2, "tonne"): 5.0}


def test_report_carries_unresolved_demands():
    log = Log()
    log.unresolved(
        Demand(flow=Flow(iri=HEAT), amount=5.0, unit="MJ"), reason="no_producer", depth=1
    )
    report = Report.from_log(log)
    assert len(report.unresolved) == 1
    assert report.unresolved[0].reason == "no_producer"


def test_provenance_is_keyed_by_node_id():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            provenance={"location_used": "RER", "location_fallback": True},
        ),
    )
    report = Report.from_log(log)
    assert report.provenance[node_id]["location_used"] == "RER"


def test_graph_structure_is_carried_through():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")])
    root = log.write(demand, result)
    child = log.write(demand, result, depth=1, parent=root)
    report = Report.from_log(log)
    assert [node.id for node in report.nodes] == [root, child]
    assert report.edges == [(root, child)]


def test_truncated_flag_defaults_to_false_and_is_settable():
    assert Report.from_log(Log()).truncated is False
    assert Report.from_log(Log(), truncated=True).truncated is True


def test_empty_log_gives_an_empty_report():
    report = Report.from_log(Log())
    assert report.inventory == {}
    assert report.unresolved == []
    assert report.nodes == []
