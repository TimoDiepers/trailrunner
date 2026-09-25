---
icon: lucide/scan
tags:
  - api
---

# Coverage

Where, when and under which conditions a model is valid. `None` on `locations` or `time_range` means no restriction; a `ContextRange` restricts only flows that name that condition (a demand asking for no pressure accepts any). A flow outside a model's coverage is reported as `coverage_excluded`, not `no_model_found`.

`time_range` is a [`TimeRange`](time.md), built with [`year_range`](time.md) for the common case; a `ContextRange`'s bounds are read with the [unit](units.md) they are stated in.

::: trailrunner.params.coverage
