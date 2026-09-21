---
icon: lucide/scroll-text
tags:
  - api
---

# Log

The append-only record of everything the traversal did: nodes, edges, cutoff leaves and warnings, in the order they happened. `to_parquet` writes all of it to one flat table under one explicit schema, so two runs can be diffed with a single read.

::: trailrunner.orchestration.log
