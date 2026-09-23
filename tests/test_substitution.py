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
    # Both products are declared, because the plant really does make both and
    # a glossary that hid one would be lying about the technology. It is the
    # *credit* that must not come back here: the Orchestrator marks a
    # substitution credit with the model that minted it, and resolution drops
    # that instance, so CHP is not a candidate for its own avoided burden
    # while Grid still is. Narrowing `produces` to hide the co-product was the
    # old way of getting these tests to pass, and it hid the bug: with both
    # declared and no exclusion, a sole producer answers its own credit until
    # `max_depth` and the inventory cancels to exactly zero.
    produces = [HEAT, POWER]
    supports = frozenset({"none", "economic", "substitution"})

    def apply(self, demand: Demand) -> Result:
        # Scaled against whichever product was asked for, so the plant can
        # honestly answer a demand for its power as well as one for its heat.
        reference = 100.0 if demand.flow.iri == HEAT else 50.0
        scale = abs(demand.amount) / reference
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


def test_a_credit_is_not_answered_by_the_model_that_minted_it():
    """The regression test for the self-substitution loop.

    With ``produces = [HEAT, POWER]`` and no exclusion, both CHP and Grid are
    candidates for the -50 MJ credit and ``Glossary.resolve`` raises
    ``AmbiguousModelMatch``; with CHP excluded, exactly one candidate is left
    and it is the displaced grid, which is what a credit means.
    """
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    chp, grid = CHP(), Grid()
    report = Orchestrator(Glossary([chp, grid]), settings=settings).calculate(HEAT_DEMAND)
    credits = [node for node in report.nodes if node.demand.amount < 0]
    assert [node.model for node in credits] == ["Grid"]
    assert sum(report.inventory.values()) == pytest.approx(7.0)


def test_a_sole_producer_does_not_credit_its_own_burden_away():
    """CHP is the only model that makes POWER, so its credit has no answer.

    Before the exclusion, the credit resolved straight back to CHP, which
    answered it by producing -100 MJ of heat and crediting +50 MJ of power,
    and so on until ``max_depth``: ten nodes, eight loop warnings, and an
    inventory summing to exactly 0.0 -- the process credited away its entire
    burden. The honest answer is one node and a visible cutoff.
    """
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    report = Orchestrator(Glossary([CHP()]), settings=settings).calculate(HEAT_DEMAND)

    assert len(report.nodes) == 1
    assert not report.truncated
    assert report.warnings == []
    assert sum(report.inventory.values()) == pytest.approx(12.0)

    [cutoff] = report.unresolved
    assert cutoff.demand.flow.iri == POWER
    assert cutoff.demand.amount == -50.0
    assert cutoff.reason == "no_model_found"


def test_a_forgone_credit_is_counted_as_one_in_the_summary():
    """A forgone credit overstates the impact; a forgone burden understates it.

    One bucket for both tells the reader neither, so the summary splits them.
    """
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    report = Orchestrator(Glossary([CHP()]), settings=settings).calculate(HEAT_DEMAND)
    assert "1 unresolved (no_model_found: 1, of which 1 on a credit branch)" in report.summary()


class TwinPlant(Model):
    """One class, two sites. What each instance makes is instance state.

    The CH plant cogenerates; the FR plant next door is a power station. They
    are the same class, so excluding by class rather than by identity would
    take both out and turn the CH plant's credit into a cutoff.
    """

    supports = frozenset({"none", "substitution"})

    def __init__(self, produces, co2_per_mj):
        super().__init__()
        self.produces = list(produces)
        self.co2_per_mj = co2_per_mj

    def apply(self, demand: Demand) -> Result:
        if demand.flow.iri == HEAT:
            scale = demand.amount / 100.0
            return Result(
                production=[
                    Exchange(flow=Flow(iri=HEAT, location="CH"), amount=100.0 * scale, unit="MJ"),
                    Exchange(flow=Flow(iri=POWER, location="CH"), amount=50.0 * scale, unit="MJ"),
                ],
                biosphere=[
                    Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0 * scale, unit="kg")
                ],
            )
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2, location="CH"),
                    amount=self.co2_per_mj * demand.amount,
                    unit="kg",
                )
            ],
        )


def test_two_instances_of_one_class_answer_each_others_credits():
    """Exclusion is by instance identity, not by class."""
    settings = Settings(attribution=AttributionSettings(allocation="substitution"))
    cogen = TwinPlant([HEAT, POWER], co2_per_mj=0.1)
    neighbour = TwinPlant([POWER], co2_per_mj=0.2)
    report = Orchestrator(Glossary([cogen, neighbour]), settings=settings).calculate(HEAT_DEMAND)

    assert report.unresolved == []
    # The neighbour answered, at its own 0.2 kg/MJ, not the cogen's 0.1:
    # 12 kg from the plant, minus 0.2 * 50 credited.
    assert sum(report.inventory.values()) == pytest.approx(12.0 - 10.0)
