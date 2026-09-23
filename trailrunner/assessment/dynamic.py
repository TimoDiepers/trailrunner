"""Time-explicit characterization.

Every ``Exchange`` already carries ``flow.time``, so the inventory *is* a time
series. This module reshapes it into the four columns
``dynamic_characterization.characterize()`` expects and hands it over. That is
the whole trick, and it is only available because the traversal keeps the year
each emission happens in rather than summing it away.

Two things about ``dynamic_characterization``'s own conventions are worth
writing down, because they surprise a reader expecting a plain
``emission_year .. emission_year + horizon - 1`` calendar range:

- The marginal radiative-forcing series is the diff of a cumulative decay
  curve, and the IPCC AR6 CO2 impulse-response function is exactly zero at
  year 0 (its own emission year). The diff at that point is therefore exactly
  zero and gets filtered out (the library drops zero rows), so the series'
  *first* row falls in ``emission_year + 1``, not ``emission_year``.
- The library builds its year offsets with ``numpy``'s ``timedelta64[Y]``,
  which is a fixed 365.2425-day average Gregorian year, not a calendar year.
  Added to a real calendar date, the accumulated drift means a 20-year
  horizon's *last* row can land a day short of its naive last anniversary
  (e.g. ``2048-12-31`` instead of ``2049-01-01``), one calendar year earlier
  than a naive reading of ``horizon`` would suggest.

Both are the installed library's behaviour, not this module's; the tests
assert the observed values rather than the naive ones.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trailrunner.orchestration.report import Report

CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"
CO2_BIOGENIC_UPTAKE = "https://vocab.sentier.dev/flows/co2-uptake"
CH4_FOSSIL = "https://vocab.sentier.dev/flows/ch4-fossil"
N2O = "https://vocab.sentier.dev/flows/n2o"
CO = "https://vocab.sentier.dev/flows/co"

METRICS = ("radiative_forcing", "GWP", "pGWP", "pGTP", "prospective_radiative_forcing")

METRIC_UNITS = {
    "radiative_forcing": "W/m2",
    "prospective_radiative_forcing": "W/m2",
    "GWP": "kg CO2eq",
    "pGWP": "kg CO2eq",
    "pGTP": "kg CO2eq",
}


def _require(module: str):
    """Import an extra's module, or say which extra is missing.

    Imported here rather than at module top so that ``trailrunner.assessment``
    keeps working with pyarrow alone.
    """
    try:
        return __import__(module, fromlist=["_"])
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            f"{module} is needed for dynamic assessment; install it with "
            "`uv sync --extra dynamic`"
        ) from exc


def default_functions() -> dict[str, Callable]:
    """IRI -> IPCC AR6 characterization function.

    A declared table rather than a lookup through a background database: the
    flows are identified by vocabulary IRI, and the mapping from an IRI to the
    physics of that gas is a fact about the gas, not about anyone's database.
    """
    ipcc = _require("dynamic_characterization.ipcc_ar6")
    return {
        CO2_FOSSIL: ipcc.characterize_co2,
        CO2_BIOGENIC_UPTAKE: ipcc.characterize_co2_uptake,
        CH4_FOSSIL: ipcc.characterize_ch4,
        N2O: ipcc.characterize_n2o,
        CO: ipcc.characterize_co,
    }


@dataclass
class DynamicAssessment:
    """A characterized time series, its cumulative curve, and what was left out."""

    series: Any = None
    """DataFrame: date, amount, flow, activity — the characterized inventory."""
    curve: Any = None
    """DataFrame: date, amount — the cumulative integral of ``series``."""
    total: float = 0.0
    metric: str = "radiative_forcing"
    unit: str = ""
    horizon: int = 100
    uncharacterized: list[str] = field(default_factory=list)
    """Flow IRIs with no characterization function. Reported, never zeroed."""
    undated: list[tuple[str, str, float]] = field(default_factory=list)
    """(IRI, unit, amount) for exchanges with no ``time``. A dynamic assessment
    cannot place them on the axis, so it says so instead of assuming a year."""


def inventory_dataframe(report: Report) -> Any:
    """The report's biosphere exchanges as the four columns the library wants.

    ``Flow.time`` is a year and ``characterize`` wants a timestamp, so year Y
    becomes ``datetime(Y, 1, 1)``. That is an assumption, not a fact — a finer
    ``Flow.time`` would change it — and it lives in this one function so the
    change would be one edit.
    """
    pandas = _require("pandas")
    rows = []
    for node in report.nodes:
        activity = node.model or f"node {node.id}"
        for exchange in node.result.biosphere:
            if exchange.flow.time is None:
                continue
            rows.append(
                {
                    "date": datetime(exchange.flow.time, 1, 1),
                    "amount": exchange.amount,
                    "flow": exchange.flow.iri,
                    "activity": activity,
                }
            )
    frame = pandas.DataFrame(rows, columns=["date", "amount", "flow", "activity"])
    return frame.astype({"date": "datetime64[s]", "amount": "float64"})


def assess_dynamic(
    report: Report,
    metric: str = "radiative_forcing",
    horizon: int = 100,
    fixed_time_horizon: bool = False,
    functions: Mapping[str, Callable] | None = None,
) -> DynamicAssessment:
    """Characterize the time-stamped inventory over ``horizon`` years.

    ``fixed_time_horizon=False`` is the conventional convention: each emission
    is characterized over its own horizon. ``True`` is Levasseur: every horizon
    ends at the same date, so an earlier emission is counted for longer. Both
    are exposed because neither is the obviously right one.
    """
    if metric not in METRICS:
        raise ValueError(f"{metric!r} is not a known metric; allowed: {', '.join(METRICS)}")

    pandas = _require("pandas")
    characterization = _require("dynamic_characterization")

    table = functions if functions is not None else default_functions()

    assessment = DynamicAssessment(
        metric=metric, unit=METRIC_UNITS[metric], horizon=horizon
    )
    for node in report.nodes:
        for exchange in node.result.biosphere:
            if exchange.flow.time is None:
                assessment.undated.append((exchange.flow.iri, exchange.unit, exchange.amount))
            elif exchange.flow.iri not in table:
                if exchange.flow.iri not in assessment.uncharacterized:
                    assessment.uncharacterized.append(exchange.flow.iri)

    frame = inventory_dataframe(report)
    if frame.empty:
        assessment.series = frame
        assessment.curve = pandas.DataFrame(columns=["date", "amount"])
        return assessment

    series = characterization.characterize(
        frame,
        metric=metric,
        characterization_functions=dict(table),
        time_horizon=horizon,
        fixed_time_horizon=fixed_time_horizon,
    )
    assessment.series = series

    if len(series):
        curve = series.groupby("date", as_index=False)["amount"].sum().sort_values("date")
        curve["amount"] = curve["amount"].cumsum()
        assessment.curve = curve.reset_index(drop=True)
        assessment.total = float(assessment.curve["amount"].iloc[-1])
    else:
        assessment.curve = pandas.DataFrame(columns=["date", "amount"])
    return assessment
