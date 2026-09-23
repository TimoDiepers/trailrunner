"""The Model base class: Python code for one process."""

from collections.abc import Sequence
from typing import Any

from trailrunner.core.flow import Demand
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings
from trailrunner.params.coverage import Coverage


class Model:
    """Base class for process models.

    A process is any activity that turns demands into products: a technology,
    a service, a transport leg.

    Subclasses declare which product IRIs they ``produces``, optionally
    restrict their validity with ``coverage``, and implement ``apply``.

    ``apply`` receives the *full* demand amount, never a unit demand, so that
    nonlinear behaviour is preserved: a plant at ten times the scale is not ten
    times the plant.
    """

    # An empty tuple, not an empty list: a class-level mutable default is
    # shared by every subclass, so one model appending instead of assigning
    # would quietly add its product to every other model in the run.
    # Subclasses may still assign a list; only membership is ever tested.
    produces: Sequence[str] = ()
    coverage: Coverage | None = None
    params: Any = None

    supports: frozenset[str] = frozenset({"none"})
    """Allocation rules this model can honour.

    The default is the conservative one: a model says nothing about
    multifunctionality until its author has thought about it. A run asking for
    a rule that is not here raises ``UnsupportedAttribution`` rather than
    quietly answering a different question.
    """

    def __init__(self, settings: Settings | None = None, params: Any = None) -> None:
        self.settings = settings if settings is not None else Settings()
        if params is not None:
            self.params = params

    def apply(self, demand: Demand) -> Result:
        """Answer one demand: what I made, what I need, what I emitted.

        The production contract, which the Runner enforces and every subclass
        must honour:

        - ``result.production`` contains the demanded product — an Exchange on
          the **same flow IRI**, in the **same unit** as the demand.
        - Its amount (summed, if split over several entries) **covers**
          ``demand.amount``. ``apply`` receives the full demanded amount, never
          a unit demand, and nothing downstream rescales the Result: producing
          1 kg against a demand for 1000 would shrink the whole inventory
          thousandfold. Producing more than demanded is allowed.
        - Every amount in ``production`` is positive, and every exchange in
          all three lists carries a non-empty unit.
        - ``supports`` names the allocation rules this model can honour; the
          Runner rejects a run whose rule is not in it rather than letting the
          model silently ignore it.

        The usual first line is therefore::

            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)]

        ``technosphere`` demands are pushed onto the traversal queue,
        ``biosphere`` exchanges are accumulated into the inventory, and
        ``provenance`` records which parameter rows and fallbacks were used.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement apply(demand) -> Result"
        )
