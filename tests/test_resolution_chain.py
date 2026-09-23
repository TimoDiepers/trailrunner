import pytest

from trailrunner.core.errors import AmbiguousModelMatch
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import Coverage
from trailrunner.resolution import ModelProvider, Offer, ResolutionChain

HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"

DEMAND = Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=10.0, unit="MJ")


class Boiler(Model):
    produces = [HEAT]

    def apply(self, demand: Demand) -> Result:
        return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])


class AlwaysOffers:
    """A stub tier that answers everything, to prove ordering."""

    def __init__(self, tier: str) -> None:
        self.tier = tier
        self.model = Boiler()

    def offer(self, demand):
        return Offer(model=self.model, demand=demand, tier=self.tier,
                     resolution={"tier": self.tier})

    def explain(self, demand):
        return None


def test_model_provider_offers_an_exact_match():
    offer = ModelProvider(Glossary([Boiler()])).offer(DEMAND)
    assert isinstance(offer.model, Boiler)
    assert offer.tier == "model"
    assert offer.demand is DEMAND


def test_model_provider_declines_what_it_does_not_produce():
    gas_demand = Demand(flow=Flow(iri=GAS), amount=1.0, unit="kg")
    assert ModelProvider(Glossary([Boiler()])).offer(gas_demand) is None


def test_model_provider_still_raises_on_ambiguity():
    class OtherBoiler(Boiler):
        pass

    with pytest.raises(AmbiguousModelMatch):
        ModelProvider(Glossary([Boiler(), OtherBoiler()])).offer(DEMAND)


def test_chain_returns_the_first_offer():
    chain = ResolutionChain([AlwaysOffers("first"), AlwaysOffers("second")])
    assert chain.offer(DEMAND).tier == "first"


def test_chain_falls_through_to_a_later_tier():
    chain = ResolutionChain([ModelProvider(Glossary()), AlwaysOffers("second")])
    assert chain.offer(DEMAND).tier == "second"


def test_chain_returns_none_when_every_tier_declines():
    assert ResolutionChain([ModelProvider(Glossary())]).offer(DEMAND) is None


def test_explain_reports_a_coverage_miss_from_tier_one():
    class Dated(Model):
        produces = [HEAT]
        coverage = Coverage(time_range=(2040, 2050))

        def apply(self, demand):
            return Result(production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)])

    chain = ResolutionChain([ModelProvider(Glossary([Dated()]))])
    reason, detail = chain.explain(DEMAND)
    assert reason == "coverage_excluded"
    assert "Dated" in detail


def test_explain_defaults_to_no_model_found():
    reason, _ = ResolutionChain([ModelProvider(Glossary())]).explain(DEMAND)
    assert reason == "no_model_found"


def test_chain_exposes_the_glossary_of_its_model_tier():
    glossary = Glossary([Boiler()])
    assert ResolutionChain([ModelProvider(glossary)]).glossary is glossary


class TierOnlyOffer:
    """A provider that sets ``Offer.tier`` and leaves ``resolution`` empty.

    The shape a provider written against the dataclass -- rather than against
    the undocumented convention that the dict must repeat the tier -- would
    naturally take.
    """

    def offer(self, demand):
        return Offer(model=Boiler(), demand=demand, tier="mystery")

    def explain(self, demand):
        return None


def test_an_offer_that_only_sets_the_tier_field_still_records_it():
    offer = TierOnlyOffer().offer(DEMAND)
    assert offer.resolution["tier"] == "mystery"


def test_a_tier_only_offer_is_a_proxy_in_the_report_not_an_exact_match():
    """The end-to-end shape of the bug: the Orchestrator forwards
    ``offer.resolution`` alone, so a tier carried only on the field used to
    print as ``[model: ...]`` and leave ``report.proxies`` empty -- a
    concession made invisible by the mechanism meant to show it."""
    from trailrunner.orchestration.orchestrator import Orchestrator

    chain = ResolutionChain([ModelProvider(Glossary()), TierOnlyOffer()])
    report = Orchestrator(chain).calculate(DEMAND)
    assert len(report.proxies) == 1
    assert "[mystery]" in report.tree()
    assert "[model" not in report.tree()


def test_an_offer_whose_dict_contradicts_its_tier_is_refused():
    """Two sources of truth disagreeing is a provider bug, not a precedence
    question, so neither one silently wins."""
    with pytest.raises(ValueError, match="cannot be two things"):
        Offer(model=Boiler(), demand=DEMAND, tier="background",
              resolution={"tier": "model"})


def test_a_model_tier_resolution_speaks_the_shared_vocabulary():
    resolution = ModelProvider(Glossary([Boiler()])).offer(DEMAND).resolution
    assert resolution["tier"] == "model"
    assert resolution["model"] == "Boiler"
    assert resolution["asked"] == f"{HEAT} @CH/2030"
    assert resolution["answered"] == resolution["asked"]


def test_no_model_found_is_reachable_with_a_generalising_tier_in_the_chain():
    """The chain the docs recommend, asked for a product nothing models and
    nothing can relax: tier 1 has no near miss to report, tier 2 has no
    candidate to try, tier 3 never explains. That is ``no_model_found``, and
    for a while it was unreachable -- tier 2 answered "generalisation budget
    spent" for every demand, which was false twice over."""
    from trailrunner.resolution import GeneralisingProvider

    glossary = Glossary([Boiler()])
    chain = ResolutionChain([
        ModelProvider(glossary),
        GeneralisingProvider(ModelProvider(glossary)),
    ])
    unmodelled = Demand(
        flow=Flow(iri="https://vocab.sentier.dev/products/unobtainium"),
        amount=1.0,
        unit="kg",
    )
    assert chain.offer(unmodelled) is None
    reason, _detail = chain.explain(unmodelled)
    assert reason == "no_model_found"
