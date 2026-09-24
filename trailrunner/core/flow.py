"""Identity and quantity: the two things every exchange in trailrunner is made of."""

from dataclasses import dataclass

from trailrunner.core.units import symbol


@dataclass(frozen=True)
class Property:
    """A quantified attribute: a name, a value and the unit it is in.

    Two places use it. On an ``Exchange`` it is what an allocation rule
    partitions co-production on -- mass, price, energy content. In a
    ``Flow``'s ``context`` it is a condition the demand is made under -- the
    pressure gas is wanted at -- and so part of what a model has to cover.
    The unit travels with the value because a partition over ``price`` in EUR
    and one in USD are not the same partition, and 4 bar is not 4 psi.
    """

    name: str
    value: float
    unit: str


@dataclass(frozen=True)
class Flow:
    """Identity of a thing: what it is, where, when, and under which conditions.

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

    context: tuple[Property, ...] = ()
    """Conditions beyond place and year that decide who can answer the flow.

    The pressure gas is wanted at, the purity of a solvent: anything a
    ``Coverage`` can declare a range for. A tuple rather than a mapping for
    the same hashability reason as ``Exchange.properties``. Empty means the
    flow asks for nothing beyond its IRI, location and year, and a coverage
    range on a condition the flow does not name is no restriction on it --
    only the demander knows what it needs.
    """

    def describe_context(self) -> str:
        """The context as one short string, ``pressure=4 bar``; empty if there is none."""
        return ", ".join(
            f"{entry.name}={entry.value:g} {symbol(entry.unit)}" for entry in self.context
        )

    def get_context(self, name: str) -> Property | None:
        """The context entry called ``name``, or ``None``."""
        for candidate in self.context:
            if candidate.name == name:
                return candidate
        return None


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
