import pytest

from trailrunner.core.flow import Demand, Exchange, Flow, Property

HEAT = "https://vocab.sentier.dev/products/heat"


def test_flow_is_hashable_and_value_equal():
    a = Flow(iri="https://vocab.sentier.dev/products/co2-captured", location="CH", time=2030)
    b = Flow(iri="https://vocab.sentier.dev/products/co2-captured", location="CH", time=2030)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_flow_location_and_time_are_optional():
    flow = Flow(iri="https://vocab.sentier.dev/products/heat")
    assert flow.location is None
    assert flow.time is None


def test_flow_is_usable_as_an_aggregation_key():
    flow = Flow(iri="co2", location="CH", time=2030)
    totals: dict[Flow, float] = {}
    totals[flow] = totals.get(flow, 0.0) + 2.0
    totals[Flow(iri="co2", location="CH", time=2030)] = totals.get(flow, 0.0) + 3.0
    assert totals == {flow: 5.0}


def test_exchange_carries_amount_and_unit():
    exchange = Exchange(flow=Flow(iri="heat"), amount=5.4, unit="MJ")
    assert exchange.amount == 5.4
    assert exchange.unit == "MJ"


def test_exchange_is_immutable():
    exchange = Exchange(flow=Flow(iri="heat"), amount=5.4, unit="MJ")
    with pytest.raises(Exception):
        exchange.amount = 9.0


def test_demand_is_an_alias_for_exchange():
    assert Demand is Exchange


def test_exchange_defaults_to_no_properties():
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")
    assert exchange.properties == ()


def test_exchange_carries_properties_and_stays_hashable():
    mass = Property(name="mass", value=2.5, unit="kg")
    price = Property(name="price", value=18.0, unit="EUR")
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass, price))
    # Hashability is the whole reason properties is a tuple: Flow is an
    # aggregation key and QueueItem is a frozen dataclass holding a Demand.
    assert hash(exchange) == hash(
        Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass, price))
    )


def test_get_property_finds_by_name():
    mass = Property(name="mass", value=2.5, unit="kg")
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass,))
    assert exchange.get_property("mass") is mass


def test_get_property_returns_none_when_absent():
    exchange = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")
    assert exchange.get_property("mass") is None


def test_properties_do_not_affect_the_flow_aggregation_key():
    mass = Property(name="mass", value=2.5, unit="kg")
    with_property = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ", properties=(mass,))
    without = Exchange(flow=Flow(iri=HEAT), amount=1.0, unit="MJ")
    assert with_property.flow == without.flow
