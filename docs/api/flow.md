---
icon: lucide/fingerprint
tags:
  - api
---

# Flows

`Flow` is identity - what a thing is, where it is, when it is, and optionally under which conditions (`context`, e.g. `pressure=4 bar`). It carries no amount and no unit, which keeps it hashable and usable directly as an aggregation key in the inventory.

`Exchange` adds the quantity. `Demand` is an alias of `Exchange`, not a subclass, so the two cannot drift apart.

::: trailrunner.core.flow
