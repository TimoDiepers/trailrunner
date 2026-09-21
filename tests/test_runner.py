import pytest

from trailrunner.core.errors import NoModelFound, ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.runner import Runner

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

DEMAND = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")


def make_runner(result: Result) -> Runner:
    class Stub(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return result

    return Runner(Glossary([Stub()]))


def good_result() -> Result:
    return Result(
        production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit="kg")],
        technosphere=[Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=5000.0, unit="MJ")],
        biosphere=[Exchange(flow=Flow(iri=CO2, location="CH", time=2030), amount=12.0, unit="kg")],
    )


def test_apply_resolves_the_model_and_returns_its_result():
    runner = make_runner(good_result())
    result = runner.apply(DEMAND)
    assert result.production[0].amount == 1000.0
    assert result.technosphere[0].unit == "MJ"


def test_apply_raises_when_nothing_produces_the_demand():
    runner = Runner(Glossary())
    with pytest.raises(NoModelFound):
        runner.apply(DEMAND)


def test_apply_uses_a_model_passed_in_without_resolving():
    class Passed(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return good_result()

    runner = Runner(Glossary())
    assert runner.apply(DEMAND, model=Passed()).production[0].amount == 1000.0


def test_production_must_include_the_demanded_product():
    runner = make_runner(Result(production=[Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")]))
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert CAPTURED in str(excinfo.value)


def test_production_unit_must_match_the_demand_unit():
    runner = make_runner(
        Result(production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit="tonne")])
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert "tonne" in str(excinfo.value)


def test_production_amount_must_be_positive():
    runner = make_runner(Result(production=[Exchange(flow=DEMAND.flow, amount=0.0, unit="kg")]))
    with pytest.raises(ValidationError):
        runner.apply(DEMAND)


def test_every_exchange_must_carry_a_unit():
    runner = make_runner(
        Result(
            production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2), amount=12.0, unit="")],
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert CO2 in str(excinfo.value)


def test_a_model_returning_the_wrong_type_is_a_validation_error():
    class Broken(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand):
            return None

    runner = Runner(Glossary([Broken()]))
    with pytest.raises(ValidationError):
        runner.apply(DEMAND)
