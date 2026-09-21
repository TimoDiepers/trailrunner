---
tags:
  - concepts
---

# Reading a Report

`Orchestrator.calculate()` returns a [`Report`](../api/report.md). The numbers are only part
of it: the unresolved list and the provenance table say how much the numbers are worth.

## `inventory`

Biosphere exchanges summed over the whole traversal, keyed by `(Flow, unit)`. The `Flow`
keeps its location and time, so emissions at different places or years stay apart.

```python
for (flow, unit), amount in report.inventory.items():
    print(f"{amount:>12.2f} {unit}  {flow.iri}  {flow.location} {flow.time}")
```

## `unresolved`

Every demand that never became inventory, with the reason it stopped:

| `reason` | What happened | What to do |
| --- | --- | --- |
| `no_producer` | no registered model declares this product IRI | write or register a model |
| `coverage_excluded` | a model declares it, but its `Coverage` rejected this location or year; `detail` names the model | widen the coverage, or fix the flow's location/year |
| `max_depth` | the traversal hit the depth limit here | raise `max_depth` |
| `max_nodes` | the node budget ran out; the rest of the queue was drained into this list | raise `max_nodes` |

```python
for record in report.unresolved:
    line = f"{record.reason}: {record.demand.amount:.1f} {record.demand.unit} of {record.demand.flow.iri}"
    if record.detail:
        line += f" — {record.detail}"
    print(line)
```

A demand nobody models is reported, never silently treated as zero. An inventory with a
long unresolved list is an incomplete inventory, and the report says so out loud.

## `provenance`

Per node id, whatever that node's model recorded — for models that pass their parameter row
through, which location and year were actually used and whether a fallback or interpolation
happened:

```python
for node_id, entries in report.provenance.items():
    if entries.get("location_fallback") or entries.get("time_interpolated"):
        print(node_id, entries)
```

## `nodes` and `edges`

The traversal graph as it happened. `nodes` are the `NodeRecord`s in visit order, each with
its `demand`, its `result`, its `depth` and its `parent`; `edges` are `(parent, child)` id
pairs. Every visit is its own node — nodes are never merged, so the same technology
appearing twice in a supply chain appears twice here.

## `warnings` and `truncated`

`warnings` is a list of `(message, node_id)`. A flow that repeats on its own supply chain
path gets one: the traversal was **truncated, not converged**.

`truncated` is `True` when `max_depth` or `max_nodes` bit anywhere in the run. A truncated
tree with an honest unresolved list beats a converged number that would be wrong.

```python
if report.truncated:
    print("limits hit — raise max_depth / max_nodes, or accept the cutoffs")
```

The defaults (`max_depth=10`, `max_nodes=1000`) are starting points, not tuned figures:
large enough for the supply chains v1 is exercised on, small enough that a runaway loop
stops quickly. Raise them freely.

## Writing the log to parquet

The underlying [`Log`](../api/log.md) can go to a single parquet file, one row per record,
tagged by `kind` — `biosphere`, `node` (a node that emitted nothing, so it does not vanish),
`unresolved`, and `provenance`:

```python
from trailrunner.orchestration.log import Log

log = Log()
# ... a traversal fills it ...
log.to_parquet("run.parquet")
```

One flat table under one explicit schema, rather than four files, because the point is to
diff two runs with a single read: runs that differ only in which cutoffs they hit or which
parameter fallbacks they took differ on disk too.
