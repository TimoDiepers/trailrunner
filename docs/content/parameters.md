---
icon: lucide/sliders-horizontal
tags:
  - parameters
---

# Parameters

A [`ParameterSet`](../api/parameter_set.md) is a table of rows keyed by location and year.
`at(location, time)` widens the lookup until something matches and records each widening
step in the returned row's provenance. Nothing is substituted silently, and nothing is
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
metadata under the key `datapackage.json`. For each field, trailrunner reads `unit.name`
and `rdfType` (or `taxonomyUrl`), which is how `row.unit_of()` and `row.iri_of()` answer
without the model hard-coding anything. The field list is read from
`resources[].schema.fields`, where Frictionless puts it and trailpack writes it. The flatter
`resources[].fields` is also accepted, for descriptors assembled by hand.

[trailpack](https://github.com/TimoDiepers/trailpack) writes these files: `Field`, `Unit`
and `MetaDataBuilder` for the descriptor, `Packing.write_parquet` for the file.
`examples/dac.ipynb` does it end to end. Any tool that writes the same metadata works: the
[CLI tutorial](getting_started/cli.md#5-get-a-score-method) writes one with pyarrow alone.

The location and time columns default to `location` and `time`:

```python
params = ParameterSet.from_parquet(path, location_column="region", time_column="year")
```

## In memory

Useful for tests and first runs. Units and IRIs are passed directly instead of coming from
file metadata:

```python
params = ParameterSet(
    rows=[
        {"location": "CH", "time": 2020, "heat_demand": 6.0},
        {"location": "CH", "time": 2030, "heat_demand": 5.0},
        {"location": "RER", "time": 2030, "heat_demand": 7.0},
    ],
    units={"heat_demand": "MJ"},
    iris={"heat_demand": "https://vocab.sentier.dev/parameters/heat-demand"},
    hierarchy=LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"}),
    source="hand-written parameters",
)
```

`source` is optional and only appears in error messages. `from_parquet` sets it to the
file path, so a `MissingUnit` can point at the file.

## Resolution order

1. **Exact match** on `(location, time)`.
2. **Time interpolation**, linear, between the two years bracketing the request at that
   location.
3. **Location fallback** along the [`LocationHierarchy`](../api/location.md), most specific
   first (`FR → RER → GLO`), repeating 1 and 2 at each level.

A location with no row bracketing the requested year is skipped rather than extrapolated.
If the chain runs out, [`ParameterNotFound`](../api/errors.md) is raised, naming what was
tried.

!!! note "The chain always ends at the root"

    `LocationHierarchy.chain` always ends at its root (`GLO` by default). A location that
    isn't in the map jumps straight to the root: with `{"CH": "RER", "RER": "GLO"}`, a
    lookup for `FR` tries `FR`, then `GLO`, and never `RER`. Put every location your
    demands use into the map.

!!! note "Booleans are not averaged"

    Interpolation applies only to real-valued columns. A boolean column keeps the lower
    row's value.

## What a row tells you

With the in-memory table above:

```python
row = params.at(location="CH", time=2025)

row["heat_demand"]            # 5.5, halfway between 2020 and 2030
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

and a fallback:

```python
params.at(location="FR", time=2030).provenance
# {'location_requested': 'FR', 'location_used': 'RER', 'location_fallback': True,
#  'time_requested': 2030, 'time_used': 2030, 'time_interpolated': False}
```

`location_used` is the location of the row actually taken. With no location requested
every row is a candidate and the first one wins, and `location_used` says which one it was.

A row owns its values and sees units and IRIs through read-only views, so nothing done to a
row reaches back into the parameter set.

!!! warning "`unit_of` is strict"

    A column with no declared unit raises [`MissingUnit`](../api/errors.md), naming the
    column and the file. The caller is almost always building an `Exchange`, whose unit is
    a `str`. Returning `None` would travel into the model's result and fail later in the
    Runner, blaming the model for what is really a gap in the file's metadata.

    Pass a `default` to ask without asserting: `row.unit_of("location", default=None)`.
    `iri_of` is permissive and returns `None`, since an IRI is metadata rather than
    something that ends up in a result.

## Getting provenance into the report

A model passes the row's provenance through in its `Result`:

```python
return Result(..., provenance=dict(row.provenance))
```

and the [`Report`](../api/report.md) collects it per node in `report.provenance`, so a
reader can see which fallbacks a number rests on without re-running anything. Add your own
keys alongside if they help a reader: `MeteredCementPlant` adds `"source": "measured"`.

## When many rows are the answer: fleets

A parameter lookup resolves to one row. Some tables work differently. In a list of plants
that were actually built, *every* plant running in the demanded year is part of the
answer, and each one was built in its own year.

[`Fleet`](../api/fleet.md) reads that shape. Rows need a location, `build_year`,
`capacity` and `lifetime`, and optionally a `plant` identifier (all column names can be
overridden):

```python
from trailrunner import Fleet, LocationHierarchy

fleet = Fleet(
    rows=[
        {"plant": "ch-1", "location": "CH", "build_year": 2026, "capacity": 4000.0, "lifetime": 20},
        {"plant": "ch-2", "location": "CH", "build_year": 2029, "capacity": 8000.0, "lifetime": 20},
        {"plant": "rer-1", "location": "RER", "build_year": 2024, "capacity": 50000.0, "lifetime": 20},
    ],
    units={"capacity": "t/year", "lifetime": "year"},
    hierarchy=LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"}),
)

running = fleet.operating(location="CH", time=2030)
running.provenance["plants"]     # ['ch-1', 'ch-2']
running.total_capacity           # 12000.0
running.unit_of("capacity")      # 't/year'
running.mean_build_year          # 2028.0, weighted by capacity

fleet.operating(location="CH", time=2027).provenance["plants"]   # ['ch-1']
fleet.operating(location="FR", time=2030).provenance["plants"]   # ['rer-1'], via RER
```

`Fleet.from_parquet(path, hierarchy=...)` reads the same table, with units from the
metadata.

A plant runs in year `t` when `build_year <= t < build_year + lifetime`: a twenty-year
plant built in 2005 is gone by 2025. `operating` widens through the hierarchy when a
location has nothing running, but it never pools two levels, since mixing Swiss plants with
European ones would count the Swiss ones twice. It never interpolates a plant into
existence either.

`DirectAirCapture` and `CementPlant` accept a `fleet=`. With one, they amortize each running
plant's construction over its output according to the run's
[capital rule](attribution.md#capital-per_output-per_year-first_life), and demand that
plant's share **in the plant's own build year**, years before the output it pays for.
