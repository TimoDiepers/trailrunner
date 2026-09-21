# trailrunner — Design

Date: 2026-09-21
Status: approved design, ready for implementation planning

## Purpose

`trailrunner` computes a life-cycle inventory by traversing a supply chain of
*models* rather than a fixed matrix. A model is Python code for one technology.
It consumes parameters published as a trailpack parquet file (PyST-linked
metadata), and returns what it produced, what it needs, and what it emitted.
An orchestrator walks the resulting demands outward through the supply chain
and accumulates the inventory.

Scope boundary: `trailpack` authors and validates the parameter data.
`trailrunner` consumes it, models with it, and orchestrates the traversal.

## Non-goals (v1)

- No impact assessment. The output is an aggregated elementary-flow inventory,
  not a characterized score.
- No Brightway/ecoinvent background. A demand with no model is a cutoff leaf.
- No concurrency. The Runner is synchronous.
- No cycle solving. Loops are truncated by depth/node guards and reported.
- No frontend. The public entry point is a Python API.

## Architecture

```
Caller ──> Orchestrator ──> Glossary   (product IRI -> Model)
                │
                ├────────> Runner      (resolve, validate, model.apply)
                │              │
                │              └──────> Model (per technology)
                │                          └──> ParameterSet (trailpack parquet)
                ├────────> Queue       (pluggable priority, FIFO default)
                └────────> Log         (append-only nodes/edges)
                               │
                               └──────> Report
```

Each component is independently testable: Glossary needs only a registry,
Runner needs only a Glossary and a Model, Queue needs nothing, Log needs only
Results.

## Core types

```python
@dataclass(frozen=True)
class Flow:
    """Identity of a thing: what, where, when. Hashable; used as an
    aggregation key. Carries no amount and no unit."""
    iri: str                    # PyST concept IRI
    location: str | None = None
    time: int | None = None     # year


@dataclass(frozen=True)
class Exchange:
    """A quantified flow."""
    flow: Flow
    amount: float
    unit: str


Demand = Exchange   # alias: a technosphere Exchange that someone must satisfy


@dataclass
class Result:
    production: list[Exchange]          # must cover the demand
    technosphere: list[Demand]          # pushed onto the Queue
    biosphere: list[Exchange]           # accumulated into the inventory
    provenance: dict                    # param rows and fallbacks actually used
```

Rationale:

- **Unit lives on `Exchange`, not `Flow`**, so `Flow` stays a pure hashable
  identity usable as a dict key. Unit compatibility is checked by the Runner at
  the component boundary.
- **`Demand` is an alias, not a parallel class**, so the two cannot drift apart.

## Model

```python
class Model:
    produces: list[str]                  # product IRIs this model can make
    coverage: Coverage | None = None     # optional location/time validity
    params: ParameterSet | None = None
    settings: Settings

    def apply(self, demand: Demand) -> Result:
        ...
```

`apply` receives the **full demand amount**, not a unit demand. This preserves
nonlinearity: a DAC plant at 10 kt/yr is not ten times one at 1 kt/yr. The cost
is that results cannot be cached and reused across demands for the same node.
Models that are genuinely linear may opt into caching later by declaring
themselves linear; v1 does not implement that.

`coverage` lives on the Model — a model knows its own validity range. The
Glossary only indexes it.

Shipped example: `DirectAirCapture`, whose heat and electricity demands depend
on ambient temperature and relative humidity drawn from its ParameterSet.

### Settings and Coverage

```python
@dataclass(frozen=True)
class Settings:
    """Run-wide knobs, passed down from the Orchestrator to every model.
    Models may read keys they care about and must ignore the rest."""
    values: dict[str, Any]


@dataclass(frozen=True)
class Coverage:
    locations: set[str] | None = None        # None = any location
    time_range: tuple[int, int] | None = None  # inclusive; None = any time

    def covers(self, flow: Flow) -> bool: ...
```

`Settings` is a single flat namespace for the whole run (scenario name, default
year, model-specific switches). It is deliberately not per-model configuration:
anything that varies per technology belongs in that technology's ParameterSet.

## ParameterSet

```python
params = ParameterSet.from_parquet("dac_params.parquet")
row = params.at(location="CH", time=2030)
```

- Reads the parquet with pyarrow and the embedded `datapackage.json` metadata
  that trailpack writes, giving each column a PyST concept IRI and a unit.
- Resolution order for `.at()`:
  1. exact `(location, time)` match;
  2. location fallback by walking a declared location hierarchy
     (e.g. `CH -> RER -> GLO`);
  3. time interpolation between the nearest bracketing rows, when time is
     numeric.
- **Every fallback and interpolation is recorded** into the `Result.provenance`
  of the model that used it, so the report states which parameters were
  actually used. No silent substitution.
- Exhausting all three steps raises `ParameterNotFound`.

## Glossary

Indexes registered model classes by `produces`, filtered by `coverage`.

```python
glossary.resolve(flow) -> Model | None
```

- 0 hits → `None`; the Orchestrator records the demand as an unresolved cutoff
  leaf.
- 1 hit → that model.
- 2+ hits → `AmbiguousProducer`, naming the candidates. Ambiguity is a data
  error, not something to resolve by silent precedence.

## Runner

Synchronous. The single place where validation happens.

```python
class Runner:
    def apply(self, demand: Demand) -> Result:
        model = self.glossary.resolve(demand.flow)
        result = model.apply(demand)
        self.validate(demand, result)
        return result
```

`validate` checks that production covers the demand (matching IRI, compatible
unit, positive amount) and that every exchange carries a known unit.

The Runner is a separate object precisely so a concurrent implementation can
replace it behind the same interface without touching the Orchestrator.

## Queue

A `Queue` that takes an optional priority callable.

- Default: FIFO, i.e. breadth-first traversal.
- With a callable: `heapq`-backed priority ordering.

No priority function ships in v1, because with no impact score there is nothing
meaningful to rank by — amounts in MJ, kg and kWh are not comparable. The seam
exists so score-based ranking drops in unchanged once characterization is
added.

## Orchestrator

```python
queue.push(root_demand, depth=0)
while queue and nodes < max_nodes:
    demand, depth = queue.pop()
    if depth >= max_depth:
        log.unresolved(demand, reason="max_depth")
        continue
    model = glossary.resolve(demand.flow)
    if model is None:
        log.unresolved(demand, reason="no_producer")
        continue
    result = runner.apply(demand)
    log.write(node, parent_edge, demand, result)
    nodes += 1
    for d in result.technosphere:
        queue.push(d, depth + 1)
```

**Cycles.** Every visit is its own node; nodes are never merged. A loop such as
electricity → steel → electricity is therefore bounded by `max_depth` and
`max_nodes`, and a repeated flow on the same path is flagged as a warning in the
Log. v1 deliberately produces a truncated tree with an honest unresolved list
rather than a converged number that would be wrong.

## Log and Report

The Log is append-only in memory: one record per node (demand, result,
provenance, depth) and one per edge (parent node → child demand). The graph
structure is read back out of it to build the report.

```python
report.inventory     # biosphere aggregated by (iri, location, time), per unit
report.unresolved    # dangling demands with reason (no_producer, max_depth)
report.provenance    # per node: parameter rows and fallbacks used
report.graph         # nodes and edges, for later tree/Sankey rendering
```

`log.to_parquet()` writes the same records to disk — symmetry with trailpack,
and it makes results diffable between runs.

## Error handling

| Situation | Behavior |
|---|---|
| No model produces a flow | Unresolved leaf, reason `no_producer`. Traversal continues. |
| Several models produce a flow | `AmbiguousProducer` raised, candidates named. |
| Production does not cover the demand | `ValidationError` from the Runner, node identified. |
| Unit mismatch on any exchange | `ValidationError` from the Runner. |
| No parameter row resolvable | `ParameterNotFound` from ParameterSet. |
| Depth or node budget exhausted | Unresolved leaf, reason `max_depth` / `max_nodes`. Report says the traversal was truncated. |

Unresolvable *data* produces a recorded leaf; unresolvable *contracts* raise.

## Testing

Test-driven throughout, pytest.

- Core types: construction, hashability of `Flow`, aggregation by `Flow` key.
- ParameterSet: exact hit, location fallback, time interpolation, provenance
  contents, `ParameterNotFound`. Fixtures are small hand-written parquet files
  with trailpack-style embedded metadata.
- Glossary: zero, one, and ambiguous producers; coverage filtering.
- Runner: valid result passes; uncovered demand, unit mismatch, and negative
  production each raise.
- Queue: FIFO order by default; priority callable respected.
- Orchestrator: single-node traversal; two-level traversal; cutoff leaf
  recorded; cycle truncated at `max_depth`; `max_nodes` honored.
- End-to-end: the DAC example model at two locations, asserting the inventory,
  the unresolved list, and the provenance of the parameter fallback.

## Project layout

```
trailrunner/
├── pyproject.toml            # uv, Python >= 3.11, deps: pyarrow, trailpack
├── README.md
├── trailrunner/
│   ├── core/                 # flow.py model.py result.py settings.py
│   ├── params/               # parameter_set.py coverage.py
│   ├── orchestration/        # glossary.py runner.py queue.py
│   │                         # orchestrator.py log.py report.py
│   └── models/               # dac.py
├── tests/
└── docs/superpowers/specs/
```

Clean minimal uv project. Sphinx docs, CI workflows and packaging recipes are
deliberately deferred until the design stops moving.

## Deferred

- Impact characterization, and with it a real Queue priority function.
- A background provider (Brightway or other) behind the Glossary, turning
  `resolve` into an ordered provider chain.
- Concurrent Runner.
- Linear-model result caching.
- Cycle convergence.
