"""Calls a model and checks that it honoured its contract."""

import math

from trailrunner.attribution.allocation import allocate, substitute
from trailrunner.core.errors import NoModelFound, UnsupportedAttribution, ValidationError
from trailrunner.core.flow import Demand
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings
from trailrunner.orchestration.glossary import Glossary

PRODUCTION_RELATIVE_TOLERANCE = 1e-9
"""How far below the demand production may fall and still count as covering it.

Relative, not absolute, because amounts span many orders of magnitude, and a
tolerance is needed at all because a model built on interpolated parameters
does not round-trip to the last bit: a demand of 1000 kg met by a chain of
float multiplications can come back as 999.9999999999999. 1e-9 is far above
that float noise and far below any modelling error worth hiding.
"""


class Runner:
    """Synchronous. The single place where Result validation happens.

    It is a separate object so that a concurrent implementation can replace it
    behind the same interface without the Orchestrator changing.
    """

    def __init__(self, glossary: Glossary | None = None, settings: Settings | None = None) -> None:
        # `None` is a real case since phase 2: a ResolutionChain with no
        # ModelProvider has no Glossary to expose, and the Orchestrator always
        # passes `model=offer.model` into apply(), so the Runner never consults
        # it. The annotation now says so instead of leaving a type-checker
        # mismatch for the next reader to trip over.
        self.glossary = glossary
        self.settings = settings if settings is not None else Settings()

    def apply(self, demand: Demand, model: Model | None = None) -> Result:
        if model is None:
            model = self.glossary.resolve(demand.flow)
        if model is None:
            raise NoModelFound(
                f"no model produces {demand.flow.iri} at "
                f"location={demand.flow.location!r} time={demand.flow.time!r}"
            )
        result = model.apply(demand)
        self.validate(demand, result, model=model)

        rule = self.settings.attribution.allocation
        supports = getattr(model, "supports", frozenset({"none"}))
        if rule != "none" and rule not in supports:
            raise UnsupportedAttribution(
                f"the run's allocation rule is {rule!r} but "
                f"{type(model).__name__} supports only {sorted(supports)}"
            )
        if rule == "substitution":
            return substitute(demand, result, type(model).__name__)
        return allocate(demand, result, rule, type(model).__name__)

    @staticmethod
    def validate(demand: Demand, result: Result, model: Model | None = None) -> None:
        """Check a Result against the Model contract.

        Four rules, in the order a model author would want to hear about them:
        every exchange carries a unit; production has the same sign as the
        demand, and covers it in magnitude; the demanded product is among
        them, in the demanded unit; and the summed production of that
        product *covers* the demanded amount. The sign rule is not "amounts
        are positive" because a substitution credit *is* a negative demand —
        the co-product an avoided process would otherwise have made, pushed
        onto the queue with a flipped sign — and refusing negative demands
        would make that rule unusable. The coverage rule is load-bearing
        either way: ``apply`` receives the full demand and nothing downstream
        rescales, so under-delivery silently shrinks the whole inventory (or,
        for a credit, under-credits it). Over-production is allowed — a
        process may legitimately make more than was asked of it.
        """
        origin = type(model).__name__ if model is not None else "model"

        if not isinstance(result, Result):
            raise ValidationError(f"{origin} returned {type(result).__name__}, expected Result")

        sign = 1.0 if demand.amount >= 0 else -1.0

        # One pass over every exchange. The unit rule is checked before the
        # amount rule on each exchange, so an entry that breaks both is
        # reported as the missing unit it is rather than having that masked.
        produced = len(result.production)
        for index, exchange in enumerate(
            (*result.production, *result.technosphere, *result.biosphere)
        ):
            if not exchange.unit:
                raise ValidationError(f"{origin} returned {exchange.flow.iri} without a unit")
            if index < produced and exchange.amount * sign <= 0:
                raise ValidationError(
                    f"{origin} produced {exchange.amount} of {exchange.flow.iri} "
                    f"against a demand of {demand.amount}; production must have "
                    "the same sign as the demand"
                )

        matching = [e for e in result.production if e.flow.iri == demand.flow.iri]
        if not matching:
            raise ValidationError(
                f"{origin} did not produce the demanded product {demand.flow.iri}; "
                f"produced {[e.flow.iri for e in result.production]}"
            )

        mismatched = [e.unit for e in matching if e.unit != demand.unit]
        if mismatched:
            raise ValidationError(
                f"{origin} produced {demand.flow.iri} in {mismatched[0]!r} "
                f"but the demand is in {demand.unit!r}"
            )

        total = sum(e.amount for e in matching)
        if total * sign < demand.amount * sign and not math.isclose(
            total, demand.amount, rel_tol=PRODUCTION_RELATIVE_TOLERANCE
        ):
            raise ValidationError(
                f"{origin} produced {total} {demand.unit} of {demand.flow.iri} "
                f"but {demand.amount} {demand.unit} was demanded; production must "
                "cover the demand, because apply() receives the full demand amount "
                "and nothing downstream rescales the result "
                "(magnitudes are compared, so a credit demand is covered by a "
                "credit of at least the same size)"
            )
