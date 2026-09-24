from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.coverage import Coverage
from trailrunner.core.units import KG, MJ
from trailrunner.core.time import in_year, when, year_range

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

ROOT = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=1000.0, unit=KG)


class Capturer(Model):
    """Needs 5 MJ of heat per kg captured; leaks 0.01 kg CO2 per kg."""

    produces = [CAPTURED]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(
                    flow=Flow(iri=HEAT, location=demand.flow.location, **when(demand.flow)),
                    amount=5.0 * demand.amount,
                    unit=MJ,
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, **when(demand.flow)),
                    amount=0.01 * demand.amount,
                    unit=KG,
                )
            ],
        )


class Boiler(Model):
    """Burns gas for heat; emits 0.06 kg CO2 per MJ."""

    produces = [HEAT]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(
                    flow=Flow(iri=GAS, location=demand.flow.location, **when(demand.flow)),
                    amount=0.02 * demand.amount,
                    unit=KG,
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, **when(demand.flow)),
                    amount=0.06 * demand.amount,
                    unit=KG,
                )
            ],
        )


def test_single_node_traversal_records_one_node_and_one_cutoff():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert len(report.nodes) == 1
    assert report.inventory == {(Flow(iri=CO2, location="CH", **in_year(2030)), KG): 10.0}
    assert [r.reason for r in report.unresolved] == ["no_model_found"]
    assert report.unresolved[0].demand.flow.iri == HEAT


def test_two_level_traversal_accumulates_both_nodes():
    report = Orchestrator(Glossary([Capturer(), Boiler()])).calculate(ROOT)
    assert len(report.nodes) == 2
    # capture leak 10 kg + boiler 5000 MJ * 0.06 = 300 kg
    assert report.inventory[(Flow(iri=CO2, location="CH", **in_year(2030)), KG)] == 310.0


def test_cutoff_leaf_names_the_parent_node():
    report = Orchestrator(Glossary([Capturer(), Boiler()])).calculate(ROOT)
    gas = [r for r in report.unresolved if r.demand.flow.iri == GAS][0]
    assert gas.parent == 1
    assert gas.depth == 2


def test_max_depth_truncates_and_is_reported():
    report = Orchestrator(Glossary([Capturer(), Boiler()]), max_depth=1).calculate(ROOT)
    assert len(report.nodes) == 1
    assert [r.reason for r in report.unresolved] == ["max_depth"]
    assert report.truncated is True


def test_untruncated_traversal_is_not_flagged():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert report.truncated is False


def test_max_nodes_stops_the_traversal():
    class SelfFeeder(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                technosphere=[Demand(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            )

    report = Orchestrator(Glossary([SelfFeeder()]), max_depth=100, max_nodes=5).calculate(ROOT)
    assert len(report.nodes) == 5
    assert report.truncated is True


def test_a_loop_is_warned_about():
    class SelfFeeder(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                technosphere=[Demand(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            )

    report = Orchestrator(Glossary([SelfFeeder()]), max_depth=3).calculate(ROOT)
    assert any(CAPTURED in message for message, _ in report.warnings)


class DatedCapturer(Model):
    """Only valid 2020-2050, so a flow with no year at all falls outside it."""

    produces = [CAPTURED]
    coverage = Coverage(time_range=year_range(2020, 2050))

    def apply(self, demand: Demand) -> Result:
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def test_a_flow_its_only_model_excludes_is_not_reported_as_unmodelled():
    """The registered-but-filtered-out case must not read as "nobody makes this"."""
    undated = Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=1000.0, unit=KG)
    report = Orchestrator(Glossary([DatedCapturer()])).calculate(undated)
    assert [r.reason for r in report.unresolved] == ["coverage_excluded"]


def test_a_coverage_excluded_leaf_names_the_model_that_nearly_matched():
    undated = Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=1000.0, unit=KG)
    report = Orchestrator(Glossary([DatedCapturer()])).calculate(undated)
    assert "DatedCapturer" in report.unresolved[0].detail


def test_a_genuinely_unmodelled_flow_is_still_no_model_found():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert [r.reason for r in report.unresolved] == ["no_model_found"]
    assert report.unresolved[0].detail is None


def test_priority_callable_is_passed_through_to_the_queue():
    seen: list[str] = []

    def priority(demand: Demand) -> float:
        seen.append(demand.flow.iri)
        return -demand.amount

    Orchestrator(Glossary([Capturer(), Boiler()]), priority=priority).calculate(ROOT)
    assert HEAT in seen


def test_orchestrator_accepts_a_resolution_chain():
    from trailrunner.resolution import ModelProvider, ResolutionChain

    chain = ResolutionChain([ModelProvider(Glossary([Capturer()]))])
    report = Orchestrator(chain).calculate(ROOT)
    assert len(report.nodes) == 1


def test_node_resolution_records_the_tier_that_answered():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert report.resolutions[0]["tier"] == "model"
    assert report.proxies == {}
