# Typed units and time — design

Date: 2026-09-24 · Branch: `feat/typed-unit-time` · Base: `main` @ `fdeafd5b`
(after #42, context matching)

## Why

A demand's quantity and its "when" are the two parts of a flow that are still
untyped. `unit` is a free string (`"kg"`, `"Nm3"`, `"bar"`), so two models that
mean the same unit can fail to compose, and nothing knows that 1 t is 1000 kg.
`time` is an `int` year, so a demand for a specific day or instant cannot be
stated at all.

Since #42 a flow is identified by more than time and place: `Flow.context`
carries named conditions (`pressure=4 bar`) that `Coverage` declares ranges
for and tier 2 relaxes. Those conditions carry units too. This spec therefore
types units **everywhere a unit appears** — exchanges, properties, context
conditions, context ranges, context tolerances — not only on the exchange.

## Decisions taken

| Question | Decision |
|---|---|
| Scope | Core types, not just the CLI |
| Unit representation | IRI from `https://vocab.sentier.dev/units/` (QUDT-derived) |
| Units missing from the vocab | **Strict**: only IRIs the vocab has. Models remodelled where needed |
| `tkm` | Remodel the pipeline transport model as t + km |
| Unit fallback | Exact conversion within one QUDT quantity kind, logged, not a relaxation |
| Time representation | `time: str` plus a separate `time_standard` IRI |
| Time standards | XSD datatype IRIs; registry so more can be added |

## 1. Units

### Representation

Every `unit` field holds a unit IRI:

- `Exchange.unit`
- `Property.unit` (allocation properties *and* context conditions)
- `ContextRange.unit`
- `ProxySettings.context_tolerance` gains a unit (see below)

`trailrunner/core/units.py` holds constants for the units the library and
its models use (`KG`, `TONNE`, `MJ`, `KWH`, `M3`, `PA`, `NUM`, `UNITLESS`, …),
so model code writes `unit=KG`, never a string literal.

Vocab facts checked on 2026-09-24: `KiloGM`, `TONNE`, `MegaJ`, `J`,
`KiloW-HR`, `M3`, `PA`, `DEG_C`, `K`, `PERCENT`, `NUM`, `UNITLESS` exist.
**Not** in the vocab: tonne-kilometre, standard cubic metre, EUR, kg CO2-eq,
and — notably — plain `BAR`, `KiloPA`, `MegaPA`, `HectoPA`, `ATM` (only `PA`,
and bar inside compound units).

### Unit catalog

`UnitCatalog` in `trailrunner/resolution/pyst.py`, beside `PystTaxonomy` and
built on the same `PystHttpClient`. From `GET /api/v1/concepts/<iri>` it
reads:

- `qudt:hasQuantityKind` — what may be converted into what
- `qudt:conversionMultiplier` — the factor to the SI base
- `skos:notation` of type `qudt:ucumCode` — the short display symbol (`MJ`, `kg`, `Pa`)

Cached to a committed JSON file exactly like `pyst_cache.json`: runs are
offline and reproducible. An IRI the service answers 404 for is recorded as
unknown.

Validation happens when an exchange enters the Runner (demand in, model
result out), not in the frozen dataclass constructors: building a `Flow` must
not touch the network. An unknown unit raises a `TrailrunnerError` naming the
model and the exchange.

Temperature units are never converted; they only compare equal to
themselves. The vocab gives `DEG_C` and `K` the same quantity kind and
multiplier 1 with **no** `conversionOffset`, so a multiplier-only conversion
would read 10 °C as 10 K.

### Fallback: exact conversion

`Coverage` gains `units: frozenset[str] | None` — the units a model answers
in. `None` keeps today's behaviour (any unit, passed through).

When a declaring model does not list the demanded unit but lists one of the
same quantity kind, the resolver converts the demand into that unit, lets the
model answer, and records the conversion on the node:
`unit: t -> kg ×1000`. It is **not** a proxy relaxation — conversion loses
nothing — so it has no budget, no place in `ProxySettings.order`, and does
not change the node's tier. It is shown in the tree, the report and the log
the way relaxations are. Different quantity kinds (m³ vs kg) are a plain miss.

The three hand-written guards (`if demand.unit != MJ: raise`) in
`electricity.py` and `natural_gas.py` become `coverage.units` declarations.

### Context conditions

`Coverage.covers` compares a context condition to a `ContextRange` after
converting the asked value into the range's unit when both share a quantity
kind. This replaces the "compared as written, never converted" rule from #42:
that rule existed because converting a string unit meant guessing; with the
catalog it does not.

`context_tolerance` becomes `dict[str, tuple[float, float, str]]` —
`(below, above, unit)` — because "1 above" means nothing without a unit once
conditions can be asked in any unit of their kind. `_context_candidates`
works in the tolerance's unit and writes the snapped value back in the
**asked** unit.

Because the vocab has no `BAR`, the showcase pressure becomes Pa:
`Property("pressure", 4e5, PA)`, tolerance `(0.0, 1e5, PA)`. Display goes
through the UCUM symbol (`pressure=4e+05 Pa`). Pressure is specified in Pa
throughout — decided, not a stopgap.

### Remodelling forced by the strict rule

- `Nm3` → `M3`. "Normal conditions" is a property of the gas's reference
  state, documented on the model and its parameters, not part of the unit.
- `kg CO2eq` (dynamic metric units in `assessment/dynamic.py`, method score
  units) → `KiloGM`. The "CO2-eq" belongs to the indicator's name.
- `tkm`: `NaturalGasOffshorePipelineTransport` answers `TONNE` of gas
  transported, and the distance travels with the demand as a context
  condition, `Property("distance", km, KILOMETRE)` — the route length is the
  demander's to state (the supply model knows it per consumer location), and
  #42 made context exactly the place for such a condition. The model
  multiplies tonnes by distance and applies its per-tkm parameters unchanged;
  a demand without a distance is refused with a message naming the missing
  condition. 1 t over 1 km reproduces today's 1 tkm figures exactly, so the
  BAFU reproduction numbers do not move.
- The lorry leg (`FREIGHT_LORRY`): demanded in `TONNE` with the same
  `distance` context, amount `lorry_factor × tonnes` (lorry tkm per pipeline
  tkm, so the same distance carries it).
- The background pack's two tkm datasets (`transport-freight-rail`,
  `transport-natural-gas-pipeline-long-distance`) are dropped: nothing in the
  library, examples or tests demands them, and a per-tkm dataset has no
  per-tonne reading without a distance.
- `"unit"` (pipeline infrastructure) → `NUM`.
- `EUR` does not occur in library or model code. Allocation properties
  (`Exchange.properties`) keep free-text units: the vocab has no currencies,
  and allocation only ever compares a property's unit with the same
  property's unit on the other co-products. Strict checking covers
  `Exchange.unit` and context-condition units.

### Files with units

- Parameter parquets: a column whose unit ends up on an exchange (anything
  read through `unit_of`) declares a vocab unit IRI. Ratio columns
  (`MJ/tkm`, `kg/Nm3`, …) are documentation for a human and may keep free
  text: the vocab has no such compound units, and strictness is enforced
  where a unit becomes part of an exchange — at the Runner — not on every
  metadata string.
- Method parquets: `flow_unit` column and the `cf` unit metadata become IRIs.
  `Method.factor` converts within a quantity kind when the exact unit has no
  row.
- The background pack's units are migrated.
- `dev/` scripts that build these files are updated so they regenerate them.

## 2. Time

### Representation

```python
@dataclass(frozen=True)
class Flow:
    iri: str
    location: str | None = None
    time: str | None = None
    time_standard: str | None = None
    context: tuple[Property, ...] = ()
```

Both `time` and `time_standard` are set, or both are `None`. `__post_init__`
checks the standard is registered and the value parses under it. There is no
network involved.

`trailrunner/core/time.py`:

- constants `GYEAR`, `GYEAR_MONTH`, `DATE`, `DATETIME`
  (`http://www.w3.org/2001/XMLSchema#gYear`, …)
- `year(2030)` → `{"time": "2030", "time_standard": GYEAR}`, so model code
  reads `Flow(iri=..., **year(y))`
- `interval(time, standard) -> (start, end)`: half-open, timezone-aware UTC
  `datetime`s
- `register_time_standard(iri, parser)` for further standards (fiscal year,
  ISO week, …)

Shipped parsers:

| Standard | Example | Interval |
|---|---|---|
| `xsd:gYear` | `2030` | [2030-01-01, 2031-01-01) |
| `xsd:gYearMonth` | `2030-06` | one month |
| `xsd:date` | `2030-06-15` | one day |
| `xsd:dateTime` | `2030-06-15T08:00:00Z` | an instant (zero width); timezone required |

Every comparison in the core goes through `interval`, never through the raw
string.

### Matching is containment

A coarser declaration covers a finer demand: a model valid for `2030` answers
`2030-06-15T08:00Z` directly, at tier 1. The day lies inside the year, so
nothing is conceded.

`Coverage.time_range` becomes a `TimeRange(start, end, standard)`; it covers a
flow whose interval lies inside `[interval(start).start, interval(end).end)`.

### Relaxation

`_time_candidates` keeps its logic — snap to the nearest period a declaring
model covers, within tolerance — with distance measured as the gap between
intervals. `ProxySettings.time_tolerance` stays a number of years (float),
converted to a duration. The snapped value is written in the covering model's
standard: `time: 2031-03-02 -> 2030`.

### Parameters and methods

- The parquet `time` column is a string. Its standard is declared in the
  field metadata, as `unit` is for value columns. A file without it is
  refused with a message saying what to add.
- `ParameterSet.at(time=, time_standard=)`: a row whose interval contains the
  demand's is used as is (`time_interpolated: False`). Otherwise the
  bracketing rows are interpolated by interval midpoint. For year rows and a
  year demand the fraction is identical to today's, so existing numbers do not
  move.
- Method files: the time key works the same way (containment, then `None`).

### Downstream

- Dynamic LCIA: an exchange is placed at its interval start — exactly
  `datetime(year, 1, 1)` today.
- Fleet (`params/fleet.py`): build years stay integers inside the fleet and
  leave it as gYear flows. Age arithmetic uses the demand interval's start
  year.
- `chain.py` / report: time printed as the string, `@DK/2030`.
- Log schema: `demand_time`/`flow_time` become strings, and gain
  `*_time_standard`, `*_time_start`, `*_time_end` (timestamp) columns so the
  parquet can be filtered by date. Context, which the log does not carry
  today, is added as a string column (`describe_context()`), so a node's full
  identity is in the record.

## 3. CLI

- `--unit` accepts a unit IRI, a vocab id (`KiloGM`) or a UCUM symbol
  (`kg`), resolved through the catalog; an unknown one exits 2 with the
  closest matches.
- `--year` is replaced by `--time 2030-06-15` and optional
  `--time-standard IRI`. Without the standard it is inferred from the
  lexical form (`YYYY` → gYear, `YYYY-MM` → gYearMonth, `YYYY-MM-DD` → date,
  anything with `T` → dateTime) and printed in the summary line, so the
  choice is never silent.
- New repeatable `--context NAME=VALUE UNIT` (e.g. `pressure=4e5 Pa`), because
  context is now part of what a demand is.

## 4. Showcase and pitches

`docs/showcase.md`, `examples/showcase.ipynb`, `docs/pitch.md`,
`docs/pitch-5min.md`:

- The cement demand is stated in **t** while the clinker/cement model
  declares `units={KG}`. The node reads `unit: t -> kg ×1000`, next to the
  existing `context: pressure …` and `product: …` relaxations, as a fallback
  that concedes nothing.
- The demand's time is a date (`2030-06-15`), answered by year-declared
  models through containment; the existing time relaxation line stays.
- Pressure is shown in Pa.
- The regenerated SVGs in `docs/assets/showcase/` are rebuilt.

## 5. Testing

- Unit catalog: cached lookups, 404 → unknown, offline stub client (same
  pattern as the taxonomy tests).
- Conversion: t → kg demand answered and logged; m³ → kg is a miss; `DEG_C`
  never converted.
- Context: 4e5 Pa asked vs a 5e5 Pa range; tolerance (0, 1e5, PA) snaps it.
- Time: each shipped standard's interval; containment (day in year);
  relaxation snaps by interval gap; interpolation gives today's numbers for
  year data; `dateTime` without timezone refused.
- Parameter/method files without time-standard or with non-IRI units refused.
- Every model test (cement, DAC, electricity, gas, pipeline BAFU
  reproduction) passes with unchanged numbers.
- CLI: unit resolution from `kg`/`KiloGM`/IRI, time inference, `--context`.
- The `writing_a_model.md` contract example still runs.

## Out of scope

- Proxy steps across quantity kinds (m³ → kg via density, kg → MJ via
  heating value).
- Location typing (stays an opaque key through `LocationHierarchy`).
- Non-numeric context conditions.

## Open points

1. **Breaking change.** Every model, parameter parquet and method file
   changes. No compatibility shim is planned; `docs/content/writing_a_model.md`
   and the API pages document the new contract.
