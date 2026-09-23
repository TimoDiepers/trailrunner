"""The traversal loop."""

from collections.abc import Callable

from trailrunner.core.flow import Demand
from trailrunner.core.settings import Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.queue import Queue, QueueItem
from trailrunner.orchestration.report import Report
from trailrunner.orchestration.runner import Runner
from trailrunner.resolution.chain import ResolutionChain
from trailrunner.resolution.models import ModelProvider


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
        resolver: Glossary | ResolutionChain,
        runner: Runner | None = None,
        max_depth: int = 10,
        max_nodes: int = 1000,
        priority: Callable[[Demand], float] | None = None,
        settings: Settings | None = None,
    ) -> None:
        # A bare Glossary is still a valid argument: it is the one-tier chain,
        # and every v1 caller passes one.
        self.chain = (
            resolver
            if isinstance(resolver, ResolutionChain)
            else ResolutionChain([ModelProvider(resolver)])
        )
        self.glossary = self.chain.glossary
        # self.glossary can be None here (a chain with no ModelProvider). That
        # is safe today because the Orchestrator always passes
        # model=offer.model into runner.apply below, so the Runner never
        # consults its own glossary.
        self.settings = settings if settings is not None else Settings()
        self.runner = runner if runner is not None else Runner(self.glossary, settings=self.settings)
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

            offer = self.chain.offer(item.demand)
            if offer is None:
                reason, detail = self.chain.explain(item.demand)
                log.unresolved(
                    item.demand,
                    reason=reason,
                    depth=item.depth,
                    parent=item.parent,
                    detail=detail or None,
                )
                continue

            result = self.runner.apply(offer.demand, model=offer.model)
            node_id = log.write(
                item.demand,
                result,
                depth=item.depth,
                parent=item.parent,
                model=type(offer.model).__name__,
                resolution=dict(offer.resolution),
            )

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
