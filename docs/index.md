# Supply chains as code with `trailrunner`

**`trailrunner` lets a process be Python code instead of a fixed row of coefficients.** A *model* reads its parameters from a [trailpack](https://github.com/TimoDiepers/trailpack) parquet file and answers one question: *given this demand, what did I produce, what do I need, and what did I emit?* The orchestrator walks the resulting demands outward through the supply chain and accumulates an inventory.

## 🧱 The problem

A classic life cycle inventory is a matrix of fixed coefficients. Every process is linear and scale-free: ten times the demand is exactly ten times the inputs, and the numbers never depend on where or when the process runs.

Real processes do not behave like that. A direct air capture plant needs more regeneration heat in cold, dry air, because less CO<sub>2</sub> and less water reach the sorbent per unit of air moved. That dependency cannot live in a coefficient — it has to live in code.

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
