"""Who produces what."""

from collections.abc import Iterable

from trailrunner.core.errors import AmbiguousProducer
from trailrunner.core.flow import Flow
from trailrunner.core.model import Model


class Glossary:
    """Indexes model instances by the product IRIs they declare.

    Holds *instances*, not classes, because a model needs its settings and
    parameters before it can answer anything.
    """

    def __init__(self, models: Iterable[Model] = ()) -> None:
        self._models: list[Model] = list(models)

    def register(self, model: Model) -> None:
        self._models.append(model)

    def resolve(self, flow: Flow) -> Model | None:
        """Return the model that produces ``flow``.

        ``None`` means nobody does — the caller records a cutoff leaf.
        Two or more candidates is a data error, not something to resolve by
        silent precedence.
        """
        candidates = [
            model
            for model in self._models
            if flow.iri in model.produces
            and (model.coverage is None or model.coverage.covers(flow))
        ]
        if not candidates:
            return None
        if len(candidates) > 1:
            names = ", ".join(type(model).__name__ for model in candidates)
            raise AmbiguousProducer(
                f"{len(candidates)} models produce {flow.iri} "
                f"at location={flow.location!r} time={flow.time!r}: {names}"
            )
        return candidates[0]

    def declared_producers(self, flow: Flow) -> list[Model]:
        """Every model that declares ``flow.iri``, coverage ignored.

        Separate from ``resolve`` on purpose: ``resolve`` keeps its three-way
        contract (0 → ``None``, 1 → the model, 2+ → ``AmbiguousProducer``).
        This answers the different question the caller needs when ``resolve``
        returned ``None`` — is this flow unmodelled, or did a registered
        model's coverage filter it out? Those are very different bugs, and
        reporting the second as the first is the hardest kind to track down.
        """
        return [model for model in self._models if flow.iri in model.produces]
