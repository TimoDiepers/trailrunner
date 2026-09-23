---
icon: lucide/flask-conical
tags:
  - api
---

# Example Models

Worked examples, each in code for a different reason.

## Cement

Kiln fuel is not a fixed coefficient - raw meal arrives from the quarry with water in it, and every kilogram of that has to be boiled off before any limestone calcines. Two classes live here, declaring the same product with `Coverage` ranges that do not overlap: `CementPlant` computes, `MeteredCementPlant` reads a stack monitor, and the year on the demand decides which one answers. This is the model the [5-minute tour](../showcase.md) walks.

::: trailrunner.models.cement

## Direct air capture

Sorbent regeneration heat is not a fixed coefficient - colder, drier air means less CO<sub>2</sub> and less water reaching the sorbent per unit of air moved. That dependency is the reason a model is Python code rather than a row in a table.

::: trailrunner.models.dac

## Electricity

Nothing in the grid is nonlinear; what varies is *composition*. A kilowatt hour is mostly hydro in one place and half fossil in another, and both mixes move over the decade, so the mix is resolved per location and year and split into one demand per source. `GasPower` sits behind the gas share; wind, hydro and the fuel itself are left unmodelled on purpose and surface as cutoff leaves.

::: trailrunner.models.electricity
