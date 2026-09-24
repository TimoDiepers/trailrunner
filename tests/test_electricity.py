import pytest

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Flow
from trailrunner.models.dac import CO2_AIR, CO2_CAPTURED, HEAT, DirectAirCapture
from trailrunner.models.electricity import (
    CO2_FOSSIL,
    ELECTRICITY,
    ELECTRICITY_GAS,
    ELECTRICITY_HYDRO,
    ELECTRICITY_WIND,
    NATURAL_GAS,
    GasPower,
    GridElectricity,
)
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet
from trailrunner.resolution.models import ModelProvider

from .conftest import write_parameter_parquet
from trailrunner.core.units import DEG_C, KG, KWH, MJ, UNITLESS, YEAR

HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})

GRID_FIELDS = [
    {"name": "location", "type": "string", "unit": None, "iri": None},
    {"name": "time", "type": "integer", "unit": YEAR, "iri": None},
    {"name": "share_gas", "type": "number", "unit": UNITLESS, "iri": None},
    {"name": "share_wind", "type": "number", "unit": UNITLESS, "iri": None},
    {"name": "share_hydro", "type": "number", "unit": UNITLESS, "iri": None},
    {"name": "grid_loss", "type": "number", "unit": UNITLESS, "iri": None},
]

GAS_FIELDS = [
    {"name": "location", "type": "string", "unit": None, "iri": None},
    {"name": "time", "type": "integer", "unit": YEAR, "iri": None},
    {"name": "efficiency", "type": "number", "unit": UNITLESS, "iri": None},
    {"name": "co2_factor", "type": "number", "unit": KG, "iri": None},
]


@pytest.fixture
def grid_params(tmp_path):
    rows = [
        {"location": "CH", "time": 2020, "share_gas": 0.06, "share_wind": 0.04,
         "share_hydro": 0.90, "grid_loss": 0.07},
        {"location": "CH", "time": 2030, "share_gas": 0.02, "share_wind": 0.18,
         "share_hydro": 0.80, "grid_loss": 0.06},
        {"location": "RER", "time": 2020, "share_gas": 0.50, "share_wind": 0.30,
         "share_hydro": 0.20, "grid_loss": 0.08},
        {"location": "RER", "time": 2030, "share_gas": 0.25, "share_wind": 0.55,
         "share_hydro": 0.20, "grid_loss": 0.07},
        # Hydro only: the zero shares must not become zero-amount demands.
        {"location": "NO", "time": 2030, "share_gas": 0.0, "share_wind": 0.0,
         "share_hydro": 1.00, "grid_loss": 0.05},
        # Deliberately broken: the shares do not add up.
        {"location": "XX", "time": 2030, "share_gas": 0.10, "share_wind": 0.10,
         "share_hydro": 0.60, "grid_loss": 0.05},
    ]
    path = write_parameter_parquet(tmp_path / "grid.parquet", rows, GRID_FIELDS)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


@pytest.fixture
def gas_params(tmp_path):
    rows = [
        {"location": "RER", "time": 2020, "efficiency": 0.55, "co2_factor": 0.056},
        {"location": "RER", "time": 2030, "efficiency": 0.62, "co2_factor": 0.056},
    ]
    path = write_parameter_parquet(tmp_path / "gas.parquet", rows, GAS_FIELDS)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def kwh(iri=ELECTRICITY, location="CH", time=2030, amount=100.0):
    return Demand(flow=Flow(iri=iri, location=location, time=time), amount=amount, unit=KWH)


def by_iri(demands):
    return {demand.flow.iri: demand for demand in demands}


def test_grid_echoes_the_demanded_electricity(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh())
    assert result.production[0].flow.iri == ELECTRICITY
    assert result.production[0].amount == 100.0
    assert result.production[0].unit == KWH


def test_grid_splits_the_demand_into_one_demand_per_source(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh())
    assert set(by_iri(result.technosphere)) == {
        ELECTRICITY_GAS,
        ELECTRICITY_WIND,
        ELECTRICITY_HYDRO,
    }


def test_grid_generates_more_than_is_consumed_because_of_losses(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh())
    generated = sum(demand.amount for demand in result.technosphere)
    assert generated == pytest.approx(100.0 / (1 - 0.06))


def test_grid_sources_carry_the_shares_of_the_generated_amount(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh())
    generated = 100.0 / (1 - 0.06)
    sources = by_iri(result.technosphere)
    assert sources[ELECTRICITY_GAS].amount == pytest.approx(0.02 * generated)
    assert sources[ELECTRICITY_WIND].amount == pytest.approx(0.18 * generated)
    assert sources[ELECTRICITY_HYDRO].amount == pytest.approx(0.80 * generated)


def test_grid_sources_keep_the_place_time_and_unit_of_the_demand(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh(location="RER", time=2020))
    for demand in result.technosphere:
        assert demand.flow.location == "RER"
        assert demand.flow.time == 2020
        assert demand.unit == KWH


def test_grid_mix_differs_by_location(grid_params):
    grid = GridElectricity(params=grid_params)
    swiss = by_iri(grid.apply(kwh(location="CH")).technosphere)
    european = by_iri(grid.apply(kwh(location="RER")).technosphere)
    assert european[ELECTRICITY_GAS].amount > swiss[ELECTRICITY_GAS].amount


def test_grid_mix_decarbonizes_over_time(grid_params):
    grid = GridElectricity(params=grid_params)
    early = by_iri(grid.apply(kwh(location="RER", time=2020)).technosphere)
    late = by_iri(grid.apply(kwh(location="RER", time=2030)).technosphere)
    assert late[ELECTRICITY_GAS].amount < early[ELECTRICITY_GAS].amount


def test_grid_interpolates_the_mix_between_two_years(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh(location="RER", time=2025))
    generated = 100.0 / (1 - 0.075)
    assert by_iri(result.technosphere)[ELECTRICITY_GAS].amount == pytest.approx(
        0.375 * generated
    )


def test_grid_falls_back_to_the_parent_location(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh(location="FR"))
    assert result.provenance["location_used"] == "RER"
    assert result.provenance["location_fallback"] is True


def test_grid_omits_a_source_with_a_zero_share(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh(location="NO"))
    assert set(by_iri(result.technosphere)) == {ELECTRICITY_HYDRO}


def test_grid_rejects_shares_that_do_not_add_up(grid_params):
    with pytest.raises(ValidationError) as raised:
        GridElectricity(params=grid_params).apply(kwh(location="XX"))
    message = str(raised.value)
    assert "0.8" in message
    assert "'XX'" in message
    assert "2030" in message


def test_grid_records_the_mix_it_used_in_its_provenance(grid_params):
    result = GridElectricity(params=grid_params).apply(kwh())
    assert result.provenance["shares"] == {
        ELECTRICITY_GAS: pytest.approx(0.02),
        ELECTRICITY_WIND: pytest.approx(0.18),
        ELECTRICITY_HYDRO: pytest.approx(0.80),
    }
    assert result.provenance["grid_loss"] == pytest.approx(0.06)
    assert result.provenance["time_used"] == 2030


def test_gas_echoes_the_demanded_electricity(gas_params):
    result = GasPower(params=gas_params).apply(kwh(iri=ELECTRICITY_GAS))
    assert result.production[0].flow.iri == ELECTRICITY_GAS
    assert result.production[0].amount == 100.0


def test_gas_burns_fuel_at_the_row_efficiency(gas_params):
    result = GasPower(params=gas_params).apply(kwh(iri=ELECTRICITY_GAS))
    fuel = by_iri(result.technosphere)[NATURAL_GAS]
    assert fuel.amount == pytest.approx(100.0 * 3.6 / 0.62)
    assert fuel.unit == MJ


def test_gas_emits_co2_in_proportion_to_the_fuel_it_burned(gas_params):
    result = GasPower(params=gas_params).apply(kwh(iri=ELECTRICITY_GAS))
    emission = [e for e in result.biosphere if e.flow.iri == CO2_FOSSIL][0]
    assert emission.amount == pytest.approx(100.0 * 3.6 / 0.62 * 0.056)
    assert emission.unit == KG


def test_gas_gets_more_efficient_over_time(gas_params):
    plant = GasPower(params=gas_params)
    early = plant.apply(kwh(iri=ELECTRICITY_GAS, location="RER", time=2020))
    late = plant.apply(kwh(iri=ELECTRICITY_GAS, location="RER", time=2030))
    assert late.biosphere[0].amount < early.biosphere[0].amount


def test_gas_refuses_a_mass_demand_as_a_unit_mismatch(gas_params):
    demand = Demand(
        flow=Flow(iri=ELECTRICITY_GAS, location="CH", time=2030), amount=100.0, unit=KG
    )
    provider = ModelProvider(Glossary([GasPower(params=gas_params)]))
    assert provider.offer(demand) is None
    assert provider.explain(demand)[0] == "unit_mismatch"


def test_gas_is_handed_kwh_for_an_mj_demand(gas_params):
    demand = Demand(
        flow=Flow(iri=ELECTRICITY_GAS, location="CH", time=2030), amount=3.6, unit=MJ
    )
    offer = ModelProvider(Glossary([GasPower(params=gas_params)])).offer(demand)
    assert offer.demand.unit == KWH
    assert offer.demand.amount == pytest.approx(1.0)


# --- The traversal ---------------------------------------------------------
#
# With a model behind the DAC's electricity demand, the chain is three levels
# deep: captured CO2 -> electricity -> gas electricity -> natural gas. These
# check that the Orchestrator and the Queue carry it without any change of
# their own, and that what they report about it is honest.

DAC_FIELDS = [
    {"name": "location", "type": "string", "unit": None, "iri": None},
    {"name": "time", "type": "integer", "unit": YEAR, "iri": None},
    {"name": "heat_demand", "type": "number", "unit": MJ, "iri": None},
    {"name": "electricity_demand", "type": "number", "unit": KWH, "iri": None},
    {"name": "temperature", "type": "number", "unit": DEG_C, "iri": None},
    {"name": "humidity", "type": "number", "unit": UNITLESS, "iri": None},
]


@pytest.fixture
def chain(tmp_path, grid_params, gas_params):
    """DAC, grid and gas plant registered together, plus the root demand."""
    rows = [
        {"location": "CH", "time": 2030, "heat_demand": 5.0, "electricity_demand": 0.4,
         "temperature": 10.0, "humidity": 0.70},
        {"location": "RER", "time": 2030, "heat_demand": 5.5, "electricity_demand": 0.45,
         "temperature": 12.0, "humidity": 0.65},
    ]
    path = write_parameter_parquet(tmp_path / "dac.parquet", rows, DAC_FIELDS)
    dac_params = ParameterSet.from_parquet(path, hierarchy=HIERARCHY)
    glossary = Glossary(
        [
            DirectAirCapture(params=dac_params),
            GridElectricity(params=grid_params),
            GasPower(params=gas_params),
        ]
    )
    demand = Demand(
        flow=Flow(iri=CO2_CAPTURED, location="CH", time=2030), amount=1000.0, unit=KG
    )
    return glossary, demand


def iris_of(records):
    return [record.demand.flow.iri for record in records]


def test_the_electricity_demand_becomes_a_node_instead_of_a_cutoff(chain):
    glossary, demand = chain
    report = Orchestrator(glossary).calculate(demand)
    assert ELECTRICITY in iris_of(report.nodes)
    assert ELECTRICITY not in iris_of(report.unresolved)


def test_the_chain_reaches_natural_gas_three_levels_down(chain):
    glossary, demand = chain
    report = Orchestrator(glossary).calculate(demand)
    fuel = [record for record in report.unresolved if record.demand.flow.iri == NATURAL_GAS]
    assert len(fuel) == 1
    assert fuel[0].depth == 3


def test_every_node_is_linked_to_the_one_that_demanded_it(chain):
    glossary, demand = chain
    report = Orchestrator(glossary).calculate(demand)
    by_id = {node.id: node.demand.flow.iri for node in report.nodes}
    assert [(by_id[parent], by_id[child]) for parent, child in report.edges] == [
        (CO2_CAPTURED, ELECTRICITY),
        (ELECTRICITY, ELECTRICITY_GAS),
    ]


def test_wind_and_hydro_stay_unmodelled_cutoffs(chain):
    glossary, demand = chain
    report = Orchestrator(glossary).calculate(demand)
    reasons = {
        record.demand.flow.iri: record.reason
        for record in report.unresolved
    }
    assert reasons[ELECTRICITY_WIND] == "no_model_found"
    assert reasons[ELECTRICITY_HYDRO] == "no_model_found"
    assert reasons[HEAT] == "no_model_found"


def test_the_grid_mix_puts_fossil_co2_against_the_captured_co2(chain):
    glossary, demand = chain
    report = Orchestrator(glossary).calculate(demand)
    inventory = {(flow.iri, unit): amount for (flow, unit), amount in report.inventory.items()}
    assert inventory[(CO2_AIR, KG)] == -1000.0
    # 1000 kg captured needs 400 kWh; the 2030 Swiss grid is 2 % gas, so the
    # combustion CO2 that comes back is small but not nothing.
    assert 0 < inventory[(CO2_FOSSIL, KG)] < 10.0


def test_the_fossil_co2_follows_the_grid_mix_of_the_location(chain, grid_params):
    glossary, _ = chain
    swiss = Orchestrator(glossary).calculate(
        Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", time=2030), amount=1000.0, unit=KG)
    )
    european = Orchestrator(glossary).calculate(
        Demand(flow=Flow(iri=CO2_CAPTURED, location="RER", time=2030), amount=1000.0, unit=KG)
    )

    def fossil(report):
        return sum(
            amount for (flow, _), amount in report.inventory.items() if flow.iri == CO2_FOSSIL
        )

    assert fossil(european) > fossil(swiss)


def test_each_node_keeps_the_parameters_it_resolved(chain):
    glossary, demand = chain
    report = Orchestrator(glossary).calculate(demand)
    grid_node = [node for node in report.nodes if node.demand.flow.iri == ELECTRICITY][0]
    assert report.provenance[grid_node.id]["shares"][ELECTRICITY_GAS] == pytest.approx(0.02)
    # The gas plant has no Swiss row and had to borrow Europe's.
    gas_node = [node for node in report.nodes if node.demand.flow.iri == ELECTRICITY_GAS][0]
    assert report.provenance[gas_node.id]["location_used"] == "RER"


def test_the_depth_budget_truncates_the_longer_chain_cleanly(chain):
    glossary, demand = chain
    report = Orchestrator(glossary, max_depth=2).calculate(demand)
    assert report.truncated is True
    assert ELECTRICITY_GAS not in iris_of(report.nodes)
    cut = [r for r in report.unresolved if r.demand.flow.iri == ELECTRICITY_GAS][0]
    assert cut.reason == "max_depth"


def test_the_node_budget_drains_what_is_left_on_the_queue(chain):
    glossary, demand = chain
    report = Orchestrator(glossary, max_nodes=2).calculate(demand)
    assert report.truncated is True
    assert len(report.nodes) == 2
    assert "max_nodes" in {record.reason for record in report.unresolved}


def test_a_priority_queue_reorders_the_traversal(chain):
    """The Queue's priority seam, exercised on a tree deep enough to show it.

    Ranking by raw amount mixes MJ with kWh, which is exactly the reason no
    priority function ships by default — but it is enough to prove the order
    is the Queue's to decide.
    """
    glossary, demand = chain
    fifo = Orchestrator(glossary).calculate(demand)
    smallest_first = Orchestrator(
        glossary, priority=lambda d: d.amount
    ).calculate(demand)

    assert iris_of(fifo.unresolved)[0] == HEAT
    assert iris_of(smallest_first.unresolved)[0] == NATURAL_GAS


def test_the_order_of_traversal_does_not_change_the_inventory(chain):
    glossary, demand = chain
    fifo = Orchestrator(glossary).calculate(demand)
    smallest_first = Orchestrator(glossary, priority=lambda d: d.amount).calculate(demand)
    assert fifo.inventory == smallest_first.inventory
