---
icon: lucide/file-text
tags:
  - concepts
---

# Reading a Report

`Orchestrator.calculate()` returns a [`Report`](../api/report.md). The inventory is only
part of it. The unresolved list, the proxies and the provenance say how much the inventory
is worth.

| Attribute | What it holds |
| --- | --- |
| `inventory` | `{(Flow, unit): amount}`, biosphere flows summed over the whole traversal |
| `unresolved` | every demand that never became inventory, with its reason |
| `provenance` | `{node_id: dict}`, what each node's model recorded about its parameters |
| `resolutions` | `{node_id: dict}`, which tier answered each node and what it conceded |
| `proxies` | the subset of `resolutions` that weren't exact model matches |
| `attribution` | `{node_id: dict}`, the allocation rule applied to each node |
| `attribution_settings` | the run's `AttributionSettings` |
| `nodes`, `edges` | the traversal graph |
| `warnings` | `[(message, node_id)]`, e.g. a flow repeating on its own path |
| `truncated` | `True` if `max_depth` or `max_nodes` was hit |
| `log` | the underlying [`Log`](../api/log.md), for writing to parquet |

## `summary()` and `tree()`

Start here. Both return a string instead of printing, so they can be tested or written to
a file:

```python
print(report.summary())
print()
print(report.tree())
```

Here is the shipped cement chain for 1 t in Denmark in 2030, with tier 1 only:

```text
7 nodes, 11 inventory entries
9 unresolved (coverage_excluded: 1, no_model_found: 8)
0 proxies
attribution: allocation=none, capital=per_output

1000 kg fi_37440 @DK/2030  [model: CementPlant]
  100 kWh fi_17100 @DK/2030  [model: GridElectricity]
    8.46561 kWh electricity-natural-gas @DK/2030  [model: GasPower]
      49.1551 MJ fi_12020 @DK/2030  [model: NaturalGasSupply]
      ...
    84.6561 kWh electricity-wind @DK/2030  [cutoff: no_model_found]
    12.6984 kWh electricity-hydro @DK/2030  [cutoff: no_model_found]
  1125 kg fi_15200 @DK/2030  [cutoff: no_model_found]
  2475 MJ fi_12020 @DK/2030 (http://qudt.org/vocab/quantitykind/Pressure=4 http://qudt.org/vocab/unit/BAR)  [cutoff: coverage_excluded]
  10 kg fi_37420 @DK/2030  [cutoff: no_model_found]
```

The kiln's gas asks for `http://qudt.org/vocab/quantitykind/Pressure` at 4 `http://qudt.org/vocab/unit/BAR` and the only supplier delivers 5, so tier 1
reports it as `coverage_excluded`: a supplier exists, and its coverage is what to look
at. A [`context_tolerance`](resolution.md#tier-2-generalising-a-demand) turns it into a
recorded proxy instead.

**`summary()`** gives, in order: node and inventory counts, unresolved demands broken down
by reason, the proxy count (with incomplete borrows called out), the run's attribution
rules, and then, only when they apply, a truncation line and a warning count. Check these
before trusting the inventory.

**`tree()`** is the traversal as indented text. Each line is
`amount unit product @location/year (context)  [how it was answered]`, with the context
part only when the demand names one:

| Tag | Meaning |
| --- | --- |
| `[model: CementPlant]` | an exact match in tier 1 |
| `[proxy: product: fi_37420 -> fi_374]` | answered by relaxing the demand, naming what was relaxed |
| `[proxy: context: http://qudt.org/vocab/quantitykind/Pressure 4 http://qudt.org/vocab/unit/BAR -> 5 http://qudt.org/vocab/unit/BAR]` | answered after moving a context condition within its tolerance |
| `[background: cumulative]` | borrowed from a background pack, upstream included |
| `[background: unit_process, incomplete]` | borrowed, direct emissions only, upstream missing |
| `[cutoff: no_model_found]` | nothing answered, with the reason |

A cutoff sits under the node that demanded it, because that's where in the chain it
happened. See [Resolution](resolution.md) for the tiers.

The product is the last segment of its IRI. Pass `labels=`, a dict or any callable taking
an IRI, to print names instead. [`PystLabels`](../api/resolution.md) supplies them from a
committed cache, and anything without a name falls back to the segment:

```python
from trailrunner.resolution import PystLabels

print(report.tree(labels=PystLabels("examples/pyst_labels.json").label))
# 1000 kg Portland cement, aluminous cement, slag cement and similar hydraulic cements, ... @DK/2030  [model: CementPlant]
#   100 kWh electricity @DK/2030  [model: GridElectricity]
```

## `inventory`

Biosphere exchanges summed over the whole traversal, keyed by `(Flow, unit)`. The `Flow`
keeps its location and year, so emissions at different places or times stay separate:

```python
for (flow, unit), amount in report.inventory.items():
    print(f"{amount:>12.4g} {unit}  {flow.iri}  {flow.location} {flow.time}")
```

Two entries for the same substance in different units also stay separate. Nothing is
converted.

## `unresolved`

Every demand that never became inventory, as an `UnresolvedRecord` with `demand`,
`reason`, `detail`, `depth` and `parent`:

| `reason` | What happened | What to do |
| --- | --- | --- |
| `no_model_found` | no registered model declares this product | write or register a model, or add a resolution tier |
| `coverage_excluded` | a model declares it, but its `Coverage` rejects this location or year. `detail` names the model | widen the coverage, or check the flow's location and year |
| `generalisation_exhausted` | tier 2 tried relaxing the demand and nothing matched. `detail` counts the candidates | raise `ProxySettings.max_steps`, or model it |
| `max_depth` | the branch reached the depth limit | raise `max_depth` |
| `max_nodes` | the node budget ran out, and the rest of the queue was drained here | raise `max_nodes` |

```python
for record in report.unresolved:
    line = f"{record.reason}: {record.demand.amount:.4g} {record.demand.unit} of {record.demand.flow.iri}"
    if record.detail:
        line += f" ({record.detail})"
    print(line)
```

A demand nobody models is reported, never counted as zero. An inventory with a long
unresolved list is incomplete, and the report says so.

## `provenance`

Per node, whatever that node's model recorded: for a model that passes its parameter row
through, which location and year were used and whether a fallback or interpolation
happened. Only the model's own record goes here. How the model was *chosen* is in
`resolutions`, and the run's normative choices are in `attribution`, since the model
neither made nor saw them.

```python
for node_id, entries in report.provenance.items():
    if entries.get("location_fallback") or entries.get("time_interpolated"):
        print(node_id, entries)
```

## `resolutions` and `proxies`

Every node's resolution: `tier`, `model`, `asked`, `answered`, plus `relaxations` (tier
2) or `dataset`, `source`, `basis`, `complete` (tier 3). `proxies` keeps only the nodes
whose tier isn't `"model"`. [Resolution](resolution.md#what-a-resolution-records) covers
the keys.

## `nodes` and `edges`

The traversal graph as it happened. `nodes` are `NodeRecord`s in visit order, each with
`id`, `demand`, `result`, `depth`, `parent`, `model` (a class name), `resolution` and
`attribution`. `edges` are `(parent, child)` id pairs. Nodes are never merged, so a process
that appears twice in the supply chain appears twice here.

## `warnings` and `truncated`

A flow that repeats on its own supply-chain path gets a warning: the traversal was
**truncated, not converged**. `truncated` is `True` when `max_depth` or `max_nodes` was hit
anywhere, and `summary()` then adds `traversal was truncated: max_depth or max_nodes was
reached`.

The defaults (`max_depth=10`, `max_nodes=1000`) are starting points, not tuned values:
large enough for the shipped chains, small enough that a runaway loop stops quickly. Raise
them freely.

## To pandas

With pandas installed (the `viz` or `dynamic` extra), `report.to_dataframe()` gives one
row per node: `node`, `parent`, `depth`, `model`, `tier`, `demand_iri`, `location`, `time`,
`amount`, `unit`.

## Writing the log to parquet

```python
report.log.to_parquet("run.parquet")
```

or `trailrunner run ... --out run.parquet`. The result is one flat table under one
explicit schema, with one row per record, tagged by `kind`:

| `kind` | One row per |
| --- | --- |
| `biosphere` | biosphere exchange (`flow_*`, `amount`, `unit`) |
| `node` | node that emitted nothing, so it doesn't vanish from the file |
| `unresolved` | cutoff (`reason`, `detail`) |
| `provenance` | key a model recorded (`key`, `value`) |
| `resolution` | key of a node's resolution |
| `attribution` | key of a node's attribution record |

Every row also carries the node context: `model`, `node`, `parent`, `depth` and the
`demand_*` columns. Nested values are flattened one row per leaf (`relaxation.0`,
`co_product.1`), so every column can be filtered on without parsing.

It is one file rather than six because the point is comparing runs: two runs that differ
only in which cutoffs they hit or which fallbacks they took differ on disk too, and one
read shows it.
