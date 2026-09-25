import pytest

from trailrunner.core.settings import AttributionSettings, ProxySettings, Settings
from trailrunner.core.units import PA


def test_settings_defaults_are_the_conservative_ones():
    settings = Settings()
    assert settings.attribution.allocation == "none"
    assert settings.attribution.capital == "per_output"
    assert settings.attribution.reuse == "first_life"
    assert settings.proxy.order == ("time", "location", "context", "product")
    assert settings.proxy.time_tolerance == 5
    # context is in the order but relaxes nothing until a condition is named.
    assert settings.proxy.context_tolerance == {}


def test_context_tolerance_carries_its_unit():
    settings = ProxySettings(context_tolerance={"pressure": (0.0, 1e5, PA)})
    assert settings.context_tolerance["pressure"][2] == PA


@pytest.mark.parametrize("bounds", [(0.0, 1.0), (-1.0, 1.0, PA), (0.0, 1.0, 5)])
def test_context_tolerance_rejects_bad_bounds(bounds):
    with pytest.raises(ValueError, match="context tolerance"):
        ProxySettings(context_tolerance={"pressure": bounds})


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


def test_a_context_condition_is_a_dimension_of_its_own():
    settings = ProxySettings(
        order=("context.pressure", ("context.pressure", "location")),
        context_tolerance={"pressure": (0.0, 1.0, PA)},
    )
    # absent from max_steps, so it takes the context budget
    assert settings.steps_allowed("context.pressure") == settings.steps_allowed("context")


def test_a_context_condition_may_have_its_own_budget():
    settings = ProxySettings(
        order=("context.pressure",),
        max_steps={"context.pressure": 3},
        context_tolerance={"pressure": (0.0, 1.0, PA)},
    )
    assert settings.steps_allowed("context.pressure") == 3


def test_a_context_condition_without_a_tolerance_is_rejected():
    with pytest.raises(ValueError, match="no context_tolerance for 'pressure'"):
        ProxySettings(order=("context.pressure",))


def test_context_cannot_be_combined_with_its_own_condition():
    with pytest.raises(ValueError, match="combines context with one of its own"):
        ProxySettings(
            order=(("context", "context.pressure"),),
            context_tolerance={"pressure": (0.0, 1.0, PA)},
        )


def test_an_empty_context_condition_is_rejected():
    with pytest.raises(ValueError, match="names no context condition"):
        ProxySettings(order=("context.",))
