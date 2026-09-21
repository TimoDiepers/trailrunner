from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

ROOT = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")


class Capturer(Model):
    """Needs 5 MJ of heat per kg captured; leaks 0.01 kg CO2 per kg."""

    produces = [CAPTURED]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[
                Demand(
                    flow=Flow(iri=HEAT, location=demand.flow.location, time=demand.flow.time),
                    amount=5.0 * demand.amount,
                    unit="MJ",
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                    amount=0.01 * demand.amount,
                    unit="kg",
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
                    flow=Flow(iri=GAS, location=demand.flow.location, time=demand.flow.time),
                    amount=0.02 * demand.amount,
                    unit="kg",
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                    amount=0.06 * demand.amount,
                    unit="kg",
                )
            ],
        )


def test_single_node_traversal_records_one_node_and_one_cutoff():
    report = Orchestrator(Glossary([Capturer()])).calculate(ROOT)
    assert len(report.nodes) == 1
    assert report.inventory == {(Flow(iri=CO2, location="CH", time=2030), "kg"): 10.0}
    assert [r.reason for r in report.unresolved] == ["no_model_found"]
    assert report.unresolved[0].demand.flow.iri == HEAT


def test_two_level_traversal_accumulates_both_nodes():
    report = Orchestrator(Glossary([Capturer(), Boiler()])).calculate(ROOT)
    assert len(report.nodes) == 2
    # capture leak 10 kg + boiler 5000 MJ * 0.06 = 300 kg
    assert report.inventory[(Flow(iri=CO2, location="CH", time=2030), "kg")] == 310.0


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


def test_priority_callable_is_passed_through_to_the_queue():
    seen: list[str] = []

    def priority(demand: Demand) -> float:
        seen.append(demand.flow.iri)
        return -demand.amount

    Orchestrator(Glossary([Capturer(), Boiler()]), priority=priority).calculate(ROOT)
    assert HEAT in seen
