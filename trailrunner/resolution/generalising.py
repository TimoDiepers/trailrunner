"""Tier 2: answer a demand nothing models exactly, by asking for less.

Which concession is acceptable, and in what order, is a modelling decision —
so the order and the budgets come from ``ProxySettings`` and every step taken
is recorded. A proxy nobody can see is indistinguishable from a wrong number.

**Relaxations compose only when asked to.** Each plain entry in the order is
tried from the original demand. A demand needing both a wider region and an
earlier year is answered only by a combined entry such as
``("location", "time")``, written where the practitioner wants it in the
order. Its search order (fewest total steps, ties to the member written
first) is documented on ``ProxySettings`` rather than invented here, because
choosing one silently is the thing this module exists to prevent.
"""

from collections.abc import Iterator, Sequence
from dataclasses import replace
from itertools import islice
from typing import Protocol

from trailrunner.core.flow import Demand, Property
from trailrunner.core.model import Model
from trailrunner.core.settings import ProxySettings, context_condition
from trailrunner.core.time import interval, midpoint_year
from trailrunner.core.units import symbol
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

    def offer(self, demand: Demand, exclude: Sequence[Model] = ()) -> Offer | None:
        """Relax, then re-ask tier 1 — carrying ``exclude`` with the demand.

        Forwarding it is not optional. A relaxed demand is still the same
        credit, so a generalised offer that dropped ``exclude`` would land the
        credit right back on the model that minted it, one hop later and
        wearing a proxy label.
        """
        for entry in self.settings.order:
            for candidate, notes in self._entry_candidates(demand, entry):
                inner_offer = self.inner.offer(candidate, exclude=exclude)
                if inner_offer is None:
                    continue
                resolution = {
                    "model": type(inner_offer.model).__name__,
                    "relaxations": notes,
                    "asked": describe(demand),
                    "answered": describe(candidate),
                }
                conversion = inner_offer.resolution.get("conversion")
                if conversion is not None:
                    resolution["conversion"] = conversion
                return Offer(
                    model=inner_offer.model,
                    # The inner offer's demand, not the candidate: it is the
                    # candidate already converted into the model's unit.
                    demand=inner_offer.demand,
                    tier="generalising",
                    resolution=resolution,
                )
        return None

    def explain(self, demand: Demand, exclude: Sequence[Model] = ()) -> tuple[str, str] | None:
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
        for entry in self.settings.order:
            attempts = sum(1 for _ in self._entry_candidates(demand, entry))
            if attempts:
                label = entry if isinstance(entry, str) else "+".join(entry)
                tried.append(f"{label}({attempts})")
        if not tried:
            # Nothing to relax along any dimension: not this tier's story to
            # tell, so the chain falls through to ``no_model_found``.
            return None
        return (
            "generalisation_exhausted",
            "every generalisation of this demand was tried and none matched; "
            f"candidates tried: {', '.join(tried)}",
        )

    def _entry_candidates(
        self, demand: Demand, entry: str | tuple[str, ...]
    ) -> Iterator[tuple[Demand, list[str]]]:
        """One entry of the order: a single dimension, or several together.

        A combined entry nests rather than crossing precomputed lists, because
        what one dimension can offer depends on where another has moved the
        demand: the years worth trying are the ones declared for the flow as
        relaxed so far. Every member moves at least one step (the plain
        entries already cover the rest), and the candidates are then sorted
        by total steps, ties going to whichever moved the member written
        first the least. Materialising them is cheap: budgets are a handful
        of steps each.
        """
        if isinstance(entry, str):
            budget = self.settings.steps_allowed(entry)
            if budget <= 0:
                return
            for candidate, note, _step in self._candidates(demand, entry, budget):
                yield candidate, [note]
            return
        combined = sorted(
            self._combine(demand, tuple(entry), (), ()),
            key=lambda found: (sum(found[0]), found[0]),
        )
        for _steps, candidate, notes in combined:
            yield candidate, list(notes)

    def _combine(
        self,
        demand: Demand,
        members: tuple[str, ...],
        steps: tuple[int, ...],
        notes: tuple[str, ...],
    ) -> Iterator[tuple[tuple[int, ...], Demand, tuple[str, ...]]]:
        if not members:
            yield steps, demand, notes
            return
        first, rest = members[0], members[1:]
        budget = self.settings.steps_allowed(first)
        for candidate, note, step in self._candidates(demand, first, budget):
            yield from self._combine(candidate, rest, steps + (step,), notes + (note,))

    def _candidates(
        self, demand: Demand, dimension: str, budget: int
    ) -> Iterator[tuple[Demand, str, int]]:
        """Every candidate worth trying along ``dimension``, within ``budget``.

        ``budget`` is a number of *steps away from the original demand*: hops
        up the location hierarchy, levels up the taxonomy, or years and
        context values snapped to. One step can offer more than one candidate — a concept with two
        broader concepts is one level up either way — and all of them are
        tried, which is why the budget is enforced here rather than by
        counting candidates at the call site. Each candidate comes with the
        step it sits at, which a combined entry sums to rank its search.
        """
        if dimension == "location":
            yield from self._location_candidates(demand, budget)
        elif dimension == "time":
            yield from self._time_candidates(demand, budget)
        elif dimension == "context":
            yield from self._context_candidates(demand, budget)
        elif context_condition(dimension) is not None:
            yield from self._context_candidates(demand, budget, context_condition(dimension))
        elif dimension == "product":
            yield from self._product_candidates(demand, budget)

    def _location_candidates(
        self, demand: Demand, budget: int
    ) -> Iterator[tuple[Demand, str, int]]:
        original = demand.flow.location
        if original is None:
            return
        for step, location in enumerate(self.hierarchy.chain(original)[1 : budget + 1], 1):
            flow = replace(demand.flow, location=location)
            yield replace(demand, flow=flow), f"location: {original} -> {location}", step

    def _time_candidates(self, demand: Demand, budget: int) -> Iterator[tuple[Demand, str, int]]:
        """Snap to the nearest period a declaring model covers, within tolerance.

        Asks the registry rather than guessing: the only periods worth trying
        are the edges of ranges some model actually declares -- the nearer
        edge of each. Distance is between period midpoints in decimal years,
        which for year data is exactly the old ``abs(year - original)``. A
        range that already covers the time offers nothing, as clamping a year
        into its own range never moved it.
        """
        original = demand.flow
        if original.time is None:
            return
        here = midpoint_year(interval(original.time, original.time_standard))
        found: dict[tuple[str, str], float] = {}
        for model in self.inner.glossary.declared_models(original):
            window = getattr(model.coverage, "time_range", None) if model.coverage else None
            if window is None or window.contains(original.time, original.time_standard):
                continue
            distance, value = min(
                (abs(midpoint_year(interval(edge, window.standard)) - here), edge)
                for edge in window.edges()
            )
            key = (value, window.standard)
            if distance > self.settings.time_tolerance or key == (original.time, original.time_standard):
                continue
            found[key] = min(found.get(key, distance), distance)
        ranked = sorted(found.items(), key=lambda item: (item[1], item[0]))
        for step, ((value, standard), _distance) in enumerate(islice(ranked, budget), 1):
            flow = replace(original, time=value, time_standard=standard)
            yield replace(demand, flow=flow), f"time: {original.time} -> {value}", step

    def _context_candidates(
        self, demand: Demand, budget: int, only: str | None = None
    ) -> Iterator[tuple[Demand, str, int]]:
        """Move one condition to the nearest value a declaring model covers.

        ``only`` restricts this to one condition: that is the
        ``context.<name>`` dimension, and what lets a combined entry move two
        conditions together by nesting, as it nests location and time.
        Without it, every tolerated condition is a candidate, one at a time.

        The same move as ``_time_candidates``, one condition at a time: ask
        the registry which ranges exist, snap into each, keep what lies within
        ``context_tolerance``. The tolerance is ``(below, above, unit)`` so
        that a condition with a safe side -- gas at a higher pressure can be
        throttled, gas at a lower one cannot be boosted -- is only ever moved
        to that side. A condition with no tolerance, or declared in a unit of
        another quantity kind, is not moved at all. The comparison and the
        snap both happen in the tolerance's own unit, because that is what
        "0.0 below, 1e5 above" is written in; the result is converted back
        into the unit the demander asked in before it is written to the flow.
        """
        catalog = self.inner.units
        found: dict[tuple[str, float], tuple[float, Property]] = {}
        for asked in demand.flow.context:
            if only is not None and asked.name != only:
                continue
            tolerance = self.settings.context_tolerance.get(asked.name)
            if tolerance is None:
                continue
            below, above, unit = tolerance
            asked_value = catalog.try_convert(asked.value, asked.unit, unit)
            if asked_value is None:
                continue
            for model in self.inner.glossary.declared_models(demand.flow):
                if model.coverage is None:
                    continue
                declared = model.coverage.context_range(asked.name)
                if declared is None:
                    continue
                low = catalog.try_convert(declared.minimum, declared.unit, unit)
                high = catalog.try_convert(declared.maximum, declared.unit, unit)
                if low is None or high is None:
                    continue
                value = min(max(asked_value, low), high)
                shift = value - asked_value
                if shift == 0 or not -below <= shift <= above:
                    continue
                # Written back in the unit the demander asked in.
                snapped = catalog.convert(value, unit, asked.unit)
                found.setdefault((asked.name, snapped), (abs(shift), asked))
        ranked = sorted(found.items(), key=lambda item: (item[1][0], item[0]))
        for step, ((name, value), (_distance, asked)) in enumerate(islice(ranked, budget), 1):
            context = tuple(
                replace(entry, value=value) if entry.name == name else entry
                for entry in demand.flow.context
            )
            flow = replace(demand.flow, context=context)
            shown = symbol(asked.unit)
            note = f"context: {name} {asked.value:g} {shown} -> {value:g} {shown}"
            yield replace(demand, flow=flow), note, step

    def _product_candidates(
        self, demand: Demand, budget: int
    ) -> Iterator[tuple[Demand, str, int]]:
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
        for level in range(1, budget + 1):
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
                        level,
                    )
            if not wider:
                return
            frontier = wider
