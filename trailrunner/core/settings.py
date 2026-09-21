"""Run-wide knobs."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Settings:
    """One flat namespace for the whole run.

    Scenario names, a default year, model-specific switches. Anything that
    varies per technology belongs in that technology's ParameterSet instead.

    Frozen to prevent reassignment, but not hashable — ``values`` is a dict.
    """

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)
