"""The fleet table, and the construction inputs the DAC model builds from it."""

import pytest

from trailrunner.core.errors import ParameterNotFound
from trailrunner.core.flow import Demand, Flow
from trailrunner.models.dac import CO2_CAPTURED, DAC_PLANT, HEAT, DirectAirCapture
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.fleet import Fleet
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet

HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})

FLEET_FIELDS = [
    {"name": "plant", "type": "string", "unit": None, "iri": None},
    {"name": "location", "type": "string", "unit": None, "iri": None},
    {"name": "build_year", "type": "integer", "unit": "year", "iri": None},
    {"name": "capacity", "type": "number", "unit": "kg/year", "iri": None},
    {"name": "lifetime", "type": "number", "unit": "year", "iri": None},
]

DAC_FIELDS = [
    {"name": "location", "type": "string", "unit": None, "iri": None},
    {"name": "time", "type": "integer", "unit": "year", "iri": None},
    {"name": "heat_demand", "type": "number", "unit": "MJ", "iri": None},
    {"name": "electricity_demand", "type": "number", "unit": "kWh", "iri": None},
    {"name": "temperature", "type": "number", "unit": "degC", "iri": None},
    {"name": "humidity", "type": "number", "unit": "dimensionless", "iri": None},
]


@pytest.fixture
def fleet(tmp_path):
    rows = [
        # Retired before 2030: built 2005, twenty-year life.
        {"plant": "ch-0", "location": "CH", "build_year": 2005, "capacity": 5000.0, "lifetime": 20.0},
        {"plant": "ch-1", "location": "CH", "build_year": 2026, "capacity": 12000.0, "lifetime": 20.0},
        {"plant": "ch-2", "location": "CH", "build_year": 2029, "capacity": 40000.0, "lifetime": 20.0},
        # Not built yet in 2030.
        {"plant": "ch-3", "location": "CH", "build_year": 2035, "capacity": 9000.0, "lifetime": 20.0},
        {"plant": "rer-1", "location": "RER", "build_year": 2024, "capacity": 8000.0, "lifetime": 25.0},
    ]
    path = write_parameter_parquet(tmp_path / "fleet.parquet", rows, FLEET_FIELDS)
    return Fleet.from_parquet(path, hierarchy=HIERARCHY)


@pytest.fixture
def dac_params(tmp_path):
    rows = [
        {"location": "CH", "time": 2030, "heat_demand": 5.0, "electricity_demand": 0.4,
         "temperature": 10.0, "humidity": 0.70},
        {"location": "RER", "time": 2030, "heat_demand": 5.5, "electricity_demand": 0.45,
         "temperature": 12.0, "humidity": 0.65},
    ]
    path = write_parameter_parquet(tmp_path / "dac.parquet", rows, DAC_FIELDS)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def plants_of(selection):
    return {plant["plant"] for plant in selection.plants}


def test_fleet_keeps_only_the_plants_running_in_that_year(fleet):
    assert plants_of(fleet.operating(location="CH", time=2030)) == {"ch-1", "ch-2"}


def test_fleet_excludes_a_plant_that_is_not_built_yet(fleet):
    assert plants_of(fleet.operating(location="CH", time=2027)) == {"ch-1"}


def test_fleet_includes_a_plant_in_its_first_year(fleet):
    assert "ch-2" in plants_of(fleet.operating(location="CH", time=2029))


def test_fleet_retires_a_plant_at_the_end_of_its_lifetime(fleet):
    assert plants_of(fleet.operating(location="CH", time=2024)) == {"ch-0"}
    assert "ch-0" not in plants_of(fleet.operating(location="CH", time=2025))


def test_fleet_sums_the_capacity_of_what_is_running(fleet):
    assert fleet.operating(location="CH", time=2030).total_capacity == pytest.approx(52000.0)


def test_fleet_averages_the_build_year_by_capacity(fleet):
    selection = fleet.operating(location="CH", time=2030)
    assert selection.mean_build_year == pytest.approx(
        (2026 * 12000 + 2029 * 40000) / 52000
    )


def test_fleet_falls_back_to_the_parent_location(fleet):
    selection = fleet.operating(location="FR", time=2030)
    assert plants_of(selection) == {"rer-1"}
    assert selection.provenance["location_used"] == "RER"
    assert selection.provenance["location_fallback"] is True


def test_fleet_records_what_it_selected(fleet):
    provenance = fleet.operating(location="CH", time=2030).provenance
    assert provenance["plants"] == ["ch-1", "ch-2"]
    assert provenance["total_capacity"] == pytest.approx(52000.0)
    assert provenance["time_requested"] == 2030


def test_fleet_without_a_year_takes_every_plant_at_that_location(fleet):
    assert plants_of(fleet.operating(location="CH")) == {"ch-0", "ch-1", "ch-2", "ch-3"}


def test_fleet_widens_to_the_parent_when_the_local_fleet_has_a_gap(fleet):
    """2025 is between the Swiss plants: ch-0 has retired, ch-1 is not built.

    The hierarchy is the only widening a Fleet does. It will not interpolate a
    plant into existence, and it will not pool two levels: the answer is every
    plant at the first location that has one.
    """
    selection = fleet.operating(location="CH", time=2025)
    assert plants_of(selection) == {"rer-1"}
    assert selection.provenance["location_used"] == "RER"


def test_fleet_complains_when_nothing_is_running_anywhere(fleet):
    with pytest.raises(ParameterNotFound) as raised:
        fleet.operating(location="CH", time=2000)
    assert "'CH'" in str(raised.value)
    assert "2000" in str(raised.value)


def test_fleet_carries_the_units_of_its_columns(fleet):
    assert fleet.operating(location="CH", time=2030).unit_of("capacity") == "kg/year"


def demand(location="CH", time=2030, amount=1000.0):
    return Demand(
        flow=Flow(iri=CO2_CAPTURED, location=location, time=time), amount=amount, unit="kg"
    )


def construction(result):
    return [d for d in result.technosphere if d.flow.iri == DAC_PLANT]


def test_dac_without_a_fleet_demands_no_construction(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    assert construction(result) == []


def test_dac_demands_construction_of_every_operating_plant(dac_params, fleet):
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    assert len(construction(result)) == 2


def test_construction_is_demanded_in_the_year_the_plant_was_built(dac_params, fleet):
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    assert sorted(d.flow.time for d in construction(result)) == [2026, 2029]


def test_construction_stays_at_the_location_of_the_plant_that_was_built(dac_params, fleet):
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand(location="FR"))
    assert [d.flow.location for d in construction(result)] == ["RER"]


def test_construction_is_amortized_over_capacity_and_lifetime(dac_params, fleet):
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    by_year = {d.flow.time: d.amount for d in construction(result)}
    assert by_year[2026] == pytest.approx(1000.0 * 12000.0 / (52000.0 * 20.0))
    assert by_year[2029] == pytest.approx(1000.0 * 40000.0 / (52000.0 * 20.0))


def test_the_construction_demanded_is_the_fleet_share_of_a_lifetime(dac_params, fleet):
    """With one lifetime across the fleet, the total is demand / lifetime."""
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    assert sum(d.amount for d in construction(result)) == pytest.approx(1000.0 / 20.0)


def test_construction_is_demanded_in_the_capacity_unit(dac_params, fleet):
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    assert {d.unit for d in construction(result)} == {"kg/year"}


def test_a_bigger_demand_claims_a_bigger_share_of_the_same_fleet(dac_params, fleet):
    model = DirectAirCapture(params=dac_params, fleet=fleet)
    small = model.apply(demand(amount=1000.0))
    large = model.apply(demand(amount=5000.0))
    assert sum(d.amount for d in construction(large)) == pytest.approx(
        5 * sum(d.amount for d in construction(small))
    )


def test_dac_records_the_fleet_it_amortized_over(dac_params, fleet):
    result = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    assert result.provenance["share_of_fleet"] == pytest.approx(1000.0 / 52000.0)
    assert result.provenance["plants"] == ["ch-1", "ch-2"]
    assert result.provenance["mean_build_year"] == pytest.approx(
        (2026 * 12000 + 2029 * 40000) / 52000
    )


def test_the_heat_demand_is_unchanged_by_the_fleet(dac_params, fleet):
    """Construction is added to the answer; it does not rescale operation."""
    without = DirectAirCapture(params=dac_params).apply(demand())
    with_fleet = DirectAirCapture(params=dac_params, fleet=fleet).apply(demand())
    heat = [d.amount for d in without.technosphere if d.flow.iri == HEAT]
    assert [d.amount for d in with_fleet.technosphere if d.flow.iri == HEAT] == heat


def test_construction_reaches_the_report_as_two_cutoffs_in_two_years(dac_params, fleet):
    glossary = Glossary([DirectAirCapture(params=dac_params, fleet=fleet)])
    report = Orchestrator(glossary).calculate(demand())
    years = sorted(
        record.demand.flow.time
        for record in report.unresolved
        if record.demand.flow.iri == DAC_PLANT
    )
    assert years == [2026, 2029]
