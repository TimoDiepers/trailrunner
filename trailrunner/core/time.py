"""When a flow is: a string in a declared time standard, read as an interval.

``Flow.time`` used to be an ``int`` year, so a demand for a day or an instant
could not be stated at all. A time is now a string plus the IRI of the
standard it is written in -- by default the XSD datatypes, so ``"2030"`` in
``xsd:gYear``, ``"2030-06-15"`` in ``xsd:date``, ``"2030-06-15T08:00:00Z"``
in ``xsd:dateTime`` -- and a registry turns the pair into a half-open UTC
interval. Every comparison the library makes goes through that interval,
never through the string: a model declared for a year covers any day in it,
because the day lies inside the year.

More standards can be registered (a fiscal year, an ISO week): a parser is
all a standard needs to be.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

XSD = "http://www.w3.org/2001/XMLSchema#"
GYEAR = XSD + "gYear"
GYEAR_MONTH = XSD + "gYearMonth"
DATE = XSD + "date"
DATETIME = XSD + "dateTime"

Interval = tuple[datetime, datetime]
"""Half-open ``[start, end)``, timezone-aware UTC. An instant has start == end."""

_PARSERS: dict[str, Callable[[str], Interval]] = {}


def short(standard: str) -> str:
    return "xsd:" + standard[len(XSD):] if standard.startswith(XSD) else standard


def register_time_standard(iri: str, parser: Callable[[str], Interval]) -> None:
    """Teach the library a time standard: ``parser`` maps a value to its interval.

    The parser raises ``ValueError`` for a value it cannot read, and returns
    timezone-aware UTC datetimes.
    """
    _PARSERS[iri] = parser


def is_registered(iri: str) -> bool:
    return iri in _PARSERS


def interval(time: str, standard: str) -> Interval:
    parser = _PARSERS.get(standard)
    if parser is None:
        known = ", ".join(sorted(short(iri) for iri in _PARSERS))
        raise ValueError(
            f"{standard!r} is not a registered time standard (known: {known}); "
            "register one with trailrunner.core.time.register_time_standard()"
        )
    if not isinstance(time, str):
        raise ValueError(f"a time is a string, got {time!r}")
    try:
        return parser(time)
    except ValueError as error:
        raise ValueError(f"{time!r} is not a valid {short(standard)} value: {error}") from None


def _year(text: str) -> Interval:
    if not re.fullmatch(r"\d{4}", text):
        raise ValueError("expected YYYY")
    year = int(text)
    return datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)


def _year_month(text: str) -> Interval:
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if not match:
        raise ValueError("expected YYYY-MM")
    year, month = int(match[1]), int(match[2])
    if not 1 <= month <= 12:
        raise ValueError("month out of range")
    end = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
    return datetime(year, month, 1, tzinfo=UTC), end


def _date(text: str) -> Interval:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("expected YYYY-MM-DD")
    day = date.fromisoformat(text)
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _datetime(text: str) -> Interval:
    if "T" not in text:
        raise ValueError("expected YYYY-MM-DDThh:mm:ss with a timezone")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError("a dateTime must carry a timezone, e.g. 'Z' or '+01:00'")
    moment = moment.astimezone(UTC)
    return moment, moment


register_time_standard(GYEAR, _year)
register_time_standard(GYEAR_MONTH, _year_month)
register_time_standard(DATE, _date)
register_time_standard(DATETIME, _datetime)


def contains(outer: Interval, inner: Interval) -> bool:
    """Whether ``inner`` lies inside ``outer``; an instant at ``outer``'s end does not."""
    return outer[0] <= inner[0] and inner[1] <= outer[1] and inner[0] < outer[1]


def decimal_year(moment: datetime) -> float:
    """2030-01-01 is 2030.0; the fraction counts this year's own length.

    Counting in the year's own length, not in days, is what makes a gYear's
    midpoint exactly ``Y + 0.5`` whether or not ``Y`` is a leap year -- and so
    what keeps interpolating between year rows exactly as it was when a time
    was an int.
    """
    start = datetime(moment.year, 1, 1, tzinfo=UTC)
    length = (datetime(moment.year + 1, 1, 1, tzinfo=UTC) - start).total_seconds()
    return moment.year + (moment - start).total_seconds() / length


def midpoint_year(span: Interval) -> float:
    return (decimal_year(span[0]) + decimal_year(span[1])) / 2


def in_year(year: int) -> dict[str, str]:
    """``Flow(iri=..., **in_year(2030))`` -- the common case, spelled once."""
    return {"time": str(year), "time_standard": GYEAR}


def when(flow: Any) -> dict[str, str | None]:
    """A flow's time and standard, to pass on: ``Flow(iri=..., **when(demand.flow))``."""
    return {"time": flow.time, "time_standard": flow.time_standard}


def year_of(flow: Any) -> int | None:
    """The calendar year a flow's time starts in, for code that counts in years (fleets)."""
    if flow.time is None:
        return None
    return interval(flow.time, flow.time_standard)[0].year


@dataclass(frozen=True)
class TimeRange:
    """A model's validity in time: from the start of ``start`` to the end of ``end``.

    Both ends inclusive, as ``time_range=(2026, 2050)`` was: ``year_range(2026,
    2050)`` covers every day of 2050.
    """

    start: str
    end: str
    standard: str = GYEAR

    def __post_init__(self) -> None:
        low, high = self.bounds()
        if high <= low:
            raise ValueError(f"time range {self.start!r}..{self.end!r} is empty")

    def bounds(self) -> Interval:
        return interval(self.start, self.standard)[0], interval(self.end, self.standard)[1]

    def contains(self, time: str, standard: str) -> bool:
        return contains(self.bounds(), interval(time, standard))

    def edges(self) -> tuple[str, str]:
        return self.start, self.end


def year_range(first: int, last: int) -> TimeRange:
    return TimeRange(str(first), str(last), GYEAR)


def infer_standard(text: str) -> str:
    """The XSD standard a value's lexical form implies; for the CLI, which prints it."""
    if re.fullmatch(r"\d{4}", text):
        return GYEAR
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return GYEAR_MONTH
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return DATE
    if "T" in text:
        return DATETIME
    raise ValueError(
        f"cannot tell which standard {text!r} is in; pass --time-standard with an IRI"
    )
