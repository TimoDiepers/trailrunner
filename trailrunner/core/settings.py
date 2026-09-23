"""Run-wide knobs, including the run's normative choices."""

from dataclasses import dataclass, field
from typing import Any

ALLOCATION_RULES = frozenset({"none", "mass", "economic", "energy", "substitution"})
CAPITAL_RULES = frozenset({"per_output", "per_year", "first_life"})
REUSE_RULES = frozenset({"first_life", "shared"})
PROXY_DIMENSIONS = ("time", "location", "product")


def _check(value: str, allowed, label: str) -> None:
    if value not in allowed:
        raise ValueError(
            f"{value!r} is not a known {label}; allowed: {', '.join(sorted(allowed))}"
        )


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

    Frozen to prevent reassignment, but not hashable — ``max_steps`` is a dict.
    """

    order: tuple[str, ...] = PROXY_DIMENSIONS
    max_steps: dict[str, int] = field(
        default_factory=lambda: {"time": 1, "location": 3, "product": 2}
    )
    """How many steps away from the original demand each dimension may go.

    A step means the same thing in every dimension: one level up the location
    hierarchy, one level up the product taxonomy's ``skos:broader``, or one
    year snapped to. A single step can offer more than one candidate — a
    concept with two broader concepts is one level up either way — and all of
    a permitted level's candidates are tried. A dimension absent from this
    dict is not relaxed at all.
    """

    time_tolerance: int = 5
    """Years. How far a demand's year may be moved to meet a model's coverage."""

    def __post_init__(self) -> None:
        for dimension in self.order:
            _check(dimension, PROXY_DIMENSIONS, "proxy dimension")
        if len(set(self.order)) != len(self.order):
            raise ValueError(f"each proxy dimension may appear only once in {self.order}")
        for dimension, budget in self.max_steps.items():
            _check(dimension, PROXY_DIMENSIONS, "proxy dimension")
            if budget < 0:
                raise ValueError(f"{budget!r} is not a valid proxy budget; must be >= 0")
        if self.time_tolerance < 0:
            raise ValueError(
                f"{self.time_tolerance!r} is not a valid time_tolerance; must be >= 0"
            )

    def steps_allowed(self, dimension: str) -> int:
        """Budget for ``dimension``. Absent means zero: no accidental relaxation."""
        return self.max_steps.get(dimension, 0)


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
