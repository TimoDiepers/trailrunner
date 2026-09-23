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
| `no_model_found` | no registered model declares this product IRI | write or register a model |
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
happened. The model's record and nothing else: how the model was *chosen* is in
`resolutions`, and the run's normative choices are in `attribution`, because the model
neither made nor saw them:

```python
for node_id, entries in report.provenance.items():
    if entries.get("location_fallback") or entries.get("time_interpolated"):
        print(node_id, entries)
```

## `nodes` and `edges`

The traversal graph as it happened. `nodes` are the `NodeRecord`s in visit order, each with
its `demand`, its `result`, its `depth` and its `parent`; `edges` are `(parent, child)` id
pairs. Every visit is its own node — nodes are never merged, so the same process
appearing twice in a supply chain appears twice here.

## `summary()` and `tree()`

Both return a string rather than printing, so they are testable and a caller can write them to
a file.

`tree()` is the traversal as indented text. Every line says how honestly that node was
answered: `[model: ...]` for an exact match, `[proxy: ...]` for a node answered by relaxing the
demand (naming what was relaxed), `[background: cumulative]` or
`[background: unit_process, incomplete]` for one borrowed from a background pack — see
[Resolution](resolution.md) for what that distinction means — or `[cutoff: ...]` for a demand
nothing answered. A cutoff hangs under the node that asked for it, because that is where in
the chain it happened, not under the root.

`summary()` is nodes, inventory size, unresolved counts broken down by reason, proxy count, and
whether the traversal was truncated — the numbers to check before trusting the inventory.

Under `substitution` both the unresolved and the proxy line also split out what happened on
a **credit branch** — a negative demand, an avoided burden being traversed:

```text
1 unresolved (no_model_found: 1, of which 1 on a credit branch)
```

The sign is the point. A forgone burden *understates* the impact; a forgone credit
*overstates* it. One bucket counting both tells the reader neither. Under any rule but
`substitution` nothing negative is ever demanded, so the clause never prints.

```python
print(report.tree())
print()
print(report.summary())
```

Running the DAC traversal with a `Boiler` model answering the heat demand and nothing
registered for electricity (`tests/test_dac.py::test_end_to_end_traversal_with_a_heat_model`)
prints:

```text
1000 kg co2-captured @CH/2030  [model: DirectAirCapture]
  5000 MJ heat @CH/2030  [model: Boiler]
  400 kWh electricity @CH/2030  [cutoff: no_model_found]

2 nodes, 2 inventory entries
1 unresolved (no_model_found: 1)
0 proxies
```

The electricity cutoff is indented under the DAC node, not the root, because the DAC node is
what asked for it. This particular run only ever asked the `model` tier — `[proxy: ...]` and
`[background: ...]` appear once a [`ResolutionChain`](../api/resolution.md) with a
generalising or background provider answers a node instead; see
[Resolution](resolution.md).

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
`unresolved`, `provenance`, `resolution` (how a node's demand was matched — which tier
answered and what, if anything, was relaxed to get there) and `attribution` (the normative
choice applied to it):

```python
from trailrunner.orchestration.log import Log

log = Log()
# ... a traversal fills it ...
log.to_parquet("run.parquet")
```

One flat table under one explicit schema, rather than six files, because the point is to
diff two runs with a single read: runs that differ only in which cutoffs they hit or which
parameter fallbacks they took differ on disk too.

Nothing nested goes into a cell. A `resolution` or `attribution` record is flattened one
row per leaf — `relaxation.0`, `allocation`, `property`, `share`, `co_product.0`,
`co_product.1` — because a list or a dict stringified whole lands as a Python repr a reader
has to parse back out, and a column nobody can filter on is not a reproducible record.
