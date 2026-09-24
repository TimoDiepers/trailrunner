import pytest

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Flow
from trailrunner.models.natural_gas import (
    CO2_FOSSIL,
    NATURAL_GAS,
    NATURAL_GAS_IN_GROUND,
    NaturalGasExtraction,
    NaturalGasSupply,
)
from trailrunner.models.natural_gas_pipeline_transport import (
    NATURAL_GAS_AT_PRODUCTION,
    TRANSPORT,
)
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet
from trailrunner.core.units import KG, M3, MJ

SUPPLY_ROWS = [
    {"location": "DK", "time": 2020, "origin": "NO", "transport_distance_km": 1000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
    {"location": "DK", "time": 2050, "origin": "NO", "transport_distance_km": 1000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
    {"location": "RER", "time": 2020, "origin": "RU", "transport_distance_km": 4000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
    {"location": "RER", "time": 2050, "origin": "RU", "transport_distance_km": 4000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
]
EXTRACTION_ROWS = [
    {"location": "NO", "time": 2020, "co2_kg_per_nm3": 0.075, "extracted_nm3_per_nm3": 1.02},
    {"location": "NO", "time": 2050, "co2_kg_per_nm3": 0.055, "extracted_nm3_per_nm3": 1.02},
]


def _fields(row, units=None):
    units = units or {}
    return [
        {
            "name": name,
            "type": "string" if isinstance(value, str) else "number",
            "unit": units.get(name),
        }
        for name, value in row.items()
    ]


@pytest.fixture
def supply(tmp_path):
    path = write_parameter_parquet(
        tmp_path / "supply.parquet", SUPPLY_ROWS, _fields(SUPPLY_ROWS[0])
    )
    return NaturalGasSupply(params=ParameterSet.from_parquet(path))


@pytest.fixture
def extraction(tmp_path):
    path = write_parameter_parquet(
        tmp_path / "extraction.parquet",
        EXTRACTION_ROWS,
        _fields(EXTRACTION_ROWS[0], units={"co2_kg_per_nm3": KG}),
    )
    return NaturalGasExtraction(params=ParameterSet.from_parquet(path))


def gas(location="DK", amount=2475.0, unit=MJ, time=2030):
    return Demand(
        flow=Flow(iri=NATURAL_GAS, location=location, time=time),
        amount=amount,
        unit=unit,
    )


def wellhead(location="NO", amount=68.75, unit=M3, time=2030):
    return Demand(
        flow=Flow(iri=NATURAL_GAS_AT_PRODUCTION, location=location, time=time),
        amount=amount,
        unit=unit,
    )


def test_supply_converts_energy_to_wellhead_volume(supply):
    result = supply.apply(gas())
    volume = [d for d in result.technosphere if d.flow.iri == NATURAL_GAS_AT_PRODUCTION][0]
    assert volume.amount == pytest.approx(2475.0 / 36.0)
    assert volume.unit == M3


def test_supply_converts_volume_to_tonne_kilometres(supply):
    result = supply.apply(gas())
    transport = [d for d in result.technosphere if d.flow.iri == TRANSPORT][0]
    # 68.75 Nm3 * 0.735 kg/Nm3 = 50.53 kg = 0.05053 t, over 1000 km.
    assert transport.amount == pytest.approx(2475.0 / 36.0 * 0.735 / 1000 * 1000.0)
    assert transport.unit == "tkm"


def test_supply_places_both_demands_at_the_origin(supply):
    result = supply.apply(gas())
    assert {d.flow.location for d in result.technosphere} == {"NO"}
    assert result.provenance["origin"] == "NO"


def test_a_further_origin_means_more_transport_for_the_same_energy(supply):
    danish = supply.apply(gas(location="DK"))
    european = supply.apply(gas(location="RER"))
    assert european.provenance["origin"] == "RU"
    assert european.provenance["transport_tkm"] == pytest.approx(
        4 * danish.provenance["transport_tkm"]
    )


def test_supply_emits_nothing_itself(supply):
    assert supply.apply(gas()).biosphere == []


def test_supply_rejects_a_unit_its_energy_content_cannot_read(supply):
    with pytest.raises(ValidationError, match="MJ/Nm3"):
        supply.apply(gas(unit=KG))


def test_extraction_scales_both_flows_with_the_volume(extraction):
    result = extraction.apply(wellhead(amount=100.0, time=2020))
    co2 = [e for e in result.biosphere if e.flow.iri == CO2_FOSSIL][0]
    resource = [e for e in result.biosphere if e.flow.iri == NATURAL_GAS_IN_GROUND][0]
    assert co2.amount == pytest.approx(7.5)
    assert co2.unit == KG
    assert resource.amount == pytest.approx(102.0)
    assert resource.unit == M3


def test_extraction_takes_more_out_of_the_ground_than_it_delivers(extraction):
    result = extraction.apply(wellhead(amount=1.0, time=2020))
    resource = [e for e in result.biosphere if e.flow.iri == NATURAL_GAS_IN_GROUND][0]
    assert resource.amount > result.production[0].amount


def test_extraction_is_a_leaf(extraction):
    assert extraction.apply(wellhead(time=2020)).technosphere == []


def test_extraction_rejects_a_unit_its_factors_cannot_read(extraction):
    with pytest.raises(ValidationError, match="m3"):
        extraction.apply(wellhead(unit=KG, time=2020))


def test_the_two_models_chain_through_the_glossary(supply, extraction):
    glossary = Glossary([supply, extraction])
    assert glossary.resolve(gas().flow) is supply
    volume = [
        d for d in supply.apply(gas()).technosphere
        if d.flow.iri == NATURAL_GAS_AT_PRODUCTION
    ][0]
    assert glossary.resolve(volume.flow) is extraction
