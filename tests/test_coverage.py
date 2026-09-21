from trailrunner.core.flow import Flow
from trailrunner.params.coverage import Coverage


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
