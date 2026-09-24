"""A model's declared validity in space, time and context."""

from dataclasses import dataclass

from trailrunner.core.flow import Flow


@dataclass(frozen=True)
class ContextRange:
    """The values of one context condition a model can answer, inclusive.

    ``minimum == maximum`` declares a single value: gas delivered at 5 bar.
    The unit is compared as written, never converted; a flow asking in
    another unit is not covered, because guessing a conversion is exactly
    the kind of silent concession this library refuses to make.
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
    time_range: tuple[int, int] | None = None
    context: tuple[ContextRange, ...] = ()
    units: frozenset[str] | None = None
    """Unit IRIs the model answers in; ``None`` means any unit, passed through.

    Not a restriction on *whether* the model answers but on *what it is
    handed*: a demand in another unit of the same quantity kind is converted
    exactly before ``apply`` sees it (``ModelProvider``), and one of another
    kind is not answered at all. ``covers`` does not read this field, because
    a unit is on the demand, not on the flow.
    """

    def covers(self, flow: Flow) -> bool:
        if self.locations is not None:
            if flow.location is None or flow.location not in self.locations:
                return False
        if self.time_range is not None:
            if flow.time is None:
                return False
            earliest, latest = self.time_range
            if not earliest <= flow.time <= latest:
                return False
        for declared in self.context:
            asked = flow.get_context(declared.name)
            if asked is None:
                continue
            if asked.unit != declared.unit:
                return False
            if not declared.minimum <= asked.value <= declared.maximum:
                return False
        return True

    def context_range(self, name: str) -> ContextRange | None:
        """The declared range for condition ``name``, or ``None``."""
        for declared in self.context:
            if declared.name == name:
                return declared
        return None
