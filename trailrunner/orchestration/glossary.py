"""Who produces what."""

from collections.abc import Iterable

from trailrunner.core.errors import AmbiguousModelMatch
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
            raise AmbiguousModelMatch(
                f"{len(candidates)} models produce {flow.iri} "
                f"at location={flow.location!r} time={flow.time!r}: {names}"
            )
        return candidates[0]
