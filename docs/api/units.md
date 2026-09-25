---
icon: lucide/ruler
tags:
  - api
---

# Units

A unit is a concept IRI from the sentier vocabulary's units scheme (QUDT-derived), not a string a model author invented. `UnitCatalog` reads what the vocabulary says about an IRI: its quantity kind, its multiplier to the SI base, and its UCUM symbol. The facts for every constant this library uses ship in `units.json`, so a run with no network validates and converts exactly what an online one does; a catalog given a client asks the vocabulary about anything else and caches the answer. A unit the catalog cannot confirm raises `UnknownUnit`.

::: trailrunner.core.units
