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

    def resolve(self, flow: Flow, exclude: Iterable[Model] = ()) -> Model | None:
        """Return the model that produces ``flow``.

        ``None`` means nobody does — the caller records a cutoff leaf.
        Two or more candidates is a data error, not something to resolve by
        silent precedence.

        ``exclude`` drops candidates **by instance identity**. It exists for
        one caller: a substitution credit must be answered by someone *other*
        than the process that just made the co-product, or the credit resolves
        back to that process, which credits itself again, and the burden
        cancels to zero. Identity, not class, because a CH plant and an FR
        plant of the same class are different processes and each remains a
        candidate for the other's credits.
        """
        excluded = {id(model) for model in exclude}
        candidates = [
            model
            for model in self._models
            if flow.iri in model.produces
            and (model.coverage is None or model.coverage.covers(flow))
            and id(model) not in excluded
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

    def declared_models(self, flow: Flow, exclude: Iterable[Model] = ()) -> list[Model]:
        """Every model that declares ``flow.iri``, coverage ignored.

        Separate from ``resolve`` on purpose: ``resolve`` keeps its three-way
        contract (0 → ``None``, 1 → the model, 2+ → ``AmbiguousModelMatch``).
        This answers the different question the caller needs when ``resolve``
        returned ``None`` — is this flow unmodelled, or did a registered
        model's coverage filter it out? Those are very different bugs, and
        reporting the second as the first is the hardest kind to track down.

        ``exclude`` drops the same instances ``resolve`` would drop, so that a
        credit the offering model alone could have answered is explained as
        the cutoff it is rather than as a coverage miss it is not.
        """
        excluded = {id(model) for model in exclude}
        return [
            model
            for model in self._models
            if flow.iri in model.produces and id(model) not in excluded
        ]
