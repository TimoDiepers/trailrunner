"""The traversal loop."""

from collections.abc import Callable

from trailrunner.core.flow import Demand
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.queue import Queue, QueueItem
from trailrunner.orchestration.report import Report
from trailrunner.orchestration.runner import Runner


class Orchestrator:
    """Walks demands outward through the supply chain.

    Every visit is its own node; nodes are never merged. A loop is therefore
    bounded by ``max_depth`` and ``max_nodes`` and flagged as a warning, rather
    than solved. A truncated tree with an honest unresolved list beats a
    converged number that would be wrong.
    """

    def __init__(
        self,
        glossary: Glossary,
        runner: Runner | None = None,
        max_depth: int = 10,
        max_nodes: int = 1000,
        priority: Callable[[Demand], float] | None = None,
    ) -> None:
        self.glossary = glossary
        self.runner = runner if runner is not None else Runner(glossary)
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.priority = priority

    def calculate(self, demand: Demand) -> Report:
        log = Log()
        queue = Queue(priority=self.priority)
        queue.push(QueueItem(demand=demand, depth=0, parent=None, path=()))
        truncated = False

        while queue:
            if len(log.nodes) >= self.max_nodes:
                truncated = True
                self._drain(queue, log, reason="max_nodes")
                break

            item = queue.pop()

            if item.depth >= self.max_depth:
                truncated = True
                log.unresolved(item.demand, reason="max_depth", depth=item.depth, parent=item.parent)
                continue

            model = self.glossary.resolve(item.demand.flow)
            if model is None:
                log.unresolved(
                    item.demand, reason="no_producer", depth=item.depth, parent=item.parent
                )
                continue

            result = self.runner.apply(item.demand, model=model)
            node_id = log.write(item.demand, result, depth=item.depth, parent=item.parent)

            if item.demand.flow.iri in item.path:
                log.warn(
                    f"{item.demand.flow.iri} repeats on its own supply chain path; "
                    "traversal is truncated, not converged",
                    node_id,
                )

            path = (*item.path, item.demand.flow.iri)
            for child in result.technosphere:
                queue.push(
                    QueueItem(demand=child, depth=item.depth + 1, parent=node_id, path=path)
                )

        return Report.from_log(log, truncated=truncated)

    @staticmethod
    def _drain(queue: Queue, log: Log, reason: str) -> None:
        while queue:
            item = queue.pop()
            log.unresolved(item.demand, reason=reason, depth=item.depth, parent=item.parent)
