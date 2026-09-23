import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from trailrunner.core.errors import DuplicateBackgroundEntry
from trailrunner.core.flow import Demand, Flow
from trailrunner.core.settings import ALLOCATION_RULES, AttributionSettings, Settings
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution import BackgroundPack, BackgroundProvider
from trailrunner.resolution.chain import ResolutionChain

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


def _row(**overrides):
    row = {
        "product_iri": GAS, "product_unit": "kg", "location": "GLO",
        "dataset": "natural gas, at consumer", "source": "ede67f01",
        "basis": "unit_process", "flow_iri": CO2, "flow_unit": "kg", "amount": 0.4,
    }
    row.update(overrides)
    return row


def _pack(tmp_path, rows, name="pack.parquet"):
    path = tmp_path / name
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def test_two_datasets_for_one_product_and_location_are_refused(tmp_path):
    """The lookup key is (product, unit, location) and an index cannot hold
    two answers honestly: keeping whichever came last would put an
    unexplained number in the inventory and label it with the other
    dataset's name -- the same reasoning as ``AmbiguousModelMatch`` and
    ``DuplicateFactor``."""
    path = _pack(tmp_path, [
        _row(dataset="natural gas, at consumer", source="ede67f01"),
        _row(dataset="natural gas, at long-distance pipeline", source="a4273d5b", amount=0.9),
    ])
    with pytest.raises(DuplicateBackgroundEntry) as raised:
        BackgroundPack.from_parquet(path)
    message = str(raised.value)
    assert "natural gas, at consumer" in message
    assert "natural gas, at long-distance pipeline" in message
    assert GAS in message
    assert "GLO" in message


def test_the_same_dataset_at_two_locations_is_not_a_duplicate(tmp_path):
    path = _pack(tmp_path, [
        _row(location="RER"),
        _row(location="CH"),
    ])
    pack = BackgroundPack.from_parquet(path)
    demand = Demand(flow=Flow(iri=GAS, location="CH"), amount=1.0, unit="kg")
    assert pack.lookup(demand) is not None


def test_an_unknown_basis_is_refused_on_load(tmp_path):
    """``complete`` is ``basis == "cumulative"``, so an unrecognised word
    would quietly read as an incomplete borrow nobody declared, described by
    a term no reader can look up."""
    path = _pack(tmp_path, [_row(basis="estimated")])
    with pytest.raises(ValueError, match="not a known background basis"):
        BackgroundPack.from_parquet(path)


def test_every_background_resolution_speaks_the_shared_vocabulary(pack_file):
    """``tier``, ``model``, ``asked`` and ``answered`` mean here what they
    mean in tiers 1 and 2 -- tier 3 used to carry no ``model`` at all."""
    demand = Demand(flow=Flow(iri=GAS, location="GLO", time=2030), amount=1.0, unit="kg")
    resolution = provider(pack_file).offer(demand).resolution
    assert resolution["tier"] == "background"
    assert resolution["model"] == "BackgroundDataset"
    assert resolution["asked"] == f"{GAS} @GLO/2030"
    assert resolution["answered"] == resolution["asked"]


def test_a_borrowed_row_is_compatible_with_every_allocation_rule(pack_file):
    """Its monofunctionality is a fact, not a value judgement.

    A borrowed row has one product, so there is nothing to partition and the
    number is the same under all five rules. Declaring only ``none`` turned
    that into a refusal: any run under any other rule died at the first
    borrowed node, on the very grounds that make the borrow compatible.
    """
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    model = provider(pack_file).offer(demand).model
    assert model.supports == ALLOCATION_RULES


def test_a_borrowed_row_traverses_under_a_partitioning_rule(pack_file):
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=10.0, unit="kg")
    settings = Settings(attribution=AttributionSettings(allocation="economic"))
    chain = ResolutionChain([BackgroundProvider(BackgroundPack.from_parquet(pack_file))])
    report = Orchestrator(chain, settings=settings).calculate(demand)
    assert [node.model for node in report.nodes] == ["BackgroundDataset"]
    assert report.attribution[0]["share"] == 1.0
