import pytest

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import AttributionSettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.orchestration.runner import Runner

HEAT = "https://vocab.sentier.dev/products/heat"
POWER = "https://vocab.sentier.dev/products/electricity"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

HEAT_DEMAND = Demand(flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ")


class CHP(Model):
    # `produces` only tells the Glossary which *direct* demands this model
    # may be resolved for; POWER is a co-product returned by `apply` below,
    # not something CHP should be asked to make on its own. Declaring it here
    # too would make CHP and Grid both candidates for the POWER credit demand,
    # which `Glossary.resolve` correctly treats as an unresolvable ambiguity
    # (two producers of the same flow is a data error, never silent
    # precedence) rather than something substitution should paper over.
    produces = [HEAT]
    supports = frozenset({"none", "economic", "substitution"})

    def apply(self, demand: Demand) -> Result:
        scale = abs(demand.amount) / 100.0
        return Result(
            production=[
                Exchange(flow=Flow(iri=HEAT, location="CH"), amount=100.0 * scale, unit="MJ",
                         properties=(Property("price", 3.0, "EUR"),)),
                Exchange(flow=Flow(iri=POWER, location="CH"), amount=50.0 * scale, unit="MJ",
                         properties=(Property("price", 9.0, "EUR"),)),
            ],
            biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0 * scale, unit="kg")],
        )


class Grid(Model):
    """The displaced electricity. Answers negative demands as readily as positive."""

    produces = [POWER]
    supports = frozenset({"none", "substitution"})

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            biosphere=[
                Exchange(flow=Flow(iri=CO2, location="CH"), amount=0.1 * demand.amount, unit="kg")
            ],
        )


def substituting_runner(models):
    return Runner(
        Glossary(models),
        settings=Settings(attribution=AttributionSettings(allocation="substitution")),
    )


def test_the_co_product_becomes_a_negative_demand():
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    credits = [d for d in result.technosphere if d.amount < 0]
    assert len(credits) == 1
    assert credits[0].flow.iri == POWER
    assert credits[0].amount == -50.0


def test_the_burden_is_not_scaled_down():
    """Substitution credits the avoided product; it does not partition."""
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    assert result.biosphere[0].amount == 12.0


def test_only_the_demanded_product_remains_in_production():
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    assert [e.flow.iri for e in result.production] == [HEAT]


def test_the_rule_is_recorded_with_what_was_credited():
    result = substituting_runner([CHP()]).apply(HEAT_DEMAND)
    attribution = result.provenance["attribution"]
    assert attribution["allocation"] == "substitution"
    assert attribution["substituted"] == [POWER]


def test_a_negative_demand_passes_validation():
    """Production must cover the demand in magnitude, with the same sign."""
    credit = Demand(flow=Flow(iri=POWER, location="CH"), amount=-50.0, unit="MJ")
    result = substituting_runner([Grid()]).apply(credit)
    assert result.production[0].amount == -50.0


class HalfHeartedGrid(Model):
    """Delivers only half of whatever credit it is asked for."""

    produces = [POWER]
    supports = frozenset({"none", "substitution"})

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount / 2, unit=demand.unit)]
        )


def test_under_delivered_credit_is_rejected():
    """The magnitude comparison must be sign-aware, not sign-blind.

    A credit demand of -100 answered with -50 production under-delivers by
    half. A naive fix that simply drops the old positivity check but leaves
    ``total < demand.amount`` as a sign-blind comparison would wave this
    through: -50 < -100 is False, so the under-covering credit would look
    like it "exceeds" the demand. Comparing magnitudes (via the sign
    multiplier) is what catches it.
    """
    credit = Demand(flow=Flow(iri=POWER, location="CH"), amount=-100.0, unit="MJ")
    with pytest.raises(ValidationError):
        substituting_runner([HalfHeartedGrid()]).apply(credit)


def test_the_credit_traverses_and_subtracts_from_the_inventory():
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    report = Orchestrator(Glossary([CHP(), Grid()]), settings=settings).calculate(HEAT_DEMAND)
    total = sum(report.inventory.values())
    # 12 kg from the CHP, minus 5 kg credited for 50 MJ of displaced grid power
    assert total == pytest.approx(12.0 - 5.0)


def test_the_credit_node_appears_in_the_graph():
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    report = Orchestrator(Glossary([CHP(), Grid()]), settings=settings).calculate(HEAT_DEMAND)
    assert any(node.demand.amount < 0 for node in report.nodes)


def test_substitution_under_a_different_rule_does_not_create_credits():
    settings = Settings(attribution=AttributionSettings(allocation="economic"))
    report = Orchestrator(Glossary([CHP(), Grid()]), settings=settings).calculate(HEAT_DEMAND)
    assert all(node.demand.amount > 0 for node in report.nodes)
