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

    The defaults ``max_depth=10`` and ``max_nodes=1000`` are arbitrary starting
    points, not tuned figures: they are large enough for the supply chains v1
    is exercised on and small enough that a runaway loop stops quickly. Raise
    them freely; ``report.truncated`` says when they bit.
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
                # "Nobody models this" and "a model does, but its coverage
                # rejected this flow" are different problems with different
                # fixes — widen the coverage, or fill in the year the flow is
                # missing. Reporting the second as the first sends the reader
                # looking for a model that is already registered.
                near_misses = self.glossary.declared_producers(item.demand.flow)
                if near_misses:
                    names = ", ".join(type(m).__name__ for m in near_misses)
                    log.unresolved(
                        item.demand,
                        reason="coverage_excluded",
                        depth=item.depth,
                        parent=item.parent,
                        detail=(
                            f"{names} declares this product but its coverage does not "
                            f"cover location={item.demand.flow.location!r} "
                            f"time={item.demand.flow.time!r}"
                        ),
                    )
                else:
                    log.unresolved(
                        item.demand, reason="no_model_found", depth=item.depth, parent=item.parent
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
