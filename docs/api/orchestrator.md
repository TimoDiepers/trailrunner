---
icon: lucide/waypoints
tags:
  - api
---

# Orchestrator

The traversal loop. Walks demands outward, every visit its own node. Loops are bounded by `max_depth` and `max_nodes` and flagged as warnings, not solved - a truncated tree with an honest unresolved list beats a converged number that would be wrong.

::: trailrunner.orchestration.orchestrator
