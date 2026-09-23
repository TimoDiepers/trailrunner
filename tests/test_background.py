import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from trailrunner.core.flow import Demand, Flow
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import BackgroundPack, BackgroundProvider

GAS = "https://vocab.sentier.dev/products/natural-gas"
STEEL = "https://vocab.sentier.dev/products/steel"
CLINKER = "https://vocab.sentier.dev/products/clinker"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"
CH4 = "https://vocab.sentier.dev/flows/ch4-fossil"


@pytest.fixture
def pack_file(tmp_path):
    path = tmp_path / "pack.parquet"
    rows = [
        # A unit-process row: only the direct exchanges of "natural gas, at
        # consumer" are known here, so its own upstream (extraction,
        # processing, pipeline) is missing from the inventory.
        {"product_iri": GAS, "product_unit": "kg", "location": "GLO",
         "dataset": "natural gas, at consumer", "source": "ede67f01-b29c-3537-8678-5c36efd1bad2",
         "basis": "unit_process", "flow_iri": CO2, "flow_unit": "kg", "amount": 0.4},
        {"product_iri": GAS, "product_unit": "kg", "location": "GLO",
         "dataset": "natural gas, at consumer", "source": "ede67f01-b29c-3537-8678-5c36efd1bad2",
         "basis": "unit_process", "flow_iri": CH4, "flow_unit": "kg", "amount": 0.01},
        {"product_iri": STEEL, "product_unit": "kg", "location": "RER",
         "dataset": "steel, low-alloyed", "source": "b9430f24-d0b9-3422-a5ad-f874acbbef18",
         "basis": "unit_process", "flow_iri": CO2, "flow_unit": "kg", "amount": 1.9},
        # A cumulative row: this one behaves as though it came from
        # ``lca.inventory`` -- the whole upstream is already in these
        # exchanges, so the subtree is honestly complete.
        {"product_iri": CLINKER, "product_unit": "kg", "location": "GLO",
         "dataset": "clinker, at plant (cumulative)", "source": "137152eb-d111-382a-9eae-3e592047418d",
         "basis": "cumulative", "flow_iri": CO2, "flow_unit": "kg", "amount": 0.85},
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def provider(path, hierarchy=None):
    return BackgroundProvider(BackgroundPack.from_parquet(path, hierarchy=hierarchy))


def test_a_pack_row_answers_the_demand(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.tier == "background"


def test_biosphere_scales_linearly_with_the_demand(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    result = offer.model.apply(demand)
    amounts = {exchange.flow.iri: exchange.amount for exchange in result.biosphere}
    assert amounts[CO2] == pytest.approx(4.0)
    assert amounts[CH4] == pytest.approx(0.1)


def test_the_result_produces_the_demanded_flow_and_terminates(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    result = provider(pack_file).offer(demand).model.apply(demand)
    assert result.production[0].flow == demand.flow
    assert result.production[0].amount == 10.0
    assert result.technosphere == []


def test_the_borrowed_subtree_says_it_is_matrix_lca(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.resolution["tier"] == "background"
    assert offer.resolution["kind"] == "linear_background"
    assert offer.resolution["dataset"] == "natural gas, at consumer"


def test_the_biosphere_flows_carry_the_demands_time(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO", time=2030), amount=1.0, unit="kg")
    result = provider(pack_file).offer(demand).model.apply(demand)
    assert all(exchange.flow.time == 2030 for exchange in result.biosphere)


def test_location_falls_back_up_the_hierarchy(pack_file):
    demand = Demand(flow=Flow(iri=STEEL, location="CH"), amount=1.0, unit="kg")
    offer = provider(pack_file, LocationHierarchy({"CH": "RER", "RER": "GLO"})).offer(demand)
    assert offer.resolution["location_used"] == "RER"


def test_a_product_not_in_the_pack_is_declined(pack_file):
    demand = Demand(flow=Flow(iri="https://vocab.sentier.dev/products/unobtainium"),
                    amount=1.0, unit="kg")
    assert provider(pack_file).offer(demand) is None


def test_a_different_unit_is_declined(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="tonne")
    assert provider(pack_file).offer(demand) is None


def test_the_background_tier_never_explains(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    assert provider(pack_file).explain(demand) is None


def test_a_unit_process_row_is_flagged_incomplete(pack_file):
    """A unit-process borrow has no matrix behind it: the biosphere shown is
    only the dataset's own direct exchanges, so its upstream is missing."""
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.resolution["basis"] == "unit_process"
    assert offer.resolution["complete"] is False


def test_a_cumulative_row_is_flagged_complete(pack_file):
    """A cumulative borrow is the whole upstream already, exactly what a
    Brightway-backed provider would hand back from ``lca.inventory``."""
    demand = Demand(flow=Flow(iri=CLINKER, location="GLO"), amount=1.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.resolution["basis"] == "cumulative"
    assert offer.resolution["complete"] is True


def test_the_source_dataset_is_traceable_in_the_resolution(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    offer = provider(pack_file).offer(demand)
    assert offer.resolution["source"] == "ede67f01-b29c-3537-8678-5c36efd1bad2"


def test_both_bases_terminate_with_no_technosphere_children(pack_file):
    """Complete or not, a borrowed subtree never pushes further demands: a
    unit-process row has no matrix to resolve its inputs with, and a
    cumulative row has already netted them into its biosphere."""
    unit_process_demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    cumulative_demand = Demand(flow=Flow(iri=CLINKER, location="GLO"), amount=1.0, unit="kg")
    provider_ = provider(pack_file)
    assert provider_.offer(unit_process_demand).model.apply(unit_process_demand).technosphere == []
    assert provider_.offer(cumulative_demand).model.apply(cumulative_demand).technosphere == []
