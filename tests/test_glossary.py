import pytest

from trailrunner.core.errors import AmbiguousProducer
from trailrunner.core.flow import Flow
from trailrunner.core.model import Model
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.coverage import Coverage

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"


class Capturer(Model):
    produces = [CAPTURED]


class SwissCapturer(Model):
    produces = [CAPTURED]
    coverage = Coverage(locations=frozenset({"CH"}))


class GermanCapturer(Model):
    produces = [CAPTURED]
    coverage = Coverage(locations=frozenset({"DE"}))


def test_resolve_returns_none_when_nothing_produces_the_flow():
    glossary = Glossary([Capturer()])
    assert glossary.resolve(Flow(iri=HEAT)) is None


def test_resolve_returns_the_single_producer():
    model = Capturer()
    glossary = Glossary([model])
    assert glossary.resolve(Flow(iri=CAPTURED)) is model


def test_coverage_disambiguates_two_producers_of_the_same_product():
    swiss, german = SwissCapturer(), GermanCapturer()
    glossary = Glossary([swiss, german])
    assert glossary.resolve(Flow(iri=CAPTURED, location="CH")) is swiss
    assert glossary.resolve(Flow(iri=CAPTURED, location="DE")) is german


def test_out_of_coverage_flow_has_no_producer():
    glossary = Glossary([SwissCapturer()])
    assert glossary.resolve(Flow(iri=CAPTURED, location="FR")) is None


def test_two_matching_producers_raise_and_name_the_candidates():
    glossary = Glossary([Capturer(), Capturer()])
    with pytest.raises(AmbiguousProducer) as excinfo:
        glossary.resolve(Flow(iri=CAPTURED))
    assert "Capturer" in str(excinfo.value)
    assert CAPTURED in str(excinfo.value)


def test_register_adds_a_model_after_construction():
    glossary = Glossary()
    model = Capturer()
    glossary.register(model)
    assert glossary.resolve(Flow(iri=CAPTURED)) is model
