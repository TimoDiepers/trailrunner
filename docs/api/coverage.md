---
icon: lucide/scan
tags:
  - api
---

# Coverage

Where, when and under which conditions a model is valid. `None` on `locations` or `time_range` means no restriction; a `ContextRange` restricts only flows that name that condition (a demand asking for no pressure accepts any). A flow outside a model's coverage is reported as `coverage_excluded`, not `no_model_found`.

::: trailrunner.params.coverage
