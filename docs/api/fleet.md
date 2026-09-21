---
icon: lucide/factory
tags:
  - api
---

# Fleet

A [`ParameterSet`](parameter_set.md) answers *what is the number here and now*, and one row wins. A `Fleet` is the other shape: **every** plant running in the demanded year is part of the answer, because each was built in its own year, and its construction belongs in that year rather than in the year it produces anything.

The table is a list of plants that were actually built - where, when, how big, and for how long:

| plant | location | build_year | capacity | lifetime |
|-------|----------|-----------|----------|----------|
| ch-1 | CH | 2026 | 12000.0 | 20 |
| ch-2 | CH | 2029 | 40000.0 | 20 |
| rer-1 | RER | 2024 | 8000.0 | 25 |

`operating(location=..., time=...)` keeps the plants with `build_year <= time < build_year + lifetime`, widening through the [`LocationHierarchy`](location.md) when a location has none running. The window is half-open at the top so the year a plant retires is not also a year it produces. Nothing is interpolated: a `Fleet` will not invent a plant for a year between two of them, it looks to the parent location instead.

What comes back is the plant rows themselves plus the two summaries every model needs - `total_capacity` to divide by, and the capacity-weighted `mean_build_year` - and a provenance entry naming the plants it selected.

::: trailrunner.params.fleet
