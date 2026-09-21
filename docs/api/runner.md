---
icon: lucide/shield-check
tags:
  - api
---

# Runner

Calls a model and checks that it honoured its contract. The single place where [`Result`](result.md) validation happens, and a separate object so a concurrent implementation can replace it behind the same interface.

::: trailrunner.orchestration.runner
