---
tags:
  - api
---

# API Reference

Generated from the `trailrunner` source docstrings.

Most users touch four things: a [`Model`](model.md) subclass, a
[`ParameterSet`](parameter_set.md), a [`Glossary`](glossary.md) and an
[`Orchestrator`](orchestrator.md).

## Core

- [`flow`](flow.md) — `Flow`, `Exchange` and the `Demand` alias: identity and quantity.
- [`model`](model.md) — the `Model` base class, Python code for one technology.
- [`result`](result.md) — what a model run returned.
- [`settings`](settings.md) — run-wide knobs shared by every model.
- [`errors`](errors.md) — the errors `trailrunner` raises.

## Orchestration

- [`glossary`](glossary.md) — who produces what.
- [`orchestrator`](orchestrator.md) — the traversal loop.
- [`runner`](runner.md) — calls a model and checks it honoured its contract.
- [`queue`](queue.md) — what to traverse next.
- [`log`](log.md) — append-only record of everything the traversal did.
- [`report`](report.md) — what the caller gets back.

## Parameters

- [`parameter_set`](parameter_set.md) — rows out of a trailpack parquet file, with honest fallback.
- [`location`](location.md) — the `CH → RER → GLO` fallback ladder.
- [`coverage`](coverage.md) — a model's declared validity in space and time.

## Models

- [`models`](models.md) — the direct air capture worked example.
