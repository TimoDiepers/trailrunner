import pytest

from trailrunner.models.cement import moisture_penalty


def test_moisture_penalty_at_reference_conditions_is_exactly_one():
    assert moisture_penalty(0.04, 10.0) == 1.0


def test_moisture_penalty_rises_with_wetter_feed():
    # Eight percent moisture against a four percent reference: twice the water
    # to evaporate before anything calcines.
    assert moisture_penalty(0.08, 10.0) == pytest.approx(1.08)


def test_moisture_penalty_rises_with_colder_feed():
    assert moisture_penalty(0.04, 0.0) == pytest.approx(1.04)


def test_moisture_penalty_falls_for_dry_warm_feed():
    assert moisture_penalty(0.02, 20.0) == pytest.approx(0.92)


def test_moisture_penalty_is_linear_in_both_terms():
    combined = moisture_penalty(0.08, 0.0)
    assert combined == pytest.approx(1.08 + 0.04)
