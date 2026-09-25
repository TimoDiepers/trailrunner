import pytest

from trailrunner.core.errors import UnknownUnit
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.units import KG, M3, MJ, TONNE, VOCAB
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.coverage import Coverage
from trailrunner.resolution.chain import ResolutionChain
from trailrunner.resolution.generalising import GeneralisingProvider, StaticTaxonomy
from trailrunner.resolution.models import ModelProvider

CEMENT = "https://example.org/cement"
BINDER = "https://example.org/binder"
CO2 = "https://example.org/co2"


class PerKilogram(Model):
    """Emits 0.5 kg CO2 per kg -- only right if it is really handed kilograms."""

    produces = [CEMENT]
    coverage = Coverage(units=frozenset({KG}))

    def apply(self, demand):
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            biosphere=[Exchange(flow=Flow(iri=CO2), amount=0.5 * demand.amount, unit=KG)],
        )


def test_a_tonne_demand_reaches_a_kilogram_model_as_kilograms():
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=2.0, unit=TONNE)
    )
    assert report.inventory[(Flow(iri=CO2), KG)] == 1000.0
    node = report.nodes[0]
    assert node.demand.unit == TONNE  # the log keeps what was asked
    assert node.resolution["tier"] == "model"
    assert node.resolution["conversion"] == "unit: t -> kg ×1000"
    assert report.proxies == {}  # a conversion concedes nothing


def test_the_tree_shows_the_conversion():
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=2.0, unit=TONNE)
    )
    assert "[model: PerKilogram; unit: t -> kg ×1000]" in report.tree()


def test_the_demanded_unit_is_used_as_is_when_declared():
    offer = ModelProvider(Glossary([PerKilogram()])).offer(
        Demand(flow=Flow(iri=CEMENT), amount=5.0, unit=KG)
    )
    assert offer.demand.amount == 5.0
    assert "conversion" not in offer.resolution


def test_a_model_without_declared_units_takes_any_unit():
    class Anything(PerKilogram):
        coverage = None

    offer = ModelProvider(Glossary([Anything()])).offer(
        Demand(flow=Flow(iri=CEMENT), amount=5.0, unit=MJ)
    )
    assert offer.demand.unit == MJ


def test_another_quantity_kind_is_a_unit_mismatch_not_a_crash():
    # Review focus 4.
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=1.0, unit=M3)
    )
    assert report.nodes == []
    [record] = report.unresolved
    assert record.reason == "unit_mismatch"
    assert "PerKilogram" in record.detail and "m3" in record.detail and "kg" in record.detail


def test_a_generalised_demand_is_converted_too():
    class BinderPerKg(PerKilogram):
        produces = [BINDER]

    chain = ResolutionChain(
        [
            ModelProvider(Glossary([BinderPerKg()])),
            GeneralisingProvider(
                ModelProvider(Glossary([BinderPerKg()])),
                taxonomy=StaticTaxonomy({CEMENT: [BINDER]}),
            ),
        ]
    )
    report = Orchestrator(chain).calculate(Demand(flow=Flow(iri=CEMENT), amount=1.0, unit=TONNE))
    node = report.nodes[0]
    assert node.resolution["tier"] == "generalising"
    assert node.resolution["conversion"] == "unit: t -> kg ×1000"
    assert report.inventory[(Flow(iri=CO2), KG)] == 500.0
    assert "unit: t -> kg ×1000" in report.tree()


def test_a_free_text_unit_is_refused_at_the_model_provider():
    # Review focus 2 (legacy free-text units ruling).
    with pytest.raises(UnknownUnit, match=r"'kg' is not a unit of the vocabulary"):
        ModelProvider(Glossary([PerKilogram()])).offer(
            Demand(flow=Flow(iri=CEMENT), amount=5.0, unit="kg")
        )


def test_an_uncached_vocab_unit_with_a_colliding_symbol_shows_full_iris():
    # Review focus 2: `known()` is None (an uncached vocabulary IRI), so
    # offer/explain keep working, but its fallback symbol happens to read
    # the same as the accepted unit's -- the detail must show full IRIs
    # instead, plus the warm-cache hint.
    demand_unit = VOCAB + "kg"  # not bundled; symbol falls back to "kg", same as KG's
    report = Orchestrator(Glossary([PerKilogram()])).calculate(
        Demand(flow=Flow(iri=CEMENT), amount=1.0, unit=demand_unit)
    )
    assert report.nodes == []
    [record] = report.unresolved
    assert record.reason == "unit_mismatch"
    assert KG in record.detail
    assert demand_unit in record.detail
    assert "warm_unit_cache" in record.detail
