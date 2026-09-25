from datetime import datetime

import pytest

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

from .conftest import CO2_IRI

pytest.importorskip("dynamic_characterization")

from trailrunner.assessment import assess_dynamic, inventory_dataframe  # noqa: E402
from trailrunner.core.units import GRAM, KG, TONNE, W_PER_M2
from trailrunner.core.time import in_year

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"

GREENHOUSE_GASES = frozenset(
    {CO2_IRI, "https://vocab.sentier.dev/flows/ch4-fossil", "https://vocab.sentier.dev/flows/n2o"}
)


def _greenhouse_gases_in(uncharacterized) -> set[str]:
    """Which of the gases the default functions cover went uncharacterized.

    A chain may legitimately emit substances no climate method knows — mercury,
    NMVOC, a resource flow — and those belong in ``uncharacterized``. A
    greenhouse gas landing there is a spelling bug, and this is what tells the
    two apart.
    """
    return GREENHOUSE_GASES & {flow.iri for flow, _, _ in uncharacterized}


def report_with(emissions) -> Report:
    """One node per (year, amount[, unit]) tuple, each emitting fossil CO2 that year.

    ``unit`` defaults to ``KG``, which is what the IPCC AR6 characterization
    functions are defined for; pass another to exercise the mismatch path.
    """
    log = Log()
    for emission in emissions:
        year, amount = emission[0], emission[1]
        unit = emission[2] if len(emission) > 2 else KG
        demand = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(year)), amount=1.0, unit=KG)
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
                biosphere=[
                    Exchange(flow=Flow(iri=CO2_IRI, location="CH", **in_year(year)), amount=amount, unit=unit)
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


def test_the_activity_column_names_the_model_and_the_node():
    """Not just the model: two nodes of one model class must stay apart, or a
    row of the series cannot be attributed back to a place in the chain."""
    frame = inventory_dataframe(report_with([(2030, 10.0), (2040, 10.0)]))
    assert list(frame["activity"]) == ["DirectAirCapture#0", "DirectAirCapture#1"]


def test_exchanges_without_a_time_are_left_out_and_reported():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=1.0, unit=KG)
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="CH"), amount=5.0, unit=KG)],
        ),
        model="Undated",
    )
    assessment = assess_dynamic(Report.from_log(log))
    assert assessment.undated == [(Flow(iri=CO2_IRI, location="CH"), KG, 5.0)]
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
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=1.0, unit=KG)
    unknown = "https://vocab.sentier.dev/flows/unobtainium"
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=unknown, location="CH", **in_year(2030)), amount=1.0, unit=KG)],
        ),
        model="Mystery",
    )
    assessment = assess_dynamic(Report.from_log(log))
    assert assessment.uncharacterized == [
        (Flow(iri=unknown, location="CH", **in_year(2030)), KG, 1.0)
    ]
    assert assessment.wrong_unit == []
    assert assessment.total == 0.0


def test_an_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="cheeseburgers"):
        assess_dynamic(report_with([(2030, 10.0)]), metric="cheeseburgers")


# --- the unit is half the key -------------------------------------------------
#
# The IPCC AR6 functions are per kilogram. Feeding them an amount denominated
# in anything else is a silent factor of 1000 (or 1/1000), which is worse than
# no answer: the static path puts exactly the same exchange in
# `uncharacterized`, so the two paths would disagree about the same input.


def test_an_exchange_in_grams_is_reported_and_contributes_nothing():
    assessment = assess_dynamic(report_with([(2030, 10.0, GRAM)]), horizon=20)
    assert assessment.wrong_unit == [
        (Flow(iri=CO2_IRI, location="CH", **in_year(2030)), GRAM, 10.0)
    ]
    assert assessment.uncharacterized == []
    assert assessment.total == 0.0
    assert len(assessment.series) == 0


def test_an_exchange_in_tonnes_is_reported_and_contributes_nothing():
    assessment = assess_dynamic(report_with([(2030, 10.0, TONNE)]), horizon=20)
    assert assessment.wrong_unit == [
        (Flow(iri=CO2_IRI, location="CH", **in_year(2030)), TONNE, 10.0)
    ]
    assert assessment.total == 0.0


def test_an_exchange_in_kilograms_is_characterized():
    assessment = assess_dynamic(report_with([(2030, 10.0, KG)]), horizon=20)
    assert assessment.wrong_unit == []
    assert assessment.uncharacterized == []
    assert assessment.total > 0.0


def test_a_mixed_report_characterizes_only_the_kilograms_and_reports_the_rest():
    """The grams must not be swept in as kilograms, and must not vanish: the
    total is the kg-only total exactly, and the grams are named with their
    amount."""
    kilograms_only = assess_dynamic(report_with([(2030, 10.0, KG)]), horizon=20)
    mixed = assess_dynamic(report_with([(2030, 10.0, KG), (2030, 5.0, GRAM)]), horizon=20)
    assert mixed.total == pytest.approx(kilograms_only.total)
    assert mixed.wrong_unit == [
        (Flow(iri=CO2_IRI, location="CH", **in_year(2030)), GRAM, 5.0)
    ]
    assert mixed.uncharacterized == []


def test_a_wrong_unit_is_not_filed_as_uncharacterized():
    """Two different problems: 'nobody characterized this gas' versus 'this gas
    is characterized, per kilogram, and the model emitted grams'."""
    assessment = assess_dynamic(report_with([(2030, 10.0, GRAM)]), horizon=20)
    assert assessment.uncharacterized == []
    assert len(assessment.wrong_unit) == 1


def test_a_caller_can_supply_functions_for_another_unit():
    """The table is keyed on (iri, unit), and a caller keys theirs the same way."""
    from trailrunner.assessment.dynamic import default_functions

    functions = dict(default_functions())
    functions[(CO2_IRI, GRAM)] = functions[(CO2_IRI, KG)]
    grams = assess_dynamic(report_with([(2030, 10.0, GRAM)]), horizon=20, functions=functions)
    assert grams.wrong_unit == []
    assert grams.total > 0.0


def test_the_undated_and_the_uncharacterized_are_both_recorded_for_one_exchange():
    """An exchange can be both. Recording it only as undated hides the other
    gap from anyone who reads the other list."""
    log = Log()
    unknown = "https://vocab.sentier.dev/flows/unobtainium"
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH"), amount=1.0, unit=KG)
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=unknown, location="CH"), amount=3.0, unit=KG)],
        ),
        model="Mystery",
    )
    assessment = assess_dynamic(Report.from_log(log))
    entry = (Flow(iri=unknown, location="CH"), KG, 3.0)
    assert assessment.undated == [entry]
    assert assessment.uncharacterized == [entry]


# --- the Levasseur anchor -----------------------------------------------------


def test_a_fixed_horizon_spans_the_full_horizon_from_the_anchor():
    """With the anchor derived from the report's own earliest emission, the
    only emission there is gets exactly its full horizon -- the same span the
    conventional convention gives it, which is the definition of the anchor
    being right."""
    fixed = assess_dynamic(report_with([(2030, 10.0)]), horizon=20, fixed_time_horizon=True)
    conventional = assess_dynamic(report_with([(2030, 10.0)]), horizon=20)
    assert fixed.time_horizon_start == datetime(2030, 1, 1)
    assert fixed.series["date"].dt.year.min() == conventional.series["date"].dt.year.min()
    assert fixed.series["date"].dt.year.max() == conventional.series["date"].dt.year.max()
    assert fixed.total == pytest.approx(conventional.total)


def test_a_fixed_horizon_run_is_reproducible():
    """The library's own default anchor is ``datetime.now()`` bound at import,
    so this used to depend on the day it ran."""
    one = assess_dynamic(report_with([(2030, 10.0)]), horizon=20, fixed_time_horizon=True)
    two = assess_dynamic(report_with([(2030, 10.0)]), horizon=20, fixed_time_horizon=True)
    assert one.total == two.total
    assert one.time_horizon_start == two.time_horizon_start


def test_an_earlier_emission_is_integrated_for_longer_under_levasseur():
    """That is what the convention *is*: both horizons end together."""
    assessment = assess_dynamic(
        report_with([(2030, 10.0), (2040, 10.0)]), horizon=20, fixed_time_horizon=True
    )
    conventional = assess_dynamic(report_with([(2030, 10.0), (2040, 10.0)]), horizon=20)
    assert assessment.series["date"].dt.year.max() < conventional.series["date"].dt.year.max()


def test_an_emission_past_the_end_of_a_fixed_horizon_does_not_raise():
    """It gets a zero-length horizon from the library and comes back as a
    single NaT row. Guarding on the series rather than the curve used to walk
    straight into an IndexError off the end of an empty frame."""
    assessment = assess_dynamic(
        report_with([(2030, 10.0), (2300, 10.0)]), horizon=20, fixed_time_horizon=True
    )
    only_the_first = assess_dynamic(
        report_with([(2030, 10.0)]), horizon=20, fixed_time_horizon=True
    )
    assert assessment.total == pytest.approx(only_the_first.total)
    assert assessment.curve["date"].notna().all()


def test_an_explicit_anchor_is_honoured():
    """An anchor ten years before the emission cuts ten years off its horizon."""
    early = assess_dynamic(
        report_with([(2030, 10.0)]),
        horizon=20,
        fixed_time_horizon=True,
        time_horizon_start=datetime(2020, 1, 1),
    )
    derived = assess_dynamic(report_with([(2030, 10.0)]), horizon=20, fixed_time_horizon=True)
    assert early.time_horizon_start == datetime(2020, 1, 1)
    assert early.series["date"].dt.year.max() < derived.series["date"].dt.year.max()
    assert early.total < derived.total


def test_the_anchor_is_recorded_even_for_the_conventional_convention():
    assessment = assess_dynamic(report_with([(2040, 10.0), (2030, 10.0)]), horizon=20)
    assert assessment.time_horizon_start == datetime(2030, 1, 1)


# --- units and summary --------------------------------------------------------


def test_the_cumulative_unit_is_the_integral_of_the_marginal_one():
    assessment = assess_dynamic(report_with([(2030, 10.0)]), horizon=20)
    assert assessment.unit == W_PER_M2
    assert assessment.cumulative_unit == "W·yr/m2"


def test_the_gwp_metrics_accumulate_into_their_own_unit():
    assessment = assess_dynamic(report_with([(2030, 10.0)]), metric="GWP", horizon=20)
    assert assessment.unit == KG
    assert assessment.cumulative_unit == KG


def test_the_summary_names_the_total_the_anchor_and_every_gap():
    assessment = assess_dynamic(
        report_with([(2030, 10.0, KG), (2031, 5.0, GRAM)]),
        horizon=20,
        fixed_time_horizon=True,
    )
    summary = assessment.summary()
    assert "W·yr/m2" in summary
    assert "radiative_forcing" in summary
    assert "2030-01-01" in summary
    assert "1 wrong unit exchange" in summary
    assert "0 uncharacterized exchanges" in summary
    assert "0 undated exchanges" in summary


def test_the_summary_prints_the_unit_symbol_not_the_iri():
    """``symbol(KG)`` is ``"kg"``: a reader should never see a vocabulary IRI
    in text meant to be read, the same rule ``Report.tree()`` and
    ``Assessment.summary()`` already follow."""
    assessment = assess_dynamic(report_with([(2030, 10.0)]), metric="GWP", horizon=20)
    summary = assessment.summary()
    assert "kg" in summary
    assert "units/unit" not in summary


def test_two_units_of_one_flow_with_different_functions_is_refused():
    """The characterization library keys its own function table on the flow
    column alone, so this cannot be expressed in one call. Refused loudly
    rather than resolved by whichever came first."""
    from trailrunner.assessment.dynamic import default_functions

    functions = dict(default_functions())
    functions[(CO2_IRI, GRAM)] = lambda *args, **kwargs: None
    with pytest.raises(ValueError, match="assess them separately"):
        assess_dynamic(
            report_with([(2030, 10.0, KG), (2030, 5.0, GRAM)]),
            horizon=20,
            functions=functions,
        )


def test_a_wrong_unit_exchange_does_not_drag_the_anchor_back():
    """The anchor must come from the exchanges that actually enter the frame.

    A 2010 exchange in grams is reported and never characterized -- but if it
    is allowed to set the anchor, the fixed horizon ends in 2030, the one
    genuinely characterizable emission falls past it, and the total comes back
    0.0 with nothing anywhere saying a characterized exchange was discarded.
    """
    alone = assess_dynamic(
        report_with([(2030, 10.0, KG)]), horizon=20, fixed_time_horizon=True
    )
    with_noise = assess_dynamic(
        report_with([(2010, 1.0, GRAM), (2030, 10.0, KG)]),
        horizon=20,
        fixed_time_horizon=True,
    )
    assert with_noise.time_horizon_start == datetime(2030, 1, 1)
    assert with_noise.total == pytest.approx(alone.total)
    assert with_noise.total != 0.0
    assert len(with_noise.wrong_unit) == 1


def test_an_uncharacterized_exchange_does_not_drag_the_anchor_back():
    """Same for a flow no function covers: reported, never in the frame, and
    therefore never the thing the horizon is anchored to."""
    log = Log()
    unknown = "https://vocab.sentier.dev/flows/unobtainium"
    early = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2010)), amount=1.0, unit=KG)
    log.write(
        early,
        Result(
            production=[Exchange(flow=early.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=unknown, location="CH", **in_year(2010)), amount=1.0, unit=KG)],
        ),
        model="Mystery",
    )
    late = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=1.0, unit=KG)
    log.write(
        late,
        Result(
            production=[Exchange(flow=late.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="CH", **in_year(2030)), amount=10.0, unit=KG)],
        ),
        model="DirectAirCapture",
    )
    assessment = assess_dynamic(Report.from_log(log), horizon=20, fixed_time_horizon=True)
    alone = assess_dynamic(
        report_with([(2030, 10.0, KG)]), horizon=20, fixed_time_horizon=True
    )
    assert assessment.time_horizon_start == datetime(2030, 1, 1)
    assert assessment.total == pytest.approx(alone.total)


def test_an_emission_past_the_horizon_is_reported_not_silently_dropped():
    """It entered the frame, it was characterizable, and its characterized
    rows did not survive. A reader told nothing would read the total as though
    that emission had been counted."""
    assessment = assess_dynamic(
        report_with([(2030, 10.0), (2300, 10.0)]), horizon=20, fixed_time_horizon=True
    )
    assert assessment.beyond_horizon == [
        (Flow(iri=CO2_IRI, location="CH", **in_year(2300)), KG, 10.0)
    ]
    assert assessment.uncharacterized == []
    assert assessment.wrong_unit == []
    assert "1 beyond-horizon exchange" in assessment.summary()


def test_nothing_is_beyond_the_horizon_when_everything_fits():
    assessment = assess_dynamic(
        report_with([(2030, 10.0), (2035, 10.0)]), horizon=20, fixed_time_horizon=True
    )
    assert assessment.beyond_horizon == []


def test_the_dynamic_assessment_carries_the_inventorys_own_gaps():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=1.0, unit=KG)
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            biosphere=[Exchange(flow=Flow(iri=CO2_IRI, location="CH", **in_year(2030)), amount=10.0, unit=KG)],
        ),
        model="DirectAirCapture",
    )
    log.unresolved(
        Demand(flow=Flow(iri=CAPTURED, location="CH", **in_year(2030)), amount=5.0, unit=KG),
        reason="max_depth",
        parent=0,
    )
    report = Report.from_log(log, truncated=True)
    assessment = assess_dynamic(report, horizon=20)
    assert assessment.truncated is True
    assert assessment.unresolved == 1
    assert assessment.proxies == len(report.proxies)
    summary = assessment.summary()
    assert "1 unresolved" in summary
    assert "truncated" in summary


def test_a_legacy_iri_keyed_functions_mapping_is_rejected_by_name():
    """``ValueError: too many values to unpack`` names neither the argument
    nor the key shape it wanted."""
    with pytest.raises(ValueError, match="functions"):
        assess_dynamic(
            report_with([(2030, 10.0)]),
            horizon=20,
            functions={CO2_IRI: lambda *args, **kwargs: None},
        )


# --- the sign of a removal ----------------------------------------------------


def test_the_showcase_chain_characterizes_its_capture_as_cooling():
    """1000 kg captured must come back **negative**, from the defaults alone.

    Two sign conventions live in this codebase: ``co2-from-air``, which
    ``DirectAirCapture`` emits already negative, and ``co2-uptake``, whose
    convention is a positive amount negated by ``characterize_co2_uptake``.
    Pairing either flow with the other's function inverts the curve silently --
    a removal would read as a century of warming, and nothing would complain.

    So this pins a capture demand end to end, through the committed example
    parameters and ``default_functions()`` with nothing passed: the total is
    cooling, and the capture is not sitting in ``uncharacterized``.

    The models are assembled here rather than loaded from
    ``examples/showcase_models.py``. What is being guarded is a sign
    convention in ``DirectAirCapture``, which is a library model; the showcase
    stages whichever example is currently most useful to a reader, and the two
    should not be able to break each other.
    """
    from pathlib import Path

    from trailrunner.models.dac import CO2_AIR, CO2_CAPTURED, DirectAirCapture
    from trailrunner.models.electricity import GasPower, GridElectricity
    from trailrunner.orchestration.glossary import Glossary
    from trailrunner.orchestration.orchestrator import Orchestrator
    from trailrunner.params.location import LocationHierarchy
    from trailrunner.params.parameter_set import ParameterSet

    examples = Path(__file__).resolve().parent.parent / "examples"
    hierarchy = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})

    def params(name):
        return ParameterSet.from_parquet(examples / name, hierarchy=hierarchy)

    models = [
        DirectAirCapture(params=params("dac_params.parquet")),
        GridElectricity(params=params("grid_electricity_params.parquet")),
        GasPower(params=params("gas_power_params.parquet")),
    ]
    report = Orchestrator(Glossary(models)).calculate(
        Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", **in_year(2030)), amount=1000.0, unit=KG)
    )
    assert report.inventory[(Flow(iri=CO2_AIR, location="CH", **in_year(2030)), KG)] == -1000.0

    dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
    assert dynamic.uncharacterized == []
    assert dynamic.total < 0.0


def test_the_showcase_chain_characterizes_its_cement_as_warming():
    """The mirror of the capture guard, for the example the showcase stages.

    ``CementPlant`` writes calcination and combustion CO2 on ``co2-fossil``
    with **positive** amounts, which is the ordinary convention. Getting that
    backwards would be as silent as getting the removal convention backwards
    and twice as embarrassing, since a cement works that came back cooling
    would be quoted at us forever.

    Runs the showcase's own model list, so it also fails if
    ``examples/showcase_models.py`` stops resolving the chain at all.
    """
    from pathlib import Path

    from trailrunner.cli import load_models
    from trailrunner.models.cement import CEMENT, CO2_FOSSIL
    from trailrunner.orchestration.glossary import Glossary
    from trailrunner.orchestration.orchestrator import Orchestrator

    models = load_models(
        Path(__file__).resolve().parent.parent / "examples" / "showcase_models.py"
    )
    report = Orchestrator(Glossary(models)).calculate(
        Demand(flow=Flow(iri=CEMENT, location="DK", **in_year(2030)), amount=1000.0, unit=KG)
    )
    direct = report.inventory[(Flow(iri=CO2_FOSSIL, location="DK", **in_year(2030)), KG)]
    # The plant's own two exchanges are 397.5 kg of calcination and 138.6 kg
    # of combustion. The inventory key aggregates every co2-fossil exchange at
    # this place and year, so the grid's gas share lands here too and the
    # total only ever exceeds the plant's own 536.1.
    assert direct > 536.1

    dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
    # Not "nothing uncharacterized": the gas chain behind the kiln fuel emits
    # ethane, mercury, NMVOC and the wellhead's resource flow, and
    # default_functions() characterizes none of those. What must never land
    # there is a greenhouse gas.
    assert not _greenhouse_gases_in(dynamic.uncharacterized)
    assert dynamic.total > 0.0


def test_the_metered_year_reaches_the_meter_and_still_characterizes():
    """A past year is answered by the meter, and its stack figure scores.

    The measured beat is only worth a beat if the measurement lands in the
    inventory like any other exchange. One merged stack number, characterized
    by the same ``co2-fossil`` function the computed model's two exchanges
    use.
    """
    from pathlib import Path

    from trailrunner.cli import load_models
    from trailrunner.models.cement import CEMENT, CO2_FOSSIL
    from trailrunner.orchestration.glossary import Glossary
    from trailrunner.orchestration.orchestrator import Orchestrator

    models = load_models(
        Path(__file__).resolve().parent.parent / "examples" / "showcase_models.py"
    )
    report = Orchestrator(Glossary(models)).calculate(
        Demand(flow=Flow(iri=CEMENT, location="DK", **in_year(2023)), amount=1000.0, unit=KG)
    )
    # Same aggregation as above: 562.0 kg off the meter, plus whatever the
    # grid burns to supply the plant's metered electricity.
    assert report.inventory[(Flow(iri=CO2_FOSSIL, location="DK", **in_year(2023)), KG)] > 562.0

    dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
    assert not _greenhouse_gases_in(dynamic.uncharacterized)
    assert dynamic.total > 0.0
