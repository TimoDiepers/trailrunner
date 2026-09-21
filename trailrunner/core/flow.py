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
    """An opaque key, resolved through ``LocationHierarchy`` (``CH`` -> ``RER``
    -> ``GLO``). Deliberately not an ISO 3166-1 alpha-2 code: regional and
    global codes have to be expressible too, and a coordinate pair has no
    parent to fall back to. ``None`` means the flow is not location-specific.
    """

    time: int | None = None
    """A year. ``None`` means the flow is not time-specific."""


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
