import pytest

from trailrunner.core.errors import MissingProperty, UnsupportedAttribution
from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import AttributionSettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.runner import Runner

HEAT = "https://vocab.sentier.dev/products/heat"
POWER = "https://vocab.sentier.dev/products/electricity"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

HEAT_DEMAND = Demand(flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ")


class CHP(Model):
    """Makes 100 MJ of heat and 50 MJ of electricity from 200 MJ of gas."""

    produces = [HEAT, POWER]
    supports = frozenset({"none", "mass", "economic", "energy", "substitution"})

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[
                Exchange(
                    flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ",
                    properties=(Property("energy", 100.0, "MJ"), Property("price", 3.0, "EUR"),
                                Property("mass", 0.0, "kg")),
                ),
                Exchange(
                    flow=Flow(iri=POWER, location="CH"), amount=50.0, unit="MJ",
                    properties=(Property("energy", 50.0, "MJ"), Property("price", 9.0, "EUR"),
                                Property("mass", 0.0, "kg")),
                ),
            ],
            technosphere=[Demand(flow=Flow(iri=GAS, location="CH"), amount=200.0, unit="MJ")],
            biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0, unit="kg")],
        )


class Unwilling(CHP):
    supports = frozenset({"none"})


def runner_for(model, allocation="none"):
    return Runner(
        Glossary([model]),
        settings=Settings(attribution=AttributionSettings(allocation=allocation)),
    )


def test_none_rejects_co_production():
    with pytest.raises(ValueError, match="co-product"):
        runner_for(CHP(), "none").apply(HEAT_DEMAND)


def test_energy_allocation_splits_by_energy_content():
    result = runner_for(CHP(), "energy").apply(HEAT_DEMAND)
    # heat is 100 of 150 MJ: two thirds
    assert result.technosphere[0].amount == pytest.approx(200.0 * 2 / 3)
    assert result.biosphere[0].amount == pytest.approx(12.0 * 2 / 3)


def test_economic_allocation_splits_by_price():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    # heat is 3 of 12 EUR: one quarter
    assert result.technosphere[0].amount == pytest.approx(50.0)
    assert result.biosphere[0].amount == pytest.approx(3.0)


def test_allocation_scales_technosphere_and_biosphere_alike():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    assert result.technosphere[0].amount / 200.0 == pytest.approx(
        result.biosphere[0].amount / 12.0
    )


def test_the_allocated_result_keeps_only_the_demanded_product():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    assert [exchange.flow.iri for exchange in result.production] == [HEAT]
    assert result.production[0].amount == 100.0


def test_the_rule_and_the_share_are_recorded():
    result = runner_for(CHP(), "economic").apply(HEAT_DEMAND)
    attribution = result.provenance["attribution"]
    assert attribution["allocation"] == "economic"
    assert attribution["share"] == pytest.approx(0.25)
    assert attribution["property"] == "price"


def test_a_missing_property_names_the_model_and_the_co_product():
    class NoPrices(CHP):
        def apply(self, demand):
            result = super().apply(demand)
            result.production = [
                Exchange(flow=exchange.flow, amount=exchange.amount, unit=exchange.unit)
                for exchange in result.production
            ]
            return result

    with pytest.raises(MissingProperty, match="NoPrices"):
        runner_for(NoPrices(), "economic").apply(HEAT_DEMAND)


def test_a_model_that_does_not_support_the_rule_says_so():
    with pytest.raises(UnsupportedAttribution, match="Unwilling"):
        runner_for(Unwilling(), "economic").apply(HEAT_DEMAND)


def test_a_single_product_model_is_untouched_by_a_rule_it_ignores():
    class Boiler(Model):
        produces = [HEAT]
        supports = frozenset({"none", "economic"})

        def apply(self, demand):
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=5.0, unit="kg")],
            )

    result = runner_for(Boiler(), "economic").apply(HEAT_DEMAND)
    assert result.biosphere[0].amount == 5.0
    assert result.provenance["attribution"]["share"] == 1.0


def test_the_default_runner_still_takes_no_settings():
    """Every v1 caller constructs Runner(glossary) and must keep working."""
    class Boiler(Model):
        produces = [HEAT]

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    assert Runner(Glossary([Boiler()])).apply(HEAT_DEMAND).production[0].amount == 100.0


def test_a_zero_total_property_is_an_error_not_a_division():
    class Massless(CHP):
        supports = frozenset({"none", "mass"})

    with pytest.raises(MissingProperty, match="mass"):
        runner_for(Massless(), "mass").apply(HEAT_DEMAND)
