"""What a model run returned."""

from dataclasses import dataclass, field
from typing import Any

from trailrunner.core.flow import Demand, Exchange


@dataclass
class Result:
    """The answer to "given this demand, what happened?".

    ``production`` must cover the demand that triggered the run; the Runner
    checks this. ``technosphere`` demands are pushed onto the traversal queue.
    ``biosphere`` exchanges are accumulated into the inventory. ``provenance``
    records which parameter rows and fallbacks the model actually used.
    """

    production: list[Exchange]
    technosphere: list[Demand] = field(default_factory=list)
    biosphere: list[Exchange] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
