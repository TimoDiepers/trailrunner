"""Tier 1: the models themselves. An exact product IRI, within coverage."""

from collections.abc import Sequence

from trailrunner.core.flow import Demand
from trailrunner.core.model import Model
from trailrunner.orchestration.glossary import Glossary
from trailrunner.resolution.chain import Offer, describe


class ModelProvider:
    """A Provider over a Glossary. Semantics unchanged from v1.

    A thin wrapper rather than a rewrite: ``Glossary`` stays in
    ``orchestration``, keeps its public API, and works standalone for anyone
    who wants tier 1 alone.
    """

    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary

    def offer(self, demand: Demand, exclude: Sequence[Model] = ()) -> Offer | None:
        model = self.glossary.resolve(demand.flow, exclude=exclude)
        if model is None:
            return None
        return Offer(
            model=model,
            demand=demand,
            tier="model",
            # ``asked`` and ``answered`` are identical here, and said anyway:
            # they are the two keys a reader compares across tiers, and one
            # that is present only when it differs is a key whose absence has
            # to be interpreted. See ``chain``'s module docstring.
            resolution={
                "model": type(model).__name__,
                "asked": describe(demand),
                "answered": describe(demand),
            },
        )

    def explain(self, demand: Demand, exclude: Sequence[Model] = ()) -> tuple[str, str] | None:
        """A coverage miss, or nothing.

        ``exclude`` is applied here too. A credit whose only producer is the
        model that minted it was not refused for coverage — it was refused
        because a process may not answer its own avoided burden — and saying
        "coverage does not cover this location" would send the reader to widen
        a coverage that is already right. With every declaring model excluded
        there is no near miss to report, so the chain falls through to
        ``no_model_found``: nobody *else* makes this.
        """
        near_misses = self.glossary.declared_models(demand.flow, exclude=exclude)
        if not near_misses:
            return None
        names = ", ".join(type(model).__name__ for model in near_misses)
        return (
            "coverage_excluded",
            f"{names} declares this product but its coverage does not cover "
            f"location={demand.flow.location!r} time={demand.flow.time!r}",
        )
