---
icon: lucide/component
tags:
  - api
---

# Model

The base class for process models — a process is any activity that turns demands into products: a technology, a service, a transport leg. Subclasses declare the product IRIs they `produces`, optionally restrict their validity with a [`Coverage`](coverage.md), and implement `apply(demand) -> Result`.

`apply` receives the *full* demand amount, never a unit demand, so nonlinear behaviour is preserved. See [Writing a Model](../content/writing_a_model.md).

::: trailrunner.core.model
