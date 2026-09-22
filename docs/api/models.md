---
icon: lucide/flask-conical
tags:
  - api
---

# Example Models

Two worked examples, each in code for a different reason.

## Direct air capture

Sorbent regeneration heat is not a fixed coefficient - colder, drier air means less CO<sub>2</sub> and less water reaching the sorbent per unit of air moved. That dependency is the reason a model is Python code rather than a row in a table.

::: trailrunner.models.dac

## Electricity

Nothing in the grid is nonlinear; what varies is *composition*. A kilowatt hour is mostly hydro in one place and half fossil in another, and both mixes move over the decade, so the mix is resolved per location and year and split into one demand per source. `GasPower` sits behind the gas share; wind, hydro and the fuel itself are left unmodelled on purpose and surface as cutoff leaves.

::: trailrunner.models.electricity
