---
icon: lucide/zap
tags:
  - tutorial
---

# Quick Start

One full calculation in Python with the direct air capture model that ships with
`trailrunner`, and what the report says about the parts of the supply chain nobody
modelled. Prefer the shell? The [CLI tutorial](cli.md) runs a whole LCA without writing
Python.

## 1. Parameters

A model reads its numbers from a [`ParameterSet`](../../api/parameter_set.md). In a real
study they come from a [trailpack](https://github.com/TimoDiepers/trailpack) parquet file,
which carries each column's unit and concept IRI in its embedded metadata:

```python
from trailrunner import LocationHierarchy, ParameterSet

params = ParameterSet.from_parquet(
    "dac_params.parquet",
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
```

For a first run, hand the rows over directly, units included:

```python
from trailrunner import LocationHierarchy, ParameterSet
from trailrunner.core.time import GYEAR
from trailrunner.core.units import DEG_C, KWH, MJ, UNITLESS

params = ParameterSet(
    rows=[
        {
            "location": "CH",
            "time": "2030",
            "heat_demand": 5.0,
            "electricity_demand": 0.4,
            "temperature": 10.0,
            "humidity": 0.70,
        },
    ],
    units={
        "heat_demand": MJ,
        "electricity_demand": KWH,
        "temperature": DEG_C,
        "humidity": UNITLESS,
    },
    time_standard=GYEAR,
    hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}),
)
```

The [`LocationHierarchy`](../../api/location.md) is the fallback ladder: a lookup for `CH`
that finds nothing widens to `RER`, then to `GLO`. See [Parameters](../parameters.md).

## 2. Register the models

A [`Glossary`](../../api/glossary.md) indexes model *instances* by the product IRIs they
declare. Instances, not classes, because a model needs its parameters before it can answer
anything.

```python
from trailrunner import Glossary
from trailrunner.models.dac import DirectAirCapture

glossary = Glossary([DirectAirCapture(params=params)])
```

## 3. Calculate

```python
from trailrunner import Demand, Flow, Orchestrator
from trailrunner.core.time import in_year
from trailrunner.core.units import KG
from trailrunner.models.dac import CO2_CAPTURED

report = Orchestrator(glossary).calculate(
    Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", **in_year(2030)), amount=1000.0, unit=KG)
)
```

The [`Orchestrator`](../../api/orchestrator.md) finds `DirectAirCapture` for the demand,
calls it with the **full** 1000 kg, validates the [`Result`](../../api/result.md), and
queues the heat and electricity demands it returned.

## 4. Look at the whole run

```python
print(report.summary())
print()
print(report.tree())
```

```text
1 node, 1 inventory entry
2 unresolved (no_model_found: 2)
0 proxies
attribution: allocation=none, capital=per_output

1000 kg fi_2811_21 @CH/2030  [model: DirectAirCapture]
  5000 MJ fi_1730_9 @CH/2030  [cutoff: no_model_found]
  400 kWh fi_17100 @CH/2030  [cutoff: no_model_found]
```

`summary()` is the trust check: how many nodes ran, how much stayed unresolved and why, and
which normative choices the run was made under. `tree()` is the supply chain as it was
walked. Each line shows the demand, the last segment of its IRI (`fi_1730_9` is BONSAI's
"heat from main producers of heat"), where and when, and how that node was answered. Pass
`labels=` to print vocabulary names in place of IRI segments. See
[Reading a Report](../reports.md#summary-and-tree).

## 5. Read the inventory

```python
from trailrunner.core.units import symbol

for (flow, unit), amount in report.inventory.items():
    print(f"{amount:>10.2f} {symbol(unit)}  {flow.iri}  {flow.location} {flow.time}")
```

```text
  -1000.00 kg  https://vocab.sentier.dev/flows/co2-from-air  CH 2030
```

Negative, because the CO<sub>2</sub> is taken *out* of the air. The key is a `(Flow, unit)`
pair (the unit is a vocabulary IRI; `symbol` prints it the way a person reads it), and a
`Flow` keeps its location and time, so emissions at different places or times
stay apart.

## 6. Look at what is missing

Nothing in the glossary produces heat or electricity, so those demands never became
inventory. They are not silently zero. They are listed:

```python
for record in report.unresolved:
    print(f"{record.reason}: {record.demand.amount:.1f} {symbol(record.demand.unit)} "
          f"of {record.demand.flow.iri}")
```

```text
no_model_found: 5000.0 MJ of https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9
no_model_found: 400.0 kWh of https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100
```

Register a heat model and an electricity model and run again, and the inventory fills in.
[Writing a Model](../writing_a_model.md) shows how.

!!! tip "`no_model_found` vs `coverage_excluded`"

    If a model *does* declare the product but its [`Coverage`](../../api/coverage.md)
    rejects this location or year, the reason is `coverage_excluded` and `record.detail`
    names the model. The two have different fixes: register a model, or widen the coverage
    of one you already have.

## 7. Check the provenance

Every parameter lookup records how it was resolved: which location and year were used,
and whether a fallback or an interpolation happened.

```python
for node_id, provenance in report.provenance.items():
    print(node_id, provenance)
```

```text
0 {'location_requested': 'CH', 'location_used': 'CH', 'location_fallback': False,
   'time_requested': '2030', 'time_used': '2030', 'time_interpolated': False}
```

Ask for a year that is not in the table, say 2025 against rows for 2020 and 2030, and
`time_interpolated` becomes `True` with a `time_bracket` naming the two rows used.

## Next steps

- [Tutorial: an LCA from the CLI](cli.md): a full supply chain, a score and a curve, from the shell
- [Core Concepts](../concepts.md): the parts and how they fit together
- [Writing a Model](../writing_a_model.md): the `Model` contract in full
- [Reading a Report](../reports.md): everything a `Report` carries
