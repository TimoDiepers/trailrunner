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
from itertools import islice
from typing import Protocol

from trailrunner.core.flow import Demand
from trailrunner.core.settings import ProxySettings
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution.chain import Offer, describe
from trailrunner.resolution.models import ModelProvider


def _short(iri: str) -> str:
    """The last path segment of an IRI, for a note a human reads in a tree.

    The full pair is in the resolution's ``asked`` and ``answered`` (and so in
    ``report.proxies`` and the log parquet); a relaxation note carrying two
    60-character vocabulary URLs makes a ``tree()`` line nobody reads, which
    is the opposite of what this tier is for.
    """
    return iri.rstrip("/").rsplit("/", 1)[-1]


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
            for candidate, note in self._candidates(demand, dimension, budget):
                inner_offer = self.inner.offer(candidate)
                if inner_offer is None:
                    continue
                return Offer(
                    model=inner_offer.model,
                    demand=candidate,
                    tier="generalising",
                    resolution={
                        "model": type(inner_offer.model).__name__,
                        "relaxations": [note],
                        "asked": describe(demand),
                        "answered": describe(candidate),
                    },
                )
        return None

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        """``generalisation_exhausted``, but only if anything was ever tryable.

        Counted, not assumed. Deciding this from ``ProxySettings`` alone made
        the answer "budget spent" for every demand the chain could not answer,
        including a demand with no location, no year and no taxonomy, where
        not one candidate exists to spend a budget on — and, since tier 1
        explains only a coverage miss and tier 3 never explains, that wrong
        answer also made the chain's own ``no_model_found`` unreachable in the
        chain the docs recommend. It steered the reader at ``max_steps``,
        which cannot help when nothing was tryable.

        Re-walking ``_candidates`` here is safe because it is a pure
        generator: it builds relaxed demands and asks the taxonomy, and asks
        nothing of the tier-1 registry beyond what ``offer`` already asked.
        """
        tried = []
        for dimension in self.settings.order:
            budget = self.settings.steps_allowed(dimension)
            if budget <= 0:
                continue
            attempts = sum(1 for _ in self._candidates(demand, dimension, budget))
            if attempts:
                tried.append(f"{dimension}({attempts})")
        if not tried:
            # Nothing to relax along any dimension: not this tier's story to
            # tell, so the chain falls through to ``no_model_found``.
            return None
        return (
            "generalisation_exhausted",
            "every generalisation of this demand was tried and none matched; "
            f"candidates tried: {', '.join(tried)}",
        )

    def _candidates(
        self, demand: Demand, dimension: str, budget: int
    ) -> Iterator[tuple[Demand, str]]:
        """Every candidate worth trying along ``dimension``, within ``budget``.

        ``budget`` is a number of *steps away from the original demand*: hops
        up the location hierarchy, levels up the taxonomy, or years snapped
        to. One step can offer more than one candidate — a concept with two
        broader concepts is one level up either way — and all of them are
        tried, which is why the budget is enforced here rather than by
        counting candidates at the call site.
        """
        if dimension == "location":
            yield from self._location_candidates(demand, budget)
        elif dimension == "time":
            yield from self._time_candidates(demand, budget)
        elif dimension == "product":
            yield from self._product_candidates(demand, budget)

    def _location_candidates(self, demand: Demand, budget: int) -> Iterator[tuple[Demand, str]]:
        original = demand.flow.location
        if original is None:
            return
        for location in self.hierarchy.chain(original)[1 : budget + 1]:
            flow = replace(demand.flow, location=location)
            yield replace(demand, flow=flow), f"location: {original} -> {location}"

    def _time_candidates(self, demand: Demand, budget: int) -> Iterator[tuple[Demand, str]]:
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
        candidates = (
            year
            for year in sorted(set(years), key=lambda candidate: abs(candidate - original))
            if abs(year - original) <= self.settings.time_tolerance and year != original
        )
        for year in islice(candidates, budget):
            flow = replace(demand.flow, time=year)
            yield replace(demand, flow=flow), f"time: {original} -> {year}"

    def _product_candidates(self, demand: Demand, budget: int) -> Iterator[tuple[Demand, str]]:
        """Walk ``skos:broader`` upward, breadth-first, ``budget`` levels.

        Breadth-first so the most specific surviving model still wins: every
        concept one level up is tried before any concept two levels up, and a
        concept with two parents contributes both. A level, not a candidate,
        is what the budget counts — the same thing it counts for the location
        hierarchy, where each step is also one level. Walking a single level
        whatever the budget said (which is what this did) made ``product: 2``
        mean "two of the direct parents" while ``location: 3`` meant "three
        levels up", and left real vocabulary chains — ``fi_17100 -> fi_1710 ->
        fi_171`` — permanently out of reach.

        ``seen`` is not an optimisation: a vocabulary is not guaranteed
        acyclic, and a cycle here would be an infinite generator.
        """
        if self.taxonomy is None:
            return
        original = demand.flow.iri
        seen = {original}
        frontier = [original]
        for _level in range(budget):
            wider = []
            for iri in frontier:
                for broader in self.taxonomy.broader(iri):
                    if broader in seen:
                        continue
                    seen.add(broader)
                    wider.append(broader)
                    flow = replace(demand.flow, iri=broader)
                    yield (
                        replace(demand, flow=flow),
                        f"product: {_short(original)} -> {_short(broader)}",
                    )
            if not wider:
                return
            frontier = wider
