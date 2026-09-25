"""Tier 1: the models themselves. An exact product IRI, within coverage."""

from collections.abc import Sequence
from dataclasses import replace

from trailrunner.core.errors import UnknownUnit
from trailrunner.core.flow import Demand
from trailrunner.core.model import Model
from trailrunner.core.units import KG, VOCAB, UnitCatalog, default_catalog
from trailrunner.orchestration.glossary import Glossary
from trailrunner.resolution.chain import Offer, describe


class ModelProvider:
    """A Provider over a Glossary: exact product IRI, within coverage.

    Also where a demand meets the unit its model reasons in. A model that
    declares ``Coverage.units`` is handed the demand in one of them: converted
    exactly when the quantity kind matches (1 t becomes 1000 kg), refused when
    it does not. The conversion is recorded under ``"conversion"`` and is not
    a proxy -- it loses nothing -- so the tier stays ``"model"``.
    """

    def __init__(self, glossary: Glossary, units: UnitCatalog | None = None) -> None:
        self.glossary = glossary
        self.units = units if units is not None else default_catalog()

    def offer(self, demand: Demand, exclude: Sequence[Model] = ()) -> Offer | None:
        if self.units.known(demand.unit) is False:
            raise UnknownUnit(
                f"{demand.unit!r} is not a unit of the vocabulary ({VOCAB}); units are "
                f"IRIs such as {KG} — write unit=KG (from trailrunner.core.units)"
            )
        model = self.glossary.resolve(demand.flow, exclude=exclude, units=self.units)
        if model is None:
            return None
        answered, conversion = self._in_model_unit(demand, model)
        if answered is None:
            return None
        resolution = {
            "model": type(model).__name__,
            # ``asked`` and ``answered`` are identical here, and said anyway:
            # they are the two keys a reader compares across tiers, and one
            # that is present only when it differs is a key whose absence has
            # to be interpreted. See ``chain``'s module docstring.
            "asked": describe(demand),
            "answered": describe(answered),
        }
        if conversion is not None:
            resolution["conversion"] = conversion
        return Offer(model=model, demand=answered, tier="model", resolution=resolution)

    def _in_model_unit(self, demand: Demand, model: Model) -> tuple[Demand | None, str | None]:
        accepted = model.coverage.units if model.coverage is not None else None
        if accepted is None or demand.unit in accepted:
            return demand, None
        for target in sorted(accepted):
            if self.units.convertible(demand.unit, target):
                factor = self.units.factor(demand.unit, target)
                converted = replace(demand, amount=demand.amount * factor, unit=target)
                note = (
                    f"unit: {self.units.symbol(demand.unit)} -> "
                    f"{self.units.symbol(target)} ×{factor:g}"
                )
                return converted, note
        return None, None

    def explain(self, demand: Demand, exclude: Sequence[Model] = ()) -> tuple[str, str] | None:
        """A unit mismatch, a coverage miss, or nothing.

        ``exclude`` is applied here too. A credit whose only producer is the
        model that minted it was not refused for coverage — it was refused
        because a process may not answer its own avoided burden — and saying
        "coverage does not cover this location" would send the reader to widen
        a coverage that is already right. With every declaring model excluded
        there is no near miss to report, so the chain falls through to
        ``no_model_found``: nobody *else* makes this.

        A unit mismatch is checked first because it is the more specific
        answer: the model covers this flow and would answer it, in a unit the
        demand cannot be converted into.
        """
        model = self.glossary.resolve(demand.flow, exclude=exclude, units=self.units)
        if model is not None:
            accepted = sorted(model.coverage.units)  # non-None, or offer() would have answered
            demand_symbol = self.units.symbol(demand.unit)
            accepted_symbols = [self.units.symbol(unit) for unit in accepted]
            hint = ""
            if demand_symbol in accepted_symbols:
                # The units differ but display the same symbol -- typically an
                # uncached vocabulary IRI whose symbol falls back to its last
                # path segment. Saying "in kg but the demand is in kg" would
                # read as a contradiction, so show the full IRIs instead.
                accepted_display = ", ".join(accepted)
                demand_display = demand.unit
                if self.units.known(demand.unit) is None:
                    hint = " (uncached; run dev/warm_unit_cache.py to confirm it)"
            else:
                accepted_display = ", ".join(accepted_symbols)
                demand_display = demand_symbol
            return (
                "unit_mismatch",
                f"{type(model).__name__} answers {demand.flow.iri} in "
                f"{accepted_display} but the demand is in "
                f"{demand_display}, a different quantity{hint}",
            )
        near_misses = self.glossary.declared_models(demand.flow, exclude=exclude)
        if not near_misses:
            return None
        names = ", ".join(type(model).__name__ for model in near_misses)
        context = f" context={demand.flow.describe_context()!r}" if demand.flow.context else ""
        return (
            "coverage_excluded",
            f"{names} declares this product but its coverage does not cover "
            f"location={demand.flow.location!r} time={demand.flow.time!r}{context}",
        )
