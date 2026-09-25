"""A model's declared validity in space, time and context."""

from dataclasses import dataclass

from trailrunner.core.flow import Flow
from trailrunner.core.time import TimeRange
from trailrunner.core.units import UnitCatalog, default_catalog


@dataclass(frozen=True)
class ContextRange:
    """The values of one context condition a model can answer, inclusive.

    ``minimum == maximum`` declares a single value: gas delivered at 5 bar
    (5e5 Pa in the vocabulary's own unit). The unit is a vocabulary IRI. A
    flow asking in another unit of the same quantity kind is converted
    exactly before it is compared (4e5 Pa and a range in Pa; 1500 m against
    a range in km); one asking in another kind is not covered. Converting
    used to be refused here because a unit was a string and converting it
    meant guessing; with the catalog it does not.
    """

    name: str
    unit: str
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError(
                f"context range {self.name!r} has minimum {self.minimum!r} "
                f"above maximum {self.maximum!r}"
            )


@dataclass(frozen=True)
class Coverage:
    """Where, when and under which conditions a model is valid.

    ``locations`` is a frozenset rather than a set so that Coverage stays
    hashable. ``None`` on either field means "no restriction".

    ``context`` is the other way round from location and time. A flow with
    no location is not covered by a model restricted to some, because a
    model that needs a place cannot answer "anywhere". A flow that names no
    pressure *is* covered by a model restricted to 5 bar, because the
    condition is the demander's to set, and one that sets none accepts any.
    """

    locations: frozenset[str] | None = None
    time_range: TimeRange | None = None
    """A coarser range covers a finer time: ``year_range(2026, 2050)`` covers ``2050-12-31``."""
    context: tuple[ContextRange, ...] = ()
    units: frozenset[str] | None = None
    """Unit IRIs the model answers in; ``None`` means any unit, passed through.

    Not a restriction on *whether* the model answers but on *what it is
    handed*: a demand in another unit of the same quantity kind is converted
    exactly before ``apply`` sees it (``ModelProvider``), and one of another
    kind is not answered at all. ``covers`` does not read this field, because
    a unit is on the demand, not on the flow.
    """

    def __post_init__(self) -> None:
        if self.time_range is not None and not isinstance(self.time_range, TimeRange):
            try:
                first, last = self.time_range
            except (TypeError, ValueError):
                first = last = self.time_range
            raise TypeError(
                "Coverage.time_range is a TimeRange; write "
                f"time_range=year_range({first}, {last})"
            )
        if self.units is not None and (
            not isinstance(self.units, frozenset)
            or not all(isinstance(unit, str) for unit in self.units)
        ):
            raise TypeError(
                "Coverage.units is a frozenset of unit IRIs (str); write "
                "units=frozenset({KG})"
            )

    def covers(self, flow: Flow, units: UnitCatalog | None = None) -> bool:
        catalog = units if units is not None else default_catalog()
        if self.locations is not None:
            if flow.location is None or flow.location not in self.locations:
                return False
        if self.time_range is not None:
            if flow.time is None:
                return False
            if not self.time_range.contains(flow.time, flow.time_standard):
                return False
        for declared in self.context:
            asked = flow.get_context(declared.name)
            if asked is None:
                continue
            value = catalog.try_convert(asked.value, asked.unit, declared.unit)
            if value is None:
                return False
            if not declared.minimum <= value <= declared.maximum:
                return False
        return True

    def context_range(self, name: str) -> ContextRange | None:
        """The declared range for condition ``name``, or ``None``."""
        for declared in self.context:
            if declared.name == name:
                return declared
        return None
