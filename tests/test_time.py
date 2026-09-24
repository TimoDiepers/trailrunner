from datetime import UTC, datetime

import pytest

from trailrunner.core.time import (
    DATE,
    DATETIME,
    GYEAR,
    GYEAR_MONTH,
    TimeRange,
    contains,
    decimal_year,
    in_year,
    infer_standard,
    interval,
    midpoint_year,
    register_time_standard,
    year_range,
)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "standard", "expected"),
    [
        ("2030", GYEAR, (utc(2030, 1, 1), utc(2031, 1, 1))),
        ("2030-12", GYEAR_MONTH, (utc(2030, 12, 1), utc(2031, 1, 1))),
        ("2030-02", GYEAR_MONTH, (utc(2030, 2, 1), utc(2030, 3, 1))),
        ("2030-06-15", DATE, (utc(2030, 6, 15), utc(2030, 6, 16))),
        ("2030-06-15T08:00:00Z", DATETIME, (utc(2030, 6, 15, 8), utc(2030, 6, 15, 8))),
        ("2030-06-15T10:00:00+02:00", DATETIME, (utc(2030, 6, 15, 8), utc(2030, 6, 15, 8))),
    ],
)
def test_shipped_standards(value, standard, expected):
    assert interval(value, standard) == expected


@pytest.mark.parametrize(
    ("value", "standard"),
    [
        ("30", GYEAR),
        ("2030-13", GYEAR_MONTH),
        ("2030-02-30", DATE),
        ("2030-06-15T08:00:00", DATETIME),  # no timezone
        ("2030", DATETIME),
    ],
)
def test_malformed_values_are_refused(value, standard):
    with pytest.raises(ValueError):
        interval(value, standard)


def test_an_unregistered_standard_is_refused_by_name():
    with pytest.raises(ValueError, match="register_time_standard"):
        interval("FY2030", "https://example.org/fiscal-year")


def test_a_registered_standard_is_used():
    fiscal = "https://example.org/fiscal-year-test"
    register_time_standard(
        fiscal,
        lambda text: (utc(int(text[2:]) - 1, 7, 1), utc(int(text[2:]), 7, 1)),
    )
    assert interval("FY2030", fiscal) == (utc(2029, 7, 1), utc(2030, 7, 1))


def test_containment_is_half_open():
    # Review focus 2.
    year = interval("2030", GYEAR)
    assert contains(year, interval("2030-06-15", DATE))
    assert contains(year, interval("2030-12-31T23:59:59Z", DATETIME))
    assert not contains(year, interval("2031-01-01T00:00:00Z", DATETIME))
    assert not contains(interval("2030-06-15", DATE), year)


def test_decimal_years_make_year_midpoints_exact_even_across_leap_years():
    # Review focus 6: this is what keeps interpolation identical to the int-year days.
    assert midpoint_year(interval("2020", GYEAR)) == 2020.5
    assert midpoint_year(interval("2025", GYEAR)) == 2025.5
    assert decimal_year(utc(2024, 1, 1)) == 2024.0


def test_in_year():
    assert in_year(2030) == {"time": "2030", "time_standard": GYEAR}


def test_time_range_contains_finer_times():
    window = year_range(2026, 2050)
    assert window == TimeRange("2026", "2050", GYEAR)
    assert window.contains("2050-12-31", DATE)
    assert not window.contains("2051-01-01", DATE)
    assert not window.contains("2025", GYEAR)


def test_time_range_refuses_an_empty_window():
    with pytest.raises(ValueError):
        TimeRange("2050", "2026", GYEAR)


@pytest.mark.parametrize(
    ("text", "standard"),
    [("2030", GYEAR), ("2030-06", GYEAR_MONTH), ("2030-06-15", DATE), ("2030-06-15T08:00Z", DATETIME)],
)
def test_infer_standard(text, standard):
    assert infer_standard(text) == standard


def test_infer_standard_refuses_the_unrecognisable():
    with pytest.raises(ValueError):
        infer_standard("next year")
