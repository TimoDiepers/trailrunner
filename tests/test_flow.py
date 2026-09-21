import pytest

from trailrunner.core.flow import Demand, Exchange, Flow


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
