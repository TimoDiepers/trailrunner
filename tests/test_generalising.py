from pathlib import Path

import pytest

from trailrunner.core.errors import AmbiguousModelMatch
from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ProxySettings
from trailrunner.models.dac import HEAT as REAL_HEAT
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import ContextRange, Coverage
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import GeneralisingProvider, ModelProvider, PystTaxonomy, StaticTaxonomy
from trailrunner.core.time import DATE, GYEAR, in_year, year_range
from trailrunner.core.units import KELVIN, KG, KILOMETRE, METRE, MJ, NUM, PA, TONNE

HEAT = "https://vocab.sentier.dev/products/heat"
GREEN_TRUCK = "https://vocab.sentier.dev/products/truck-green"
TRUCK = "https://vocab.sentier.dev/products/truck"
VEHICLE = "https://vocab.sentier.dev/products/road-vehicle"

HIERARCHY = LocationHierarchy({"CH": "RER", "RER": "GLO"})


class RegionalBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(locations=frozenset({"RER"}))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class DatedBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(time_range=year_range(2035, 2050))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class GenericTruck(Model):
    produces = [TRUCK]

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class GenericVehicle(Model):
    produces = [VEHICLE]

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
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    offer = provider([RegionalBoiler()]).offer(demand)
    assert isinstance(offer.model, RegionalBoiler)
    assert offer.demand.flow.location == "RER"


def test_the_relaxation_is_recorded_in_the_offer():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    offer = provider([RegionalBoiler()]).offer(demand)
    assert offer.tier == "generalising"
    assert offer.resolution["relaxations"] == ["location: CH -> RER"]


def test_the_amount_and_unit_survive_the_relaxation():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    offer = provider([RegionalBoiler()]).offer(demand)
    assert offer.demand.amount == 10.0
    assert offer.demand.unit == MJ


def test_location_budget_is_respected():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    settings = ProxySettings(order=("location",), max_steps={"location": 0})
    assert provider([RegionalBoiler()], settings=settings).offer(demand) is None


def test_time_is_snapped_to_a_covered_year_within_tolerance():
    demand = Demand(flow=Flow(iri=HEAT, **in_year(2032)), amount=10.0, unit=MJ)
    offer = provider([DatedBoiler()]).offer(demand)
    assert offer.demand.flow.time == "2035"
    assert offer.resolution["relaxations"] == ["time: 2032 -> 2035"]


def test_time_outside_the_tolerance_is_not_snapped():
    demand = Demand(flow=Flow(iri=HEAT, **in_year(2020)), amount=10.0, unit=MJ)
    assert provider([DatedBoiler()]).offer(demand) is None


def test_product_is_widened_through_the_taxonomy():
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    offer = provider([GenericTruck()], taxonomy=taxonomy).offer(demand)
    assert isinstance(offer.model, GenericTruck)
    assert offer.resolution["relaxations"] == ["product: truck-green -> truck"]


def test_the_product_note_is_short_and_the_full_pair_is_still_recorded():
    """The note is what ``tree()`` prints, so it carries the last segment of
    each IRI; the full pair a reader traces a number with stays in the
    resolution, and so in ``report.proxies`` and the log parquet."""
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    offer = provider([GenericTruck()], taxonomy=taxonomy).offer(demand)
    note = offer.resolution["relaxations"][0]
    assert "https://" not in note
    assert len(note) < 60
    assert GREEN_TRUCK in offer.resolution["asked"]
    assert TRUCK in offer.resolution["answered"]


def test_product_relaxation_needs_a_taxonomy():
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    assert provider([GenericTruck()], taxonomy=None).offer(demand) is None


def test_dimensions_are_tried_in_the_declared_order():
    """Location first finds the regional boiler; time first finds the dated one."""
    demand = Demand(flow=Flow(iri=HEAT, location="CH", **in_year(2032)), amount=10.0, unit=MJ)
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

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    assert provider([ExactBoiler()]).offer(demand) is not None  # it would answer
    # but in a real chain ModelProvider is asked first and wins:
    from trailrunner.resolution import ResolutionChain
    chain = ResolutionChain([ModelProvider(Glossary([ExactBoiler()])),
                             provider([ExactBoiler()])])
    assert chain.offer(demand).tier == "model"


def test_explain_says_generalisation_was_tried():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    reason, detail = provider([]).explain(demand)
    assert reason == "generalisation_exhausted"
    assert "location" in detail


def test_explain_is_silent_when_no_candidate_could_be_generated():
    """A demand with no location, no year and no taxonomy has nothing to
    relax, whatever the budgets say. Explaining it as "budget spent" was both
    false and useless: it pointed the reader at ``max_steps``, which cannot
    manufacture a candidate. Silence here is what lets the chain fall through
    to its own ``no_model_found``."""
    demand = Demand(flow=Flow(iri="https://vocab.sentier.dev/products/unobtainium"),
                    amount=1.0, unit=KG)
    assert provider([]).explain(demand) is None


def test_explain_counts_the_candidates_it_actually_generated():
    """Not the budget it was allowed. CH -> RER -> GLO offers two candidates
    against a location budget of three, and the detail says two."""
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    settings = ProxySettings(order=("location",), max_steps={"location": 3})
    _reason, detail = provider([], settings=settings).explain(demand)
    assert "location(2)" in detail


def test_explain_ignores_a_dimension_with_nothing_to_try():
    """A budget for the product dimension with no taxonomy behind it is not a
    thing that was tried, and must not be reported as one."""
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    _reason, detail = provider([], taxonomy=None).explain(demand)
    assert "product" not in detail
    assert "time" not in detail


def test_explain_is_silent_when_no_budget_was_available():
    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
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

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)

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

    demand = Demand(flow=Flow(iri=HEAT, location="CH"), amount=10.0, unit=MJ)
    with pytest.raises(AmbiguousModelMatch):
        provider([BoilerA(), BoilerB()]).offer(demand)


def test_the_product_walk_climbs_more_than_one_level():
    """``product: 2`` means two levels up the vocabulary, the way
    ``location: 3`` means three steps up the hierarchy -- not two of the
    direct parents. A real chain (fi_17100 -> fi_1710 -> fi_171) is three
    levels deep, and a single-level walk could never reach past the first.
    """
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK], TRUCK: [VEHICLE]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    settings = ProxySettings(order=("product",), max_steps={"product": 2})
    offer = provider([GenericVehicle()], settings=settings, taxonomy=taxonomy).offer(demand)
    assert isinstance(offer.model, GenericVehicle)
    assert offer.demand.flow.iri == VEHICLE
    assert offer.resolution["relaxations"] == ["product: truck-green -> road-vehicle"]


def test_the_product_budget_stops_the_walk_at_the_level_it_says():
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK], TRUCK: [VEHICLE]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    settings = ProxySettings(order=("product",), max_steps={"product": 1})
    assert provider([GenericVehicle()], settings=settings, taxonomy=taxonomy).offer(demand) is None


def test_the_nearer_concept_is_tried_before_the_wider_one():
    """Breadth-first: every concept one level up is tried before any concept
    two levels up, so the most specific model still standing wins."""
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK], TRUCK: [VEHICLE]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    settings = ProxySettings(order=("product",), max_steps={"product": 2})
    offer = provider(
        [GenericTruck(), GenericVehicle()], settings=settings, taxonomy=taxonomy
    ).offer(demand)
    assert isinstance(offer.model, GenericTruck)


def test_a_cycle_in_the_taxonomy_does_not_hang_the_walk():
    """A vocabulary is not guaranteed acyclic, and this walks it in a loop."""
    taxonomy = StaticTaxonomy({GREEN_TRUCK: [TRUCK], TRUCK: [GREEN_TRUCK]})
    demand = Demand(flow=Flow(iri=GREEN_TRUCK), amount=1.0, unit=NUM)
    settings = ProxySettings(order=("product",), max_steps={"product": 5})
    assert provider([], settings=settings, taxonomy=taxonomy).offer(demand) is None


def test_every_tier_two_resolution_speaks_the_shared_vocabulary():
    """``tier``, ``model``, ``asked`` and ``answered`` mean the same thing in
    every tier, and ``asked`` describes the demand rather than restating an
    IRI that did not change."""
    demand = Demand(flow=Flow(iri=HEAT, location="CH", **in_year(2030)), amount=10.0, unit=MJ)
    resolution = provider([RegionalBoiler()]).offer(demand).resolution
    assert resolution["tier"] == "generalising"
    assert resolution["model"] == "RegionalBoiler"
    assert resolution["asked"] == f"{HEAT} @CH/2030"
    assert resolution["answered"] == f"{HEAT} @RER/2030"


def test_a_relaxed_demand_still_carries_the_exclusion():
    """A generalised credit must not land back on the model that minted it.

    Relaxing a demand does not change whose avoided burden it is. A tier-2
    offer that dropped ``exclude`` on its way to tier 1 would answer a
    substitution credit with the very process that produced the co-product --
    the self-substitution loop again, one hop later and wearing a proxy label.
    """
    boiler = RegionalBoiler()
    swiss_heat = Demand(flow=Flow(iri=HEAT, location="CH"), amount=1.0, unit=MJ)

    offer = provider([boiler]).offer(swiss_heat)
    assert offer.model is boiler

    assert provider([boiler]).offer(swiss_heat, exclude=(boiler,)) is None


class RegionalDatedBoiler(Model):
    """Answers only a demand that is both regional and late enough: no single
    relaxation of a Swiss 2032 demand reaches it."""
    produces = [HEAT]
    coverage = Coverage(locations=frozenset({"RER"}), time_range=year_range(2035, 2050))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class GlobalDatedBoiler(Model):
    produces = [HEAT]
    coverage = Coverage(locations=frozenset({"GLO"}), time_range=year_range(2033, 2050))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


SWISS_2032 = Demand(flow=Flow(iri=HEAT, location="CH", **in_year(2032)), amount=10.0, unit=MJ)
COMBINED = ProxySettings(
    order=("time", "location", ("location", "time")),
    max_steps={"time": 1, "location": 2},
)


def test_relaxations_do_not_compose_unless_asked_to():
    settings = ProxySettings(order=("time", "location"), max_steps={"time": 1, "location": 2})
    assert provider([RegionalDatedBoiler()], settings=settings).offer(SWISS_2032) is None


def test_a_combined_entry_answers_what_no_single_dimension_can():
    offer = provider([RegionalDatedBoiler()], settings=COMBINED).offer(SWISS_2032)
    assert isinstance(offer.model, RegionalDatedBoiler)
    assert offer.demand.flow.location == "RER"
    assert offer.demand.flow.time == "2035"
    assert offer.resolution["relaxations"] == ["location: CH -> RER", "time: 2032 -> 2035"]
    assert offer.resolution["answered"] == f"{HEAT} @RER/2035"


def at(location, year):
    """A heat model covering one place and one year."""

    class Boiler(Model):
        produces = [HEAT]
        coverage = Coverage(locations=frozenset({location}), time_range=year_range(year, year))

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    Boiler.__name__ = f"Boiler{location}{year}"
    return Boiler()


def test_the_combined_search_tries_the_fewest_total_steps_first():
    """Covered years, nearest first: 2033, 2034, 2036 -- steps 1, 2, 3.
    GLO/2033 is three steps away, RER/2036 four; walking location as the outer
    loop would reach RER/2036 first, and the search must not."""
    models = [at("GLO", 2033), at("XX", 2034), at("RER", 2036)]
    settings = ProxySettings(order=(("location", "time"),), max_steps={"time": 3, "location": 2})
    offer = provider(models, settings=settings).offer(SWISS_2032)
    assert offer.demand.flow.location == "GLO"
    assert offer.demand.flow.time == "2033"


def test_a_combined_entry_placed_before_product_beats_the_product_proxy():
    """The reason to compose at all: a neighbouring region and year can be a
    better proxy than a wider product category, and the order says which."""
    taxonomy = StaticTaxonomy({HEAT: [VEHICLE]})

    class WiderProduct(Model):
        produces = [VEHICLE]

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    models = [RegionalDatedBoiler(), WiderProduct()]
    budgets = {"time": 1, "location": 2, "product": 1}
    combo_first = ProxySettings(order=("location", ("location", "time"), "product"), max_steps=budgets)
    product_first = ProxySettings(order=("location", "product", ("location", "time")), max_steps=budgets)
    assert isinstance(provider(models, combo_first, taxonomy).offer(SWISS_2032).model, RegionalDatedBoiler)
    assert isinstance(provider(models, product_first, taxonomy).offer(SWISS_2032).model, WiderProduct)


def test_the_combined_search_respects_every_member_budget():
    tight = ProxySettings(order=(("location", "time"),), max_steps={"time": 1, "location": 1})
    assert provider([GlobalDatedBoiler()], settings=tight).offer(SWISS_2032) is None
    wide = ProxySettings(order=(("location", "time"),), max_steps={"time": 1, "location": 2})
    assert isinstance(provider([GlobalDatedBoiler()], settings=wide).offer(SWISS_2032).model, GlobalDatedBoiler)


def test_the_combined_search_respects_the_time_tolerance():
    settings = ProxySettings(
        order=(("location", "time"),), max_steps={"time": 1, "location": 2}, time_tolerance=2
    )
    assert provider([RegionalDatedBoiler()], settings=settings).offer(SWISS_2032) is None


def test_a_tie_in_total_steps_goes_to_the_member_declared_first():
    """Two steps either way: RER + second-nearest year, or GLO + nearest year.
    ``("time", "location")`` prefers moving time less; ``("location", "time")``
    prefers moving location less."""

    # Covered years: 2033 (step 1), 2036 (step 2). RER/2036 is (location 1,
    # time 2), GLO/2033 is (location 2, time 1): three steps each.
    glo, rer = at("GLO", 2033), at("RER", 2036)
    models = [glo, rer]
    budgets = {"time": 2, "location": 2}
    location_less = ProxySettings(order=(("location", "time"),), max_steps=budgets)
    time_less = ProxySettings(order=(("time", "location"),), max_steps=budgets)
    assert provider(models, location_less).offer(SWISS_2032).model is rer
    assert provider(models, time_less).offer(SWISS_2032).model is glo


def test_a_combined_offer_still_carries_the_exclusion():
    boiler = RegionalDatedBoiler()
    assert provider([boiler], settings=COMBINED).offer(SWISS_2032, exclude=(boiler,)) is None


def test_explain_counts_the_combined_candidates():
    _reason, detail = provider([RegionalDatedBoiler()], settings=COMBINED).explain(SWISS_2032)
    assert "location+time(" in detail


PYST_CACHE = Path(__file__).resolve().parent.parent / "examples" / "pyst_cache.json"

# The real BONSAI parent of trailrunner.models.dac.HEAT (fi_1730_9, "heat
# from main producers of heat"): fi_1730, "Steam and hot water" -- verified
# live against https://vocab.sentier.dev and cached by dev/warm_pyst_cache.py.
# Before the models were repointed at real vocabulary concepts, HEAT was the
# invented "https://vocab.sentier.dev/products/heat", which the concepts
# endpoint answers 404 for; skos:broader had nothing to walk, so this exact
# test -- unchanged apart from which HEAT it imports -- would find no offer.
HEAT_PARENT = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730"


def test_the_committed_offline_cache_lets_a_parent_model_answer_a_child_demand():
    """The product dimension relaxes something real, not a fixture.

    Reads only the cache committed at ``examples/pyst_cache.json`` -- no
    client, so no network and a deterministic result. A model registered at
    the *parent* BONSAI concept (steam and hot water) answers a demand for
    the *child* (heat from main producers of heat) exactly the way the
    showcase's generalisation beat needs it to.
    """
    class SteamAndHotWaterBoiler(Model):
        produces = [HEAT_PARENT]

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    taxonomy = PystTaxonomy(PYST_CACHE, client=None)
    demand = Demand(flow=Flow(iri=REAL_HEAT), amount=10.0, unit=MJ)

    offer = provider([SteamAndHotWaterBoiler()], taxonomy=taxonomy).offer(demand)

    assert offer is not None
    assert isinstance(offer.model, SteamAndHotWaterBoiler)
    assert offer.demand.flow.iri == HEAT_PARENT
    assert offer.resolution["relaxations"] == ["product: fi_1730_9 -> fi_1730"]


def test_offline_cache_has_nothing_for_the_old_invented_heat_iri():
    """The other half of the proof: before the repointing, this demand had no
    candidate at all. ``HEAT`` (the module-level constant this file already
    uses for its own hand-rolled ``StaticTaxonomy`` fixtures) is the invented
    IRI ``trailrunner.models.dac.HEAT`` used to hold; it is not a real
    vocabulary concept, so the committed cache -- built only from real,
    verified concepts -- was never asked about it and has nothing cached.
    Reading it with no client therefore answers ``[]``, exactly as it did
    before this IRI stopped being used anywhere in the shipped models.
    """
    taxonomy = PystTaxonomy(PYST_CACHE, client=None)
    assert taxonomy.broader(HEAT) == []


GAS = "https://vocab.sentier.dev/products/gas"


class FiveBarGas(Model):
    produces = [GAS]
    coverage = Coverage(context=(ContextRange("pressure", PA, 5e5, 5e5),))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def gas_at(pascal, unit=PA):
    return Demand(
        flow=Flow(iri=GAS, location="CH", **in_year(2030), context=(Property("pressure", pascal, unit),)),
        amount=10.0,
        unit=MJ,
    )


PRESSURE_UP_TO_ONE_BAR_HIGHER = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})


def test_context_is_moved_to_the_value_a_model_covers():
    offer = provider([FiveBarGas()], settings=PRESSURE_UP_TO_ONE_BAR_HIGHER).offer(gas_at(4e5))
    assert isinstance(offer.model, FiveBarGas)
    assert offer.demand.flow.get_context("pressure") == Property("pressure", 5e5, PA)
    assert offer.resolution["relaxations"] == ["context: pressure 400000 Pa -> 500000 Pa"]


def test_asked_and_answered_differ_by_the_relaxed_context():
    offer = provider([FiveBarGas()], settings=PRESSURE_UP_TO_ONE_BAR_HIGHER).offer(gas_at(4e5))
    assert offer.resolution["asked"].endswith("@CH/2030 [pressure=400000 Pa]")
    assert offer.resolution["answered"].endswith("@CH/2030 [pressure=500000 Pa]")


def test_context_is_never_moved_to_the_side_the_tolerance_forbids():
    """A 6-bar burner cannot run on 5-bar gas, however close it is."""
    assert provider([FiveBarGas()], settings=PRESSURE_UP_TO_ONE_BAR_HIGHER).offer(gas_at(6e5)) is None


def test_context_is_not_moved_beyond_the_tolerance():
    assert provider([FiveBarGas()], settings=PRESSURE_UP_TO_ONE_BAR_HIGHER).offer(gas_at(3e5)) is None


def test_context_is_not_relaxed_without_a_tolerance():
    assert provider([FiveBarGas()]).offer(gas_at(4e5)) is None


def test_context_in_another_quantity_kind_is_not_relaxed():
    settings = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})
    assert provider([FiveBarGas()], settings=settings).offer(gas_at(4.0, unit=KG)) is None


HAUL = "https://vocab.sentier.dev/products/haul"


class TenKilometreHaul(Model):
    produces = [HAUL]
    coverage = Coverage(context=(ContextRange("distance", KILOMETRE, 10.0, 10.0),))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def test_context_tolerance_in_another_unit_than_the_ask():
    settings = ProxySettings(context_tolerance={"distance": (0.0, 1.0, KILOMETRE)})
    asked = Demand(
        flow=Flow(iri=HAUL, context=(Property("distance", 9500.0, METRE),)),
        amount=1.0,
        unit=TONNE,
    )
    offer = provider([TenKilometreHaul()], settings=settings).offer(asked)
    assert offer.demand.flow.get_context("distance") == Property("distance", 10000.0, METRE)
    assert offer.resolution["relaxations"] == ["context: distance 9500 m -> 10000 m"]


def test_context_budget_is_respected():
    settings = ProxySettings(
        max_steps={"context": 0}, context_tolerance={"pressure": (0.0, 1e5, PA)}
    )
    assert provider([FiveBarGas()], settings=settings).offer(gas_at(4e5)) is None


def test_a_demand_naming_no_pressure_is_answered_exactly():
    demand = Demand(flow=Flow(iri=GAS, location="CH", **in_year(2030)), amount=10.0, unit=MJ)
    assert ModelProvider(Glossary([FiveBarGas()])).offer(demand).tier == "model"


class FiveBarWarmGas(Model):
    produces = [GAS]
    coverage = Coverage(
        context=(
            ContextRange("pressure", PA, 5e5, 5e5),
            ContextRange("temperature", KELVIN, 300.0, 300.0),
        )
    )

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def gas_at_both(pascal, kelvin):
    context = (Property("pressure", pascal, PA), Property("temperature", kelvin, KELVIN))
    return Demand(flow=Flow(iri=GAS, context=context), amount=10.0, unit=MJ)


BOTH_TOLERATED = {"pressure": (0.0, 1e5, PA), "temperature": (0.0, 10.0, KELVIN)}


def test_plain_context_never_moves_two_conditions_together():
    settings = ProxySettings(context_tolerance=BOTH_TOLERATED, max_steps={"context": 5})
    assert provider([FiveBarWarmGas()], settings=settings).offer(gas_at_both(4e5, 295.0)) is None


def test_combined_context_conditions_move_together():
    settings = ProxySettings(
        order=(("context.pressure", "context.temperature"),),
        context_tolerance=BOTH_TOLERATED,
    )
    offer = provider([FiveBarWarmGas()], settings=settings).offer(gas_at_both(4e5, 295.0))
    assert offer.resolution["relaxations"] == [
        "context: pressure 400000 Pa -> 500000 Pa",
        "context: temperature 295 K -> 300 K",
    ]
    assert offer.resolution["answered"].endswith("[pressure=500000 Pa, temperature=300 K]")


def test_a_single_condition_dimension_moves_only_that_condition():
    settings = ProxySettings(order=("context.temperature",), context_tolerance=BOTH_TOLERATED)
    gas = provider([FiveBarWarmGas()], settings=settings)
    assert gas.offer(gas_at_both(4e5, 300.0)) is None  # pressure is off, and not named
    offer = gas.offer(gas_at_both(5e5, 295.0))
    assert offer.resolution["relaxations"] == ["context: temperature 295 K -> 300 K"]


def test_the_order_decides_single_before_combined():
    settings = ProxySettings(
        order=(
            "context.pressure",
            "context.temperature",
            ("context.pressure", "context.temperature"),
        ),
        context_tolerance=BOTH_TOLERATED,
    )
    gas = provider([FiveBarWarmGas()], settings=settings)
    assert gas.offer(gas_at_both(4e5, 300.0)).resolution["relaxations"] == [
        "context: pressure 400000 Pa -> 500000 Pa"
    ]
    assert len(gas.offer(gas_at_both(4e5, 295.0)).resolution["relaxations"]) == 2


def test_a_context_condition_combines_with_location():
    class RegionalFiveBarGas(FiveBarGas):
        coverage = Coverage(
            locations=frozenset({"RER"}),
            context=(ContextRange("pressure", PA, 5e5, 5e5),),
        )

    settings = ProxySettings(
        order=(("location", "context.pressure"),),
        context_tolerance={"pressure": (0.0, 1e5, PA)},
    )
    offer = provider([RegionalFiveBarGas()], settings=settings).offer(gas_at(4e5))
    assert offer.resolution["relaxations"] == [
        "location: CH -> RER",
        "context: pressure 400000 Pa -> 500000 Pa",
    ]


def test_a_combined_context_entry_stays_within_each_tolerance():
    settings = ProxySettings(
        order=(("context.pressure", "context.temperature"),),
        context_tolerance={"pressure": (0.0, 1e5, PA), "temperature": (0.0, 2.0, KELVIN)},
    )
    assert provider([FiveBarWarmGas()], settings=settings).offer(gas_at_both(4e5, 295.0)) is None


def test_a_day_outside_coverage_snaps_to_the_nearest_covered_year():
    # DatedBoiler covers 2035..2050; a demand dated the last day of 2034
    # is about half a year from 2035's midpoint.
    demand = Demand(flow=Flow(iri=HEAT, time="2034-12-31", time_standard=DATE), amount=1.0, unit=MJ)
    offer = provider([DatedBoiler()]).offer(demand)
    assert (offer.demand.flow.time, offer.demand.flow.time_standard) == ("2035", GYEAR)
    assert offer.resolution["relaxations"] == ["time: 2034-12-31 -> 2035"]


def test_a_year_snaps_exactly_as_it_did_with_int_years():
    demand = Demand(flow=Flow(iri=HEAT, **in_year(2034)), amount=1.0, unit=MJ)
    offer = provider([DatedBoiler()]).offer(demand)
    assert offer.resolution["relaxations"] == ["time: 2034 -> 2035"]


PRESSURE = "https://vocab.sentier.dev/units/quantity-kind/Pressure"


class FiveBarGasByIri(Model):
    produces = [GAS]
    coverage = Coverage(context=(ContextRange(PRESSURE, PA, 5e5, 5e5),))

    def apply(self, demand):
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


def test_iri_conditions_match_by_iri_and_are_written_in_full():
    demand = Demand(
        flow=Flow(iri=GAS, context=(Property(PRESSURE, 4e5, PA),)), amount=10.0, unit=MJ
    )
    settings = ProxySettings(
        order=(f"context.{PRESSURE}",), context_tolerance={PRESSURE: (0.0, 1e5, PA)}
    )
    offer = provider([FiveBarGasByIri()], settings=settings).offer(demand)
    assert offer.resolution["relaxations"] == [f"context: {PRESSURE} 400000 Pa -> 500000 Pa"]
    assert offer.resolution["answered"].endswith(f"[{PRESSURE}=500000 Pa]")


def test_a_short_name_does_not_match_an_iri_condition():
    demand = Demand(
        flow=Flow(iri=GAS, context=(Property("Pressure", 4e5, PA),)), amount=10.0, unit=MJ
    )
    settings = ProxySettings(context_tolerance={"Pressure": (0.0, 1e5, PA)})
    assert provider([FiveBarGasByIri()], settings=settings).offer(demand) is None
