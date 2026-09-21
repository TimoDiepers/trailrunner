"""A model's declared validity in space and time."""

from dataclasses import dataclass

from trailrunner.core.flow import Flow


@dataclass(frozen=True)
class Coverage:
    """Where and when a model is valid.

    ``locations`` is a frozenset rather than a set so that Coverage stays
    hashable. ``None`` on either field means "no restriction".
    """

    locations: frozenset[str] | None = None
    time_range: tuple[int, int] | None = None

    def covers(self, flow: Flow) -> bool:
        if self.locations is not None:
            if flow.location is None or flow.location not in self.locations:
                return False
        if self.time_range is not None:
            if flow.time is None:
                return False
            earliest, latest = self.time_range
            if not earliest <= flow.time <= latest:
                return False
        return True
