"""The surface a user actually imports from."""

import trailrunner


def test_the_exceptions_a_calculation_can_raise_are_importable_from_the_top():
    """calculate() propagates these; catching one must not mean reaching into
    trailrunner.core.errors."""
    for name in (
        "TrailrunnerError",
        "NoModelFound",
        "AmbiguousModelMatch",
        "ValidationError",
        "ParameterNotFound",
        # The attribution refusals reach the caller by the same route, and the
        # docs tell a reader to handle them by name.
        "MissingProperty",
        "UnsupportedAttribution",
        "UnallocatedCoProduction",
    ):
        assert name in trailrunner.__all__
        assert issubclass(getattr(trailrunner, name), Exception)


def test_every_exported_error_is_a_trailrunner_error():
    for name in (
        "NoModelFound",
        "AmbiguousModelMatch",
        "ValidationError",
        "ParameterNotFound",
        "MissingUnit",
        "MissingProperty",
        "UnsupportedAttribution",
        "UnallocatedCoProduction",
    ):
        assert issubclass(getattr(trailrunner, name), trailrunner.TrailrunnerError)


def test_all_lists_only_names_that_exist():
    for name in trailrunner.__all__:
        assert hasattr(trailrunner, name), name


def test_units_and_time_are_importable_from_the_top():
    """A caller declaring context conditions or a time range works from the
    unit and time vocabulary IRIs without reaching into trailrunner.core."""
    for name in (
        "UnknownUnit",
        "MissingTimeStandard",
        "UnitCatalog",
        "TimeRange",
        "year_range",
        "in_year",
        "when",
    ):
        assert name in trailrunner.__all__
        assert hasattr(trailrunner, name)
