import pytest

from trailrunner.core.errors import AmbiguousModelMatch
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ProxySettings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import Coverage
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import GeneralisingProvider, ModelProvider, StaticTaxonomy

HEAT = "https://vocab.sentier.dev/products/heat"
GREEN_TRUCK = "https://vocab.sentier.dev/products/truck-green"
TRUCK = "https://vocab.sentier.dev/products/truck"

HIERARCHY = LocationHierarchy({"CH": "RER", "RER": "GLO"})


class RegionalBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(locations=frozenset({"RER"}))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class DatedBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(time_range=(2035, 2050))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class GenericTruck(Model):
    produces = [TRUCK]

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def provider(models, settings=None, taxonomy=None):
    return GeneralisingProvider(
        ModelProvider(Glossary(models)),
        settings=settings or ProxySettings(),
        hierarchy=HIERARCHY,
        taxonomy=taxonomy,
    )


def test_location_is_widened_up_the_hierarchy():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    offer = provider([RegionalBoiler()]).offer(demand)
    assert isinstance(offer.model, RegionalBoiler)
    assert offer.demand.flow.location == "RER"


def test_the_relaxation_is_recorded_in_the_offer():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    offer = provider([RegionalBoiler()]).offer(demand)
    assert offer.tier == "generalising"
    assert offer.resolution["relaxations"] == ["location: CH -> RER"]


def test_the_amount_and_unit_survive_the_relaxation():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    offer = provider([RegionalBoiler()]).offer(demand)
    assert offer.demand.amount == 10.0
    assert offer.demand.unit == "MJ"


def test_location_budget_is_respected():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    settings = ProxySettings(order=("location",), max_steps={"location": 0})
    assert provider([RegionalBoiler()], settings=settings).offer(demand) is None


def test_time_is_snapped_to_a_covered_year_within_tolerance():
    demand = Demand(flow=Flow(iri=HEAT, time=2032), amount=10.0, unit="MJ")
    offer = provider([DatedBoiler()]).offer(demand)
    assert offer.demand.flow.time == 2035
    assert offer.resolution["relaxations"] == ["time: 2032 -> 2035"]


def test_time_outside_the_tolerance_is_not_snapped():
    demand = Demand(flow=Flow(iri=HEAT, time=2020), amount=10.0, unit="MJ")
    assert provider([DatedBoiler()]).offer(demand) is None


def test_product_is_widened_through_the_taxonomy():
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit="unit")
    offer = provider([GenericTruck()], taxonomy=taxonomy).offer(demand)
    assert isinstance(offer.model, GenericTruck)
    assert offer.resolution["relaxations"] == [f"product: {GREEN_TRUCK} -> {TRUCK}"]


def test_product_relaxation_needs_a_taxonomy():
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit="unit")
    assert provider([GenericTruck()], taxonomy=None).offer(demand) is None


def test_dimensions_are_tried_in_the_declared_order():
    """Location first finds the regional boiler; time first finds the dated one."""
    demand = Demand(flow=Flow(iri=HEAT, location="CH", time=2032), amount=10.0, unit="MJ")
    location_first = provider(
        [RegionalBoiler(), DatedBoiler()],
        settings=ProxySettings(order=("location", "time")),
    ).offer(demand)
    time_first = provider(
        [RegionalBoiler(), DatedBoiler()],
        settings=ProxySettings(order=("time", "location")),
    ).offer(demand)
    assert isinstance(location_first.model, RegionalBoiler)
    assert isinstance(time_first.model, DatedBoiler)


def test_an_exact_match_is_left_to_tier_one():
    """The generalising tier never answers a demand tier 1 could have."""
    class ExactBoiler(Model):
        produces = [HEAT]

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    assert provider([ExactBoiler()]).offer(demand) is not None  # it would answer
    # but in a real chain ModelProvider is asked first and wins:
    from trailrunner.resolution import ResolutionChain
    chain = ResolutionChain([ModelProvider(Glossary([ExactBoiler()])),
                             provider([ExactBoiler()])])
    assert chain.offer(demand).tier == "model"


def test_explain_says_generalisation_was_tried():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    reason, detail = provider([]).explain(demand)
    assert reason == "generalisation_exhausted"
    assert "location" in detail


def test_explain_is_silent_when_no_budget_was_available():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    settings = ProxySettings(order=(), max_steps={})
    assert provider([], settings=settings).explain(demand) is None


def test_budget_counts_attempts_not_successes():
    """A step is spent on every candidate tried, not only on ones that match.

    HIERARCHY runs CH -> RER -> GLO; this model covers only GLO, the second
    hop. A budget of 1 is spent trying RER (which fails) and never reaches
    GLO. ``test_location_budget_is_respected`` uses ``max_steps=0``, which the
    outer ``budget <= 0`` guard catches before the inner per-step comparison
    ever runs -- it cannot tell "0 attempts" apart from "1 attempt that
    failed." This does.
    """

    class GloOnlyBoiler(Model):
        produces = [HEAT]
        coverage = Coverage(locations=frozenset({"GLO"}))

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")

    one_step = ProxySettings(order=("location",), max_steps={"location": 1})
    assert provider([GloOnlyBoiler()], settings=one_step).offer(demand) is None

    two_steps = ProxySettings(order=("location",), max_steps={"location": 2})
    offer = provider([GloOnlyBoiler()], settings=two_steps).offer(demand)
    assert isinstance(offer.model, GloOnlyBoiler)
    assert offer.demand.flow.location == "GLO"


def test_ambiguous_match_reached_through_relaxation_is_not_swallowed():
    """Two models matching the *relaxed* demand are a data error, not a decline.

    ``Glossary.resolve`` already raises ``AmbiguousModelMatch`` for two
    candidates at tier 1; the generalising tier must let that propagate
    rather than catching it and reporting "no offer", which would hide a real
    modelling conflict behind an ordinary cutoff.
    """

    class BoilerA(Model):
        produces = [HEAT]
        coverage = Coverage(locations=frozenset({"RER"}))

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    class BoilerB(Model):
        produces = [HEAT]
        coverage = Coverage(locations=frozenset({"RER"}))

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit="MJ")
    with pytest.raises(AmbiguousModelMatch):
        provider([BoilerA(), BoilerB()]).offer(demand)
