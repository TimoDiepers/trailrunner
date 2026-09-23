# Supply chains as models calling models

`trailrunner` computes a life cycle inventory by orchestrating computational models instead of static unit-process datasets.

## 💡 The idea

Treat one physical activity as one *model*. A model is a computational model (e.g., Python code) for one process. Given a demand for one of its products, it works out what other inputs it needs to produce that, and what it emitted, reading its parameters from a [trailpack](https://github.com/TimoDiepers/trailpack) parquet file rather than hard-coding them. Because the demand is an argument, one model covers every place, year and scale it was written for.

A model need not compute anything at all. It can just as well be a plain measurement, such as metered emissions for this process at this location and time, read straight from the same trailpack parquet file.

Every flow that crosses a model's boundary is identified by an IRI from the hierarchical [sentier vocabulary](https://vocab.sentier.dev), so the orchestrator can look at a model's further demands, work out which other models produce those flows, and call them in turn, cascading outward through the whole supply chain until nothing is left open.

That cascade is the loop below. One demand goes in, and a handful of objects pass it around until the queue is empty.

```mermaid
flowchart TB
    D([initial demand]) --> Q[[Queue]]
    Q -->|pop demand| C{{ResolutionChain}}
    C -->|ask model tier: who can offer?| G[(Glossary: available models)]
    G -->|Offer: model + demand| C
    C -->|nobody offers| X[cutoff, with a reason]
    C -->|selected offer| R[Runner]
    R -->|apply demand| M[Model: your code]
    M -->|Result| R
    R -->|Result - technosphere demands| Q
    R -->|Result - biosphere flows| I[(inventory)]
    X --> L[(Log)]
    R --> L
    L --> P([Report])
```

| Part | Its one job |
| --- | --- |
| [`Demand`](api/flow.md) | an amount and a unit of a `Flow`, which carries what, where and when |
| [`Queue`](api/queue.md) | the demands still waiting. FIFO unless you hand it a priority |
| [`ResolutionChain`](api/resolution.md) | who can answer this demand? It asks each tier in order. Tier 1 is the [`Glossary`](api/glossary.md), which offers a `(model, demand)` pair to run. A demand no tier offers for is logged as a cutoff |
| [`Model`](api/model.md) | one process, as code. `apply(demand) -> Result` |
| [`Runner`](api/runner.md) | applies the model and validates the [`Result`](api/result.md) against the demand |
| [`Log`](api/log.md) | append-only. Every node, edge, cutoff, fallback and rule, written out to one parquet file |

**You bring** a [`Model`](api/model.md) per process:

- it declares the product IRIs it `produces`, and optionally a [`Coverage`](api/coverage.md) restricting where and when it is valid
- its `apply(demand)` receives the full demanded amount, the whole thing that was asked for, so nonlinear behaviour survives
- it returns a [`Result`](api/result.md) holding what it produced, which upstream demands it needs, and what it emitted

**You get** a [`Report`](api/report.md) holding an aggregated biosphere inventory, an explicit list of everything that stayed *unresolved*, which tier answered each node, and the provenance of every parameter fallback taken along the way.

An IRI in place of a free-text name is what lets two people's models meet at all, and it keeps paying after the match. The same concept carries its own `skos:prefLabel`, the name [`Report.tree()`](api/report.md) prints when given one, and its `skos:broader` parent, the ladder the [generalising tier](content/resolution.md) climbs when nobody produces the exact concept asked for.

The seams are deliberate. The traversal never learns how a process works, and a process never learns what else is in the supply chain. A model *returns* demands, so it cannot reach into the graph, and it has no way of knowing whether anyone will answer. And because a [`Flow`](api/flow.md) carries its year the way it carries its location, the inventory comes out dated without any step of the walk knowing about time.

[The 5-minute tour](showcase.md) carries one demand through all of that, with the real output at every step.

## 🧭 Design commitments

- **A demand nobody models is reported.** Cutoffs are data in the report, each with a reason and a place in the chain, so a reader can see what the number leaves out.
- **Every substitution is recorded.** A location fallback `CH → RER → GLO`, an interpolated year or a generalised product shows up in `report.provenance` or `report.proxies`.
- **Two models producing the same flow raises.** Precedence between them is a data question for the practitioner to settle.
- **Loops are bounded.** Every visit is its own node; `max_depth` and `max_nodes` bound the walk, and `report.truncated` says when they bit.
- **Value judgements are the practitioner's.** A co-producing model runs once the study states an allocation rule, and the rule it ran under is on the report.

## 👩‍💻 Getting started

- [Installation](content/installation.md)
- [The 5-minute tour](showcase.md)
- [Quick Start](content/getting_started/quickstart.md)
- [Core Concepts](content/concepts.md)
- [Writing a Model](content/writing_a_model.md)
- [API Reference](api/index.md)

## 🚧 Status

Early development. The traversal produces an inventory. [`trailrunner.assessment`](content/assessment.md) is a separate reading of it that turns the inventory into a static score or a time-explicit curve.
