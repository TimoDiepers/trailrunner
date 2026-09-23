"""Partitioning a multifunctional Result.

The rule is the run's, not the model's, and it is applied here rather than
inside each model so that every model partitions identically and so the choice
is recorded in one place. A model that cannot honour the rule refuses; it never
silently answers a different question.
"""

from dataclasses import replace

from trailrunner.core.errors import MissingProperty
from trailrunner.core.flow import Demand
from trailrunner.core.result import Result

ALLOCATION_PROPERTY = {"mass": "mass", "economic": "price", "energy": "energy"}
"""Which property each rule partitions on. ``economic`` reads ``price``: the
rule is named for the question and the property for the number."""


def allocate(demand: Demand, result: Result, rule: str, model_name: str) -> Result:
    """Return ``result`` partitioned to the demanded product.

    ``substitution`` is not handled here — it changes the traversal rather than
    the arithmetic, so the Runner does it. ``none`` refuses co-production
    outright: model it monofunctionally, or choose a rule.
    """
    demanded = [e for e in result.production if e.flow.iri == demand.flow.iri]
    others = [e for e in result.production if e.flow.iri != demand.flow.iri]

    if not others:
        result.provenance["attribution"] = {"allocation": rule, "share": 1.0, "property": None}
        return result

    if rule == "none":
        raise ValueError(
            f"{model_name} returned co-products "
            f"({', '.join(e.flow.iri for e in others)}) but the run's allocation "
            "rule is 'none'; model it monofunctionally or choose a rule"
        )

    key = ALLOCATION_PROPERTY[rule]
    # Summed per product IRI so that a model splitting one product over
    # several exchanges partitions on their total, matching how the Runner
    # already sums production when checking coverage.
    values = {}
    units: set[str] = set()
    for exchange in result.production:
        prop = exchange.get_property(key)
        if prop is None:
            raise MissingProperty(
                f"{model_name} produced {exchange.flow.iri} without a {key!r} "
                f"property, which the {rule!r} allocation rule partitions on"
            )
        units.add(prop.unit)
        values[exchange.flow.iri] = values.get(exchange.flow.iri, 0.0) + prop.value

    # Unit compatibility is string equality here as everywhere: a mass in kg and
    # a mass in t are not summable, and a partition over their sum is a wrong
    # number that looks right. This is the reason Property carries a unit at all.
    if len(units) > 1:
        raise MissingProperty(
            f"{model_name}'s co-products declare {key!r} in more than one unit "
            f"({', '.join(sorted(units))}); trailrunner does not convert units, so "
            f"the {rule!r} rule cannot partition over them"
        )

    total = sum(values.values())
    if total == 0:
        raise MissingProperty(
            f"{model_name}'s products all have a {key!r} of zero, so the "
            f"{rule!r} rule has nothing to partition on"
        )

    share = sum(values[iri] for iri in {e.flow.iri for e in demanded}) / total

    allocated = Result(
        production=list(demanded),
        technosphere=[replace(d, amount=d.amount * share) for d in result.technosphere],
        biosphere=[replace(e, amount=e.amount * share) for e in result.biosphere],
        provenance=dict(result.provenance),
    )
    allocated.provenance["attribution"] = {
        "allocation": rule,
        "property": key,
        "share": share,
        "co_products": [e.flow.iri for e in others],
    }
    return allocated


def substitute(demand: Demand, result: Result, model_name: str) -> Result:
    """Credit each co-product as an avoided burden.

    The co-product is pushed onto the queue as a **negative** demand: whoever
    would otherwise have made it is asked what that would have cost, and the
    answer is subtracted. This is the only rule that reaches the traversal
    rather than the arithmetic, which is why the Runner calls it instead of
    ``allocate``.
    """
    demanded = [e for e in result.production if e.flow.iri == demand.flow.iri]
    others = [e for e in result.production if e.flow.iri != demand.flow.iri]

    credits = [
        Demand(flow=exchange.flow, amount=-exchange.amount, unit=exchange.unit)
        for exchange in others
    ]

    substituted = Result(
        production=list(demanded),
        technosphere=[*result.technosphere, *credits],
        biosphere=list(result.biosphere),
        provenance=dict(result.provenance),
    )
    substituted.provenance["attribution"] = {
        "allocation": "substitution",
        "share": 1.0,
        "substituted": [exchange.flow.iri for exchange in others],
    }
    return substituted
