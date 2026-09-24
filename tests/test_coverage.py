import pytest

from trailrunner.core.flow import Flow, Property
from trailrunner.params.coverage import ContextRange, Coverage


def test_empty_coverage_covers_everything():
    coverage = Coverage()
    assert coverage.covers(Flow(iri="heat"))
    assert coverage.covers(Flow(iri="heat", location="CH", time=2030))


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
    coverage = Coverage(time_range=(2020, 2050))
    assert coverage.covers(Flow(iri="heat", time=2020))
    assert coverage.covers(Flow(iri="heat", time=2050))
    assert not coverage.covers(Flow(iri="heat", time=2019))
    assert not coverage.covers(Flow(iri="heat", time=2051))


def test_time_range_rejects_missing_time():
    coverage = Coverage(time_range=(2020, 2050))
    assert not coverage.covers(Flow(iri="heat"))


def test_coverage_is_hashable():
    coverage = Coverage(locations=frozenset({"CH"}), time_range=(2020, 2050))
    assert hash(coverage) == hash(Coverage(locations=frozenset({"CH"}), time_range=(2020, 2050)))


def test_context_range_restricts_only_flows_that_name_the_condition():
    coverage = Coverage(context=(ContextRange("pressure", "bar", 5.0, 5.0),))
    assert coverage.covers(Flow(iri="gas"))
    assert coverage.covers(Flow(iri="gas", context=(Property("pressure", 5.0, "bar"),)))
    assert not coverage.covers(Flow(iri="gas", context=(Property("pressure", 4.0, "bar"),)))


def test_context_in_another_unit_is_not_covered():
    coverage = Coverage(context=(ContextRange("pressure", "bar", 0.0, 10.0),))
    assert not coverage.covers(Flow(iri="gas", context=(Property("pressure", 4.0, "psi"),)))


def test_a_context_condition_the_coverage_does_not_declare_is_no_restriction():
    coverage = Coverage(context=(ContextRange("pressure", "bar", 5.0, 5.0),))
    assert coverage.covers(Flow(iri="gas", context=(Property("purity", 0.9, "-"),)))


def test_context_range_rejects_minimum_above_maximum():
    with pytest.raises(ValueError, match="minimum"):
        ContextRange("pressure", "bar", 6.0, 5.0)
