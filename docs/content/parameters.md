---
tags:
  - parameters
---

# Parameters

A [`ParameterSet`](../api/parameter_set.md) is a table of rows keyed by location and time.
`at(location, time)` widens the lookup until something matches, and writes every widening
step into the returned row's provenance. Nothing is substituted silently, and nothing is
extrapolated beyond the data.

## Loading from a trailpack file

```python
from trailrunner import LocationHierarchy, ParameterSet

params = ParameterSet.from_parquet(
    "dac_params.parquet",
    hierarchy=LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"}),
)
```

The parquet file carries a [Data Package](https://datapackage.org) descriptor in its schema
metadata under the key `datapackage.json`. `trailrunner` reads each field's `unit.name` and
its `rdfType` (or `taxonomyUrl`) out of it, which is how `row.unit_of()` and `row.iri_of()`
can answer without the model hardcoding anything.

Column names default to `location` and `time` and can be overridden:

```python
params = ParameterSet.from_parquet(path, location_column="region", time_column="year")
```

## Resolution order

1. **Exact match** on `(location, time)`.
2. **Location fallback** along the [`LocationHierarchy`](../api/location.md) chain, most
   specific first: `CH → RER → GLO`. The chain always ends at the root, so every lookup has
   a last resort.
3. **Time interpolation**, linear, between the two bracketing years present for that
   location.

If a location has no row bracketing the requested year, the lookup moves on to the next
location in the chain rather than extrapolating. When the chain is exhausted,
[`ParameterNotFound`](../api/errors.md) is raised, naming what was tried.

!!! note "Booleans are not averaged"

    Interpolation applies to real-valued columns only. A boolean column keeps the lower
    row's value instead of being averaged into a meaningless float.

## What a row tells you

```python
row = params.at(location="CH", time=2025)

row["heat_demand"]            # 5.5
row.heat_demand               # the same value
row.unit_of("heat_demand")    # "MJ"
row.iri_of("heat_demand")     # "https://vocab.sentier.dev/parameters/heat-demand"
row.provenance
```

```python
{
    "location_requested": "CH",
    "location_used": "CH",
    "location_fallback": False,
    "time_requested": 2025,
    "time_used": 2025,
    "time_interpolated": True,
    "time_bracket": (2020, 2030),
}
```

`location_used` is the location of the row actually taken, not the candidate that was
searched for. With no location requested every row is a candidate and the first one wins —
reporting `None` there while handing back the `CH` row would be exactly the silent
precedence this design refuses.

A row owns its `values` and sees `units` and `iris` through read-only views, so nothing done
to a row can reach back into the parameter set that produced it.

## Getting provenance into the report

Models pass the row's provenance through in their `Result`:

```python
return Result(..., provenance=dict(row.provenance))
```

The [`Report`](../api/report.md) then collects it per node in `report.provenance`, so a
reader can see which fallbacks the number rests on without re-running anything.

## In-memory parameter sets

Handy for tests and for a first run, where the units are passed directly instead of coming
from the file metadata:

```python
params = ParameterSet(
    rows=[{"location": "CH", "time": 2030, "heat_demand": 5.0}],
    units={"heat_demand": "MJ"},
    iris={"heat_demand": "https://vocab.sentier.dev/parameters/heat-demand"},
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
```
