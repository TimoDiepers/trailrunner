"""The Model base class: Python code for one technology."""

from typing import Any

from trailrunner.core.flow import Demand
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings
from trailrunner.params.coverage import Coverage


class Model:
    """Base class for technology models.

    Subclasses declare which product IRIs they ``produces``, optionally
    restrict their validity with ``coverage``, and implement ``apply``.

    ``apply`` receives the *full* demand amount, never a unit demand, so that
    nonlinear behaviour is preserved: a plant at ten times the scale is not ten
    times the plant.
    """

    produces: list[str] = []
    coverage: Coverage | None = None
    params: Any = None

    def __init__(self, settings: Settings | None = None, params: Any = None) -> None:
        self.settings = settings if settings is not None else Settings()
        if params is not None:
            self.params = params

    def apply(self, demand: Demand) -> Result:
        raise NotImplementedError(
            f"{type(self).__name__} must implement apply(demand) -> Result"
        )
