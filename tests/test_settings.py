import pytest

from trailrunner.core.settings import AttributionSettings, ProxySettings, Settings


def test_settings_defaults_are_the_conservative_ones():
    settings = Settings()
    assert settings.attribution.allocation == "none"
    assert settings.attribution.capital == "per_output"
    assert settings.attribution.reuse == "first_life"
    assert settings.proxy.order == ("time", "location", "product")
    assert settings.proxy.time_tolerance == 5


def test_values_mapping_still_works_alongside_the_typed_fields():
    settings = Settings(values={"scenario": "SSP2"})
    assert settings.get("scenario") == "SSP2"
    assert settings.get("missing") is None


def test_unknown_allocation_rule_is_rejected_at_construction():
    with pytest.raises(ValueError, match="economical"):
        AttributionSettings(allocation="economical")


def test_unknown_capital_rule_is_rejected_at_construction():
    with pytest.raises(ValueError, match="per_decade"):
        AttributionSettings(capital="per_decade")


def test_every_documented_allocation_rule_is_accepted():
    for rule in ("none", "mass", "economic", "energy", "substitution"):
        assert AttributionSettings(allocation=rule).allocation == rule


def test_unknown_proxy_dimension_is_rejected():
    with pytest.raises(ValueError, match="colour"):
        ProxySettings(order=("time", "colour"))


def test_repeated_proxy_dimension_is_rejected():
    with pytest.raises(ValueError, match="once"):
        ProxySettings(order=("time", "time", "location"))


def test_proxy_order_may_be_a_subset():
    settings = ProxySettings(order=("location",))
    assert settings.order == ("location",)


def test_steps_allowed_reads_max_steps_with_a_zero_default():
    settings = ProxySettings(max_steps={"location": 2})
    assert settings.steps_allowed("location") == 2
    assert settings.steps_allowed("product") == 0


def test_each_settings_gets_its_own_proxy_budget():
    """A shared mutable default would let one run's budget change another's."""
    first, second = Settings(), Settings()
    assert first.proxy is not second.proxy
    first.proxy.max_steps["time"] = 999
    assert second.proxy.max_steps["time"] == 1


def test_each_settings_gets_its_own_attribution():
    assert Settings().attribution is not Settings().attribution


def test_unknown_max_steps_key_is_rejected():
    with pytest.raises(ValueError, match="locaiton"):
        ProxySettings(max_steps={"locaiton": 3})


def test_negative_proxy_budget_is_rejected():
    with pytest.raises(ValueError, match="-1"):
        ProxySettings(max_steps={"location": -1})


def test_negative_time_tolerance_is_rejected():
    with pytest.raises(ValueError, match="-1"):
        ProxySettings(time_tolerance=-1)


def test_valid_partial_max_steps_is_accepted():
    settings = ProxySettings(max_steps={"location": 2})
    assert settings.steps_allowed("location") == 2


def test_a_combined_entry_is_accepted_alongside_its_members():
    settings = ProxySettings(order=("location", ("location", "time"), "product"))
    assert settings.order[1] == ("location", "time")


def test_a_combined_entry_needs_two_dimensions():
    with pytest.raises(ValueError, match="at least two"):
        ProxySettings(order=(("location",),))


def test_a_combined_entry_rejects_an_unknown_dimension():
    with pytest.raises(ValueError, match="locaiton"):
        ProxySettings(order=(("locaiton", "time"),))


def test_a_combined_entry_rejects_a_repeated_dimension():
    with pytest.raises(ValueError, match="once"):
        ProxySettings(order=(("time", "time"),))


def test_the_same_combination_may_appear_only_once():
    """Whatever order its members are written in: the pair is one search."""
    with pytest.raises(ValueError, match="once"):
        ProxySettings(order=(("location", "time"), ("time", "location")))


def test_a_combined_entry_needs_a_budget_for_every_member():
    """Every member must move at least one step, so a zero budget makes the
    entry unreachable -- say so where it is written, not by silence at run time."""
    with pytest.raises(ValueError, match="product"):
        ProxySettings(
            order=(("location", "product"),), max_steps={"location": 2}
        )
