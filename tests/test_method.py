import pytest

from trailrunner.assessment import Method
from trailrunner.core.errors import DuplicateFactor, MissingColumns, MissingUnit
from trailrunner.core.flow import Flow
from trailrunner.params.location import LocationHierarchy

from .conftest import CH4_IRI, CO2_IRI, write_method_parquet


def test_exact_factor_is_found(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    factor = method.factor(Flow(iri=CO2_IRI, location="GLO"), "kg")
    assert factor.value == 1.0


def test_score_unit_comes_from_the_cf_column_metadata(method_parquet_file):
    assert Method.from_parquet(method_parquet_file).unit == "kg CO2eq"


def test_location_falls_back_up_the_hierarchy(method_parquet_file):
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="CH"), "kg")
    assert factor.value == 27.0
    assert factor.provenance["location_used"] == "RER"
    assert factor.provenance["location_fallback"] is True


def test_exact_location_is_preferred_over_the_fallback(method_parquet_file):
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="RER"), "kg")
    assert factor.value == 27.0
    assert factor.provenance["location_fallback"] is False


def test_a_flow_with_no_factor_returns_none(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    assert method.factor(Flow(iri="https://vocab.sentier.dev/flows/sox"), "kg") is None


def test_a_factor_for_a_different_unit_does_not_match(method_parquet_file):
    """String equality, no conversion: a CF per kg says nothing about tonnes."""
    method = Method.from_parquet(method_parquet_file)
    assert method.factor(Flow(iri=CO2_IRI, location="GLO"), "tonne") is None


def test_a_flow_without_a_location_matches_the_root_row(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    factor = method.factor(Flow(iri=CO2_IRI), "kg")
    assert factor.value == 1.0
    assert factor.provenance["location_fallback"] is False


def test_a_cf_column_without_a_declared_unit_raises(tmp_path):
    path = tmp_path / "unitless.parquet"
    write_method_parquet(
        path,
        [{"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.0}],
        [
            {"name": "flow_iri", "type": "string", "unit": None, "iri": None},
            {"name": "flow_unit", "type": "string", "unit": None, "iri": None},
            {"name": "location", "type": "string", "unit": None, "iri": None},
            {"name": "cf", "type": "number", "unit": None, "iri": None},
        ],
    )
    with pytest.raises(MissingUnit, match="cf"):
        Method.from_parquet(path)


STRING = {"type": "string", "unit": None, "iri": None}
YEAR = {"type": "integer", "unit": None, "iri": None}
CF = {"type": "number", "unit": "kg CO2eq", "iri": None}


def timed_method(tmp_path, rows, hierarchy=None):
    """A method parquet with the optional ``time`` column present."""
    path = tmp_path / "timed.parquet"
    write_method_parquet(
        path,
        rows,
        [
            {"name": "flow_iri", **STRING},
            {"name": "flow_unit", **STRING},
            {"name": "location", **STRING},
            {"name": "time", **YEAR},
            {"name": "cf", **CF},
        ],
    )
    return Method.from_parquet(path, hierarchy=hierarchy)


def test_an_exact_year_is_matched(tmp_path):
    method = timed_method(
        tmp_path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2030, "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2040, "cf": 2.0},
        ],
    )
    assert method.factor(Flow(iri=CO2_IRI, location="GLO", time=2040), "kg").value == 2.0


def test_a_year_with_no_row_falls_through_to_the_untimed_row(tmp_path):
    """No interpolation between two conventions: either the year is stated, or
    the method's undated factor answers."""
    method = timed_method(
        tmp_path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2030, "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": None, "cf": 9.0},
        ],
    )
    factor = method.factor(Flow(iri=CO2_IRI, location="GLO", time=2035), "kg")
    assert factor.value == 9.0
    assert factor.provenance["time_used"] is None


def test_a_year_with_no_row_and_no_untimed_row_is_uncharacterized(tmp_path):
    method = timed_method(
        tmp_path,
        [{"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2030, "cf": 1.0}],
    )
    assert method.factor(Flow(iri=CO2_IRI, location="GLO", time=2035), "kg") is None


def test_location_outranks_time(tmp_path):
    """Pinned deliberately: the location chain is the *outer* loop and time the
    inner one, so a CH row with no year beats a GLO row written for exactly the
    year asked for. A method states its factors where they hold, and reaching
    past a regional convention to the global table would answer with a
    different method's opinion."""
    method = timed_method(
        tmp_path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "CH", "time": None, "cf": 5.0},
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2030, "cf": 1.0},
        ],
        hierarchy=LocationHierarchy({"CH": "GLO"}),
    )
    factor = method.factor(Flow(iri=CO2_IRI, location="CH", time=2030), "kg")
    assert factor.value == 5.0
    assert factor.provenance["location_used"] == "CH"
    assert factor.provenance["time_used"] is None


def test_a_factor_of_exactly_zero_is_a_factor_not_a_gap(tmp_path):
    """``0.0`` is the method saying "this flow does not contribute", which is a
    different claim from "nobody wrote a factor for it". A truthiness check
    instead of ``is not None`` would collapse the two and silently move the
    flow into ``uncharacterized``."""
    path = tmp_path / "zero.parquet"
    write_method_parquet(
        path,
        [{"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 0.0}],
        [
            {"name": "flow_iri", **STRING},
            {"name": "flow_unit", **STRING},
            {"name": "location", **STRING},
            {"name": "cf", **CF},
        ],
    )
    factor = Method.from_parquet(path).factor(Flow(iri=CO2_IRI, location="GLO"), "kg")
    assert factor is not None
    assert factor.value == 0.0


def test_two_factors_for_one_key_raise(tmp_path):
    """Last-wins would put a number in the score that appears in no message
    anywhere -- the same reason two models producing one product raises."""
    path = tmp_path / "duplicate.parquet"
    write_method_parquet(
        path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.5},
        ],
        [
            {"name": "flow_iri", **STRING},
            {"name": "flow_unit", **STRING},
            {"name": "location", **STRING},
            {"name": "cf", **CF},
        ],
    )
    with pytest.raises(DuplicateFactor) as raised:
        Method.from_parquet(path)
    assert CO2_IRI in str(raised.value)
    assert "duplicate.parquet" in str(raised.value)


def test_two_factors_differing_only_by_time_are_not_duplicates(tmp_path):
    method = timed_method(
        tmp_path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2030, "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "time": 2040, "cf": 2.0},
        ],
    )
    assert method.factor(Flow(iri=CO2_IRI, location="GLO", time=2030), "kg").value == 1.0


def test_a_parquet_without_the_method_columns_names_the_file_and_the_layout(tmp_path):
    """A bare ``KeyError('flow_iri')`` names neither."""
    path = tmp_path / "not_a_method.parquet"
    write_method_parquet(
        path,
        [{"substance": "CO2", "cf": 1.0}],
        [
            {"name": "substance", **STRING},
            {"name": "cf", **CF},
        ],
    )
    with pytest.raises(MissingColumns) as raised:
        Method.from_parquet(path)
    message = str(raised.value)
    assert "not_a_method.parquet" in message
    assert "flow_iri" in message and "flow_unit" in message


def test_provenance_records_the_location_that_was_asked_for(method_parquet_file):
    """``ParameterSet`` records ``location_requested``; a reader comparing two
    runs needs the same field here."""
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="CH"), "kg")
    assert factor.provenance["location_requested"] == "CH"
    assert factor.provenance["location_used"] == "RER"
