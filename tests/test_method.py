import pytest

from trailrunner.assessment import Method
from trailrunner.core.errors import MissingUnit
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
