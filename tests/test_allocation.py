import pytest

from trailrunner.core.errors import (
    MissingProperty,
    TrailrunnerError,
    UnallocatedCoProduction,
    UnsupportedAttribution,
)
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


def test_a_product_split_across_exchanges_is_not_double_counted():
    class SplitHeat(CHP):
        def apply(self, demand):
            return Result(
                production=[
                    Exchange(
                        flow=Flow(iri=HEAT, location="CH"), amount=50.0, unit="MJ",
                        properties=(Property("energy", 50.0, "MJ"),),
                    ),
                    Exchange(
                        flow=Flow(iri=HEAT, location="CH"), amount=50.0, unit="MJ",
                        properties=(Property("energy", 50.0, "MJ"),),
                    ),
                    Exchange(
                        flow=Flow(iri=POWER, location="CH"), amount=50.0, unit="MJ",
                        properties=(Property("energy", 50.0, "MJ"),),
                    ),
                ],
                technosphere=[Demand(flow=Flow(iri=GAS, location="CH"), amount=200.0, unit="MJ")],
                biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0, unit="kg")],
            )

    result = runner_for(SplitHeat(), "energy").apply(HEAT_DEMAND)
    # heat is still 100 of 150 MJ total, whether it arrives as one exchange or
    # two: the split must not change the share.
    assert result.provenance["attribution"]["share"] == pytest.approx(2 / 3)
    assert result.technosphere[0].amount == pytest.approx(200.0 * 2 / 3)


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


def test_a_negative_property_is_refused_rather_than_partitioned_over():
    """A share taken over a negative total is not a share.

    With heat at +10 EUR and power at -8 EUR the total is 2, and heat's
    "share" comes out 5.0 -- the demanded product silently carrying five times
    the process's own burden, with nothing in the report saying so. A negative
    price means that output is a waste the process pays to be rid of, which is
    a different question than co-production, and `economic` is exactly where
    it turns up.
    """
    class WasteHeat(CHP):
        def apply(self, demand):
            return Result(
                production=[
                    Exchange(flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ",
                             properties=(Property("price", 10.0, "EUR"),)),
                    Exchange(flow=Flow(iri=POWER, location="CH"), amount=50.0, unit="MJ",
                             properties=(Property("price", -8.0, "EUR"),)),
                ],
                technosphere=[Demand(flow=Flow(iri=GAS, location="CH"), amount=200.0, unit="MJ")],
                biosphere=[Exchange(flow=Flow(iri=CO2, location="CH"), amount=12.0, unit="kg")],
            )

    with pytest.raises(MissingProperty, match="waste"):
        runner_for(WasteHeat(), "economic").apply(HEAT_DEMAND)


def test_the_total_being_positive_does_not_excuse_a_negative_part():
    """Caught on the value, not on the total: -8 and +10 sum to a positive 2,
    so a guard on the total alone lets the 5.0 share straight through."""
    class Mixed(CHP):
        def apply(self, demand):
            result = super().apply(demand)
            result.production = [
                Exchange(flow=Flow(iri=HEAT, location="CH"), amount=100.0, unit="MJ",
                         properties=(Property("mass", 10.0, "kg"),)),
                Exchange(flow=Flow(iri=POWER, location="CH"), amount=50.0, unit="MJ",
                         properties=(Property("mass", -8.0, "kg"),)),
            ]
            return result

    with pytest.raises(MissingProperty, match="'mass'"):
        runner_for(Mixed(), "mass").apply(HEAT_DEMAND)


def test_co_production_under_none_raises_a_trailrunner_error():
    """`none` is the default, so this is the likeliest refusal a user meets.
    A bare ValueError put that one refusal outside `except TrailrunnerError`."""
    with pytest.raises(UnallocatedCoProduction, match="co-product"):
        runner_for(CHP(), "none").apply(HEAT_DEMAND)
    assert issubclass(UnallocatedCoProduction, TrailrunnerError)
    # Still a ValueError as well: code written against the old behaviour keeps
    # catching it.
    assert issubclass(UnallocatedCoProduction, ValueError)


def test_the_monofunctional_short_circuit_does_not_write_into_the_caller():
    """A model reusing one provenance dict must not find `attribution` in it.

    The co-product path copies; this path used to mutate and return the
    caller's own Result, so the run's normative choice was written into
    whatever the model handed over.
    """
    shared: dict = {}

    class Boiler(Model):
        produces = [HEAT]
        supports = frozenset({"none", "economic"})

        def apply(self, demand):
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                provenance=shared,
            )

    model = Boiler()
    result = runner_for(model, "economic").apply(HEAT_DEMAND)
    assert result.provenance["attribution"]["share"] == 1.0
    assert shared == {}
