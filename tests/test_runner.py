import pytest

from trailrunner.core.errors import NoModelFound, ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.runner import Runner
from trailrunner.core.flow import Property
from trailrunner.core.units import KG, MJ, PA, TONNE, VOCAB, UnitCatalog
from trailrunner.core.time import in_year

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"

DEMAND = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=1000.0, unit=KG)


def make_runner(result: Result) -> Runner:
    class Stub(Model):
        produces = [CAPTURED]

        def apply(self, demand: Demand) -> Result:
            return result

    return Runner(Glossary([Stub()]))


def good_result() -> Result:
    return Result(
        production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit=KG)],
        technosphere=[Demand(flow=Flow(iri=HEAT, location="CH", **in_year(2030)), amount=5000.0, unit=MJ)],
        biosphere=[Exchange(flow=Flow(iri=CO2, location="CH", **in_year(2030)), amount=12.0, unit=KG)],
    )


def test_apply_resolves_the_model_and_returns_its_result():
    runner = make_runner(good_result())
    result = runner.apply(DEMAND)
    assert result.production[0].amount == 1000.0
    assert result.technosphere[0].unit == MJ


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
    runner = make_runner(Result(production=[Exchange(flow=Flow(iri=HEAT), amount=1.0, unit=MJ)]))
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert CAPTURED in str(excinfo.value)


def test_production_unit_must_match_the_demand_unit():
    runner = make_runner(
        Result(production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit=TONNE)])
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert TONNE in str(excinfo.value)


def test_production_amount_must_be_positive():
    runner = make_runner(Result(production=[Exchange(flow=DEMAND.flow, amount=0.0, unit=KG)]))
    with pytest.raises(ValidationError):
        runner.apply(DEMAND)


def test_production_below_the_demand_is_rejected():
    """The load-bearing invariant: nothing downstream rescales the result.

    ``apply`` receives the full demand amount, so a model that produces one
    kilogram against a demand for a thousand would silently yield an inventory
    a thousandfold too low.
    """
    runner = make_runner(
        Result(
            production=[Exchange(flow=DEMAND.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=CO2), amount=0.01, unit=KG)],
        )
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    message = str(excinfo.value)
    assert "Stub" in message
    assert "1.0" in message
    assert "1000.0" in message


def test_production_split_over_several_entries_is_summed():
    runner = make_runner(
        Result(
            production=[
                Exchange(flow=DEMAND.flow, amount=400.0, unit=KG),
                Exchange(flow=DEMAND.flow, amount=600.0, unit=KG),
            ]
        )
    )
    assert len(runner.apply(DEMAND).production) == 2


def test_production_within_relative_tolerance_of_the_demand_is_accepted():
    """Interpolated parameters do not round-trip to the last bit."""
    runner = make_runner(
        Result(production=[Exchange(flow=DEMAND.flow, amount=1000.0 * (1 - 1e-12), unit=KG)])
    )
    assert runner.apply(DEMAND).production[0].amount < 1000.0


def test_over_production_is_allowed():
    """A process may legitimately make more than was asked of it."""
    runner = make_runner(
        Result(production=[Exchange(flow=DEMAND.flow, amount=1500.0, unit=KG)])
    )
    assert runner.apply(DEMAND).production[0].amount == 1500.0


def test_a_missing_unit_is_reported_even_when_the_amount_is_also_wrong():
    """The unit rule must not be masked by the amount rule on the same exchange."""
    runner = make_runner(
        Result(production=[Exchange(flow=DEMAND.flow, amount=0.0, unit="")])
    )
    with pytest.raises(ValidationError) as excinfo:
        runner.apply(DEMAND)
    assert "without a unit" in str(excinfo.value)


def test_every_exchange_must_carry_a_unit():
    runner = make_runner(
        Result(
            production=[Exchange(flow=DEMAND.flow, amount=1000.0, unit=KG)],
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


def _result(unit=KG, context=()):
    flow = Flow(iri="https://example.org/p")
    return (
        Demand(flow=flow, amount=1.0, unit=KG),
        Result(
            production=[Exchange(flow=flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri="https://example.org/e", context=context), amount=1.0, unit=unit)],
        ),
    )


def test_a_free_text_unit_is_refused():
    demand, result = _result(unit="kg")
    with pytest.raises(ValidationError, match="not a unit of the vocabulary"):
        Runner.validate(demand, result)


def test_a_context_unit_is_checked_too():
    demand, result = _result(context=(Property("pressure", 4.0, "bar"),))
    with pytest.raises(ValidationError, match="pressure"):
        Runner.validate(demand, result)


def test_a_demand_in_free_text_is_refused():
    flow = Flow(iri="https://example.org/p")
    demand = Demand(flow=flow, amount=1.0, unit="tkm")
    result = Result(production=[Exchange(flow=flow, amount=1.0, unit="tkm")])
    with pytest.raises(ValidationError, match="tkm"):
        Runner.validate(demand, result)


def test_an_uncached_vocab_unit_offline_says_how_to_fix_it():
    # Review focus 3.
    demand, result = _result(unit=VOCAB + "LB")
    with pytest.raises(ValidationError, match="warm_unit_cache"):
        Runner.validate(demand, result, units=UnitCatalog())


def test_vocab_units_pass():
    demand, result = _result(context=(Property("pressure", 4e5, PA),))
    Runner.validate(demand, result)
