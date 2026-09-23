import pytest

from trailrunner.attribution import amortize

# A plant built in 2027, running 20 years, making a flat 1000 t/yr.
FLAT = dict(capital=2_000_000.0, annual_output=1000.0, lifetime_output=20_000.0,
            lifetime_years=20, build_year=2027, demand_year=2030)

# The same plant, in a year it only managed 500 t. Its lifetime total is
# unchanged: this is one lean year, not a smaller plant.
LEAN = dict(FLAT, annual_output=500.0)


def test_per_output_spreads_over_the_lifetime_output():
    assert amortize(rule="per_output", demanded_output=1000.0, **FLAT) == pytest.approx(100_000.0)


def test_per_output_is_linear_in_the_demand():
    half = amortize(rule="per_output", demanded_output=500.0, **FLAT)
    full = amortize(rule="per_output", demanded_output=1000.0, **FLAT)
    assert full == pytest.approx(2 * half)


def test_per_year_gives_each_year_an_equal_share():
    assert amortize(rule="per_year", demanded_output=1000.0, **FLAT) == pytest.approx(100_000.0)


def test_the_two_rules_agree_when_output_is_flat():
    assert amortize(rule="per_year", demanded_output=1000.0, **FLAT) == pytest.approx(
        amortize(rule="per_output", demanded_output=1000.0, **FLAT)
    )


def test_a_lean_year_carries_a_full_years_capital_under_per_year():
    """All 500 t made that year carry the whole annual share of 100,000."""
    assert amortize(rule="per_year", demanded_output=500.0, **LEAN) == pytest.approx(100_000.0)


def test_a_lean_year_carries_only_its_own_share_under_per_output():
    """500 t of a 20,000 t lifetime carries 1/40th of the capital."""
    assert amortize(rule="per_output", demanded_output=500.0, **LEAN) == pytest.approx(50_000.0)


def test_first_life_puts_everything_in_the_build_year():
    in_build_year = dict(FLAT, demand_year=2027)
    assert amortize(rule="first_life", demanded_output=1000.0, **in_build_year) == pytest.approx(
        2_000_000.0
    )


def test_first_life_attributes_nothing_to_later_years():
    assert amortize(rule="first_life", demanded_output=1000.0, **FLAT) == 0.0


def test_an_unknown_rule_is_rejected():
    with pytest.raises(ValueError, match="per_fortnight"):
        amortize(rule="per_fortnight", demanded_output=1000.0, **FLAT)


def test_zero_output_is_an_error_not_a_division():
    with pytest.raises(ValueError, match="output"):
        amortize(rule="per_output", demanded_output=1.0, **dict(FLAT, annual_output=0.0))


# A plant with a fractional lifetime. Flat output still means
# lifetime_output == annual_output * lifetime_years, so per_year and
# per_output must agree exactly, the same as they do for FLAT above. A
# lifetime_years that gets truncated to an int (20.5 -> 20) breaks this
# agreement purely from rounding, not from any real difference between the
# two rules.
FRACTIONAL_LIFETIME = dict(
    capital=2_000_000.0, annual_output=1000.0, lifetime_output=20_500.0,
    lifetime_years=20.5, build_year=2027, demand_year=2030,
)


def test_per_year_and_per_output_agree_on_flat_output_with_a_fractional_lifetime():
    assert amortize(rule="per_year", demanded_output=1000.0, **FRACTIONAL_LIFETIME) == pytest.approx(
        amortize(rule="per_output", demanded_output=1000.0, **FRACTIONAL_LIFETIME)
    )


def test_first_life_refuses_a_demand_with_no_year():
    """``None == build_year`` is False, so the silent answer would be zero
    capital for a demand that never said which year it was asking about --
    indistinguishable from the honest zero of a year nothing was built in."""
    with pytest.raises(ValueError, match="no year"):
        amortize(rule="first_life", demanded_output=1000.0, **dict(FLAT, demand_year=None))


def test_the_rules_that_never_read_the_year_accept_a_demand_without_one():
    yearless = dict(FLAT, demand_year=None)
    assert amortize(rule="per_output", demanded_output=1000.0, **yearless) == pytest.approx(
        100_000.0
    )
    assert amortize(rule="per_year", demanded_output=1000.0, **yearless) == pytest.approx(
        100_000.0
    )
