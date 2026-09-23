"""An ordered chain of ways to answer a demand.

Tier 1 is the models. Later tiers are concessions — a generalised demand, a
borrowed background dataset — and each one says so in its resolution. The
order is the practitioner's, which is why precedence across tiers is not
silent the way a hidden default would be.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from trailrunner.core.flow import Demand
from trailrunner.core.model import Model


@dataclass(frozen=True)
class Offer:
    """A tier's answer: a model, and the demand to apply it to.

    ``demand`` is not always the demand that came in. A generalising tier
    relaxes it — a different year, a wider region — and the model is applied
    to, and validated against, the relaxed one. The original is what the Log
    records, so the report shows both what was asked and what was answered.
    """

    model: Model
    demand: Demand
    tier: str
    resolution: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    def offer(self, demand: Demand) -> Offer | None:
        """Answer this demand, or decline by returning ``None``."""

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        """Why this tier declined, as ``(reason, detail)``, or ``None``.

        Called only after the whole chain has declined, and only to write an
        honest unresolved record. Stateless on purpose: a provider that
        remembered its last refusal would give a different answer depending on
        what else had been asked.
        """


class ResolutionChain:
    """Asks each provider in order; the first offer wins."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        self._providers = list(providers)

    def offer(self, demand: Demand) -> Offer | None:
        for provider in self._providers:
            offer = provider.offer(demand)
            if offer is not None:
                return offer
        return None

    def explain(self, demand: Demand) -> tuple[str, str]:
        """The most specific reason any tier can give, else no_model_found.

        Tier order is reused deliberately: tier 1 knows about coverage misses,
        which is a more useful thing to tell the reader than "generalisation
        ran out", and the reader who widens the coverage fixes both.
        """
        for provider in self._providers:
            explanation = provider.explain(demand)
            if explanation is not None:
                return explanation
        return ("no_model_found", "")

    @property
    def glossary(self):
        """The first tier-1 Glossary, for callers that need the registry itself."""
        for provider in self._providers:
            registry = getattr(provider, "glossary", None)
            if registry is not None:
                return registry
        return None
