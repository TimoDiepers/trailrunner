"""Tier 2: answer a demand nothing models exactly, by asking for less.

Which concession is acceptable, and in what order, is a modelling decision —
so the order and the budgets come from ``ProxySettings`` and every step taken
is recorded. A proxy nobody can see is indistinguishable from a wrong number.

**Relaxations do not compose.** Each dimension is tried from the original
demand, in the declared order; a demand needing both a wider region and an
earlier year is not answered. The composed search is a cross-product whose
preference order is a second normative choice, and inventing one silently is
the thing this module exists to prevent. Deferred, not forgotten.
"""

from collections.abc import Iterator
from dataclasses import replace
from typing import Protocol

from trailrunner.core.flow import Demand
from trailrunner.core.settings import ProxySettings
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution.chain import Offer
from trailrunner.resolution.models import ModelProvider


class Taxonomy(Protocol):
    def broader(self, iri: str) -> list[str]:
        """Concepts directly above ``iri``, most specific first."""


class StaticTaxonomy:
    """A hand-written parent map, for tests and for offline runs."""

    def __init__(self, parents: dict[str, list[str]]) -> None:
        self._parents = dict(parents)

    def broader(self, iri: str) -> list[str]:
        return list(self._parents.get(iri, []))


class GeneralisingProvider:
    """Relaxes a demand one dimension at a time and re-asks tier 1."""

    def __init__(
        self,
        inner: ModelProvider,
        settings: ProxySettings | None = None,
        hierarchy: LocationHierarchy | None = None,
        taxonomy: Taxonomy | None = None,
    ) -> None:
        self.inner = inner
        self.settings = settings if settings is not None else ProxySettings()
        self.hierarchy = hierarchy if hierarchy is not None else LocationHierarchy()
        self.taxonomy = taxonomy

    def offer(self, demand: Demand) -> Offer | None:
        for dimension in self.settings.order:
            budget = self.settings.steps_allowed(dimension)
            if budget <= 0:
                continue
            for step, (candidate, note) in enumerate(self._candidates(demand, dimension)):
                if step >= budget:
                    break
                inner_offer = self.inner.offer(candidate)
                if inner_offer is None:
                    continue
                return Offer(
                    model=inner_offer.model,
                    demand=candidate,
                    tier="generalising",
                    resolution={
                        "tier": "generalising",
                        "model": type(inner_offer.model).__name__,
                        "relaxations": [note],
                        "asked": demand.flow.iri,
                    },
                )
        return None

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        tried = [
            f"{dimension}({self.settings.steps_allowed(dimension)})"
            for dimension in self.settings.order
            if self.settings.steps_allowed(dimension) > 0
        ]
        if not tried:
            return None
        return (
            "generalisation_exhausted",
            f"generalisation budget spent without a match; tried {', '.join(tried)}",
        )

    def _candidates(self, demand: Demand, dimension: str) -> Iterator[tuple[Demand, str]]:
        if dimension == "location":
            yield from self._location_candidates(demand)
        elif dimension == "time":
            yield from self._time_candidates(demand)
        elif dimension == "product":
            yield from self._product_candidates(demand)

    def _location_candidates(self, demand: Demand) -> Iterator[tuple[Demand, str]]:
        original = demand.flow.location
        if original is None:
            return
        for location in self.hierarchy.chain(original)[1:]:
            flow = replace(demand.flow, location=location)
            yield replace(demand, flow=flow), f"location: {original} -> {location}"

    def _time_candidates(self, demand: Demand) -> Iterator[tuple[Demand, str]]:
        """Snap to the nearest year a declaring model covers, within tolerance.

        Asks the registry rather than guessing: the only years worth trying are
        the ones some model actually claims.
        """
        original = demand.flow.time
        if original is None:
            return
        years: list[int] = []
        for model in self.inner.glossary.declared_models(demand.flow):
            window = getattr(model.coverage, "time_range", None) if model.coverage else None
            if window is None:
                continue
            earliest, latest = window
            years.append(min(max(original, earliest), latest))
        for year in sorted(set(years), key=lambda candidate: abs(candidate - original)):
            if abs(year - original) > self.settings.time_tolerance or year == original:
                continue
            flow = replace(demand.flow, time=year)
            yield replace(demand, flow=flow), f"time: {original} -> {year}"

    def _product_candidates(self, demand: Demand) -> Iterator[tuple[Demand, str]]:
        if self.taxonomy is None:
            return
        original = demand.flow.iri
        for broader in self.taxonomy.broader(original):
            flow = replace(demand.flow, iri=broader)
            yield replace(demand, flow=flow), f"product: {original} -> {broader}"
