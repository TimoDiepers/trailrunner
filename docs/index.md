# Supply chains as computational models talking to each other

**`trailrunner` replaces the static unit-process inventory with computational models that call each other.** A *model* is a computational model (e.g., Python code) for one process: given a demand for one of its products, it works out what other inputs it needs to produce that, and what it emitted — and reads its parameters from a [trailpack](https://github.com/TimoDiepers/trailpack) parquet file rather than hard-coding them. Not every model computes anything, either: it can just as well be a plain measurement, such as metered emissions for this process at this location and time, read straight from the same trailpack parquet file. Every flow that crosses a model's boundary is identified by an IRI from the hierarchical [sentier vocabulary](https://vocab.sentier.dev), so the orchestrator can look at a model's further demands, work out which other models produce those flows, and call them in turn — cascading outward through the whole supply chain until nothing is left open.

## 🧱 The problem

A classic life cycle inventory is a matrix of fixed coefficients: one row of numbers per process, and a separate dataset for every location, year, or technology variant of the same physical activity, because a fixed coefficient can't adapt to context on its own. The catalog grows by duplication instead of by parameterization.

`trailrunner` treats context as an input instead: one physical activity is one model, and the model picks whichever number actually fits the demand it was just given — a parameter read for the matching context, a plain measurement taken for exactly this location and time if one exists, or, when neither is on hand, the best available data found by falling back through the vocabulary's hierarchy: a precise location up to a broader region, a specific process up to a more general one. Nothing is substituted silently; every fallback taken shows up in `report.provenance`.

## ✨ What `trailrunner` does

**You bring** a [`Model`](api/model.md) per process:

- it declares the product IRIs it `produces`, and optionally a [`Coverage`](api/coverage.md) restricting where and when it is valid
- its `apply(demand)` receives the **full** demand amount, never a unit demand, so nonlinear behaviour survives
- it returns a [`Result`](api/result.md): what it produced, which upstream demands it needs, and what it emitted

**`trailrunner` figures out** who produces each demand ([`Glossary`](api/glossary.md)), checks that every model honoured its contract ([`Runner`](api/runner.md)), and walks the open demands outward until nothing is left ([`Orchestrator`](api/orchestrator.md)).

**You get** a [`Report`](api/report.md): an aggregated biosphere inventory, an explicit list of everything that stayed *unresolved*, and the provenance of every parameter fallback taken along the way.

## 🧭 Design commitments

- **A demand nobody models is reported, never silently treated as zero.** Cutoffs are data in the report, not gaps in the number.
- **Nothing is substituted silently.** A location fallback `CH → RER → GLO` or an interpolated year shows up in `report.provenance`.
- **Two models producing the same flow is an error**, not something to resolve by precedence.
- **Loops are truncated, not converged.** Every visit is its own node; `max_depth` and `max_nodes` bound the walk and `report.truncated` says when they bit.

## 👩‍💻 Getting started

- [Installation](content/installation.md)
- [Quick Start](content/getting_started/quickstart.md)
- [Core Concepts](content/concepts.md)
- [Writing a Model](content/writing_a_model.md)
- [API Reference](api/index.md)

## 🚧 Status

Early development. Inventory only — no impact characterization yet, and therefore no single score.
