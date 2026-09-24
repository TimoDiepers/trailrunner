"""Run-wide knobs, including the run's normative choices."""

from dataclasses import dataclass, field
from typing import Any

ALLOCATION_RULES = frozenset({"none", "mass", "economic", "energy", "substitution"})
CAPITAL_RULES = frozenset({"per_output", "per_year", "first_life"})
REUSE_RULES = frozenset({"first_life", "shared"})
PROXY_DIMENSIONS = ("time", "location", "context", "product")
CONTEXT_PREFIX = "context."
"""``context.pressure`` is a dimension of its own: one context condition."""


def _check(value: str, allowed, label: str) -> None:
    if value not in allowed:
        raise ValueError(
            f"{value!r} is not a known {label}; allowed: {', '.join(sorted(allowed))}"
        )


def context_condition(dimension: str) -> str | None:
    """``"context.pressure"`` -> ``"pressure"``; ``None`` for any other dimension."""
    if dimension.startswith(CONTEXT_PREFIX):
        return dimension[len(CONTEXT_PREFIX) :]
    return None


def _check_dimension(dimension: str) -> None:
    if context_condition(dimension) == "":
        raise ValueError(f"{dimension!r} names no context condition; write context.<name>")
    if context_condition(dimension) is None:
        _check(dimension, PROXY_DIMENSIONS + ("context.<name>",), "proxy dimension")


@dataclass(frozen=True)
class AttributionSettings:
    """The run's normative choices, closed and typed.

    Closed rather than free-form keys because these are value judgements, and a
    typo must not silently select a different ethics. An unknown value is
    rejected where it is written, not where it is read.
    """

    allocation: str = "none"
    """How co-production is handled: none | mass | economic | energy | substitution."""

    capital: str = "per_output"
    """How a long-lived asset's construction is attributed: per_output | per_year | first_life."""

    reuse: str = "first_life"
    """Whether initial production falls entirely on the first life, or is shared."""

    def __post_init__(self) -> None:
        _check(self.allocation, ALLOCATION_RULES, "allocation rule")
        _check(self.capital, CAPITAL_RULES, "capital rule")
        _check(self.reuse, REUSE_RULES, "reuse rule")


@dataclass(frozen=True)
class ProxySettings:
    """How far, and in which order, a demand may be generalised to find a model.

    The order is the practitioner's preference hierarchy, not the library's:
    relaxing the year and relaxing the product are different concessions, and
    which one is acceptable first is a modelling decision.

    An entry is one dimension, or a tuple of them to relax *together*:
    ``("time", "location", ("location", "time"), "product")`` tries a
    neighbouring region and year before a wider product category. A combined
    entry moves every member at least one step, within each member's own
    budget, and tries the fewest total steps first; a tie goes to the
    candidate that moved the member written first the least. None is in the
    default order: composing is a concession the practitioner opts into.

    ``context`` sits before ``product`` in the default order because meeting
    a condition a little differently -- gas at 5 bar for a burner asking 4 --
    keeps the product itself, which a broader concept does not. It relaxes
    nothing until ``context_tolerance`` names a condition, and then it moves
    one tolerated condition at a time, never two together.

    To relax conditions together, name each as a dimension of its own,
    ``context.<name>``, and combine them like any other:
    ``("context.pressure", "context.temperature",
    ("context.pressure", "context.temperature"))`` tries pressure alone,
    temperature alone, and only then both. A ``context.<name>`` entry needs
    a ``context_tolerance`` for that name, and may not share a combined entry
    with plain ``context``, which would move the same condition twice.

    Frozen to prevent reassignment, but not hashable — ``max_steps`` is a dict.
    """

    order: tuple[str | tuple[str, ...], ...] = PROXY_DIMENSIONS
    max_steps: dict[str, int] = field(
        default_factory=lambda: {"time": 1, "location": 3, "context": 1, "product": 2}
    )
    """How many steps away from the original demand each dimension may go.

    A step means the same thing in every dimension: one level up the location
    hierarchy, one level up the product taxonomy's ``skos:broader``, or one
    year or context value snapped to. A single step can offer more than one
    candidate — a concept with two broader concepts is one level up either
    way — and all of a permitted level's candidates are tried. A dimension
    absent from this dict is not relaxed at all, except that a
    ``context.<name>`` absent here takes the ``context`` budget.
    """

    time_tolerance: int = 5
    """Years. How far a demand's year may be moved to meet a model's coverage."""

    context_tolerance: dict[str, tuple[float, float, str]] = field(default_factory=dict)
    """Per context condition, how far ``(below, above, unit)`` the asked value may move.

    Two numbers, not one, because most conditions have a safe side. Gas at a
    higher pressure than asked can be throttled down at the burner; gas at a
    lower one cannot be pushed up there, so pressure wants ``(0.0, 1e5, PA)``,
    not ``1e5`` either way. The unit says what the two numbers are in,
    because a condition may be asked in any unit of its kind: "1 above" means
    nothing until it says 1 of what. A condition absent here is never
    relaxed: empty by default, so no condition is.
    """

    def __post_init__(self) -> None:
        seen: set[frozenset[str]] = set()
        for entry in self.order:
            members = (entry,) if isinstance(entry, str) else tuple(entry)
            for dimension in members:
                _check_dimension(dimension)
                name = context_condition(dimension)
                if name is not None and name not in self.context_tolerance:
                    raise ValueError(
                        f"{dimension!r} can never be tried: no context_tolerance for {name!r}"
                    )
            if len(set(members)) != len(members):
                raise ValueError(f"each proxy dimension may appear only once in {entry}")
            if "context" in members and any(context_condition(m) for m in members):
                raise ValueError(
                    f"{entry!r} combines context with one of its own conditions; "
                    "name the conditions instead"
                )
            key = frozenset(members)
            if key in seen:
                raise ValueError(f"each proxy entry may appear only once in {self.order}")
            seen.add(key)
        for dimension, budget in self.max_steps.items():
            _check_dimension(dimension)
            if budget < 0:
                raise ValueError(f"{budget!r} is not a valid proxy budget; must be >= 0")
        for entry in self.order:
            if isinstance(entry, str):
                continue
            if len(entry) < 2:
                raise ValueError(
                    f"{entry!r} combines at least two dimensions or is written as a plain one"
                )
            unbudgeted = [dimension for dimension in entry if self.steps_allowed(dimension) <= 0]
            if unbudgeted:
                raise ValueError(
                    f"{entry!r} can never be tried: no max_steps budget for "
                    f"{', '.join(unbudgeted)}"
                )
        for name, bounds in self.context_tolerance.items():
            if (
                len(bounds) != 3
                or not isinstance(bounds[2], str)
                or any(not isinstance(bound, (int, float)) or bound < 0 for bound in bounds[:2])
            ):
                raise ValueError(
                    f"{bounds!r} is not a valid context tolerance for {name!r}; "
                    "must be (below, above, unit) with both bounds >= 0"
                )
        if self.time_tolerance < 0:
            raise ValueError(
                f"{self.time_tolerance!r} is not a valid time_tolerance; must be >= 0"
            )

    def steps_allowed(self, dimension: str) -> int:
        """Budget for ``dimension``. Absent means zero: no accidental relaxation.

        A ``context.<name>`` absent from ``max_steps`` falls back to the
        ``context`` budget: its tolerance already had to be written, so it
        cannot relax by accident.
        """
        if dimension in self.max_steps:
            return self.max_steps[dimension]
        if context_condition(dimension) is not None:
            return self.max_steps.get("context", 0)
        return 0


@dataclass(frozen=True)
class Settings:
    """One flat namespace for the whole run, plus two closed typed fields.

    ``values`` stays the open namespace a model may read keys from. Anything
    that varies per process belongs in that process's ParameterSet instead.

    Frozen to prevent reassignment, but not hashable — ``values`` is a dict.
    """

    values: dict[str, Any] = field(default_factory=dict)
    attribution: AttributionSettings = field(default_factory=AttributionSettings)
    proxy: ProxySettings = field(default_factory=ProxySettings)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)
