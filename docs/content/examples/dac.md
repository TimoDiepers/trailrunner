---
icon: lucide/wind
tags:
  - example
  - notebook
  - parameters
---

<!-- Generated from examples/dac.ipynb by docs/convert_notebooks.py.
     Edit the notebook, then re-run the script; edits here are lost. -->

<div hidden data-source-edit-url="https://github.com/TimoDiepers/trailrunner/edit/main/examples/dac.ipynb" data-source-view-url="https://github.com/TimoDiepers/trailrunner/blob/main/examples/dac.ipynb"></div>

# Direct air capture, end to end

trailrunner computes a life cycle inventory by traversing a supply chain of
Python *models* — one per technology — instead of solving a fixed matrix. A
model reads its parameters from a [trailpack](https://github.com/TimoDiepers/trailpack)
parquet file and answers one question: *given this demand, what did I produce,
what do I need, and what did I emit?*

`DirectAirCapture` is the worked example, and it exists because of one number:
the heat needed to regenerate the sorbent is not a constant. Colder, drier air
carries less CO2 and less water to the sorbent per unit of air moved, so heat
and fan work per kilogram captured go up. A coefficient in a table cannot say
that; a function can.

This notebook writes its parameter files with trailpack, reads them back
through trailrunner, runs the model on a single demand, and then lets the
orchestrator walk outward from it.

## 1. Parameters live in a trailpack parquet file

Model code holds the *behaviour*; the *numbers* come from a parquet file with a
Frictionless `datapackage.json` embedded in its schema metadata. That descriptor
is what makes the columns self-describing: a unit at
`resources[].schema.fields[].unit.name`, itself a concept IRI from the
[sentier units vocabulary](https://vocab.sentier.dev/units/), a
[PyST](https://vocab.sentier.dev) concept IRI at
`resources[].schema.fields[].rdfType`, and on the time column a
`timeStandard` saying how its values are to be read.

[trailpack](https://github.com/TimoDiepers/trailpack) is what writes those
files, so this notebook uses it rather than assembling the descriptor by hand —
that is the whole point of the format being a standard. `Field` and `Unit`
describe one column, `MetaDataBuilder` collects the package-level metadata the
standard requires, `StandardValidator` says whether the result is compliant,
and `Packing.write_parquet` puts data and metadata into a single file.

Install it alongside trailrunner with `uv sync --extra examples`.

```python
import tempfile
from pathlib import Path

import pandas as pd
from trailpack.packing import (
    Field,
    MetaDataBuilder,
    Packing,
    Resource,
    Unit,
    read_parquet,
)
from trailpack.validation import StandardValidator
from trailrunner.core.time import GYEAR
from trailrunner.core.units import (
    DEG_C, KG, KWH, MJ, TONNE_PER_YEAR, UNITLESS, YEAR, symbol,
)

workdir = Path(tempfile.mkdtemp())
REPOSITORY = "https://github.com/TimoDiepers/trailrunner"
VALIDATOR = StandardValidator()

# Every table here is indexed the same way, so these two columns are described
# once and reused.
LOCATION_FIELD = Field(
    name="location", type="string", description="Region the row applies to"
)
# A time is a string in a declared standard. These rows are calendar years,
# so the column says xsd:gYear.
TIME_FIELD = Field(
    name="time",
    type="string",
    description="Year the row applies to",
)


def write_parameters(name, title, description, rows, fields):
    """Describe these columns with trailpack, validate, and write the parquet."""
    path = workdir / f"{name}.parquet"
    frame = pd.DataFrame(rows)
    metadata = (
        MetaDataBuilder()
        .set_basic_info(name=name, title=title, description=description, version="1.0.0")
        .set_keywords(["life cycle assessment", "inventory parameters", "trailrunner"])
        .set_links(homepage=REPOSITORY, repository=REPOSITORY)
        .add_license("MIT")
        .add_contributor("Timo Diepers", role="author")
        .add_source(title="trailrunner example notebook", path=REPOSITORY)
        .add_resource(
            Resource(
                name=name,
                path=path.name,
                format="parquet",
                title=title,
                description=description,
                fields=fields,
            )
        )
        .build()
    )
    # trailpack's Field has no slot for a time standard, so it is added to the
    # descriptor here: the key trailrunner reads is "timeStandard".
    for field in metadata["resources"][0]["schema"]["fields"]:
        if field["name"] == "time":
            field["timeStandard"] = GYEAR

    report = VALIDATOR.validate_all(metadata, frame)
    if not report.is_valid:
        raise ValueError(f"{name} is not compliant:{report}")
    print(f"{path.name}: {report.level}")

    Packing(frame, metadata).write_parquet(str(path))
    return path
```

```python
DAC_ROWS = [
    {"location": "CH", "time": "2020", "heat_demand": 6.0, "electricity_demand": 0.50,
     "temperature": 9.0, "humidity": 0.75},
    {"location": "CH", "time": "2030", "heat_demand": 5.0, "electricity_demand": 0.40,
     "temperature": 10.0, "humidity": 0.70},
    {"location": "RER", "time": "2020", "heat_demand": 6.6, "electricity_demand": 0.55,
     "temperature": 11.0, "humidity": 0.68},
    {"location": "RER", "time": "2030", "heat_demand": 5.5, "electricity_demand": 0.45,
     "temperature": 12.0, "humidity": 0.65},
]

DAC_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    Field(
        name="heat_demand",
        type="number",
        unit=Unit(name=MJ, long_name="megajoule"),
        description="Sorbent regeneration heat per kilogram captured, at reference air",
        rdf_type="https://vocab.sentier.dev/parameters/heat-demand",
    ),
    Field(
        name="electricity_demand",
        type="number",
        unit=Unit(name=KWH, long_name="kilowatt hour"),
        description="Fan and compressor work per kilogram captured, at reference air",
        rdf_type="https://vocab.sentier.dev/parameters/electricity-demand",
    ),
    Field(
        name="temperature",
        type="number",
        unit=Unit(name=DEG_C, long_name="degree Celsius"),
        description="Mean ambient air temperature",
        rdf_type="https://vocab.sentier.dev/parameters/air-temperature",
    ),
    Field(
        name="humidity",
        type="number",
        unit=Unit(name=UNITLESS),
        description="Mean ambient relative humidity, 0 to 1",
        rdf_type="https://vocab.sentier.dev/parameters/relative-humidity",
    ),
]

parameter_file = write_parameters(
    "dac-parameters",
    "Direct air capture parameters",
    "Heat, electricity and reference air conditions per location and year.",
    DAC_ROWS,
    DAC_FIELDS,
)
print(parameter_file)
```

    dac-parameters.parquet: ✅ STRICT COMPLIANCE
    /var/folders/l1/k90rhb0j0ns58y35ymznsd700000gn/T/tmpa_ffspwr/dac-parameters.parquet

The file that comes out carries its own description, and `read_parquet` hands
back both halves of it. This is exactly what `ParameterSet` will see in the next
section: one descriptor per column, with a unit and a concept IRI attached to
the ones that have them. The unit column below prints each unit IRI by its
symbol, and the time column its standard.

```python
frame, descriptor = read_parquet(str(parameter_file))
print(descriptor["name"], descriptor["version"], descriptor["licenses"][0]["name"])
for field in descriptor["resources"][0]["schema"]["fields"]:
    unit = (field.get("unit") or {}).get("name")
    unit = symbol(unit) if unit else field.get("timeStandard", "-").rsplit("#", 1)[-1]
    print(f"  {field['name']:20} {field['type']:8} {unit:14} {field.get('rdfType', '')}")
```

    dac-parameters 1.0.0 MIT
      location             string   -              
      time                 string   gYear          
      heat_demand          number   MJ             https://vocab.sentier.dev/parameters/heat-demand
      electricity_demand   number   kWh            https://vocab.sentier.dev/parameters/electricity-demand
      temperature          number   °C             https://vocab.sentier.dev/parameters/air-temperature
      humidity             number   UNITLESS       https://vocab.sentier.dev/parameters/relative-humidity

## 2. Reading parameters, with fallback that says so

`ParameterSet.from_parquet` reads the rows and that descriptor together, so a
column's unit and IRI travel with its value. A lookup goes through
`params.at(location=..., time=..., time_standard=...)` (`**in_year(2030)` spells
the common case) and widens until something matches: the exact row first, then
up the `LocationHierarchy`, then linear interpolation between the midpoints of
two bracketing rows. Nothing is extrapolated past the data, and every widening
step is written into the row's `provenance`.

```python
from trailrunner import LocationHierarchy, ParameterSet
from trailrunner.core.time import in_year

hierarchy = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})
params = ParameterSet.from_parquet(parameter_file, hierarchy=hierarchy)

row = params.at(location="CH", **in_year(2030))
print(row["heat_demand"], row.unit_of("heat_demand"), row.iri_of("heat_demand"))
print(row.provenance)
```

    5.0 https://vocab.sentier.dev/units/unit/MegaJ https://vocab.sentier.dev/parameters/heat-demand
    {'location_requested': 'CH', 'location_used': 'CH', 'location_fallback': False, 'time_requested': '2030', 'time_used': '2030', 'time_interpolated': False}

France has no row of its own, and 2025 is not a year anybody wrote down. The
lookup still answers — France falls back to `RER`, and the two European rows are
interpolated — but the provenance names both substitutions: `location_used`,
`location_fallback`, `time_interpolated` and the `time_bracket` it interpolated
between. This is the whole contract: widen, but never silently.

```python
fallback = params.at(location="FR", **in_year(2025))
for column in ("heat_demand", "electricity_demand", "temperature", "humidity"):
    print(f"{column:>20}: {fallback[column]:7.3f} {symbol(fallback.unit_of(column))}")
print(fallback.provenance)
```

             heat_demand:   6.050 MJ
      electricity_demand:   0.500 kWh
             temperature:  11.500 °C
                humidity:   0.665 UNITLESS
    {'location_requested': 'FR', 'location_used': 'RER', 'location_fallback': True, 'time_requested': '2025', 'time_used': '2025', 'time_interpolated': True, 'time_bracket': ('2020', '2030')}

## 3. The part that has to be code

The parquet figures assume reference air: 10 °C at 70 % relative humidity.
`ambient_penalty` scales heat and electricity when the air is something else —
colder or drier means more work per kilogram captured, warmer or wetter means
less.

The response is deliberately a plain linear one. The point of the example is
that the dependency lives in code and can be read, argued with and replaced —
not that this particular curve is right.

```python
import inspect

from trailrunner.models import dac

print(inspect.getsource(dac.ambient_penalty))
```

    def ambient_penalty(temperature: float, humidity: float) -> float:
        """Multiplier on heat and electricity demand for non-reference air.
        Colder or drier than the reference gives a value above 1.0; warmer or
        wetter gives one below. Deliberately a simple linear response: the point is
        that the dependency exists and lives in code, not that this particular
        curve is the right one.
        """
        temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
        humidity_term = HUMIDITY_SENSITIVITY * (REFERENCE_HUMIDITY - humidity)
        return 1.0 + temperature_term + humidity_term

```python
for temperature, humidity in [(10.0, 0.70), (0.0, 0.40), (20.0, 0.90)]:
    penalty = dac.ambient_penalty(temperature, humidity)
    print(f"{temperature:5.1f} degC, RH {humidity:.2f} -> penalty {penalty:.3f}")
```

     10.0 degC, RH 0.70 -> penalty 1.000
      0.0 degC, RH 0.40 -> penalty 1.190
     20.0 degC, RH 0.90 -> penalty 0.840

## 4. Answering one demand

A model is constructed with its `ParameterSet` and answers a `Demand`: a `Flow`
(what, where, when) plus an amount and a unit. `apply` receives the **full**
demanded amount, never a unit demand — a plant at ten times the scale is not ten
times the plant, and nothing downstream rescales the answer.

The `Result` has three lists:

- **production** — the demand echoed back, same flow, same unit. The Runner
  rejects a model that under-produces rather than letting the inventory shrink.
- **technosphere** — what it needs. These become demands on the queue, here heat
  and electricity at the same place and time, each in its parameter column's own
  unit (MJ and kWh).
- **biosphere** — what it exchanged with the environment. CO2 from air is
  **negative**: this process takes it out of the atmosphere.

```python
from trailrunner import Demand, Flow
from trailrunner.models.dac import CO2_CAPTURED, DirectAirCapture

model = DirectAirCapture(params=params)
demand = Demand(
    flow=Flow(iri=CO2_CAPTURED, location="CH", **in_year(2030)), amount=1000.0, unit=KG
)
result = model.apply(demand)

print("production:")
for exchange in result.production:
    print(f"  {exchange.amount:10.2f} {symbol(exchange.unit):4} {exchange.flow.iri}")
print("technosphere:")
for child in result.technosphere:
    print(f"  {child.amount:10.2f} {symbol(child.unit):4} {child.flow.iri}")
print("biosphere:")
for exchange in result.biosphere:
    print(f"  {exchange.amount:10.2f} {symbol(exchange.unit):4} {exchange.flow.iri}")
print("provenance:", result.provenance)
```

    production:
         1000.00 kg   https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_2811_21
    technosphere:
         5000.00 MJ   https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9
          400.00 kWh  https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100
    biosphere:
        -1000.00 kg   https://vocab.sentier.dev/flows/co2-from-air
    provenance: {'location_requested': 'CH', 'location_used': 'CH', 'location_fallback': False, 'time_requested': '2030', 'time_used': '2030', 'time_interpolated': False}

## 5. The same demand, elsewhere and later

Asking the same 1000 kg in different places and years exercises the parameter
lookup and the penalty together. Switzerland in 2030 sits exactly at reference
conditions, so its penalty is 1.0. Europe is warmer *and* slightly drier: the
warmth dominates, so the penalty lands just below 1.0 even though the underlying
heat figure is higher. France borrows Europe's row — and the `row used` column
says so.

```python
header = f"{'location':>8} {'year':>6} {'degC':>6} {'RH':>5} {'penalty':>8} {'heat [MJ]':>10} {'row used':>10}"
print(header)
for location in ("CH", "FR", "RER"):
    for year in (2020, 2025, 2030):
        flow = Flow(iri=CO2_CAPTURED, location=location, **in_year(year))
        out = model.apply(Demand(flow=flow, amount=1000.0, unit=KG))
        heat = [d for d in out.technosphere if d.flow.iri == dac.HEAT][0]
        air = params.at(location=location, **in_year(year))
        penalty = dac.ambient_penalty(air["temperature"], air["humidity"])
        print(
            f"{location:>8} {year:>6} {air['temperature']:>6.1f} {air['humidity']:>5.2f} "
            f"{penalty:>8.3f} {heat.amount:>10.1f} {out.provenance['location_used']:>10}"
        )
```

    location   year   degC    RH  penalty  heat [MJ]   row used
          CH   2020    9.0  0.75    0.995     5970.0         CH
          CH   2025    9.5  0.72    0.997     5486.2         CH
          CH   2030   10.0  0.70    1.000     5000.0         CH
          FR   2020   11.0  0.68    0.996     6573.6        RER
          FR   2025   11.5  0.67    0.995     6022.8        RER
          FR   2030   12.0  0.65    0.995     5472.5        RER
         RER   2020   11.0  0.68    0.996     6573.6        RER
         RER   2025   11.5  0.67    0.995     6022.8        RER
         RER   2030   12.0  0.65    0.995     5472.5        RER

## 6. Letting the orchestrator walk outward

A `Glossary` says who produces what; the `Orchestrator` pops a demand, finds its
model, runs it, and pushes the resulting technosphere demands back onto the
queue. With only the DAC model registered, the traversal is one node deep — and
that is exactly what makes the next point visible.

The heat and electricity nobody models are reported as **cutoff leaves**, with a
reason. They are not quietly dropped and not silently zero: the unresolved list
is part of the answer, and it is the to-do list for the next model to write.
Section 7 works that list: register something that `produces` electricity and
those 400 kWh become a node of their own, with its own emissions.

```python
from trailrunner import Glossary, Orchestrator

report = Orchestrator(Glossary([model])).calculate(demand)

print("inventory:")
for (flow, unit), amount in report.inventory.items():
    print(f"  {amount:10.2f} {symbol(unit):4} {flow.iri}  ({flow.location}, {flow.time})")
print("unresolved:")
for record in report.unresolved:
    print(
        f"  {record.demand.amount:10.2f} {symbol(record.demand.unit):4} "
        f"{record.demand.flow.iri}  [{record.reason}]"
    )
print("nodes:", len(report.nodes), "truncated:", report.truncated)
```

    inventory:
        -1000.00 kg   https://vocab.sentier.dev/flows/co2-from-air  (CH, 2030)
    unresolved:
         5000.00 MJ   https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9  [no_model_found]
          400.00 kWh  https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100  [no_model_found]
    nodes: 1 truncated: False

Every parameter fallback used along the way is collected per node, so the report
can be audited without re-running anything.

```python
for node_id, provenance in report.provenance.items():
    print(node_id, provenance)
```

    0 {'location_requested': 'CH', 'location_used': 'CH', 'location_fallback': False, 'time_requested': '2030', 'time_used': '2030', 'time_interpolated': False}

## 7. Working the to-do list: electricity

`GridElectricity` is the counterpart to the DAC model, and it earns its place as
code for the opposite reason. Nothing about it is nonlinear — what varies is
*composition*. A Swiss kilowatt hour is mostly hydro, a European one is half
fossil in 2020, and both mixes move over the decade. One emission factor per kWh
would flatten that into a number wrong in both places, so the mix is resolved per
(location, time) and split into one demand per source, each an ordinary product
with its own IRI.

Grid losses come out of the same row: what a consumer takes off the grid is less
than what was generated, so the generation demanded upstream is
`amount / (1 - grid_loss)`.

`GasPower` sits behind the gas share. It converts kilowatt hours to megajoules of
fuel at the row's efficiency — which improves with the year — and emits fossil
CO<sub>2</sub> in proportion. Wind and hydro are left unmodelled on purpose, and
so is the natural gas itself: they stay on the to-do list.

```python
GRID_ROWS = [
    {"location": "CH", "time": "2020", "share_gas": 0.06, "share_wind": 0.04,
     "share_hydro": 0.90, "grid_loss": 0.070},
    {"location": "CH", "time": "2030", "share_gas": 0.02, "share_wind": 0.18,
     "share_hydro": 0.80, "grid_loss": 0.060},
    {"location": "RER", "time": "2020", "share_gas": 0.50, "share_wind": 0.30,
     "share_hydro": 0.20, "grid_loss": 0.080},
    {"location": "RER", "time": "2030", "share_gas": 0.25, "share_wind": 0.55,
     "share_hydro": 0.20, "grid_loss": 0.070},
]

GRID_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    Field(name="share_gas", type="number", unit=Unit(name=UNITLESS),
          description="Share of consumed electricity generated from natural gas"),
    Field(name="share_wind", type="number", unit=Unit(name=UNITLESS),
          description="Share of consumed electricity generated from wind"),
    Field(name="share_hydro", type="number", unit=Unit(name=UNITLESS),
          description="Share of consumed electricity generated from hydro power"),
    Field(name="grid_loss", type="number", unit=Unit(name=UNITLESS),
          description="Fraction of generated electricity lost before consumption"),
]

# No Swiss row: the plant parameters are European, and the lookup will say so.
GAS_ROWS = [
    {"location": "RER", "time": "2020", "efficiency": 0.55, "co2_factor": 0.056},
    {"location": "RER", "time": "2030", "efficiency": 0.62, "co2_factor": 0.056},
]

GAS_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    Field(name="efficiency", type="number", unit=Unit(name=UNITLESS),
          description="Fuel energy converted to electricity"),
    Field(name="co2_factor", type="number", unit=Unit(name=KG),
          description="Fossil CO2 emitted per megajoule of fuel burned"),
]

grid_params = ParameterSet.from_parquet(
    write_parameters(
        "grid-electricity-parameters",
        "Grid electricity parameters",
        "Generation mix and grid losses per location and year.",
        GRID_ROWS,
        GRID_FIELDS,
    ),
    hierarchy=hierarchy,
)
gas_params = ParameterSet.from_parquet(
    write_parameters(
        "gas-power-parameters",
        "Gas power plant parameters",
        "Electrical efficiency and fossil CO2 factor per location and year.",
        GAS_ROWS,
        GAS_FIELDS,
    ),
    hierarchy=hierarchy,
)
```

    grid-electricity-parameters.parquet: ✅ STRICT COMPLIANCE
    gas-power-parameters.parquet: ✅ STRICT COMPLIANCE

```python
from trailrunner.models.electricity import (
    CO2_FOSSIL,
    ELECTRICITY,
    ELECTRICITY_GAS,
    GasPower,
    GridElectricity,
)

grid = GridElectricity(params=grid_params)
plant = GasPower(params=gas_params)
glossary = Glossary([model, grid, plant])

full = Orchestrator(glossary).calculate(demand)


def short(iri):
    return iri.rsplit("/", 1)[-1]


print("nodes:")
for node in full.nodes:
    print(f"  {'  ' * node.depth}{node.demand.amount:9.2f} {symbol(node.demand.unit):4} {short(node.demand.flow.iri)}")
print("unresolved:")
for record in full.unresolved:
    print(
        f"  {'  ' * record.depth}{record.demand.amount:9.2f} {symbol(record.demand.unit):4} "
        f"{short(record.demand.flow.iri)}  [{record.reason}]"
    )
print("inventory:")
for (flow, unit), amount in full.inventory.items():
    print(f"  {amount:9.2f} {symbol(unit):4} {short(flow.iri)}  ({flow.location}, {flow.time})")
```

    nodes:
        1000.00 kg   fi_2811_21
           400.00 kWh  fi_17100
               8.51 kWh  electricity-natural-gas
    unresolved:
          5000.00 MJ   fi_1730_9  [no_model_found]
              76.60 kWh  electricity-wind  [no_model_found]
             340.43 kWh  electricity-hydro  [no_model_found]
                49.42 MJ   fi_12020  [no_model_found]
    inventory:
       -1000.00 kg   co2-from-air  (CH, 2030)
           2.77 kg   co2-fossil  (CH, 2030)

The 400 kWh cutoff is now three levels of supply chain: electricity resolves into
gas, wind and hydro generation; the gas share resolves into a plant that burns
fuel and emits. Nothing in the `Orchestrator` or the `Queue` changed to make that
happen — a model that `produces` the IRI is the whole registration.

What is left unresolved is now a *shorter, more specific* list: wind, hydro, the
natural gas, and the heat that has had no model since section 6. And the answer
has two CO<sub>2</sub> entries pulling opposite ways: the kilogram taken out of
the air by the DAC plant, and the fossil kilogram put back by the grid behind it.

Because the mix is a parameter and not a constant, the fossil side of that
balance follows place and year. Switzerland's grid is 2–6 % gas, Europe's is a
quarter to a half of it; both clean up by 2030. The gas plant has no Swiss row at
all, so its efficiency is borrowed from Europe — and `location_used` in the
node's provenance says so rather than letting the substitution pass unnoticed.

```python
header = f"{'location':>8} {'year':>6} {'gas share':>10} {'fossil CO2':>11} {'net CO2':>9} {'plant row':>10}"
print(header)
for location in ("CH", "RER"):
    for year in (2020, 2030):
        report_here = Orchestrator(glossary).calculate(
            Demand(
                flow=Flow(iri=CO2_CAPTURED, location=location, **in_year(year)),
                amount=1000.0,
                unit=KG,
            )
        )
        fossil = sum(
            amount for (flow, _), amount in report_here.inventory.items()
            if flow.iri == CO2_FOSSIL
        )
        net = sum(report_here.inventory.values())
        grid_node = [n for n in report_here.nodes if n.demand.flow.iri == ELECTRICITY][0]
        plant_node = [n for n in report_here.nodes if n.demand.flow.iri == ELECTRICITY_GAS][0]
        share = report_here.provenance[grid_node.id]["shares"][ELECTRICITY_GAS]
        row_used = report_here.provenance[plant_node.id]["location_used"]
        print(
            f"{location:>8} {year:>6} {share:>10.2f} {fossil:>11.1f} {net:>9.1f} {row_used:>10}"
        )
```

    location   year  gas share  fossil CO2   net CO2  plant row
          CH   2020       0.06        11.8    -988.2        RER
          CH   2030       0.02         2.8    -997.2        RER
         RER   2020       0.50       109.1    -890.9        RER
         RER   2030       0.25        39.1    -960.9        RER

## 8. Construction, in the years it actually happened

Everything so far is operation: heat, power, air. But a plant capturing CO<sub>2</sub>
in 2030 was poured and welded years earlier, and the fleet doing the capturing
was not built all at once.

That is a different shape of parameter table, so it gets a different reader. A
`ParameterSet` answers *what is the number here and now* and one row wins; a
`Fleet` is a list of plants that were actually built — where, when, how big, for
how long — and **every** plant running in the demanded year is part of the
answer. `operating()` keeps the rows with
`build_year <= time < build_year + lifetime` and widens through the same
`LocationHierarchy` when a location has nothing running.

No build shares are written down anywhere. The share each plant carries falls
out of the capacities, and the demanded capture decides how much of the fleet is
claimed at all:

```
total_output   = total_capacity over one year, in the demand's unit
share_of_fleet = amount / total_output
construction_i = capacity_i * amount / (total_output * lifetime_i)
```

The capacity is a rate (t/yr) and the demand an amount (kg), so a year of the
fleet's capacity is converted into kilograms before the demand is a share of
it — exactly, by the vocabulary's multipliers.

Lifetime is what stops a plant being built once per year it runs: with one
lifetime across the fleet, the construction demanded sums to the capacity that
captures `amount / lifetime` a year — one lifetime's worth of capture buys one
fleet. And each
plant's share is demanded **in that plant's own build year**, not in the year of
the capture.

```python
from trailrunner import Fleet

FLEET_ROWS = [
    # An early pilot, retired by 2027; two plants behind the 2030 fleet.
    {"plant": "ch-pilot", "location": "CH", "build_year": 2007,
     "capacity": 5000.0, "lifetime": 20.0},
    {"plant": "ch-1", "location": "CH", "build_year": 2026,
     "capacity": 12000.0, "lifetime": 20.0},
    {"plant": "ch-2", "location": "CH", "build_year": 2029,
     "capacity": 40000.0, "lifetime": 20.0},
    {"plant": "rer-1", "location": "RER", "build_year": 2024,
     "capacity": 8000.0, "lifetime": 25.0},
]

FLEET_FIELDS = [
    Field(name="plant", type="string", description="Identifier of the plant"),
    LOCATION_FIELD,
    Field(name="build_year", type="integer", unit=Unit(name=YEAR),
          description="Year the plant was commissioned"),
    Field(name="capacity", type="number", unit=Unit(name=TONNE_PER_YEAR),
          description="Nameplate capture capacity"),
    Field(name="lifetime", type="number", unit=Unit(name=YEAR),
          description="Operating lifetime before the plant retires"),
]

fleet = Fleet.from_parquet(
    write_parameters(
        "dac-fleet",
        "Direct air capture fleet",
        "The plants that were built: where, when, how big, for how long.",
        FLEET_ROWS,
        FLEET_FIELDS,
    ),
    hierarchy=hierarchy,
)

running = fleet.operating(location="CH", time=2030)
print("plants running in CH in 2030:", running.provenance["plants"])
print("total capacity:", running.total_capacity, symbol(running.unit_of("capacity")))
print("mean build year:", round(running.mean_build_year, 1))
```

    dac-fleet.parquet: ✅ STRICT COMPLIANCE
    plants running in CH in 2030: ['ch-1', 'ch-2']
    total capacity: 52000.0 t/yr
    mean build year: 2028.3

```python
dac_with_fleet = DirectAirCapture(params=params, fleet=fleet)
built = Orchestrator(Glossary([dac_with_fleet, grid, plant])).calculate(demand)

print("unresolved:")
for record in built.unresolved:
    print(
        f"  {record.demand.amount:9.4g} {symbol(record.demand.unit):8} "
        f"{short(record.demand.flow.iri):26} "
        f"{record.demand.flow.location} {record.demand.flow.time}  [{record.reason}]"
    )
print()
print("what the DAC node recorded about the fleet:")
for key in ("plants", "total_capacity", "mean_build_year", "share_of_fleet"):
    print(f"  {key:16} {built.provenance[0][key]}")
```

    unresolved:
           5000 MJ       fi_1730_9                  CH 2030  [no_model_found]
        0.01154 t/yr     direct-air-capture-plant   CH 2026  [no_model_found]
        0.03846 t/yr     direct-air-capture-plant   CH 2029  [no_model_found]
           76.6 kWh      electricity-wind           CH 2030  [no_model_found]
          340.4 kWh      electricity-hydro          CH 2030  [no_model_found]
          49.42 MJ       fi_12020                   CH 2030  [no_model_found]
    what the DAC node recorded about the fleet:
      plants           ['ch-1', 'ch-2']
      total_capacity   52000.0
      mean_build_year  2028.3076923076924
      share_of_fleet   1.923076923076923e-05

The two construction demands sit in **2026 and 2029** while the capture sits in
2030, and they are not equal: the bigger plant carries the bigger share, because
the share is its capacity's share and nothing else. Together they come to
0.05 t/yr of built capacity: the capacity that captures 50 kg a year, a
twentieth of the 1000 kg demanded, one plant-lifetime's worth.

Nothing resolves `direct-air-capture-plant` yet, so both land on the unresolved
list. That is the useful part: when a construction model does answer them, it
will be answered **twice, in two different years**, and a background that changes
with the year will be sampled in each of them.

Ask for the capture in a different year and a different fleet answers. In 2025
only the pilot is running, so the whole capital demand sits in 2007; by 2027 the
pilot has retired and `ch-1` carries everything; in 2030 the new plant dominates
and pulls the mean build year with it.

```python
print(f"{'capture':>8} {'plants running':>24} {'mean build':>11}  construction demanded")
for year in (2025, 2027, 2030):
    result = dac_with_fleet.apply(
        Demand(flow=Flow(iri=CO2_CAPTURED, location="CH", **in_year(year)), amount=1000.0, unit=KG)
    )
    capital = [d for d in result.technosphere if short(d.flow.iri) == "direct-air-capture-plant"]
    spread = ", ".join(f"{d.flow.time}: {d.amount:.4g}" for d in sorted(capital, key=lambda d: d.flow.time))
    print(
        f"{year:>8} {', '.join(result.provenance['plants']):>24} "
        f"{result.provenance['mean_build_year']:>11.1f}  {spread}"
    )
```

     capture           plants running  mean build  construction demanded
        2025                 ch-pilot      2007.0  2007: 0.05
        2027                     ch-1      2026.0  2026: 0.05
        2030               ch-1, ch-2      2028.3  2026: 0.01154, 2029: 0.03846

## 9. Coverage: outside the data, the model declines

`DirectAirCapture` declares `Coverage(time_range=year_range(2020, 2050))`. Ask it for 2015
and it is not resolved at all — but the report distinguishes *nobody models this*
(`no_model_found`) from *a registered model declined this flow*
(`coverage_excluded`), and names the model in the detail. Those are different
bugs with different fixes: write a model, or widen a coverage.

```python
print(DirectAirCapture.coverage)

early = Demand(
    flow=Flow(iri=CO2_CAPTURED, location="CH", **in_year(2015)), amount=1000.0, unit=KG
)
early_report = Orchestrator(Glossary([model])).calculate(early)

for record in early_report.unresolved:
    print(record.reason)
    print(record.detail)
print("inventory:", early_report.inventory)
```

    Coverage(locations=None, time_range=TimeRange(start='2020', end='2050', standard='http://www.w3.org/2001/XMLSchema#gYear'), context=(), units=None)
    coverage_excluded
    DirectAirCapture declares this product but its coverage does not cover location='CH' time='2015'
    inventory: {}

## 10. A second case study: pipeline transport, reverse-engineered from BAFU

`NaturalGasOffshorePipelineTransport` puts the same `Model`/`ParameterSet`/`Coverage`/`Orchestrator`
machinery to work on a domain with a different shape of nonlinearity than DAC's: not a continuous
response curve, but a **two-tier classification**.

It was reverse-engineered from the raw BAFU-2026 ecoinvent export: 11,947 ecoSpold XML files were
parsed down to the 14 country-specific "offshore pipeline, long-distance" processes and their
exchanges — the ground truth — then cross-checked against the 2025 ESU-services (Bussa et al.)
methodology report (an earlier 2007 report's per-country distance formula turned out not to match the
real corpus at all and was discarded). The report's finding, confirmed against the parsed corpus, is
that there is no per-country distance term: every origin country falls into one of two regional tiers —
`"high"` (former Soviet Union, Middle East, Africa, Asia, Latin America) or `"low"` (Europe, North
America) — and a route in the high tier leaks gas at roughly ten times the rate of one in the low tier.
Every biosphere exchange is then *derived* from that tier's leakage rate and a generic gas composition
(Tab. 3.1), not stored as a per-country number — except the gas-turbine combustion energy, the one
figure that couldn't be independently re-derived from primitives within reasonable effort and is taken
directly from the report's own worked example instead. The full six-step trail, file by file, is in
`dev/reverse-engineering of BAFU pipeline transport datasets/README.md`.

```python
# Tab. 4.4/4.6 tier constants, Tab. 3.1 generic composition, and Tab. 4.7's global constants --
# ESU-services (Bussa et al. 2025), the same values
# dev/reverse-engineering of BAFU pipeline transport datasets/build_pipeline_trailpack.py derives
# the real 14-location trailpack from. Four representative countries stand in for it here.
TIER_RATES = {
    "high": {"leakage_rate_per_1000km": 0.00204, "gas_turbine_mj_per_tkm": 0.795},
    "low": {"leakage_rate_per_1000km": 0.00019, "gas_turbine_mj_per_tkm": 0.32733},
}
GENERIC_COMPOSITION = {
    "ch4_frac": 0.6629, "c2h6_frac": 0.0549, "c3h8_frac": 0.0124, "c4h10_frac": 0.0064,
    "co2_frac": 0.0229, "hg_frac": 1e-8, "nmvoc_frac": 0.0005,
}
GLOBAL_CONSTANTS = {
    "infra_factor": 1.78e-9,
    "lorry_factor": 1.16e-7,
    "mineral_oil_disposal_factor": 1.16e-6,
    "halon1211_rate_kg_per_tkm": 2.24e-9,
    "hfc23_rate_kg_per_tkm": 8.95e-8,
}

PIPELINE_ROWS = [
    {
        "location": location, "time": "2025", "tier": tier,
        "gas_density_kg_per_nm3": 0.735,
        **TIER_RATES[tier], **GENERIC_COMPOSITION, **GLOBAL_CONSTANTS,
    }
    for tier, locations in (("high", ["DZ", "RU"]), ("low", ["NO", "GB"]))
    for location in locations
]

PIPELINE_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    Field(name="tier", type="string", description="Regional leakage/energy tier"),
    Field(name="gas_density_kg_per_nm3", type="number", unit=Unit(name="kg/Nm3"),
          description="Generic gas density (Tab. 3.1)"),
    Field(name="leakage_rate_per_1000km", type="number", unit=Unit(name=UNITLESS),
          description="Pipeline leakage rate per 1000 km (Tab. 4.4/4.6)"),
    Field(name="gas_turbine_mj_per_tkm", type="number", unit=Unit(name="MJ/tkm"),
          description="Compressor gas-turbine fuel burned per tkm (Tab. 4.7)"),
    Field(name="ch4_frac", type="number", unit=Unit(name="kg/Nm3"), description="Methane share of leaked gas"),
    Field(name="c2h6_frac", type="number", unit=Unit(name="kg/Nm3"), description="Ethane share of leaked gas"),
    Field(name="c3h8_frac", type="number", unit=Unit(name="kg/Nm3"), description="Propane share of leaked gas"),
    Field(name="c4h10_frac", type="number", unit=Unit(name="kg/Nm3"), description="Butane share of leaked gas"),
    Field(name="co2_frac", type="number", unit=Unit(name="kg/Nm3"), description="CO2 share of leaked gas"),
    Field(name="hg_frac", type="number", unit=Unit(name="kg/Nm3"), description="Mercury share of leaked gas"),
    Field(name="nmvoc_frac", type="number", unit=Unit(name="kg/Nm3"), description="NMVOC share of leaked gas"),
    Field(name="infra_factor", type="number", unit=Unit(name="unit/tkm"),
          description="Offshore pipeline infrastructure demanded per tkm"),
    Field(name="lorry_factor", type="number", unit=Unit(name="tkm/tkm"),
          description="Construction-material lorry transport demanded per tkm"),
    Field(name="mineral_oil_disposal_factor", type="number", unit=Unit(name="kg/tkm"),
          description="Hg-laden condensate disposal demanded per tkm"),
    Field(name="halon1211_rate_kg_per_tkm", type="number", unit=Unit(name="kg/tkm"),
          description="Compressor-station Halon 1211 refrigerant loss per tkm"),
    Field(name="hfc23_rate_kg_per_tkm", type="number", unit=Unit(name="kg/tkm"),
          description="Compressor-station HFC-23 refrigerant loss per tkm"),
]

pipeline_parameter_file = write_parameters(
    "natural-gas-pipeline-parameters",
    "Natural gas offshore pipeline transport parameters",
    "Two-tier leakage/energy constants and generic gas composition, ESU-services (Bussa et al. 2025).",
    PIPELINE_ROWS,
    PIPELINE_FIELDS,
)
print(pipeline_parameter_file)
```

    natural-gas-pipeline-parameters.parquet: ✅ STRICT COMPLIANCE
    /var/folders/l1/k90rhb0j0ns58y35ymznsd700000gn/T/tmpa_ffspwr/natural-gas-pipeline-parameters.parquet

The tier split is the whole model, and it is a pure function of two numbers: the tier's leakage rate
and the generic gas density. `leaked_volume_nm3_per_tkm` — mirroring `dac.ambient_penalty` as the
one piece of arithmetic worth checking in isolation — turns that rate into the Nm3 of gas lost per
tkm moved, and the high tier comes out roughly ten times the low tier's, exactly as the source report
describes it.

```python
from trailrunner.models.natural_gas_pipeline_transport import leaked_volume_nm3_per_tkm

for tier_name in ("high", "low"):
    rate = TIER_RATES[tier_name]["leakage_rate_per_1000km"]
    print(f"{tier_name:>5} tier: {leaked_volume_nm3_per_tkm(rate, 0.735):.7f} Nm3/tkm leaked")
```

     high tier: 0.0027755 Nm3/tkm leaked
      low tier: 0.0002585 Nm3/tkm leaked

## 11. Answering a demand: 1 t of gas over 1000 km out of Algeria

The pipeline moves **tonnes** of gas, and how far is a condition of the demand: a
`distance` in the flow's `context`, in any length unit. 1 t over 1000 km is the
1000 tkm an ecoinvent dataset would name.

Same contract as section 4 — `apply` gets the full demanded amount and returns production,
technosphere and biosphere — on a model whose `technosphere` list is five items long: pipeline
infrastructure, the leaked gas itself (bought back from upstream production), gas-turbine fuel for the
compressors, a sliver of lorry transport for construction materials, and disposal of the
mercury-laden condensate. All five are `provenance`-free line items here because they scale with the
tier constants, not with a fallback or an interpolation.

```python
from trailrunner.models.natural_gas_pipeline_transport import (
    METHANE_FOSSIL,
    TRANSPORT,
    NaturalGasOffshorePipelineTransport,
)

pipeline_params = ParameterSet.from_parquet(pipeline_parameter_file, hierarchy=hierarchy)
pipeline = NaturalGasOffshorePipelineTransport(params=pipeline_params)

from trailrunner import Property
from trailrunner.core.units import KILOMETRE, TONNE

OVER_1000_KM = (Property("distance", 1000.0, KILOMETRE),)
pipeline_demand = Demand(
    flow=Flow(iri=TRANSPORT, location="DZ", **in_year(2025), context=OVER_1000_KM),
    amount=1.0,
    unit=TONNE,
)
pipeline_result = pipeline.apply(pipeline_demand)

print("production:")
for exchange in pipeline_result.production:
    print(f"  {exchange.amount:10.4f} {symbol(exchange.unit):4} {exchange.flow.iri}")
print("technosphere:")
for child in pipeline_result.technosphere:
    print(f"  {child.amount:12.8f} {symbol(child.unit):4} {child.flow.iri}")
print("biosphere:")
for exchange in pipeline_result.biosphere:
    print(f"  {exchange.amount:12.8f} {symbol(exchange.unit):4} {exchange.flow.iri}")
print("provenance:", pipeline_result.provenance)
```

    production:
          1.0000 t    https://vocab.sentier.dev/products/natural-gas-transport-offshore-pipeline-long-distance
    technosphere:
        0.00000178 unit https://vocab.sentier.dev/products/pipeline-natural-gas-long-distance-high-capacity-offshore
        2.77551020 m3   https://vocab.sentier.dev/products/natural-gas-at-production
      795.00000000 MJ   https://vocab.sentier.dev/products/natural-gas-burned-in-gas-turbine
        0.00000012 t    https://vocab.sentier.dev/products/transport-freight-lorry-16t-32t
        0.00116000 kg   https://vocab.sentier.dev/products/disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration
    biosphere:
        1.83988571 kg   https://vocab.sentier.dev/flows/ch4-fossil
        0.15237551 kg   https://vocab.sentier.dev/flows/ethane
        0.03441633 kg   https://vocab.sentier.dev/flows/propane
        0.01776327 kg   https://vocab.sentier.dev/flows/butane
        0.06355918 kg   https://vocab.sentier.dev/flows/co2-fossil
        0.00000003 kg   https://vocab.sentier.dev/flows/mercury
        0.00138776 kg   https://vocab.sentier.dev/flows/nmvoc-unspecified-origin
        0.00000224 kg   https://vocab.sentier.dev/flows/methane-bromochlorodifluoro-halon-1211
        0.00008950 kg   https://vocab.sentier.dev/flows/methane-trifluoro-hfc-23
    provenance: {'location_requested': 'DZ', 'location_used': 'DZ', 'location_fallback': False, 'time_requested': '2025', 'time_used': '2025', 'time_interpolated': False, 'tier': 'high', 'leaked_volume_nm3': 2.7755102040816326, 'tkm': 1000.0}

## 12. The same demand, across both tiers

Algeria and Russia (high tier) against Norway and the UK (low tier), same 1 t over 1000 km each. Everything
scales off the tier: leaked volume, methane released, and gas-turbine fuel all roughly move together
between the two clusters, and nothing here depends on which specific high-tier or low-tier country is
asked for — the model has no finer-grained knowledge than the tier itself.

```python
header = f"{'location':>8} {'tier':>5} {'leaked Nm3':>12} {'CH4 [kg]':>10} {'gas turbine [MJ]':>17}"
print(header)
for location in ("DZ", "RU", "NO", "GB"):
    flow = Flow(iri=TRANSPORT, location=location, **in_year(2025), context=OVER_1000_KM)
    out = pipeline.apply(Demand(flow=flow, amount=1.0, unit=TONNE))
    ch4 = [e for e in out.biosphere if e.flow.iri == METHANE_FOSSIL][0]
    turbine = [d for d in out.technosphere if "gas-turbine" in d.flow.iri][0]
    print(
        f"{location:>8} {out.provenance['tier']:>5} {out.provenance['leaked_volume_nm3']:>12.6f} "
        f"{ch4.amount:>10.6f} {turbine.amount:>17.3f}"
    )
```

    location  tier   leaked Nm3   CH4 [kg]  gas turbine [MJ]
          DZ  high     2.775510   1.839886           795.000
          RU  high     2.775510   1.839886           795.000
          NO   low     0.258503   0.171362           327.330
          GB   low     0.258503   0.171362           327.330

## 13. Its own to-do list

Registered alone in a `Glossary`, this model produces a cutoff list of its own — a different one from
DAC's, because a pipeline needs infrastructure, upstream gas production, compressor fuel, freight and
waste disposal rather than heat and power. Nothing here connects to the DAC chain above: they are two
independent case studies sharing nothing but the framework that runs them.

```python
pipeline_report = Orchestrator(Glossary([pipeline])).calculate(pipeline_demand)

print("inventory:")
for (flow, unit), amount in pipeline_report.inventory.items():
    print(f"  {amount:12.8f} {symbol(unit):4} {short(flow.iri)}  ({flow.location}, {flow.time})")
print("unresolved:")
for record in pipeline_report.unresolved:
    print(
        f"  {record.demand.amount:12.8f} {symbol(record.demand.unit):6} "
        f"{short(record.demand.flow.iri):26}  [{record.reason}]"
    )
```

    inventory:
        1.83988571 kg   ch4-fossil  (DZ, 2025)
        0.15237551 kg   ethane  (DZ, 2025)
        0.03441633 kg   propane  (DZ, 2025)
        0.01776327 kg   butane  (DZ, 2025)
        0.06355918 kg   co2-fossil  (DZ, 2025)
        0.00000003 kg   mercury  (DZ, 2025)
        0.00138776 kg   nmvoc-unspecified-origin  (DZ, 2025)
        0.00000224 kg   methane-bromochlorodifluoro-halon-1211  (DZ, 2025)
        0.00008950 kg   methane-trifluoro-hfc-23  (DZ, 2025)
    unresolved:
        0.00000178 unit   pipeline-natural-gas-long-distance-high-capacity-offshore  [no_model_found]
        2.77551020 m3     natural-gas-at-production   [no_model_found]
      795.00000000 MJ     natural-gas-burned-in-gas-turbine  [no_model_found]
        0.00000012 t      transport-freight-lorry-16t-32t  [no_model_found]
        0.00116000 kg     disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration  [no_model_found]

And, echoing section 9, `coverage` here is not a time range but the 14 locations the trailpack actually
has rows for — the raw BAFU export never contained a fifteenth country, so there is nothing to
interpolate or fall back to, only a location to decline.

```python
print(NaturalGasOffshorePipelineTransport.coverage)

undocumented = Demand(
    flow=Flow(iri=TRANSPORT, location="CH", **in_year(2025), context=OVER_1000_KM),
    amount=1.0,
    unit=TONNE,
)
undocumented_report = Orchestrator(Glossary([pipeline])).calculate(undocumented)

for record in undocumented_report.unresolved:
    print(record.reason)
    print(record.detail)
print("inventory:", undocumented_report.inventory)
```

    Coverage(locations=frozenset({'QA', 'AZ', 'IT', 'ID', 'UA', 'NL', 'LY', 'RU', 'US', 'MY', 'DZ', 'GB', 'IR', 'NO'}), time_range=None, context=(), units=frozenset({'https://vocab.sentier.dev/units/unit/TONNE'}))
    coverage_excluded
    NaturalGasOffshorePipelineTransport declares this product but its coverage does not cover location='CH' time='2025' context='distance=1000 km'
    inventory: {}

## Where this stops

Every answer above is an inventory, not a score: trailrunner does no impact
characterization yet, so there is nothing to sum into a single number. Nor is
there a Brightway background — a demand nobody models stays a recorded cutoff.

Two more deliberate boundaries show up in `Report`: every visit is its own node,
never merged with an identical one elsewhere in the tree, which is what keeps
nonlinear models honest; and a cycle is truncated by the depth and node budgets
rather than solved, with `report.truncated` saying when a budget bit.

To go further from here, work either unresolved list the way section 7 did: the
README's `MyBoiler` is a ten-line model that produces the heat still cut off
above section 6. Register it in a `Glossary` alongside the other three and that
leaf becomes a node too, with its own fuel demand and its own emissions — and
the pipeline model's own cutoffs (upstream gas production, compressor fuel,
infrastructure, freight, disposal) are exactly as open to the same treatment.
