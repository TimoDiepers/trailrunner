import pyarrow.parquet as pq

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


def a_demand(iri=CAPTURED, amount=1000.0, unit="kg") -> Demand:
    return Demand(flow=Flow(iri=iri, location="CH", time=2030), amount=amount, unit=unit)


def a_result(demand: Demand) -> Result:
    return Result(
        production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
        biosphere=[Exchange(flow=Flow(iri=CO2, location="CH", time=2030), amount=12.0, unit="kg")],
        provenance={"location_used": "RER", "location_fallback": True},
    )


def test_write_returns_increasing_node_ids():
    log = Log()
    demand = a_demand()
    assert log.write(demand, a_result(demand)) == 0
    assert log.write(demand, a_result(demand)) == 1


def test_written_node_keeps_demand_result_depth_and_parent():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand), depth=2, parent=0)
    node = log.nodes[node_id]
    assert node.demand is demand
    assert node.depth == 2
    assert node.parent == 0
    assert node.result.provenance["location_fallback"] is True


def test_write_records_an_edge_when_there_is_a_parent():
    log = Log()
    demand = a_demand()
    root = log.write(demand, a_result(demand))
    child = log.write(demand, a_result(demand), depth=1, parent=root)
    assert [(e.parent, e.child) for e in log.edges] == [(root, child)]


def test_root_node_creates_no_edge():
    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand))
    assert log.edges == []


def test_unresolved_demands_are_recorded_with_a_reason():
    log = Log()
    log.unresolved(a_demand(iri=HEAT, amount=5.0, unit="MJ"), reason="no_model_found", depth=1, parent=0)
    record = log.unresolved_records[0]
    assert record.reason == "no_model_found"
    assert record.demand.flow.iri == HEAT
    assert record.parent == 0


def test_warnings_are_collected():
    log = Log()
    log.warn("flow repeats on path", node=3)
    assert log.warnings == [("flow repeats on path", 3)]


def test_to_parquet_writes_one_row_per_biosphere_exchange(tmp_path):
    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand), depth=0, parent=None)
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    table = pq.read_table(path)
    assert table.num_rows == 1
    row = table.to_pylist()[0]
    assert row["node"] == 0
    assert row["flow_iri"] == CO2
    assert row["amount"] == 12.0
    assert row["unit"] == "kg"
    assert row["demand_iri"] == CAPTURED


def test_to_parquet_on_an_empty_log_writes_an_empty_table(tmp_path):
    path = tmp_path / "log.parquet"
    Log().to_parquet(path)
    assert pq.read_table(path).num_rows == 0
