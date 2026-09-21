# trailrunner

Model-based supply chain traversal for life cycle inventories.

A *model* is Python code for one process. It reads its parameters from a
[trailpack](https://github.com/TimoDiepers/trailpack) parquet file and answers
one question: *given this demand, what did I produce, what do I need, and what
did I emit?* The orchestrator walks the resulting demands outward through the
supply chain and accumulates an inventory.

Design: `docs/superpowers/specs/2026-09-21-trailrunner-design.md`

## Status

Early development. Inventory only — no impact characterization yet.

## Development

```bash
uv sync --extra dev
uv run pytest
```
