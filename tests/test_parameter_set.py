import pytest

from trailrunner.core.errors import MissingTimeStandard, MissingUnit, ParameterNotFound
from trailrunner.core.time import DATE, GYEAR, in_year
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import HEAT_DEMAND_IRI, write_parameter_parquet
from trailrunner.core.units import MJ

# FR must be in the map: chain("FR") with only {"CH": "RER"} would be
# ["FR", "GLO"] and never reach the RER rows.
HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


def test_exact_match_returns_the_row_untouched(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2030))
    assert row["heat_demand"] == 5.0
    assert row.temperature == 10.0
    assert row.provenance["location_used"] == "CH"
    assert row.provenance["location_fallback"] is False
    assert row.provenance["time_interpolated"] is False


def test_units_and_iris_come_from_the_embedded_datapackage(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2030))
    assert row.unit_of("heat_demand") == MJ
    assert row.iri_of("heat_demand") == HEAT_DEMAND_IRI
    assert row.iri_of("location") is None


def test_a_column_with_no_declared_unit_raises_naming_the_column_and_the_file(
    dac_parameter_file,
):
    """``unit_of`` feeds ``Exchange.unit``, which is ``str``, not ``str | None``.

    Returning None here would type-check, travel into a model's Result and
    surface much later as a Runner error blaming the model for what is really
    missing parquet metadata.
    """
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2030))
    with pytest.raises(MissingUnit) as excinfo:
        row.unit_of("location")
    assert "location" in str(excinfo.value)
    assert str(dac_parameter_file) in str(excinfo.value)


def test_a_missing_unit_can_still_be_queried_without_raising(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2030))
    assert row.unit_of("location", default=None) is None
    assert row.unit_of("heat_demand", default=None) == MJ


def test_a_parameter_set_built_in_memory_says_so_when_a_unit_is_missing():
    params = ParameterSet([{"location": "CH", "time": "2030", "heat_demand": 5.0}], time_standard=GYEAR)
    with pytest.raises(MissingUnit) as excinfo:
        params.at(location="CH", **in_year(2030)).unit_of("heat_demand")
    assert "heat_demand" in str(excinfo.value)


def test_location_falls_back_up_the_hierarchy_and_says_so(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="FR", **in_year(2030))
    assert row["heat_demand"] == 5.5
    assert row.provenance["location_requested"] == "FR"
    assert row.provenance["location_used"] == "RER"
    assert row.provenance["location_fallback"] is True


def test_time_is_interpolated_between_bracketing_rows(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2025))
    assert row["heat_demand"] == pytest.approx(5.5)
    assert row["temperature"] == pytest.approx(9.5)
    assert row.provenance["time_interpolated"] is True
    assert row.provenance["time_bracket"] == ("2020", "2030")


def test_interpolated_row_keeps_non_numeric_columns_from_the_lower_row(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2025))
    assert row["location"] == "CH"


def test_time_outside_the_data_range_is_not_extrapolated(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    with pytest.raises(ParameterNotFound):
        params.at(location="CH", **in_year(2100))


def test_unknown_location_exhausts_the_hierarchy_and_raises(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=LocationHierarchy())
    with pytest.raises(ParameterNotFound) as excinfo:
        params.at(location="NZ", **in_year(2030))
    assert "NZ" in str(excinfo.value)


def test_omitting_location_ignores_the_location_column(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(**in_year(2030))
    assert row["heat_demand"] == 5.0
    assert row.provenance["location_requested"] is None


def test_omitting_location_still_says_which_row_was_used(dac_parameter_file):
    """Taking the first of several locations is a choice; the provenance says so.

    Nothing was substituted, so it is not a fallback -- but reporting
    ``location_used: None`` while returning the CH row is the silent precedence
    the design forbids.
    """
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(**in_year(2030))
    assert row["location"] == "CH"
    assert row.provenance["location_used"] == "CH"
    assert row.provenance["location_fallback"] is False


def test_interpolated_row_reports_the_location_it_interpolated_within(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="FR", **in_year(2025))
    assert row.provenance["location_used"] == "RER"
    assert row.provenance["location_fallback"] is True


def test_a_returned_row_cannot_be_used_to_corrupt_the_parameter_set(dac_parameter_file):
    """ParameterRow is frozen; its mappings must not alias the set's own state."""
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2030))

    row.values["heat_demand"] = 999.0
    with pytest.raises(TypeError):
        row.units["heat_demand"] = "kJ"
    with pytest.raises(TypeError):
        row.iris["heat_demand"] = "urn:nonsense"

    later = params.at(location="CH", **in_year(2030))
    assert later["heat_demand"] == 5.0
    assert later.unit_of("heat_demand") == MJ
    assert later.iri_of("heat_demand") == HEAT_DEMAND_IRI


def test_omitting_time_returns_the_first_matching_row(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH")
    assert row["time"] == "2020"
    assert row.provenance["time_interpolated"] is False


def test_unknown_column_raises_attribute_error(dac_parameter_file):
    params = ParameterSet.from_parquet(dac_parameter_file, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2030))
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
            {"location": "CH", "time": "2020", "heat_demand": 6.0, "is_pilot_plant": True},
            {"location": "CH", "time": "2030", "heat_demand": 5.0, "is_pilot_plant": False},
        ],
        fields=[
            {"name": "location", "type": "string", "unit": None, "iri": None},
            {"name": "time", "type": "string", "time_standard": GYEAR, "iri": None},
            {"name": "heat_demand", "type": "number", "unit": MJ, "iri": HEAT_DEMAND_IRI},
            {"name": "is_pilot_plant", "type": "boolean", "unit": None, "iri": None},
        ],
    )
    params = ParameterSet.from_parquet(path, hierarchy=HIERARCHY)
    row = params.at(location="CH", **in_year(2025))
    assert row["is_pilot_plant"] is True
    assert row["heat_demand"] == pytest.approx(5.5)


@pytest.mark.parametrize("nested", [True, False])
def test_units_and_iris_are_read_from_either_descriptor_shape(tmp_path, nested):
    # Frictionless — and so trailpack's Packing.write_parquet — nests the field
    # list under resources[].schema.fields. Reading only the flat
    # resources[].fields fails silently: every unit comes back missing and a
    # model that asks for one raises MissingUnit far from the cause.
    path = write_parameter_parquet(
        tmp_path / f"shape_{nested}.parquet",
        rows=[{"location": "CH", "time": "2020", "heat_demand": 6.0}],
        fields=[
            {"name": "location", "type": "string", "unit": None, "iri": None},
            {"name": "time", "type": "string", "time_standard": GYEAR, "iri": None},
            {"name": "heat_demand", "type": "number", "unit": MJ, "iri": HEAT_DEMAND_IRI},
        ],
        nested=nested,
    )
    row = ParameterSet.from_parquet(path, hierarchy=HIERARCHY).at(location="CH", **in_year(2020))
    assert row.unit_of("heat_demand") == MJ
    assert row.iri_of("heat_demand") == HEAT_DEMAND_IRI


ROWS = [
    {"location": "CH", "time": "2020", "x": 1.0},
    {"location": "CH", "time": "2030", "x": 3.0},
]


def test_a_day_is_answered_by_its_year_row():
    params = ParameterSet(ROWS, time_standard=GYEAR)
    row = params.at(location="CH", time="2030-06-15", time_standard=DATE)
    assert row["x"] == 3.0
    assert row.provenance["time_used"] == "2030"
    assert row.provenance["time_interpolated"] is False


def test_interpolation_between_years_is_unchanged_across_leap_years():
    params = ParameterSet(ROWS, time_standard=GYEAR)
    row = params.at(location="CH", **in_year(2025))
    assert row["x"] == pytest.approx(2.0)
    assert row.provenance["time_bracket"] == ("2020", "2030")


def test_int_time_is_refused():
    with pytest.raises(TypeError, match="in_year"):
        ParameterSet(ROWS, time_standard=GYEAR).at(location="CH", time=2030)


def test_rows_with_time_need_a_standard():
    with pytest.raises(MissingTimeStandard):
        ParameterSet(ROWS)


def test_a_file_without_a_time_standard_is_refused(tmp_path):
    path = tmp_path / "p.parquet"
    write_parameter_parquet(path, ROWS, [
        {"name": "location", "type": "string"},
        {"name": "time", "type": "string"},
        {"name": "x", "type": "number"},
    ])
    with pytest.raises(MissingTimeStandard, match="timeStandard"):
        ParameterSet.from_parquet(path)


def test_a_file_without_a_time_standard_says_the_column_must_be_strings(tmp_path):
    """The MissingTimeStandard message an old int-year parquet hits should not
    just ask for a timeStandard; it should also say the column must hold
    strings, since an old file that gets one added still fails if the values
    themselves are still ints."""
    path = tmp_path / "p.parquet"
    write_parameter_parquet(path, ROWS, [
        {"name": "location", "type": "string"},
        {"name": "time", "type": "string"},
        {"name": "x", "type": "number"},
    ])
    with pytest.raises(MissingTimeStandard, match="string"):
        ParameterSet.from_parquet(path)


def test_an_int_year_row_names_the_source_column_and_value():
    """An old int-year parquet that *does* declare a timeStandard still fails,
    because the column itself still holds ints. That failure must name the
    source, the column, and the bad value -- not just repeat the raw
    ``interval()`` complaint mid-traversal."""
    rows = [{"location": "CH", "time": 2030, "x": 1.0}]
    with pytest.raises(ValueError, match="these rows") as excinfo:
        ParameterSet(rows, time_standard=GYEAR)
    message = str(excinfo.value)
    assert "'time'" in message
    assert "2030" in message
    assert "cast the column to string" in message


def test_an_int_year_row_from_a_file_names_the_path(tmp_path):
    path = tmp_path / "legacy.parquet"
    write_parameter_parquet(
        path,
        [{"location": "CH", "time": 2030, "x": 1.0}],
        [
            {"name": "location", "type": "string"},
            {"name": "time", "type": "string", "time_standard": GYEAR},
            {"name": "x", "type": "number"},
        ],
    )
    with pytest.raises(ValueError, match="cast the column to string") as excinfo:
        ParameterSet.from_parquet(path)
    assert str(path) in str(excinfo.value)
