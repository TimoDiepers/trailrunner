"""Identity and quantity: the two things every exchange in trailrunner is made of."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Flow:
    """Identity of a thing: what it is, where it is, when it is.

    Carries no amount and no unit so that it stays hashable and can be used
    directly as an aggregation key.
    """

    iri: str
    location: str | None = None
    time: int | None = None


@dataclass(frozen=True)
class Exchange:
    """A quantified flow. The unit lives here, not on the Flow."""

    flow: Flow
    amount: float
    unit: str


Demand = Exchange
"""A technosphere Exchange that someone must satisfy.

An alias rather than a subclass so the two cannot drift apart.
"""
