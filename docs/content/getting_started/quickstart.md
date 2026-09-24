---
icon: lucide/zap
tags:
  - tutorial
---

# Quick Start

This walks through one full calculation with the direct air capture model that ships with
`trailrunner`, and shows what the report says about the parts of the supply chain nobody
modelled.

## 1. Parameters

A model reads its numbers from a [`ParameterSet`](../../api/parameter_set.md). In production
those come from a [trailpack](https://github.com/TimoDiepers/trailpack) parquet file, which
carries the units and concept IRIs of every column in its embedded datapackage metadata
(`examples/dac.ipynb` writes one with trailpack, end to end):

```python
from trailrunner import LocationHierarchy, ParameterSet

params = ParameterSet.from_parquet(
    "dac_params.parquet",
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
```

For a first run you can hand the rows over directly, units included:

```python
from trailrunner import LocationHierarchy, ParameterSet

params = ParameterSet(
    rows=[
        {
            "location": "CH",
            "time": 2030,
            "heat_demand": 5.0,
            "electricity_demand": 0.4,
            "temperature": 10.0,
            "humidity": 0.70,
        },
    ],
    units={
        "heat_demand": "MJ",
        "electricity_demand": "kWh",
        "temperature": "degC",
        "humidity": "dimensionless",
    },
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
```

The [`LocationHierarchy`](../../api/location.md) is the fallback ladder: a lookup for `CH`
that finds nothing widens to `RER`, then to `GLO`.

## 2. Register the models

A [`Glossary`](../../api/glossary.md) maps product IRIs to the model instances that produce
them. It holds *instances*, not classes, because a model needs its parameters before it can
answer anything.

```python
from trailrunner import Glossary
from trailrunner.models.dac import DirectAirCapture

glossary = Glossary([DirectAirCapture(params=params)])
```

## 3. Calculate

```python
from trailrunner import Demand, Flow, Orchestrator
from trailrunner.models.dac import CO2_CAPTURED

report = Orchestrator(glossary).calculate(
    Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg")
)
```

The [`Orchestrator`](../../api/orchestrator.md) resolves the demand to `DirectAirCapture`,
calls it with the **full** 1000 kg, validates the [`Result`](../../api/result.md), and pushes
the heat and electricity demands it returned onto the queue.

## 4. Read the report

```python
for (flow, unit), amount in report.inventory.items():
    print(f"{amount:>12.2f} {unit}  {flow.iri}")
```

```text
    -1000.00 kg  https://vocab.sentier.dev/flows/co2-from-air
```

Negative, because the CO<sub>2</sub> is taken *out* of the air.

## 5. Look at what is missing

Nothing in the glossary produces heat or electricity, so those demands never became
inventory. They are not silently zero — they are listed:

```python
for record in report.unresolved:
    print(f"{record.reason}: {record.demand.amount:.1f} {record.demand.unit} of {record.demand.flow.iri}")
```

```text
no_model_found: 5000.0 MJ of https://vocab.sentier.dev/products/heat
no_model_found: 400.0 kWh of https://vocab.sentier.dev/products/electricity
```

Registering an electricity and a heat model, and running again, is how the inventory gets
completed. See [Writing a Model](../writing_a_model.md).

!!! tip "`no_model_found` vs `coverage_excluded`"

    If a model *does* declare the product but its [`Coverage`](../../api/coverage.md)
    rejected this location or year, the reason is `coverage_excluded` and `record.detail`
    names the model. Those are different bugs with different fixes: register a model, or
    widen an existing one's coverage.

## 6. Check the provenance

Every parameter lookup records how it was resolved — which location and year were actually
used, whether a fallback or an interpolation happened:

```python
for node_id, provenance in report.provenance.items():
    print(node_id, provenance)
```

```text
0 {'location_requested': 'CH', 'location_used': 'CH', 'location_fallback': False,
   'time_requested': 2030, 'time_used': 2030, 'time_interpolated': False}
```

Ask for a year that is not in the table, say 2025, and `time_interpolated` becomes `True`
with a `time_bracket` naming the two rows it sat between. See
[Parameters](../parameters.md).

## Next steps

- [Core Concepts](../concepts.md) — the pieces and how they fit together
- [Writing a Model](../writing_a_model.md) — the `Model` contract in full
- [Reading a Report](../reports.md) — inventory, unresolved, provenance, warnings
