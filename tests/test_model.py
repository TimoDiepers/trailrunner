import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings

HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"
CAPTURED = "https://vocab.sentier.dev/products/co2-captured"


def test_result_defaults_to_empty_lists():
    result = Result(production=[Exchange(flow=Flow(iri=CAPTURED), amount=1.0, unit="kg")])
    assert result.technosphere == []
    assert result.biosphere == []
    assert result.provenance == {}


def test_result_default_lists_are_not_shared_between_instances():
    first = Result(production=[])
    second = Result(production=[])
    first.technosphere.append(Demand(flow=Flow(iri=HEAT), amount=1.0, unit="MJ"))
    assert second.technosphere == []


def test_settings_get_returns_default_for_missing_key():
    settings = Settings(values={"scenario": "base"})
    assert settings.get("scenario") == "base"
    assert settings.get("year") is None
    assert settings.get("year", 2030) == 2030


def test_settings_defaults_to_empty():
    assert Settings().get("anything") is None


def test_model_base_apply_raises_not_implemented():
    model = Model()
    with pytest.raises(NotImplementedError):
        model.apply(Demand(flow=Flow(iri=CAPTURED), amount=1.0, unit="kg"))


def test_model_subclass_declares_products_and_returns_a_result():
    class Trivial(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return Result(
                production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                biosphere=[Exchange(flow=Flow(iri=CO2), amount=0.1 * demand.amount, unit="kg")],
            )

    model = Trivial()
    result = model.apply(Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=10.0, unit="kg"))
    assert Trivial.produces == [CAPTURED]
    assert result.production[0].amount == 10.0
    assert result.biosphere[0].amount == pytest.approx(1.0)


def test_a_subclass_cannot_mutate_the_base_classs_product_list():
    """``produces`` is a class attribute; a mutable default is shared by every
    model that appends to it rather than assigning."""
    class Appender(Model):
        pass

    with pytest.raises(AttributeError):
        Appender.produces.append(CAPTURED)
    assert Model.produces == ()


def test_membership_still_works_on_the_base_default():
    assert HEAT not in Model.produces


def test_model_takes_settings_and_params_at_construction():
    class Trivial(Model):
        produces = [CAPTURED]

    settings = Settings(values={"scenario": "base"})
    model = Trivial(settings=settings, params="sentinel")
    assert model.settings is settings
    assert model.params == "sentinel"


def test_model_without_settings_gets_empty_settings():
    assert Model().settings.get("anything") is None
