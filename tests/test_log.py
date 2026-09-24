import pyarrow as pa
import pyarrow.parquet as pq

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.core.units import KG, MJ

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


def a_demand(iri=CAPTURED, amount=1000.0, unit=KG) -> Demand:
    return Demand(flow=Flow(iri=iri, location="CH", time=2030), amount=amount, unit=unit)


def a_result(demand: Demand) -> Result:
    return Result(
        production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
        biosphere=[Exchange(flow=Flow(iri=CO2, location="CH", time=2030), amount=12.0, unit=KG)],
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
    log.unresolved(a_demand(iri=HEAT, amount=5.0, unit=MJ), reason="no_model_found", depth=1, parent=0)
    record = log.unresolved_records[0]
    assert record.reason == "no_model_found"
    assert record.demand.flow.iri == HEAT
    assert record.parent == 0


def test_warnings_are_collected():
    log = Log()
    log.warn("flow repeats on path", node=3)
    assert log.warnings == [("flow repeats on path", 3)]


def rows_of_kind(path, kind):
    return [row for row in pq.read_table(path).to_pylist() if row["kind"] == kind]


def test_to_parquet_writes_one_row_per_biosphere_exchange(tmp_path):
    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand), depth=0, parent=None)
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    rows = rows_of_kind(path, "biosphere")
    assert len(rows) == 1
    row = rows[0]
    assert row["node"] == 0
    assert row["flow_iri"] == CO2
    assert row["amount"] == 12.0
    assert row["unit"] == KG
    assert row["demand_iri"] == CAPTURED


def test_to_parquet_writes_the_provenance_of_every_node(tmp_path):
    """Two runs differing only in their parameter fallbacks must differ on disk."""
    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand))
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    provenance = {row["key"]: row["value"] for row in rows_of_kind(path, "provenance")}
    assert provenance == {"location_used": "RER", "location_fallback": "True"}


def test_to_parquet_keeps_a_node_that_emitted_nothing(tmp_path):
    log = Log()
    demand = a_demand()
    log.write(demand, Result(production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)]))
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    rows = rows_of_kind(path, "node")
    assert len(rows) == 1
    assert rows[0]["demand_iri"] == CAPTURED
    assert rows[0]["demand_amount"] == 1000.0


def test_to_parquet_writes_the_unresolved_leaves(tmp_path):
    """Two runs differing only in their cutoffs must differ on disk."""
    log = Log()
    log.unresolved(a_demand(iri=HEAT, amount=5.0, unit=MJ), reason="no_model_found", depth=1, parent=0)
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    rows = rows_of_kind(path, "unresolved")
    assert len(rows) == 1
    assert rows[0]["demand_iri"] == HEAT
    assert rows[0]["reason"] == "no_model_found"
    assert rows[0]["parent"] == 0
    assert rows[0]["depth"] == 1


def test_a_complete_run_round_trips(tmp_path):
    log = Log()
    demand = a_demand()
    node = log.write(demand, a_result(demand))
    log.unresolved(a_demand(iri=HEAT, amount=5.0, unit=MJ), reason="no_model_found", parent=node)
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    kinds = [row["kind"] for row in pq.read_table(path).to_pylist()]
    assert sorted(kinds) == ["biosphere", "provenance", "provenance", "unresolved"]


def test_to_parquet_on_an_empty_log_writes_an_empty_table(tmp_path):
    path = tmp_path / "log.parquet"
    Log().to_parquet(path)
    assert pq.read_table(path).num_rows == 0


def test_an_empty_log_table_concatenates_with_a_populated_one(tmp_path):
    """Both branches must declare the same schema, not null-typed columns."""
    empty_path = tmp_path / "empty.parquet"
    Log().to_parquet(empty_path)

    log = Log()
    demand = a_demand()
    log.write(demand, a_result(demand))
    populated_path = tmp_path / "populated.parquet"
    log.to_parquet(populated_path)

    combined = pa.concat_tables([pq.read_table(empty_path), pq.read_table(populated_path)])
    assert combined.num_rows == 3


def test_write_records_the_model_name():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand), model="DirectAirCapture")
    assert log.nodes[node_id].model == "DirectAirCapture"


def test_model_and_resolution_default_to_none_and_empty():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand))
    assert log.nodes[node_id].model is None
    assert log.nodes[node_id].resolution == {}


def test_write_records_how_the_demand_was_resolved():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        a_result(demand),
        model="GridElectricity",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    assert log.nodes[node_id].resolution["tier"] == "generalising"


def test_parquet_carries_the_model_and_one_row_per_resolution_key(tmp_path):
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        a_result(demand),
        model="GridElectricity",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    path = tmp_path / "log.parquet"
    log.to_parquet(path)

    rows = pq.read_table(path).to_pylist()
    resolution_rows = [row for row in rows if row["kind"] == "resolution"]
    assert {row["key"] for row in resolution_rows} == {"tier", "relaxation.0"}
    assert all(row["model"] == "GridElectricity" for row in rows)


def test_parquet_writes_one_resolution_row_per_relaxation(tmp_path):
    """A list value under 'relaxations' must not be stringified whole -- a
    reader should never have to parse a Python repr like "['a', 'b']" out of
    a single cell."""
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        a_result(demand),
        model="GridElectricity",
        resolution={
            "tier": "generalising",
            "relaxations": ["location: CH -> RER", "time: 2030 -> 2025"],
        },
    )
    path = tmp_path / "log.parquet"
    log.to_parquet(path)

    rows = pq.read_table(path).to_pylist()
    relaxation_rows = {
        row["key"]: row["value"] for row in rows if row["kind"] == "resolution" and row["key"].startswith("relaxation.")
    }
    assert relaxation_rows == {
        "relaxation.0": "location: CH -> RER",
        "relaxation.1": "time: 2030 -> 2025",
    }
    assert all("[" not in value and "]" not in value for value in relaxation_rows.values())


def test_the_attribution_record_is_flattened_not_a_python_repr(tmp_path):
    """The run is supposed to be reproducible from the committed parquet.

    Written whole, the nested attribution dict landed in one cell as a Python
    repr a reader has to parse back out -- exactly what the resolution branch
    flattens lists to avoid. One row per field, one per credited co-product.
    """
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={
                "location_used": "RER",
                "attribution": {
                    "allocation": "economic",
                    "property": "price",
                    "share": 0.25,
                    "co_products": [HEAT, CO2],
                },
            },
        ),
    )
    path = tmp_path / "log.parquet"
    log.to_parquet(path)

    attribution = {row["key"]: row["value"] for row in rows_of_kind(path, "attribution")}
    assert attribution == {
        "allocation": "economic",
        "property": "price",
        "share": "0.25",
        "co_product.0": HEAT,
        "co_product.1": CO2,
    }
    assert not any("{" in (row["value"] or "") for row in pq.read_table(path).to_pylist())


def test_the_attribution_record_does_not_double_as_the_models_provenance(tmp_path):
    """Provenance is what the model recorded. The model neither chose the
    allocation rule nor saw it, so it is written under its own kind."""
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={"location_used": "RER", "attribution": {"allocation": "none"}},
        ),
    )
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    assert {row["key"] for row in rows_of_kind(path, "provenance")} == {"location_used"}


def test_the_node_record_carries_the_attribution_beside_the_resolution():
    log = Log()
    demand = a_demand()
    node_id = log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            provenance={"attribution": {"allocation": "substitution", "share": 1.0}},
        ),
    )
    assert log.nodes[node_id].attribution == {"allocation": "substitution", "share": 1.0}


def test_a_node_with_no_attribution_carries_an_empty_one():
    log = Log()
    demand = a_demand()
    node_id = log.write(demand, a_result(demand))
    assert log.nodes[node_id].attribution == {}


def test_a_nested_record_is_flattened_key_by_key(tmp_path):
    """The guarantee is structural: no container reaches a cell, whether it is
    a list or a dict, in a resolution or in an attribution."""
    log = Log()
    demand = a_demand()
    log.write(
        demand,
        Result(production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)]),
        resolution={"tier": "background", "window": {"earliest": 2020, "latest": 2030}},
    )
    path = tmp_path / "log.parquet"
    log.to_parquet(path)
    resolution = {row["key"]: row["value"] for row in rows_of_kind(path, "resolution")}
    assert resolution == {
        "tier": "background",
        "window.earliest": "2020",
        "window.latest": "2030",
    }
