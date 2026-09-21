"""What to traverse next."""

import heapq
import itertools
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from trailrunner.core.flow import Demand


@dataclass(frozen=True)
class QueueItem:
    """A demand waiting to be traversed, with where it came from.

    ``path`` holds the flow IRIs already visited on the way here, so the
    Orchestrator can flag a loop without maintaining separate bookkeeping.
    """

    demand: Demand
    depth: int = 0
    parent: int | None = None
    path: tuple[str, ...] = field(default=())


class Queue:
    """FIFO by default; a heap when given a priority callable.

    No priority function ships with v1: with an inventory-only result there is
    no score to rank by, and amounts in MJ, kg and kWh are not comparable. The
    seam exists so score-based ranking can drop in unchanged later.
    """

    def __init__(self, priority: Callable[[Demand], float] | None = None) -> None:
        self._priority = priority
        self._fifo: deque[QueueItem] = deque()
        self._heap: list[tuple[float, int, QueueItem]] = []
        self._counter = itertools.count()

    def push(self, item: QueueItem) -> None:
        if self._priority is None:
            self._fifo.append(item)
        else:
            heapq.heappush(
                self._heap, (self._priority(item.demand), next(self._counter), item)
            )

    def pop(self) -> QueueItem:
        if self._priority is None:
            if not self._fifo:
                raise IndexError("pop from an empty Queue")
            return self._fifo.popleft()
        if not self._heap:
            raise IndexError("pop from an empty Queue")
        return heapq.heappop(self._heap)[2]

    def __len__(self) -> int:
        return len(self._fifo) if self._priority is None else len(self._heap)

    def __bool__(self) -> bool:
        return len(self) > 0
