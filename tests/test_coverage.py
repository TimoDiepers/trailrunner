import pytest

from trailrunner.core.flow import Flow, Property
from trailrunner.core.time import DATE, GYEAR, in_year, year_range
from trailrunner.core.units import KG, KILOMETRE, METRE, PA
from trailrunner.params.coverage import ContextRange, Coverage


def test_empty_coverage_covers_everything():
    coverage = Coverage()
    assert coverage.covers(Flow(iri="heat"))
    assert coverage.covers(Flow(iri="heat", location="CH", **in_year(2030)))


def test_location_coverage_accepts_listed_location():
    coverage = Coverage(locations=frozenset({"CH", "DE"}))
    assert coverage.covers(Flow(iri="heat", location="CH"))


def test_location_coverage_rejects_unlisted_location():
    coverage = Coverage(locations=frozenset({"CH"}))
    assert not coverage.covers(Flow(iri="heat", location="DE"))


def test_location_coverage_rejects_missing_location():
    coverage = Coverage(locations=frozenset({"CH"}))
    assert not coverage.covers(Flow(iri="heat"))


def test_time_range_is_inclusive_on_both_ends():
    coverage = Coverage(time_range=year_range(2020, 2050))
    assert coverage.covers(Flow(iri="heat", **in_year(2020)))
    assert coverage.covers(Flow(iri="heat", **in_year(2050)))
    assert not coverage.covers(Flow(iri="heat", **in_year(2019)))
    assert not coverage.covers(Flow(iri="heat", **in_year(2051)))


def test_time_range_rejects_missing_time():
    coverage = Coverage(time_range=year_range(2020, 2050))
    assert not coverage.covers(Flow(iri="heat"))


def test_coverage_is_hashable():
    coverage = Coverage(locations=frozenset({"CH"}), time_range=year_range(2020, 2050))
    assert hash(coverage) == hash(Coverage(locations=frozenset({"CH"}), time_range=year_range(2020, 2050)))


def test_a_flow_naming_no_condition_is_covered():
    coverage = Coverage(context=(ContextRange("pressure", PA, 5e5, 5e5),))
    assert coverage.covers(Flow(iri="gas"))


def test_context_is_matched_in_the_declared_unit():
    coverage = Coverage(context=(ContextRange("pressure", PA, 5e5, 5e5),))
    assert coverage.covers(Flow(iri="gas", context=(Property("pressure", 5e5, PA),)))
    assert not coverage.covers(Flow(iri="gas", context=(Property("pressure", 4e5, PA),)))


def test_context_in_another_unit_of_the_same_kind_is_converted():
    coverage = Coverage(context=(ContextRange("distance", KILOMETRE, 0.0, 2000.0),))
    assert coverage.covers(Flow(iri="t", context=(Property("distance", 1.5e6, METRE),)))
    assert not coverage.covers(Flow(iri="t", context=(Property("distance", 2.5e6, METRE),)))


def test_context_of_another_kind_is_not_covered():
    coverage = Coverage(context=(ContextRange("pressure", PA, 0.0, 1e6),))
    assert not coverage.covers(Flow(iri="gas", context=(Property("pressure", 4.0, KG),)))


def test_a_context_condition_the_coverage_does_not_declare_is_no_restriction():
    coverage = Coverage(context=(ContextRange("pressure", PA, 5e5, 5e5),))
    assert coverage.covers(Flow(iri="gas", context=(Property("purity", 0.9, "-"),)))


def test_context_range_rejects_minimum_above_maximum():
    with pytest.raises(ValueError, match="minimum"):
        ContextRange("pressure", PA, 6e5, 5e5)


def test_a_year_range_covers_a_day_in_it():
    coverage = Coverage(time_range=year_range(2026, 2050))
    assert coverage.covers(Flow(iri="c", time="2050-12-31", time_standard=DATE))
    assert not coverage.covers(Flow(iri="c", time="2025", time_standard=GYEAR))


def test_coverage_rejects_a_tuple_time_range():
    with pytest.raises(TypeError, match=r"time_range=year_range\(2026, 2050\)"):
        Coverage(time_range=(2026, 2050))


def test_coverage_rejects_units_that_is_not_a_frozenset_of_str():
    with pytest.raises(TypeError):
        Coverage(units={KG})  # a plain set, not a frozenset
    with pytest.raises(TypeError):
        Coverage(units=frozenset({1, 2}))  # not strings
