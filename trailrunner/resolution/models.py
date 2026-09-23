"""Tier 1: the models themselves. An exact product IRI, within coverage."""

from trailrunner.core.flow import Demand
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

    def offer(self, demand: Demand) -> Offer | None:
        model = self.glossary.resolve(demand.flow)
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

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        near_misses = self.glossary.declared_models(demand.flow)
        if not near_misses:
            return None
        names = ", ".join(type(model).__name__ for model in near_misses)
        return (
            "coverage_excluded",
            f"{names} declares this product but its coverage does not cover "
            f"location={demand.flow.location!r} time={demand.flow.time!r}",
        )
