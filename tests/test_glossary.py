import pytest

from trailrunner.core.errors import AmbiguousModelMatch
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


def test_resolve_returns_the_single_model():
    model = Capturer()
    glossary = Glossary([model])
    assert glossary.resolve(Flow(iri=CAPTURED)) is model


def test_coverage_disambiguates_two_models_of_the_same_product():
    swiss, german = SwissCapturer(), GermanCapturer()
    glossary = Glossary([swiss, german])
    assert glossary.resolve(Flow(iri=CAPTURED, location="CH")) is swiss
    assert glossary.resolve(Flow(iri=CAPTURED, location="DE")) is german


def test_out_of_coverage_flow_has_no_model_found():
    glossary = Glossary([SwissCapturer()])
    assert glossary.resolve(Flow(iri=CAPTURED, location="FR")) is None


def test_two_matching_models_raise_and_name_the_candidates():
    glossary = Glossary([Capturer(), Capturer()])
    with pytest.raises(AmbiguousModelMatch) as excinfo:
        glossary.resolve(Flow(iri=CAPTURED))
    assert "Capturer" in str(excinfo.value)
    assert CAPTURED in str(excinfo.value)


def test_declared_models_ignore_coverage():
    """Lets the caller tell "nobody models this" from "coverage filtered it out"."""
    swiss = SwissCapturer()
    glossary = Glossary([swiss])
    assert glossary.declared_models(Flow(iri=CAPTURED, location="FR")) == [swiss]
    assert glossary.declared_models(Flow(iri=HEAT)) == []


def test_declared_models_does_not_disturb_resolve():
    glossary = Glossary([Capturer(), Capturer()])
    assert len(glossary.declared_models(Flow(iri=CAPTURED))) == 2
    with pytest.raises(AmbiguousModelMatch):
        glossary.resolve(Flow(iri=CAPTURED))


def test_register_adds_a_model_after_construction():
    glossary = Glossary()
    model = Capturer()
    glossary.register(model)
    assert glossary.resolve(Flow(iri=CAPTURED)) is model


def test_resolve_drops_an_excluded_model():
    """``exclude`` is what keeps a substitution credit off the model that
    minted it: a process may not answer its own avoided burden."""
    model = Capturer()
    glossary = Glossary([model])
    assert glossary.resolve(Flow(iri=CAPTURED)) is model
    assert glossary.resolve(Flow(iri=CAPTURED), exclude=(model,)) is None


def test_exclusion_is_by_instance_not_by_class():
    """A CH plant and an FR plant of one class are different processes.

    Each remains a candidate for the other's credits, so excluding one must
    not take the other with it. Two instances also make the flow ambiguous
    until one of them is dropped, which is exactly what makes this readable:
    the exclusion is what leaves a single candidate.
    """
    first, second = Capturer(), Capturer()
    glossary = Glossary([first, second])
    with pytest.raises(AmbiguousModelMatch):
        glossary.resolve(Flow(iri=CAPTURED))
    assert glossary.resolve(Flow(iri=CAPTURED), exclude=(first,)) is second
    assert glossary.resolve(Flow(iri=CAPTURED), exclude=(second,)) is first


def test_declared_models_honours_the_same_exclusion():
    """So that a credit nobody else makes is explained as the cutoff it is,
    rather than as a coverage miss it is not."""
    model = Capturer()
    glossary = Glossary([model])
    assert glossary.declared_models(Flow(iri=CAPTURED)) == [model]
    assert glossary.declared_models(Flow(iri=CAPTURED), exclude=(model,)) == []
