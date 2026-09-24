import pytest

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Flow, Property
from trailrunner.models.natural_gas_pipeline_transport import (
    DISTANCE,
    FREIGHT_LORRY,
    HALON_1211,
    HFC_23,
    METHANE_FOSSIL,
    MINERAL_OIL_DISPOSAL,
    NATURAL_GAS_AT_PRODUCTION,
    NATURAL_GAS_BURNED_IN_GAS_TURBINE,
    PIPELINE_INFRASTRUCTURE,
    TRANSPORT,
    NaturalGasOffshorePipelineTransport,
    leaked_volume_nm3_per_tkm,
)
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet
from trailrunner.core.units import KILOMETRE, M3, METRE, MJ, TONNE
from trailrunner.core.time import GYEAR, in_year

# A high-tier and a low-tier row, values taken directly from the source report
# (Bussa et al. 2025, Tab. 4.4/4.6/4.7) -- see
# "dev/reverse-engineering of BAFU pipeline transport datasets/build_pipeline_trailpack.py".
HIGH = {
    "location": "DZ", "time": "2025", "tier": "high",
    "gas_density_kg_per_nm3": 0.735,
    "energy_rate_per_1000km": 0.022, "leakage_rate_per_1000km": 0.00204,
    "gas_turbine_mj_per_tkm": 0.795,
    "ch4_frac": 0.6629, "c2h6_frac": 0.0549, "c3h8_frac": 0.0124, "c4h10_frac": 0.0064,
    "co2_frac": 0.0229, "hg_frac": 1e-8, "nmvoc_frac": 0.0005,
    "infra_factor": 1.78e-9, "lorry_factor": 1.16e-7, "mineral_oil_disposal_factor": 1.16e-6,
    "halon1211_rate_kg_per_tkm": 2.24e-9, "hfc23_rate_kg_per_tkm": 8.95e-8,
}
LOW = HIGH | {
    "location": "NL", "tier": "low",
    "energy_rate_per_1000km": 0.009, "leakage_rate_per_1000km": 0.00019,
    "gas_turbine_mj_per_tkm": 0.32733,
}

FIELDS = [
    {
        "name": name,
        "type": "string" if isinstance(value, str) else "number",
        "unit": None,
        "time_standard": GYEAR if name == "time" else None,
    }
    for name, value in HIGH.items()
]


@pytest.fixture
def pipeline_params(tmp_path):
    path = tmp_path / "pipeline.parquet"
    write_parameter_parquet(path, [HIGH, LOW], FIELDS)
    return ParameterSet.from_parquet(path)


def demand(location="DZ", amount=1.0, km=1.0, unit=KILOMETRE):
    """1 t over 1 km is the old 1 tkm functional unit, number for number."""
    return Demand(
        flow=Flow(iri=TRANSPORT, location=location, **in_year(2025),
                  context=(Property(DISTANCE, km, unit),)),
        amount=amount,
        unit=TONNE,
    )


def test_tonnes_times_distance_is_the_old_tkm(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    one_tkm = model.apply(demand(amount=1.0, km=1.0))
    ten_t_100_km = model.apply(demand(amount=10.0, km=100.0))
    turbine = lambda r: next(e for e in r.technosphere if e.flow.iri == NATURAL_GAS_BURNED_IN_GAS_TURBINE)
    assert turbine(ten_t_100_km).amount == pytest.approx(1000 * turbine(one_tkm).amount)


def test_distance_in_metres_is_the_same_distance(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    in_km = model.apply(demand(km=2.0))
    in_m = model.apply(demand(km=2000.0, unit=METRE))
    assert [e.amount for e in in_m.biosphere] == pytest.approx([e.amount for e in in_km.biosphere])


def test_a_demand_without_a_distance_is_refused(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    bare = Demand(flow=Flow(iri=TRANSPORT, location="DZ", **in_year(2025)), amount=1.0, unit=TONNE)
    with pytest.raises(ValidationError, match="distance"):
        model.apply(bare)


def test_the_lorry_leg_travels_the_same_distance(pipeline_params):
    result = NaturalGasOffshorePipelineTransport(params=pipeline_params).apply(demand(amount=3.0, km=50.0))
    lorry = next(e for e in result.technosphere if e.flow.iri == FREIGHT_LORRY)
    assert lorry.unit == TONNE
    assert lorry.flow.get_context(DISTANCE) == Property(DISTANCE, 50.0, KILOMETRE)
    assert lorry.amount == pytest.approx(HIGH["lorry_factor"] * 3.0)


def test_leaked_volume_is_leakage_rate_over_density():
    assert leaked_volume_nm3_per_tkm(0.00204, 0.735) == pytest.approx(0.0027755, rel=1e-4)


def test_production_covers_the_demand(pipeline_params):
    result = NaturalGasOffshorePipelineTransport(params=pipeline_params).apply(demand(amount=3.0))
    assert result.production[0].flow.iri == TRANSPORT
    assert result.production[0].amount == 3.0
    assert result.production[0].unit == TONNE


def test_high_tier_leaks_more_than_low_tier(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    high = model.apply(demand(location="DZ"))
    low = model.apply(demand(location="NL"))
    high_ch4 = [e for e in high.biosphere if e.flow.iri == METHANE_FOSSIL][0]
    low_ch4 = [e for e in low.biosphere if e.flow.iri == METHANE_FOSSIL][0]
    assert high_ch4.amount == pytest.approx(0.0027755 * 0.6629, rel=1e-3)
    assert high_ch4.amount / low_ch4.amount == pytest.approx(0.00204 / 0.00019, rel=1e-3)


def test_gas_turbine_and_at_production_amounts_are_tier_constants(pipeline_params):
    result = NaturalGasOffshorePipelineTransport(params=pipeline_params).apply(demand(location="DZ", amount=2.0))
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert by_iri[NATURAL_GAS_BURNED_IN_GAS_TURBINE].amount == pytest.approx(0.795 * 2.0)
    assert by_iri[NATURAL_GAS_BURNED_IN_GAS_TURBINE].unit == MJ
    assert by_iri[NATURAL_GAS_AT_PRODUCTION].amount == pytest.approx(0.0027755 * 2.0, rel=1e-4)
    assert by_iri[NATURAL_GAS_AT_PRODUCTION].unit == M3


def test_location_invariant_exchanges_do_not_depend_on_tier(pipeline_params):
    model = NaturalGasOffshorePipelineTransport(params=pipeline_params)
    high = model.apply(demand(location="DZ"))
    low = model.apply(demand(location="NL"))
    for result in (high, low):
        by_iri = {d.flow.iri: d for d in result.technosphere}
        assert by_iri[PIPELINE_INFRASTRUCTURE].amount == pytest.approx(1.78e-9)
        assert by_iri[MINERAL_OIL_DISPOSAL].amount == pytest.approx(1.16e-6)
        biosphere_by_iri = {e.flow.iri: e for e in result.biosphere}
        assert biosphere_by_iri[HALON_1211].amount == pytest.approx(2.24e-9)
        assert biosphere_by_iri[HFC_23].amount == pytest.approx(8.95e-8)


def test_records_tier_in_provenance(pipeline_params):
    result = NaturalGasOffshorePipelineTransport(params=pipeline_params).apply(demand(location="DZ"))
    assert result.provenance["tier"] == "high"


def test_out_of_coverage_location_is_not_resolved(pipeline_params):
    glossary = Glossary([NaturalGasOffshorePipelineTransport(params=pipeline_params)])
    assert glossary.resolve(Flow(iri=TRANSPORT, location="CH", **in_year(2025))) is None


def test_in_coverage_location_is_resolved(pipeline_params):
    glossary = Glossary([NaturalGasOffshorePipelineTransport(params=pipeline_params)])
    assert glossary.resolve(Flow(iri=TRANSPORT, location="DZ", **in_year(2025))) is not None
