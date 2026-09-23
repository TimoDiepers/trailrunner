# Supply chains as computational models talking to each other

`trailrunner` computes a life cycle inventory by calling computational models instead of looking up fixed coefficients — each one answering, for its own process, what it needs and what it emits.

## 🧱 The problem

A classic life cycle inventory is a matrix of fixed coefficients: one row of numbers per process, and a separate dataset for every location, year, or technology variant of the same physical activity, because a fixed coefficient can't adapt to context on its own. The catalog grows by duplication instead of by parameterization, and the links between datasets are frozen in at build time — nothing adapts when better data becomes available, or when a demand falls just outside what was modeled.

## 💡 The idea

Treat one physical activity as one *model* instead of one row. A model is a computational model for one process — most often Python code, but it can just as well be a plain measurement, such as metered emissions for this process at this location and time. It's called whenever something demands one of its products, and it answers by working out what other inputs it needs to produce that demand, and what it emitted — reading its parameters from a [trailpack](https://github.com/TimoDiepers/trailpack) parquet file rather than hard-coding them, so the same model adapts as better context-specific data becomes available.

Every flow crossing a model's boundary — its products, the further demands it raises, the emissions it reports — is identified by an IRI from the hierarchical, semantic [sentier vocabulary](https://vocab.sentier.dev), not a free-text name. That's what makes the system compose: the orchestrator reads a model's further demands, looks up by IRI which other model produces each one, and calls it in turn — cascading outward through the whole supply chain until nothing is left open. And because the vocabulary is hierarchical, a demand with no exact match can fall back through it instead of failing outright: a precise location up to a broader region, a specific process up to a more general one, using whatever data is actually available. Nothing is substituted silently — every fallback taken shows up in `report.provenance`.

## ✨ The interface

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
