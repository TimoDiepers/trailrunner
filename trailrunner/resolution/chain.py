"""An ordered chain of ways to answer a demand.

Tier 1 is the models. Later tiers are concessions — a generalised demand, a
borrowed background dataset — and each one says so in its resolution. The
order is the practitioner's, which is why precedence across tiers is not
silent the way a hidden default would be.

**One vocabulary across the tiers.** A resolution dict is read by people and
by code that never knows which tier wrote it, so the keys every tier carries
mean the same thing in each:

``tier``
    Which tier answered: ``"model"``, ``"generalising"``, ``"background"``.
    Copied down from ``Offer.tier`` — see ``Offer.__post_init__``.
``model``
    Class name of the model that produced the Result. Tier 3's is
    ``BackgroundDataset``, which is exactly what answered it.
``asked``
    The demand as it came in, full IRI, location and year (``describe``).
``answered``
    The demand the model was actually applied to. Equal to ``asked`` wherever
    no relaxation happened, rather than absent: a reader comparing the two
    should never have to infer anything from a missing key.

A tier then adds its own keys — ``relaxations`` for tier 2, ``dataset``,
``source``, ``basis`` and ``complete`` for tier 3.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from trailrunner.core.flow import Demand
from trailrunner.core.model import Model


def describe(demand: Demand) -> str:
    """What a demand is for, in one line: full IRI, location, year, context.

    Context is appended in brackets only when there is some, so a relaxed
    condition shows up as a difference between ``asked`` and ``answered``
    like any other relaxation does. Unshortened on purpose. This is the machine-readable half of the record —
    it lands in ``report.proxies`` and in the log parquet, where a reader
    tracing a number back needs the IRI that was actually asked for.
    ``Report.tree()`` shortens separately, for the screen.
    """
    flow = demand.flow
    location = flow.location if flow.location is not None else "-"
    time = flow.time if flow.time is not None else "-"
    described = f"{flow.iri} @{location}/{time}"
    if flow.context:
        described += f" [{flow.describe_context()}]"
    return described


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
    """How this demand was matched. Always carries ``"tier"``; see ``__post_init__``."""

    def __post_init__(self) -> None:
        """``tier`` is the single source of truth, copied down into ``resolution``.

        Only the dict is ever read downstream: the Orchestrator forwards
        ``offer.resolution`` alone, and ``Report`` defaults a missing ``tier``
        to ``"model"``. A provider that set the field and left the dict empty
        was therefore printed as an exact match and left out of
        ``report.proxies`` — a concession made invisible by the very mechanism
        that exists to show it.

        Copied here rather than the field being dropped, because the tier is
        what the chain, its providers and their tests actually talk about, and
        ``offer.tier`` reads better than a dict lookup at every call site. A
        ``resolution["tier"]`` that disagrees with the field is a bug in the
        provider, not a precedence question, so it raises instead of one
        silently winning.
        """
        declared = self.resolution.setdefault("tier", self.tier)
        if declared != self.tier:
            raise ValueError(
                f"offer declares tier {self.tier!r} but its resolution says "
                f"{declared!r}; the tier that answered cannot be two things"
            )


@runtime_checkable
class Provider(Protocol):
    def offer(self, demand: Demand, exclude: Sequence[Model] = ()) -> Offer | None:
        """Answer this demand, or decline by returning ``None``.

        ``exclude`` names model instances that must not answer, by identity.
        It carries one piece of context the demand itself cannot: a
        substitution credit is a demand for what *somebody else* would have
        made, and a provider that answered it with the very model that minted
        the credit would let a process credit away its own burden. A provider
        that reaches a model through another provider has to forward it.
        """

    def explain(self, demand: Demand, exclude: Sequence[Model] = ()) -> tuple[str, str] | None:
        """Why this tier declined, as ``(reason, detail)``, or ``None``.

        ``exclude`` is the same tuple ``offer`` was given, so that a tier
        explains the refusal it actually made rather than the one it would
        have made for an ordinary demand.

        Called only after the whole chain has declined, and only to write an
        honest unresolved record. Stateless on purpose: a provider that
        remembered its last refusal would give a different answer depending on
        what else had been asked.
        """


class ResolutionChain:
    """Asks each provider in order; the first offer wins."""

    def __init__(self, providers: Sequence[Provider]) -> None:
        self._providers = list(providers)

    def offer(self, demand: Demand, exclude: Sequence[Model] = ()) -> Offer | None:
        for provider in self._providers:
            offer = provider.offer(demand, exclude=exclude)
            if offer is not None:
                return offer
        return None

    def explain(self, demand: Demand, exclude: Sequence[Model] = ()) -> tuple[str, str]:
        """The most specific reason any tier can give, else no_model_found.

        Tier order is reused deliberately: tier 1 knows about coverage misses,
        which is a more useful thing to tell the reader than "generalisation
        ran out", and the reader who widens the coverage fixes both.
        """
        for provider in self._providers:
            explanation = provider.explain(demand, exclude=exclude)
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
