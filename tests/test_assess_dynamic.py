import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

from .conftest import CO2_IRI

pytest.importorskip("dynamic_characterization")

from trailrunner.assessment import assess_dynamic, inventory_dataframe  # noqa: E402

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"


def report_with(emissions) -> Report:
    """One node per (year, amount) pair, each emitting fossil CO2 that year."""
    log = Log()
    for year, amount in emissions:
        demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=year), amount=1.0, unit="kg")
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
                biosphere=[
                    Exchange(flow=Flow(iri=CO2_IRI, location="CH", time=year), amount=amount, unit="kg")
                ],
            ),
            model="DirectAirCapture",
        )
    return Report.from_log(log)


def test_inventory_dataframe_has_the_four_columns_the_library_wants():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert list(frame.columns) == ["date", "amount", "flow", "activity"]


def test_a_year_becomes_the_first_of_january():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert str(frame["date"].iloc[0])[:10] == "2030-01-01"


def test_the_flow_column_carries_the_iri():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert frame["flow"].iloc[0] == CO2_IRI


def test_the_activity_column_names_the_model():
    frame = inventory_dataframe(report_with([(2030, 10.0)]))
    assert frame["activity"].iloc[0] == "DirectAirCapture"


def test_exchanges_without_a_time_are_left_out_and_reported():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=1.0, unit="kg")
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="CH"), amount=5.0, unit="kg")],
        ),
        model="Undated",
    )
    assessment = assess_dynamic(Report.from_log(log))
    assert assessment.undated == [(CO2_IRI, "kg", 5.0)]
    assert len(assessment.series) == 0


def test_radiative_forcing_series_spans_the_horizon():
    """Not ``2030..2049``: the library's own conventions shift both ends (see
    the module docstring). The CO2 IRF is exactly zero at year 0, so the
    marginal series' first row falls in the emission year plus one; and the
    library's year offsets are average-Gregorian-year timedeltas rather than
    calendar years, so a 20-year horizon's last row lands a day short of the
    horizon's naive last anniversary."""
    assessment = assess_dynamic(report_with([(2030, 10.0)]), horizon=20)
    years = assessment.series["date"].dt.year
    assert years.min() == 2031
    assert years.max() == 2048


def test_the_curve_is_the_cumulative_integral_of_the_series():
    assessment = assess_dynamic(report_with([(2030, 10.0)]), horizon=20)
    assert assessment.curve["amount"].iloc[-1] == pytest.approx(
        assessment.series["amount"].sum()
    )
    assert assessment.total == pytest.approx(assessment.curve["amount"].iloc[-1])


def test_twice_the_emission_is_twice_the_forcing():
    one = assess_dynamic(report_with([(2030, 10.0)]), horizon=20).total
    two = assess_dynamic(report_with([(2030, 20.0)]), horizon=20).total
    assert two == pytest.approx(2 * one)


def test_an_emission_ten_years_later_is_characterized_over_its_own_horizon():
    """The default is the conventional convention: the horizon starts at the
    emission, not at the functional unit. The max year is 2058, not a naive
    2059 -- see the module docstring for why the library's own offsets land
    there."""
    assessment = assess_dynamic(report_with([(2030, 10.0), (2040, 10.0)]), horizon=20)
    assert assessment.series["date"].dt.year.max() == 2058


def test_an_unknown_flow_is_reported_rather_than_silently_dropped():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1.0, unit="kg")
    unknown = "https://vocab.sentier.dev/flows/unobtainium"
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")],
            biosphere=[Exchange(flow=Flow(iri=unknown, location="CH", time=2030), amount=1.0, unit="kg")],
        ),
        model="Mystery",
    )
    assessment = assess_dynamic(Report.from_log(log))
    assert unknown in assessment.uncharacterized


def test_an_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="cheeseburgers"):
        assess_dynamic(report_with([(2030, 10.0)]), metric="cheeseburgers")
