import pytest

from trailrunner.core.flow import Demand, Flow, Property
from trailrunner.models.cement import (
    CEMENT,
    CO2_FOSSIL,
    ELECTRICITY,
    LIMESTONE,
    NATURAL_GAS,
    LIME,
    CementPlant,
    MeteredCementPlant,
    moisture_penalty,
)
from trailrunner.orchestration.glossary import Glossary
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet
from trailrunner.core.units import DEG_C, KG, KWH, MJ, PA, UNITLESS
from trailrunner.core.time import GYEAR, in_year

HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


def test_moisture_penalty_at_reference_conditions_is_exactly_one():
    assert moisture_penalty(0.04, 10.0) == 1.0


def test_moisture_penalty_rises_with_wetter_feed():
    # Eight percent moisture against a four percent reference: twice the water
    # to evaporate before anything calcines.
    assert moisture_penalty(0.08, 10.0) == pytest.approx(1.08)


def test_moisture_penalty_rises_with_colder_feed():
    assert moisture_penalty(0.04, 0.0) == pytest.approx(1.04)


def test_moisture_penalty_falls_for_dry_warm_feed():
    assert moisture_penalty(0.02, 20.0) == pytest.approx(0.92)


def test_moisture_penalty_is_linear_in_both_terms():
    combined = moisture_penalty(0.08, 0.0)
    assert combined == pytest.approx(1.08 + 0.04)


@pytest.fixture
def cement_params(tmp_path):
    path = tmp_path / "cement.parquet"
    rows = [
        {"location": "CH", "time": "2030", "clinker_factor": 0.75, "fuel_demand": 3.3,
         "lime_demand": 0.010, "electricity_demand": 0.10,
         "moisture": 0.04, "temperature": 10.0},
        {"location": "RER", "time": "2030", "clinker_factor": 0.80, "fuel_demand": 3.5,
         "lime_demand": 0.012, "electricity_demand": 0.11,
         "moisture": 0.06, "temperature": 9.0},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "string", "time_standard": GYEAR, "iri": None},
        {"name": "clinker_factor", "type": "number", "unit": UNITLESS, "iri": None},
        {"name": "fuel_demand", "type": "number", "unit": MJ, "iri": None},
        {"name": "lime_demand", "type": "number", "unit": KG, "iri": None},
        {"name": "electricity_demand", "type": "number", "unit": KWH, "iri": None},
        {"name": "moisture", "type": "number", "unit": UNITLESS, "iri": None},
        {"name": "temperature", "type": "number", "unit": DEG_C, "iri": None},
    ]
    write_parameter_parquet(path, rows, fields)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def cement_demand(location="CH", time="2030", time_standard=GYEAR, amount=1000.0):
    return Demand(
        flow=Flow(iri=CEMENT, location=location, time=time, time_standard=time_standard), amount=amount, unit=KG
    )


def test_cement_plant_produces_exactly_what_was_demanded(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert result.production[0].flow.iri == CEMENT
    assert result.production[0].amount == 1000.0
    assert result.production[0].unit == KG


def test_cement_plant_demands_limestone_gas_steam_and_electricity(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert set(by_iri) == {LIMESTONE, NATURAL_GAS, LIME, ELECTRICITY}
    assert by_iri[LIMESTONE].unit == KG
    assert by_iri[NATURAL_GAS].unit == MJ
    assert by_iri[LIME].unit == KG
    assert by_iri[ELECTRICITY].unit == KWH
    for child in result.technosphere:
        assert child.flow.location == "CH"
        assert child.flow.time == "2030"


def test_burner_pressure_goes_on_the_gas_demand_and_nothing_else(cement_params):
    result = CementPlant(params=cement_params, burner_pressure=4e5).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert by_iri[NATURAL_GAS].flow.context == (Property("pressure", 4e5, PA),)
    assert all(d.flow.context == () for iri, d in by_iri.items() if iri != NATURAL_GAS)


def test_without_burner_pressure_the_gas_demand_names_none(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert all(d.flow.context == () for d in result.technosphere)


def test_clinker_factor_scales_the_limestone_and_the_fuel(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    # 1000 kg cement at a clinker factor of 0.75 is 750 kg of clinker.
    assert by_iri[LIMESTONE].amount == pytest.approx(1125.0)  # 1.5 kg per kg clinker
    assert by_iri[NATURAL_GAS].amount == pytest.approx(2475.0)  # 3.3 MJ per kg clinker


def test_lime_and_electricity_scale_with_the_cement_not_the_clinker(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert by_iri[LIME].amount == pytest.approx(10.0)
    assert by_iri[ELECTRICITY].amount == pytest.approx(100.0)


def test_calcination_and_combustion_are_two_separate_biosphere_exchanges(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert len(result.biosphere) == 2
    assert {e.flow.iri for e in result.biosphere} == {CO2_FOSSIL}
    amounts = sorted(e.amount for e in result.biosphere)
    # Combustion of 2475 MJ of gas, then calcination of 750 kg of clinker.
    assert amounts[0] == pytest.approx(138.6)
    assert amounts[1] == pytest.approx(397.5)
    for exchange in result.biosphere:
        assert exchange.unit == KG
        assert exchange.amount > 0


def test_combustion_co2_matches_the_gas_the_model_just_demanded(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    gas = [d for d in result.technosphere if d.flow.iri == NATURAL_GAS][0]
    combustion = min(e.amount for e in result.biosphere)
    assert combustion == pytest.approx(gas.amount * 0.056)


def test_wetter_feed_raises_kiln_fuel_but_not_the_recipe_quantities(cement_params):
    plant = CementPlant(params=cement_params)
    wet = {
        d.flow.iri: d.amount
        for d in plant.apply(cement_demand(location="RER")).technosphere
    }
    # RER's row is wetter and colder, so its penalty exceeds one.
    assert wet[NATURAL_GAS] / (0.80 * 1000.0 * 3.5) > 1.0
    # Lime and electricity are recipe quantities: the penalty must not touch
    # them, or a wet quarry would silently change the cement's composition.
    assert wet[LIME] == pytest.approx(1000.0 * 0.012)
    assert wet[ELECTRICITY] == pytest.approx(1000.0 * 0.11)


def test_cement_plant_records_its_parameter_provenance(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert result.provenance["location_used"] == "CH"
    assert result.provenance["time_used"] == "2030"
    assert result.provenance["source"] == "modelled"


def test_cement_plant_answers_the_full_demanded_amount_without_rescaling(cement_params):
    plant = CementPlant(params=cement_params)
    one = plant.apply(cement_demand(amount=1.0))
    thousand = plant.apply(cement_demand(amount=1000.0))
    one_gas = [d for d in one.technosphere if d.flow.iri == NATURAL_GAS][0]
    many_gas = [d for d in thousand.technosphere if d.flow.iri == NATURAL_GAS][0]
    assert many_gas.amount == pytest.approx(one_gas.amount * 1000.0)


@pytest.fixture
def metered_params(tmp_path):
    path = tmp_path / "cement_metered.parquet"
    rows = [
        {"location": "CH", "time": "2023", "metered_fuel": 2610.0, "metered_lime": 11.0,
         "metered_electricity": 108.0, "metered_co2": 562.0},
        {"location": "CH", "time": "2024", "metered_fuel": 2560.0, "metered_lime": 10.6,
         "metered_electricity": 106.0, "metered_co2": 551.0},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "string", "time_standard": GYEAR, "iri": None},
        {"name": "metered_fuel", "type": "number", "unit": MJ, "iri": None},
        {"name": "metered_lime", "type": "number", "unit": KG, "iri": None},
        {"name": "metered_electricity", "type": "number", "unit": KWH, "iri": None},
        {"name": "metered_co2", "type": "number", "unit": KG, "iri": None},
    ]
    write_parameter_parquet(path, rows, fields)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def test_metered_plant_returns_the_row_untouched(metered_params):
    result = MeteredCementPlant(params=metered_params).apply(cement_demand(**in_year(2023)))
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert by_iri[NATURAL_GAS].amount == pytest.approx(2610.0)
    assert by_iri[LIME].amount == pytest.approx(11.0)
    assert by_iri[ELECTRICITY].amount == pytest.approx(108.0)


def test_metered_plant_emits_one_merged_stack_figure(metered_params):
    result = MeteredCementPlant(params=metered_params).apply(cement_demand(**in_year(2023)))
    assert len(result.biosphere) == 1
    assert result.biosphere[0].flow.iri == CO2_FOSSIL
    assert result.biosphere[0].amount == pytest.approx(562.0)
    assert result.biosphere[0].unit == KG


def test_metered_plant_still_sends_its_purchased_energy_upstream(metered_params):
    # The emissions behind metered gas, steam and electricity happen off site.
    # A meter at the plant boundary says nothing about them, so they stay
    # technosphere demands and get answered by whoever supplies them.
    result = MeteredCementPlant(params=metered_params).apply(cement_demand(**in_year(2023)))
    assert {d.flow.iri for d in result.technosphere} == {
        NATURAL_GAS,
        LIME,
        ELECTRICITY,
    }


def test_metered_plant_scales_its_row_to_the_demanded_amount(metered_params):
    plant = MeteredCementPlant(params=metered_params)
    half = plant.apply(cement_demand(**in_year(2023), amount=500.0))
    assert half.biosphere[0].amount == pytest.approx(281.0)


def test_metered_plant_records_that_it_measured_rather_than_computed(metered_params):
    result = MeteredCementPlant(params=metered_params).apply(cement_demand(**in_year(2023)))
    assert result.provenance["source"] == "measured"


def test_glossary_picks_the_meter_for_a_past_year(cement_params, metered_params):
    glossary = Glossary(
        [CementPlant(params=cement_params), MeteredCementPlant(params=metered_params)]
    )
    chosen = glossary.resolve(Flow(iri=CEMENT, location="CH", **in_year(2023)))
    assert type(chosen) is MeteredCementPlant


def test_glossary_picks_the_model_for_a_future_year(cement_params, metered_params):
    glossary = Glossary(
        [CementPlant(params=cement_params), MeteredCementPlant(params=metered_params)]
    )
    chosen = glossary.resolve(Flow(iri=CEMENT, location="CH", **in_year(2030)))
    assert type(chosen) is CementPlant


def test_the_two_coverages_never_overlap(cement_params, metered_params):
    # Two models declaring one product IRI is only safe because their year
    # ranges are disjoint; an overlap would raise AmbiguousModelMatch on a
    # demand nobody thought to test.
    glossary = Glossary(
        [CementPlant(params=cement_params), MeteredCementPlant(params=metered_params)]
    )
    for year in range(2018, 2051):
        glossary.resolve(Flow(iri=CEMENT, location="CH", **in_year(year)))
