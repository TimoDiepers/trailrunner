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

Two conventions of this module's own, which are *not* the library's:

- **Characterization functions are keyed on ``(flow IRI, unit)``, not on the
  IRI alone.** The IPCC AR6 functions are per kilogram, so handing them an
  exchange denominated in grams would characterize 10 g of fossil CO2 as
  10 kg — a number 1000x too large with nothing anywhere saying so. Unit
  compatibility here is string equality, exactly as in ``Method``: a mismatch
  is *reported*, never converted. An exchange whose ``(iri, unit)`` has no
  function lands in ``wrong_unit`` when the IRI is known in some other unit,
  and in ``uncharacterized`` when the gas is not covered at all — two
  different problems for whoever reads the result.
- **The Levasseur horizon is anchored to the study, not to the wall clock.**
  ``dynamic_characterization.characterize``'s ``time_horizon_start`` defaults
  to ``datetime.now()`` evaluated at *module import*, which would make every
  ``fixed_time_horizon=True`` result depend on the day it was run. This module
  derives the anchor from the report instead — the earliest emission that
  actually enters the characterization, as ``datetime(year, 1, 1)`` — passes
  it explicitly, and records it on the result as ``time_horizon_start``. A
  caller who knows a better anchor (a functional unit dated earlier than any
  emission, say) can pass one.

  "Actually enters the characterization" is load-bearing. An exchange that is
  reported rather than characterized — wrong unit, or no function at all —
  never reaches the frame, so anchoring to it would end the shared horizon
  before the emissions that *are* characterized, and they would come back
  empty. A reported gap must not be able to silently zero the part of the
  answer that is not a gap.
- **An emission whose characterized rows do not survive is reported too.**
  Under a fixed horizon an emission past the horizon's end gets a zero-length
  horizon from the library and comes back as a single undated row. Dropping it
  quietly would leave a reader with a total that looks as though the emission
  had been counted, so those exchanges are recorded in ``beyond_horizon``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trailrunner.core.flow import Flow
from trailrunner.core.units import KG, W_PER_M2, symbol
from trailrunner.orchestration.report import Report

CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"
CO2_BIOGENIC_UPTAKE = "https://vocab.sentier.dev/flows/co2-uptake"
# Spelled out here, and again in trailrunner/models/dac.py, the same way
# CO2_FOSSIL is spelled out here and in trailrunner/models/electricity.py: this
# table is a fact about gases, not a dependency on whoever happens to emit them,
# so assessment does not import from models. The two sign conventions these
# constants sit either side of are documented on default_functions().
CO2_AIR = "https://vocab.sentier.dev/flows/co2-from-air"
CH4_FOSSIL = "https://vocab.sentier.dev/flows/ch4-fossil"
N2O = "https://vocab.sentier.dev/flows/n2o"
CO = "https://vocab.sentier.dev/flows/co"

METRICS = ("radiative_forcing", "GWP", "pGWP", "pGTP", "prospective_radiative_forcing")
"""The metrics ``dynamic_characterization`` accepts.

``pGWP``, ``pGTP`` and ``prospective_radiative_forcing`` are the Watanabe
et al. scenario-based metrics, and they require
``dynamic_characterization.prospective.set_scenario()`` to have been called
first. ``trailrunner`` exposes no way to call it — there is no scenario
argument anywhere in this module — so reaching those three means importing
``dynamic_characterization.prospective`` yourself and setting the scenario
before calling ``assess_dynamic``. They are listed here because the library
accepts them, not because this module wires them up.
"""

METRIC_UNITS = {
    "radiative_forcing": W_PER_M2,
    "prospective_radiative_forcing": W_PER_M2,
    "GWP": KG,
    "pGWP": KG,
    "pGTP": KG,
}
"""The unit of ``series`` — the *marginal* quantity, per year."""

CUMULATIVE_METRIC_UNITS = {
    # No vocabulary unit for W·yr/m2: a display label for a cumulative
    # result, never an exchange unit, so it stays a label.
    "radiative_forcing": "W·yr/m2",
    "prospective_radiative_forcing": "W·yr/m2",
    "GWP": KG,
    "pGWP": KG,
    "pGTP": KG,
}
"""The unit of ``curve`` and ``total`` — the cumulative sum of ``series``.

For the radiative-forcing metrics that sum is an integral over time, so it is
W·yr/m2 and not W/m2. For the GWP metrics the marginal series is already in
kg of CO2-equivalent per year and its cumulative sum is kg of CO2-equivalent,
so the two units coincide — which is exactly why a single ``unit`` field
looked right for long enough to ship. The "CO2-equivalent" is what the GWP
metric characterizes an emission into, not a property of the unit ``KG``
itself; the unit is a plain kilogram, same as any mass.
"""


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


def default_functions() -> dict[tuple[str, str], Callable]:
    """``(IRI, unit)`` -> IPCC AR6 characterization function.

    A declared table rather than a lookup through a background database: the
    flows are identified by vocabulary IRI, and the mapping from an IRI to the
    physics of that gas is a fact about the gas, not about anyone's database.

    The unit is half the key because the IPCC AR6 functions are defined per
    kilogram (their radiative efficiencies are ``radiative_efficiency_kg``).
    Applying one to an amount denominated in anything else is not a rounding
    error, it is a factor of 1000, so ``"kg"`` is stated rather than assumed.

    **Two sign conventions meet in this table, so each removal flow is paired
    with the function that matches how it is written down.**

    - ``co2-from-air`` gets :func:`characterize_co2`, the *ordinary* CO2
      function, **not** ``characterize_co2_uptake``. The flow is a removal, but
      :class:`trailrunner.models.dac.DirectAirCapture` already writes it
      **negative** (``amount=-demand.amount``), so it is a CO2 exchange like any
      other and the ordinary function gives it a negative forcing.
      ``characterize_co2_uptake`` negates its input, which applied to an
      already-negative amount would turn 1000 kg of removal into 1000 kg of
      warming — the sign error would be silent, and it would invert the whole
      curve the showcase turns on.
    - ``co2-uptake`` gets ``characterize_co2_uptake``, which is the same
      statement read the other way: that flow's convention is a **positive**
      amount meaning uptake, and the negation is what makes it cooling.

    A model emitting a removal on one of these IRIs must therefore use that
    IRI's convention. If a new model writes uptake on ``co2-uptake`` negatively,
    or on ``co2-from-air`` positively, the curve flips and nothing complains —
    which is why both conventions are written down here rather than inferred.
    """
    ipcc = _require("dynamic_characterization.ipcc_ar6")
    return {
        (CO2_FOSSIL, KG): ipcc.characterize_co2,
        # Negative-amount convention: see the docstring above.
        (CO2_AIR, KG): ipcc.characterize_co2,
        # Positive-amount convention: characterize_co2_uptake negates.
        (CO2_BIOGENIC_UPTAKE, KG): ipcc.characterize_co2_uptake,
        (CH4_FOSSIL, KG): ipcc.characterize_ch4,
        (N2O, KG): ipcc.characterize_n2o,
        (CO, KG): ipcc.characterize_co,
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
    """The unit of ``series``: the marginal quantity, per year."""
    cumulative_unit: str = ""
    """The unit of ``curve`` and ``total``: the cumulative sum of ``series``.

    Separate from ``unit`` because for the radiative-forcing metrics they
    differ — W/m2 marginal, W·yr/m2 accumulated — and labelling an integral
    with its integrand's unit is wrong by a dimension.
    """
    horizon: int = 100
    time_horizon_start: datetime | None = None
    """What the Levasseur horizon was anchored to, whether or not it was used.

    Recorded on every result so a reader can see it without re-deriving it.
    It only *changes* anything when ``fixed_time_horizon=True``; with the
    conventional convention each emission starts its own horizon and the
    anchor is inert.
    """
    uncharacterized: list[tuple[Flow, str, float]] = field(default_factory=list)
    """``(Flow, unit, amount)`` per exchange whose flow no function covers.

    Reported, never zeroed, and per exchange with its amount rather than as a
    deduplicated list of IRIs — the same shape as
    ``Assessment.uncharacterized``, so "how much did this path leave out" is
    the same question with the same answer everywhere.
    """
    wrong_unit: list[tuple[Flow, str, float]] = field(default_factory=list)
    """``(Flow, unit, amount)`` per exchange whose flow *is* covered, but not
    in the unit the exchange is denominated in.

    Kept apart from ``uncharacterized`` because they are different problems:
    "nobody characterized this gas" is a gap in the method, while "this gas is
    characterized, but per kilogram, and your model emitted grams" is a
    mismatch between the model and the method that somebody can fix today.
    """
    undated: list[tuple[Flow, str, float]] = field(default_factory=list)
    """``(Flow, unit, amount)`` for exchanges with no ``time``. A dynamic
    assessment cannot place them on the axis, so it says so instead of
    assuming a year."""
    beyond_horizon: list[tuple[Flow, str, float]] = field(default_factory=list)
    """``(Flow, unit, amount)`` per exchange that entered the characterization
    but contributed no dated row to ``series``.

    Under ``fixed_time_horizon=True`` every horizon ends at the same date, so
    an emission past that date gets a zero-length horizon and comes back as a
    single undated row. That row cannot go on a curve — but dropping it in
    silence leaves a reader with a total that reads as though the emission had
    been counted. This list is the difference between "counted as nothing" and
    "we are telling you it was not counted".
    """

    truncated: bool = False
    """``report.truncated``, carried through, for the same reason
    ``Assessment`` carries it: a curve from a traversal that stopped at
    ``max_nodes`` is a different claim from a complete one, and the two are
    indistinguishable as DataFrames."""
    unresolved: int = 0
    """How many demands the traversal could not resolve."""
    proxies: int = 0
    """How many nodes were answered by something other than an exact model match."""

    def summary(self) -> str:
        """The curve's headline number and everything left out of it.

        The same shape as ``Report.summary()`` and ``Assessment.summary()``:
        the caveats in front of the reader rather than behind an attribute
        they have to know to look at. Returns the block rather than printing
        it.
        """
        anchor = (
            self.time_horizon_start.date().isoformat()
            if self.time_horizon_start is not None
            else "none (no dated emission)"
        )
        lines = [
            f"{self.total:g} {symbol(self.cumulative_unit)}".strip(),
            f"metric: {self.metric}, horizon: {self.horizon} years",
            f"horizon anchored at: {anchor}",
        ]
        for label, entries in (
            ("uncharacterized", self.uncharacterized),
            ("wrong unit", self.wrong_unit),
            ("undated", self.undated),
            ("beyond-horizon", self.beyond_horizon),
        ):
            count = len(entries)
            lines.append(
                f"{count} {label} "
                f"{'exchange' if count == 1 else 'exchanges'}"
            )
        lines.append(f"{self.unresolved} unresolved")
        lines.append(f"{self.proxies} {'proxy' if self.proxies == 1 else 'proxies'}")
        if self.truncated:
            lines.append("traversal was truncated: max_depth or max_nodes was reached")
        return "\n".join(lines)


def _activity(node: Any) -> str:
    """A label for the ``activity`` column that is unique per *node*.

    ``node.model`` alone collapses every node of the same model class into one
    label — a supply chain with eleven gas boilers in it would come back as a
    single ``"GasBoiler"`` series — and nothing downstream could attribute a
    row back to the place in the chain it came from. The node id is what makes
    that place identifiable, so it travels with the model name.
    """
    return f"{node.model or 'node'}#{node.id}"


def _check_function_keys(functions: Mapping[Any, Callable]) -> None:
    """``functions`` is keyed on ``(iri, unit)``; say so when it is not.

    The natural mistake is an IRI-keyed mapping, which is what this module
    used to take. Unpacking one raises ``ValueError: too many values to
    unpack``, which names neither the argument nor the shape it wanted.
    """
    for key in functions:
        if not (isinstance(key, tuple) and len(key) == 2):
            raise ValueError(
                f"`functions` is keyed on (flow IRI, unit) pairs, like "
                f"{(CO2_FOSSIL, 'kg')!r}; got the key {key!r}. A mapping keyed "
                "on the IRI alone cannot say which denomination its functions "
                "are defined for, and the IPCC AR6 ones are per kilogram."
            )


def _lost_exchanges(
    series: Any,
    entered: dict[tuple[str, str], list[tuple[datetime, tuple[Flow, str, float]]]],
) -> list[tuple[Flow, str, float]]:
    """The exchanges behind the undated rows the characterization handed back.

    One input row that characterizes to nothing explodes into exactly one
    undated row, and that row still carries its ``flow`` and ``activity``. So
    the count of undated rows per ``(flow, activity)`` is the number of that
    group's exchanges that were lost, and — because a fixed horizon always
    runs out at the *late* end — they are that group's latest-dated ones.
    ``activity`` is node-unique, so a group is normally a single exchange and
    the ordering never has to break a tie at all.
    """
    undated_rows = series[series["date"].isna()]
    if not len(undated_rows):
        return []
    lost: list[tuple[Flow, str, float]] = []
    for (flow, activity), group in undated_rows.groupby(["flow", "activity"], sort=True):
        candidates = sorted(entered.get((flow, activity), []), key=lambda pair: pair[0])
        lost.extend(record for _, record in candidates[-len(group):])
    return lost


def inventory_dataframe(report: Report) -> Any:
    """The report's biosphere exchanges as the four columns the library wants.

    ``Flow.time`` is a year and ``characterize`` wants a timestamp, so year Y
    becomes ``datetime(Y, 1, 1)``. That is an assumption, not a fact — a finer
    ``Flow.time`` would change it — and it lives in this one function so the
    change would be one edit.

    Exchanges with no ``flow.time`` are **silently left out**: there is no
    place on the axis to put them and this function returns a frame, not a
    report of what it dropped. It is a shaping helper, not an assessment. Use
    ``assess_dynamic``, which records every one of them in
    ``DynamicAssessment.undated`` (along with anything the characterization
    functions could not cover), when the omissions matter — and they always
    matter to a number somebody will quote.
    """
    pandas = _require("pandas")
    rows = [
        {
            "date": datetime(exchange.flow.time, 1, 1),
            "amount": exchange.amount,
            "flow": exchange.flow.iri,
            "activity": _activity(node),
        }
        for node in report.nodes
        for exchange in node.result.biosphere
        if exchange.flow.time is not None
    ]
    frame = pandas.DataFrame(rows, columns=["date", "amount", "flow", "activity"])
    return frame.astype({"date": "datetime64[s]", "amount": "float64"})


def assess_dynamic(
    report: Report,
    metric: str = "radiative_forcing",
    horizon: int = 100,
    fixed_time_horizon: bool = False,
    functions: Mapping[tuple[str, str], Callable] | None = None,
    time_horizon_start: datetime | None = None,
) -> DynamicAssessment:
    """Characterize the time-stamped inventory over ``horizon`` years.

    ``functions`` is a mapping keyed on ``(flow IRI, unit)`` — the same shape
    ``default_functions()`` returns — because a characterization function is
    defined for a particular denomination and the IPCC AR6 ones are per
    kilogram. An exchange whose ``(iri, unit)`` pair has no entry is left out
    of the characterization and reported: in ``wrong_unit`` if some other unit
    of that IRI does have a function, in ``uncharacterized`` if none does.
    Nothing is converted between units; a mismatch is a fact about the
    inventory and the method, and this module's job is to state it.

    ``fixed_time_horizon=False`` is the conventional convention: each emission
    is characterized over its own horizon. ``True`` is Levasseur: every horizon
    ends at the same date, so an earlier emission is counted for longer. Both
    are exposed because neither is the obviously right one.

    ``time_horizon_start`` is where that shared Levasseur horizon starts.
    Left as ``None`` it is derived from the report — the earliest emission
    that *actually enters the characterization*, at 1 January — so that a
    given report and horizon give the same answer today and next year. It is
    deliberately not the earliest dated emission of any kind: an exchange that
    is reported rather than characterized never reaches the frame, and letting
    one anchor the horizon would end it before the emissions that *are*
    characterized, zeroing them. The value actually used is recorded on the
    result. Pass one explicitly when the study has a better anchor than its
    own first characterized emission, such as a functional unit dated before
    it.
    """
    if metric not in METRICS:
        raise ValueError(f"{metric!r} is not a known metric; allowed: {', '.join(METRICS)}")

    pandas = _require("pandas")
    characterization = _require("dynamic_characterization")

    if functions is not None:
        _check_function_keys(functions)
    table = dict(functions) if functions is not None else default_functions()
    known_iris = {iri for iri, _ in table}

    assessment = DynamicAssessment(
        metric=metric,
        unit=METRIC_UNITS[metric],
        cumulative_unit=CUMULATIVE_METRIC_UNITS[metric],
        horizon=horizon,
        truncated=report.truncated,
        unresolved=len(report.unresolved),
        proxies=len(report.proxies),
    )

    rows: list[dict[str, Any]] = []
    # Every exchange that made it into the frame, by (flow, activity) and
    # emission date, so a row the characterization drops can be named again.
    entered: dict[tuple[str, str], list[tuple[datetime, tuple[Flow, str, float]]]] = {}
    # Which function each IRI in the frame is characterized with. The library
    # keys its own table on the frame's ``flow`` column alone, so two units of
    # one IRI with two different functions cannot both be expressed there.
    used: dict[str, tuple[str, Callable]] = {}

    for node in report.nodes:
        activity = _activity(node)
        for exchange in node.result.biosphere:
            key = (exchange.flow.iri, exchange.unit)
            function = table.get(key)
            record = (exchange.flow, exchange.unit, exchange.amount)
            if function is None:
                # Known gas, unknown denomination, versus unknown gas: the
                # reader can act on the first one today.
                if exchange.flow.iri in known_iris:
                    assessment.wrong_unit.append(record)
                else:
                    assessment.uncharacterized.append(record)
            # An exchange can be both undated and uncharacterized, and it is
            # recorded under both: each list answers its own question, and
            # dropping it from one because it appeared in the other is how a
            # gap goes unnoticed.
            if exchange.flow.time is None:
                assessment.undated.append(record)
                continue
            if function is None:
                continue
            previous = used.get(exchange.flow.iri)
            if previous is not None and previous[1] is not function:
                raise ValueError(
                    f"{exchange.flow.iri} appears in the inventory in both "
                    f"{previous[0]!r} and {exchange.unit!r} with different "
                    "characterization functions; the characterization library "
                    "keys its functions on the flow alone, so the two cannot be "
                    "characterized in one call — assess them separately"
                )
            used[exchange.flow.iri] = (exchange.unit, function)
            date = datetime(exchange.flow.time, 1, 1)
            entered.setdefault((exchange.flow.iri, activity), []).append((date, record))
            rows.append(
                {
                    "date": date,
                    "amount": exchange.amount,
                    "flow": exchange.flow.iri,
                    "activity": activity,
                }
            )

    # Derived from the rows that are actually going to be characterized, not
    # from every dated exchange in the report: a wrong-unit or uncharacterized
    # exchange dated earlier than anything real would otherwise pull the
    # shared horizon's end back past the emissions that do count, and hand
    # back 0.0 with nothing in any list saying why.
    anchor = time_horizon_start
    if anchor is None and rows:
        anchor = min(row["date"] for row in rows)
    assessment.time_horizon_start = anchor

    empty_curve = pandas.DataFrame(columns=["date", "amount"])
    frame = pandas.DataFrame(rows, columns=["date", "amount", "flow", "activity"]).astype(
        {"date": "datetime64[s]", "amount": "float64"}
    )
    if frame.empty:
        # Nothing entered the frame, so there is nothing to anchor and nothing
        # to lose: every exchange is already in one of the reported lists.
        assessment.series = frame
        assessment.curve = empty_curve
        return assessment

    series = characterization.characterize(
        frame,
        metric=metric,
        characterization_functions={iri: func for iri, (_, func) in used.items()},
        time_horizon=horizon,
        fixed_time_horizon=fixed_time_horizon,
        time_horizon_start=anchor,
    )
    assessment.series = series

    # An emission past the end of a fixed horizon gets a zero-length horizon
    # from the library and comes back as a single NaT/NaN row. Those rows
    # carry no date, so they cannot go on a curve; drop them, then guard on
    # the *curve* rather than on the series, because a non-empty series can
    # still leave nothing to accumulate. They are named before they are
    # dropped: a characterized exchange that contributed nothing is exactly
    # the kind of omission this module exists to state out loud.
    if len(series):
        assessment.beyond_horizon.extend(_lost_exchanges(series, entered))
    dated = series.dropna(subset=["date"]) if len(series) else series
    curve = (
        dated.groupby("date", as_index=False)["amount"].sum().sort_values("date")
        if len(dated)
        else empty_curve
    )
    if len(curve):
        curve["amount"] = curve["amount"].cumsum()
        assessment.curve = curve.reset_index(drop=True)
        assessment.total = float(assessment.curve["amount"].iloc[-1])
    else:
        assessment.curve = empty_curve
    return assessment
