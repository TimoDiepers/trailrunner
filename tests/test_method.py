import pytest

from trailrunner.assessment import Method
from trailrunner.core.errors import DuplicateFactor, MissingColumns, MissingUnit, UnknownUnit
from trailrunner.core.flow import Flow
from trailrunner.params.location import LocationHierarchy

from .conftest import CH4_IRI, CO2_IRI, write_method_parquet
from trailrunner.core.units import GRAM, KG, M3, TONNE


def test_exact_factor_is_found(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    factor = method.factor(Flow(iri=CO2_IRI, location="GLO"), KG)
    assert factor.value == 1.0


def test_score_unit_comes_from_the_cf_column_metadata(method_parquet_file):
    assert Method.from_parquet(method_parquet_file).unit == KG


def test_location_falls_back_up_the_hierarchy(method_parquet_file):
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="CH"), KG)
    assert factor.value == 27.0
    assert factor.provenance["location_used"] == "RER"
    assert factor.provenance["location_fallback"] is True


def test_exact_location_is_preferred_over_the_fallback(method_parquet_file):
    method = Method.from_parquet(
        method_parquet_file, hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"})
    )
    factor = method.factor(Flow(iri=CH4_IRI, location="RER"), KG)
    assert factor.value == 27.0
    assert factor.provenance["location_fallback"] is False


def test_a_flow_with_no_factor_returns_none(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    assert method.factor(Flow(iri="https://vocab.sentier.dev/flows/sox"), KG) is None


def test_a_factor_for_a_different_kind_does_not_match(method_parquet_file):
    """A CF per kg converts to tonnes (same kind) but says nothing about m3."""
    method = Method.from_parquet(method_parquet_file)
    assert method.factor(Flow(iri=CO2_IRI, location="GLO"), M3) is None


def test_a_flow_without_a_location_matches_the_root_row(method_parquet_file):
    method = Method.from_parquet(method_parquet_file)
    factor = method.factor(Flow(iri=CO2_IRI), KG)
    assert factor.value == 1.0
    assert factor.provenance["location_fallback"] is False


def test_a_cf_column_without_a_declared_unit_raises(tmp_path):
    path = tmp_path / "unitless.parquet"
    write_method_parquet(
        path,
        [{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0}],
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
CF = {"type": "number", "unit": KG, "iri": None}


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
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2030, "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2040, "cf": 2.0},
        ],
    )
    assert method.factor(Flow(iri=CO2_IRI, location="GLO", time=2040), KG).value == 2.0


def test_a_year_with_no_row_falls_through_to_the_untimed_row(tmp_path):
    """No interpolation between two conventions: either the year is stated, or
    the method's undated factor answers."""
    method = timed_method(
        tmp_path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2030, "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": None, "cf": 9.0},
        ],
    )
    factor = method.factor(Flow(iri=CO2_IRI, location="GLO", time=2035), KG)
    assert factor.value == 9.0
    assert factor.provenance["time_used"] is None


def test_a_year_with_no_row_and_no_untimed_row_is_uncharacterized(tmp_path):
    method = timed_method(
        tmp_path,
        [{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2030, "cf": 1.0}],
    )
    assert method.factor(Flow(iri=CO2_IRI, location="GLO", time=2035), KG) is None


def test_location_outranks_time(tmp_path):
    """Pinned deliberately: the location chain is the *outer* loop and time the
    inner one, so a CH row with no year beats a GLO row written for exactly the
    year asked for. A method states its factors where they hold, and reaching
    past a regional convention to the global table would answer with a
    different method's opinion."""
    method = timed_method(
        tmp_path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "CH", "time": None, "cf": 5.0},
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2030, "cf": 1.0},
        ],
        hierarchy=LocationHierarchy({"CH": "GLO"}),
    )
    factor = method.factor(Flow(iri=CO2_IRI, location="CH", time=2030), KG)
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
        [{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 0.0}],
        [
            {"name": "flow_iri", **STRING},
            {"name": "flow_unit", **STRING},
            {"name": "location", **STRING},
            {"name": "cf", **CF},
        ],
    )
    factor = Method.from_parquet(path).factor(Flow(iri=CO2_IRI, location="GLO"), KG)
    assert factor is not None
    assert factor.value == 0.0


def test_two_factors_for_one_key_raise(tmp_path):
    """Last-wins would put a number in the score that appears in no message
    anywhere -- the same reason two models producing one product raises."""
    path = tmp_path / "duplicate.parquet"
    write_method_parquet(
        path,
        [
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.5},
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
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2030, "cf": 1.0},
            {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "time": 2040, "cf": 2.0},
        ],
    )
    assert method.factor(Flow(iri=CO2_IRI, location="GLO", time=2030), KG).value == 1.0


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
    factor = method.factor(Flow(iri=CH4_IRI, location="CH"), KG)
    assert factor.provenance["location_requested"] == "CH"
    assert factor.provenance["location_used"] == "RER"


def test_a_row_without_a_cf_names_the_column_and_the_source():
    """``from_parquet`` pre-checks the columns, so this is the direct
    construction path -- which was still raising a bare ``KeyError: 'cf'``."""
    with pytest.raises(MissingColumns) as raised:
        Method(
            rows=[{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO"}],
            unit=KG,
            name="handmade",
            source="somewhere.parquet",
        )
    message = str(raised.value)
    assert "somewhere.parquet" in message
    assert "'cf'" in message


def test_a_row_without_a_flow_iri_names_the_layout():
    with pytest.raises(MissingColumns, match="flow_iri"):
        Method(rows=[{"flow_unit": KG, "cf": 1.0}], unit=KG, name="handmade")


def _method(rows):
    return Method(rows=rows, unit=KG, name="gwp")


def test_a_factor_per_kg_scores_a_flow_in_tonnes():
    method = _method([{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0}])
    cf = method.factor(Flow(iri=CO2_IRI), TONNE)
    assert cf.value == pytest.approx(1000.0)
    assert cf.provenance["unit_used"] == KG


def test_an_exact_unit_row_wins_over_a_convertible_one():
    method = _method([
        {"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0},
        {"flow_iri": CO2_IRI, "flow_unit": GRAM, "location": "GLO", "cf": 0.002},
    ])
    assert method.factor(Flow(iri=CO2_IRI), GRAM).value == pytest.approx(0.002)


def test_another_kind_stays_uncharacterized():
    method = _method([{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0}])
    assert method.factor(Flow(iri=CO2_IRI), M3) is None


def test_a_flow_unit_that_is_not_a_vocabulary_iri_is_refused():
    """A method file still written with ``flow_unit: "kg"`` would otherwise
    match nothing silently: every flow would go uncharacterized and the score
    would be a quiet 0. Refusing at construction catches it immediately."""
    with pytest.raises(UnknownUnit, match="kg"):
        Method(
            rows=[{"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.0}],
            unit=KG,
            name="handmade",
        )


def test_a_cf_unit_that_is_not_a_vocabulary_iri_is_refused():
    with pytest.raises(UnknownUnit, match="kg CO2eq"):
        Method(
            rows=[{"flow_iri": CO2_IRI, "flow_unit": KG, "location": "GLO", "cf": 1.0}],
            unit="kg CO2eq",
            name="handmade",
        )
