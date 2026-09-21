import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.models.dac import CO2_AIR, CO2_CAPTURED, ELECTRICITY, HEAT, DirectAirCapture
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet

HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


@pytest.fixture
def dac_params(tmp_path):
    path = tmp_path / "dac.parquet"
    rows = [
        {"location": "CH", "time": 2030, "heat_demand": 5.0, "electricity_demand": 0.4,
         "temperature": 10.0, "humidity": 0.70},
        {"location": "RER", "time": 2030, "heat_demand": 5.5, "electricity_demand": 0.45,
         "temperature": 12.0, "humidity": 0.65},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "integer", "unit": "year", "iri": None},
        {"name": "heat_demand", "type": "number", "unit": "MJ", "iri": "https://vocab.sentier.dev/parameters/heat-demand"},
        {"name": "electricity_demand", "type": "number", "unit": "kWh", "iri": "https://vocab.sentier.dev/parameters/electricity-demand"},
        {"name": "temperature", "type": "number", "unit": "degC", "iri": "https://vocab.sentier.dev/parameters/air-temperature"},
        {"name": "humidity", "type": "number", "unit": "dimensionless", "iri": "https://vocab.sentier.dev/parameters/relative-humidity"},
    ]
    write_parameter_parquet(path, rows, fields)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def demand(location="CH", time=2030, amount=1000.0):
    return Demand(flow=Flow(iri=CO2_CAPTURED, location=location, time=time), amount=amount, unit="kg")


def test_dac_produces_exactly_what_was_demanded(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    assert result.production[0].flow.iri == CO2_CAPTURED
    assert result.production[0].amount == 1000.0
    assert result.production[0].unit == "kg"


def test_dac_demands_heat_and_electricity_at_the_same_place_and_time(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert set(by_iri) == {HEAT, ELECTRICITY}
    assert by_iri[HEAT].unit == "MJ"
    assert by_iri[ELECTRICITY].unit == "kWh"
    for child in result.technosphere:
        assert child.flow.location == "CH"
        assert child.flow.time == 2030


def test_dac_takes_co2_from_air_as_a_negative_biosphere_flow(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand())
    uptake = [e for e in result.biosphere if e.flow.iri == CO2_AIR][0]
    assert uptake.amount == -1000.0
    assert uptake.unit == "kg"


def test_drier_colder_air_costs_more_heat(dac_params):
    """The whole reason models are code: this is not a fixed coefficient."""
    swiss = DirectAirCapture(params=dac_params).apply(demand(location="CH"))
    european = DirectAirCapture(params=dac_params).apply(demand(location="RER"))
    swiss_heat = [d for d in swiss.technosphere if d.flow.iri == HEAT][0]
    european_heat = [d for d in european.technosphere if d.flow.iri == HEAT][0]
    assert swiss_heat.amount != european_heat.amount


def test_dac_records_which_parameter_row_it_used(dac_params):
    result = DirectAirCapture(params=dac_params).apply(demand(location="FR"))
    assert result.provenance["location_used"] == "RER"
    assert result.provenance["location_fallback"] is True


def test_dac_is_out_of_coverage_before_2020(dac_params):
    glossary = Glossary([DirectAirCapture(params=dac_params)])
    assert glossary.resolve(Flow(iri=CO2_CAPTURED, location="CH", time=1990)) is None


def test_end_to_end_traversal_with_a_heat_model(dac_params):
    class Boiler(Model):
        produces = [HEAT]

        def apply(self, d: Demand) -> Result:
            return Result(
                production=[Exchange(flow=d.flow, amount=d.amount, unit=d.unit)],
                biosphere=[
                    Exchange(
                        flow=Flow(iri="https://vocab.sentier.dev/flows/co2-fossil",
                                  location=d.flow.location, time=d.flow.time),
                        amount=0.06 * d.amount,
                        unit="kg",
                    )
                ],
            )

    glossary = Glossary([DirectAirCapture(params=dac_params), Boiler()])
    report = Orchestrator(glossary).calculate(demand())

    assert len(report.nodes) == 2
    uptake = report.inventory[(Flow(iri=CO2_AIR, location="CH", time=2030), "kg")]
    assert uptake == -1000.0
    # electricity has no model: it is a cutoff leaf, not a silent zero
    assert [r.demand.flow.iri for r in report.unresolved] == [ELECTRICITY]
    assert report.truncated is False
