import pytest

from trailrunner.core.errors import ParameterNotFound
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import HEAT_DEMAND_IRI, write_parameter_parquet

# FR must be in the map: chain("FR") with only {"CH": "RER"} would be
# ["FR", "GLO"] and never reach the RER rows.
HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


def test_exact_match_returns_the_row_untouched(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)
    assert row["heat_demand"] == 5.0
    assert row.temperature == 10.0
    assert row.provenance["location_used"] == "CH"
    assert row.provenance["location_fallback"] is False
    assert row.provenance["time_interpolated"] is False


def test_units_and_iris_come_from_the_embedded_datapackage(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)
    assert row.unit_of("heat_demand") == "MJ"
    assert row.iri_of("heat_demand") == HEAT_DEMAND_IRI
    assert row.unit_of("location") is None


def test_location_falls_back_up_the_hierarchy_and_says_so(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="FR", time=2030)
    assert row["heat_demand"] == 5.5
    assert row.provenance["location_requested"] == "FR"
    assert row.provenance["location_used"] == "RER"
    assert row.provenance["location_fallback"] is True


def test_time_is_interpolated_between_bracketing_rows(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2025)
    assert row["heat_demand"] == pytest.approx(5.5)
    assert row["temperature"] == pytest.approx(9.5)
    assert row.provenance["time_interpolated"] is True
    assert row.provenance["time_bracket"] == (2020, 2030)


def test_interpolated_row_keeps_non_numeric_columns_from_the_lower_row(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2025)
    assert row["location"] == "CH"


def test_time_outside_the_data_range_is_not_extrapolated(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    with pytest.raises(ParameterNotFound):
        params.at(location="CH", time=2100)


def test_unknown_location_exhausts_the_hierarchy_and_raises(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=LocationHierarchy())
    with pytest.raises(ParameterNotFound) as excinfo:
        params.at(location="NZ", time=2030)
    assert "NZ" in str(excinfo.value)


def test_omitting_location_ignores_the_location_column(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(time=2030)
    assert row["heat_demand"] == 5.0
    assert row.provenance["location_requested"] is None


def test_omitting_location_still_says_which_row_was_used(dac_parameter_file):
    """Taking the first of several locations is a choice; the provenance says so.

    Nothing was substituted, so it is not a fallback -- but reporting
    ``location_used: None`` while returning the CH row is the silent precedence
    the design forbids.
    """
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(time=2030)
    assert row["location"] == "CH"
    assert row.provenance["location_used"] == "CH"
    assert row.provenance["location_fallback"] is False


def test_interpolated_row_reports_the_location_it_interpolated_within(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="FR", time=2025)
    assert row.provenance["location_used"] == "RER"
    assert row.provenance["location_fallback"] is True


def test_a_returned_row_cannot_be_used_to_corrupt_the_parameter_set(dac_parameter_file):
    """ParameterRow is frozen; its mappings must not alias the set's own state."""
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)

    row.values["heat_demand"] = 999.0
    with pytest.raises(TypeError):
        row.units["heat_demand"] = "kJ"
    with pytest.raises(TypeError):
        row.iris["heat_demand"] = "urn:nonsense"

    later = params.at(location="CH", time=2030)
    assert later["heat_demand"] == 5.0
    assert later.unit_of("heat_demand") == "MJ"
    assert later.iri_of("heat_demand") == HEAT_DEMAND_IRI


def test_omitting_time_returns_the_first_matching_row(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH")
    assert row["time"] == 2020
    assert row.provenance["time_interpolated"] is False


def test_unknown_column_raises_attribute_error(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2030)
    with pytest.raises(AttributeError):
        row.nonexistent_column


def test_boolean_column_is_not_interpolated(tmp_path):
    # bool is a numbers.Real (bool subclasses int, int is Integral, Integral
    # is Real), so it must be excluded explicitly or it gets averaged into a
    # meaningless float. The interpolated row must keep the lower row's
    # boolean value unchanged.
    path = tmp_path / "bool_params.parquet"
    write_parameter_parquet(
        path,
        rows=[
            {"location": "CH", "time": 2020, "heat_demand": 6.0, "is_pilot_plant": True},
            {"location": "CH", "time": 2030, "heat_demand": 5.0, "is_pilot_plant": False},
        ],
        fields=[
            {"name": "location", "type": "string", "unit": None, "iri": None},
            {"name": "time", "type": "integer", "unit": "year", "iri": None},
            {"name": "heat_demand", "type": "number", "unit": "MJ", "iri": HEAT_DEMAND_IRI},
            {"name": "is_pilot_plant", "type": "boolean", "unit": None, "iri": None},
        ],
    )
    params = ParameterSet.from_parquet(path, hierarchy=HIERARCHY)
    row = params.at(location="CH", time=2025)
    assert row["is_pilot_plant"] is True
    assert row["heat_demand"] == pytest.approx(5.5)
