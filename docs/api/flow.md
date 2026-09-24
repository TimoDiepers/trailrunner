---
icon: lucide/fingerprint
tags:
  - api
---

# Flows

`Flow` is identity - what a thing is, where it is, when it is, and optionally under which conditions (`context`, e.g. `http://qudt.org/vocab/quantitykind/Pressure` = 4 `http://qudt.org/vocab/unit/BAR`). It carries no amount and no unit, which keeps it hashable and usable directly as an aggregation key in the inventory.

`Exchange` adds the quantity. `Demand` is an alias of `Exchange`, not a subclass, so the two cannot drift apart.

::: trailrunner.core.flow
