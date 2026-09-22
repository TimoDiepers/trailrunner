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
class Property:
    """A quantified attribute of an exchange, used to partition co-production.

    Mass, price, energy content: whatever the allocation rule divides by. The
    unit travels with the value because a partition over ``price`` in EUR and
    one in USD are not the same partition.
    """

    name: str
    value: float
    unit: str


@dataclass(frozen=True)
class Exchange:
    """A quantified flow. The unit lives here, not on the Flow."""

    flow: Flow
    amount: float
    unit: str

    properties: tuple[Property, ...] = ()
    """Attributes an allocation rule may partition on.

    A tuple rather than a mapping so that ``Exchange`` stays hashable: ``Flow``
    is an aggregation key and ``QueueItem`` is a frozen dataclass holding a
    ``Demand``, so a dict here would make the hashability of both depend on
    which fields happen to be populated.
    """

    def get_property(self, name: str) -> Property | None:
        """The property called ``name``, or ``None``.

        Deliberately lenient: the caller that *requires* a property is the
        allocation rule in the Runner, and it raises a message naming the model
        and the co-product, which is far more useful than a KeyError here.
        """
        for candidate in self.properties:
            if candidate.name == name:
                return candidate
        return None


Demand = Exchange
"""A technosphere Exchange that someone must satisfy.

An alias rather than a subclass so the two cannot drift apart.
"""
