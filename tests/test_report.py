from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report
from trailrunner.core.units import KG, MJ, TONNE
from trailrunner.core.time import in_year

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = Flow(iri="https://vocab.sentier.dev/flows/co2-fossil", location="CH", **in_year(2030))
CH4 = Flow(iri="https://vocab.sentier.dev/flows/ch4-fossil", location="CH", **in_year(2030))


def a_demand() -> Demand:
    return Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=1.0, unit=KG)


def test_inventory_sums_the_same_flow_and_unit_across_nodes():
    log = Log()
    demand = a_demand()
    for amount in (12.0, 8.0):
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
                biosphere=[Exchange(flow=CO2, amount=amount, unit=KG)],
            ),
        )
    report = Report.from_log(log)
    assert report.inventory == {(CO2, KG): 20.0}


def test_inventory_keeps_different_flows_and_units_apart():
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            biosphere=[
                Exchange(flow=CO2, amount=12.0, unit=KG),
                Exchange(flow=CH4, amount=0.3, unit=KG),
                Exchange(flow=CO2, amount=5.0, unit=TONNE),
            ],
        ),
    )
    report = Report.from_log(log)
    assert report.inventory == {(CO2, KG): 12.0, (CH4, KG): 0.3, (CO2, TONNE): 5.0}


def test_report_carries_unresolved_demands():
    log = Log()
    log.unresolved(
        Demand(flow=Flow(iri=HEAT), amount=5.0, unit=MJ), reason="no_model_found", depth=1
    )
    report = Report.from_log(log)
    assert len(report.unresolved) == 1
    assert report.unresolved[0].reason == "no_model_found"


def test_provenance_is_keyed_by_node_id():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={"location_used": "RER", "location_fallback": True},
        ),
    )
    report = Report.from_log(log)
    assert report.provenance[node_id]["location_used"] == "RER"


def test_graph_structure_is_carried_through():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)])
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


def test_report_carries_resolutions_by_node():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)])
    node_id = log.write(demand, result, model="DirectAirCapture", resolution={"tier": "model"})
    report = Report.from_log(log)
    assert report.resolutions[node_id] == {"tier": "model"}


def test_proxies_hold_only_the_nodes_that_were_not_exact_matches():
    log = Log()
    demand = a_demand()
    result = Result(production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)])
    exact = log.write(demand, result, model="DirectAirCapture", resolution={"tier": "model"})
    relaxed = log.write(
        demand,
        result,
        model="GridElectricity",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    borrowed = log.write(demand, result, resolution={"tier": "background"})

    report = Report.from_log(log)
    assert set(report.proxies) == {relaxed, borrowed}
    assert exact not in report.proxies


def test_nodes_without_a_resolution_are_not_proxies():
    log = Log()
    demand = a_demand()
    log.write(demand, Result(production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)]))
    assert Report.from_log(log).proxies == {}


def test_report_collects_per_node_attribution():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={"attribution": {"allocation": "economic", "share": 0.25}},
        ),
    )
    report = Report.from_log(log)
    assert report.attribution[node_id]["share"] == 0.25


def test_summary_states_the_runs_normative_choices():
    from trailrunner.core.settings import AttributionSettings

    report = Report.from_log(Log(), attribution_settings=AttributionSettings(allocation="economic"))
    assert "allocation=economic" in report.summary()


def test_the_attribution_record_is_not_reported_as_the_models_provenance():
    """``report.provenance`` is what the *model* recorded.

    The model never chose the run's allocation rule and cannot see it, so the
    rule belongs in ``report.attribution``, beside ``resolutions`` and on the
    same split -- not mixed into the parameter rows the model actually read.
    """
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={
                "location_used": "RER",
                "attribution": {"allocation": "economic", "share": 0.25},
            },
        ),
    )
    report = Report.from_log(log)
    assert report.provenance[node_id] == {"location_used": "RER"}
    assert report.attribution[node_id] == {"allocation": "economic", "share": 0.25}


def test_a_node_whose_only_record_is_its_attribution_has_no_provenance():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={"attribution": {"allocation": "none", "share": 1.0}},
        ),
    )
    report = Report.from_log(log)
    assert node_id not in report.provenance
    assert node_id in report.attribution


def test_the_report_keeps_its_log():
    log = Log()
    assert Report.from_log(log).log is log
