# Cement Plant Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-base the showcase notebook and the five-minute tour on a cement plant, replacing the direct-air-capture example, and add a beat showing metered data answering past years while a computed model answers future ones.

**Architecture:** One new module, `trailrunner/models/cement.py`, holding two model classes that declare the same product IRI with non-overlapping `Coverage.time_range`. `Glossary.resolve` already filters by coverage, so selecting a measurement for 2023 and a calculation for 2030 needs no library change. `DirectAirCapture` stays where it is and every existing test keeps passing.

**Tech Stack:** Python 3.11+, pyarrow (parquet parameters), pytest, nbclient (asset build), plotly (figures), mkdocs/zensical (docs).

**Spec:** `dev/.agents/specs/2026-09-24-cement-plant-showcase-design.md`

## Global Constraints

- Every product IRI used by a shipped model must be a real vocabulary concept, or be explicitly documented as invented in a module comment. Verified concepts for this work: `fi_37440`, `fi_15200`, `fi_12020`, `fi_17100`, `fi_1730_6`, `fi_1730`.
- `examples/showcase.ipynb` must execute offline with no `PYST_AUTH_TOKEN`. Every IRI it touches must be in `examples/pyst_cache.json` and `examples/pyst_labels.json` first.
- No new runtime dependency. `ParameterSet.from_parquet` reads plain pyarrow parquet with an embedded `datapackage.json`; do not reach for trailpack.
- `trailrunner/models/dac.py`, `examples/dac.ipynb`, `examples/dac_params.parquet` and every file under `tests/` that exists today are not to be modified. New test files only.
- Commit messages in this repo carry no Claude attribution footer.
- Numbers quoted in `docs/showcase.md` must be copied from an executed notebook, never typed by hand.

---

### Task 1: Warm the vocabulary caches

Nothing downstream can run offline until the three new concepts are committed. This task needs network access.

**Files:**
- Modify: `dev/warm_pyst_cache.py`
- Modify (generated): `examples/pyst_cache.json`, `examples/pyst_labels.json`

**Interfaces:**
- Consumes: nothing.
- Produces: cached `skos:broader` edges and `skos:prefLabel` strings for `fi_37440`, `fi_15200`, `fi_1730_6`. Task 5 depends on `fi_1730_6 -> fi_1730` being present or the relaxation beat cannot resolve offline.

- [ ] **Step 1: Add the three IRIs to the warm list**

In `dev/warm_pyst_cache.py`, extend `IRIS`:

```python
IRIS = [
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_2811_21",  # co2-captured: "Carbon dioxide"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9",  # heat: "heat from main producers of heat"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100",  # electricity: "electricity"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020",  # natural-gas: "Natural gas, liquefied or in the gaseous state"
    # The cement showcase. fi_1730_6 is the specific technology the plant asks
    # for and fi_1730 is the generic concept one skos:broader step above it --
    # the relaxation beat in examples/showcase.ipynb walks exactly that edge,
    # so this entry is what makes the beat resolve with no network.
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440",  # cement: "Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_15200",  # limestone: "Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_6",  # steam: "heat from electric boilers"
]
```

- [ ] **Step 2: Run the warming script**

Run: `uv run python dev/warm_pyst_cache.py`

Expected: each new IRI prints a non-empty parent list. `fi_1730_6` must print `['…/fi_1730']`. Read the "no such concept" block it prints at the end — none of the three new IRIs may appear there.

- [ ] **Step 3: Verify the caches offline**

Run:

```bash
uv run python -c "
import json
cache = json.load(open('examples/pyst_cache.json'))
labels = json.load(open('examples/pyst_labels.json'))
base = 'https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/'
assert cache[base + 'fi_1730_6'] == [base + 'fi_1730'], cache.get(base + 'fi_1730_6')
for code in ('fi_37440', 'fi_15200', 'fi_1730_6', 'fi_1730'):
    print(code, '=', labels[base + code])
"
```

Expected: no assertion error, and four labels printed.

- [ ] **Step 4: Commit**

```bash
git add dev/warm_pyst_cache.py examples/pyst_cache.json examples/pyst_labels.json
git commit -m "chore(examples): cache the cement, limestone and electric-boiler concepts"
```

---

### Task 2: The moisture penalty

The demand-dependence that justifies a model being code. Split from the model itself because it is a pure function with its own tests.

**Files:**
- Create: `trailrunner/models/cement.py`
- Test: `tests/test_cement.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `moisture_penalty(moisture: float, temperature: float) -> float`; module constants `REFERENCE_MOISTURE = 0.04`, `REFERENCE_TEMPERATURE = 10.0`, `MOISTURE_SENSITIVITY = 2.0`, `TEMPERATURE_SENSITIVITY = 0.004`. Task 3 multiplies thermal demands by this.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cement.py`:

```python
import pytest

from trailrunner.models.cement import moisture_penalty


def test_moisture_penalty_at_reference_conditions_is_exactly_one():
    assert moisture_penalty(0.04, 10.0) == 1.0


def test_moisture_penalty_rises_with_wetter_feed():
    # Eight percent moisture against a four percent reference: twice the water
    # to evaporate before anything calcines.
    assert moisture_penalty(0.08, 10.0) == pytest.approx(1.08)


def test_moisture_penalty_rises_with_colder_feed():
    assert moisture_penalty(0.04, 0.0) == pytest.approx(1.04)


def test_moisture_penalty_falls_for_dry_warm_feed():
    assert moisture_penalty(0.02, 20.0) == pytest.approx(0.92)


def test_moisture_penalty_is_linear_in_both_terms():
    combined = moisture_penalty(0.08, 0.0)
    assert combined == pytest.approx(1.08 + 0.04)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cement.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'trailrunner.models.cement'`.

- [ ] **Step 3: Write the module header and the function**

Create `trailrunner/models/cement.py`:

```python
"""Cement: the worked example.

Kiln fuel is not a fixed coefficient. Raw meal arrives from the quarry with
water in it, and every kilogram of that water has to be boiled off before any
limestone calcines, so wet feed costs both drying steam and kiln fuel. Cold
feed costs a little more again. That dependency is the reason a model is
Python code rather than a row in a table.

Two classes live here and both declare the same product. ``CementPlant``
computes; ``MeteredCementPlant`` reads a meter. Their ``Coverage`` time ranges
do not overlap, so ``Glossary.resolve`` picks between them by the year the
demand carries, and the report names which one answered. Nothing in the
library had to learn about measurement for that to work.
"""

REFERENCE_MOISTURE = 0.04  # mass fraction, the raw meal the parquet figures assume
REFERENCE_TEMPERATURE = 10.0  # degC, likewise
MOISTURE_SENSITIVITY = 2.0  # per unit of mass fraction above reference
TEMPERATURE_SENSITIVITY = 0.004  # per degC below reference


def moisture_penalty(moisture: float, temperature: float) -> float:
    """Multiplier on thermal demand for feed that is not at reference.

    Wetter or colder than the reference gives a value above 1.0; drier or
    warmer gives one below. Deliberately a simple linear response: the point is
    that the dependency exists and lives in code, not that this particular
    curve is the right one.

    Applied to the kiln fuel and the drying steam, and not to electricity.
    Grinding work is set by how fine the cement has to be, not by how wet the
    quarry was.
    """
    moisture_term = MOISTURE_SENSITIVITY * (moisture - REFERENCE_MOISTURE)
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    return 1.0 + moisture_term + temperature_term
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cement.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add trailrunner/models/cement.py tests/test_cement.py
git commit -m "feat(models): add the cement moisture penalty"
```

---

### Task 3: `CementPlant`

**Files:**
- Modify: `trailrunner/models/cement.py`
- Test: `tests/test_cement.py`

**Interfaces:**
- Consumes: `moisture_penalty` from Task 2.
- Produces: `CementPlant(settings=None, params=None, fleet=None)`, and module constants `CEMENT`, `LIMESTONE`, `NATURAL_GAS`, `ELECTRICITY`, `STEAM`, `CO2_FOSSIL`, `CEMENT_KILN`, `CLINKER_CALCINATION_CO2`, `LIMESTONE_PER_CLINKER`, `GAS_CO2_PER_MJ`. Tasks 4, 5 and 6 import these names.

Parameter columns this model reads, with units, which Task 5's parquet writer must match exactly: `clinker_factor` (dimensionless), `fuel_demand` (MJ, per kg of **clinker**), `steam_demand` (MJ, per kg of **cement**), `electricity_demand` (kWh, per kg of cement), `moisture` (dimensionless), `temperature` (degC).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cement.py`, and add the imports at the top of the file:

```python
from trailrunner.core.flow import Demand, Flow
from trailrunner.models.cement import (
    CEMENT,
    CO2_FOSSIL,
    ELECTRICITY,
    LIMESTONE,
    NATURAL_GAS,
    STEAM,
    CementPlant,
)
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

from .conftest import write_parameter_parquet

HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})


@pytest.fixture
def cement_params(tmp_path):
    path = tmp_path / "cement.parquet"
    rows = [
        {"location": "CH", "time": 2030, "clinker_factor": 0.75, "fuel_demand": 3.3,
         "steam_demand": 0.34, "electricity_demand": 0.10,
         "moisture": 0.04, "temperature": 10.0},
        {"location": "RER", "time": 2030, "clinker_factor": 0.80, "fuel_demand": 3.5,
         "steam_demand": 0.40, "electricity_demand": 0.11,
         "moisture": 0.06, "temperature": 9.0},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "integer", "unit": "year", "iri": None},
        {"name": "clinker_factor", "type": "number", "unit": "dimensionless", "iri": None},
        {"name": "fuel_demand", "type": "number", "unit": "MJ", "iri": None},
        {"name": "steam_demand", "type": "number", "unit": "MJ", "iri": None},
        {"name": "electricity_demand", "type": "number", "unit": "kWh", "iri": None},
        {"name": "moisture", "type": "number", "unit": "dimensionless", "iri": None},
        {"name": "temperature", "type": "number", "unit": "degC", "iri": None},
    ]
    write_parameter_parquet(path, rows, fields)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def cement_demand(location="CH", time=2030, amount=1000.0):
    return Demand(
        flow=Flow(iri=CEMENT, location=location, time=time), amount=amount, unit="kg"
    )


def test_cement_plant_produces_exactly_what_was_demanded(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert result.production[0].flow.iri == CEMENT
    assert result.production[0].amount == 1000.0
    assert result.production[0].unit == "kg"


def test_cement_plant_demands_limestone_gas_steam_and_electricity(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert set(by_iri) == {LIMESTONE, NATURAL_GAS, STEAM, ELECTRICITY}
    assert by_iri[LIMESTONE].unit == "kg"
    assert by_iri[NATURAL_GAS].unit == "MJ"
    assert by_iri[STEAM].unit == "MJ"
    assert by_iri[ELECTRICITY].unit == "kWh"
    for child in result.technosphere:
        assert child.flow.location == "CH"
        assert child.flow.time == 2030


def test_clinker_factor_scales_the_limestone_and_the_fuel(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    # 1000 kg cement at a clinker factor of 0.75 is 750 kg of clinker.
    assert by_iri[LIMESTONE].amount == pytest.approx(1125.0)  # 1.5 kg per kg clinker
    assert by_iri[NATURAL_GAS].amount == pytest.approx(2475.0)  # 3.3 MJ per kg clinker


def test_steam_and_electricity_scale_with_the_cement_not_the_clinker(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert by_iri[STEAM].amount == pytest.approx(340.0)
    assert by_iri[ELECTRICITY].amount == pytest.approx(100.0)


def test_calcination_and_combustion_are_two_separate_biosphere_exchanges(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert len(result.biosphere) == 2
    assert {e.flow.iri for e in result.biosphere} == {CO2_FOSSIL}
    amounts = sorted(e.amount for e in result.biosphere)
    # Combustion of 2475 MJ of gas, then calcination of 750 kg of clinker.
    assert amounts[0] == pytest.approx(138.6)
    assert amounts[1] == pytest.approx(397.5)
    for exchange in result.biosphere:
        assert exchange.unit == "kg"
        assert exchange.amount > 0


def test_combustion_co2_matches_the_gas_the_model_just_demanded(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    gas = [d for d in result.technosphere if d.flow.iri == NATURAL_GAS][0]
    combustion = min(e.amount for e in result.biosphere)
    assert combustion == pytest.approx(gas.amount * 0.056)


def test_wetter_feed_raises_thermal_demand_but_not_electricity(cement_params):
    plant = CementPlant(params=cement_params)
    dry = {d.flow.iri: d.amount for d in plant.apply(cement_demand()).technosphere}
    wet = {
        d.flow.iri: d.amount
        for d in plant.apply(cement_demand(location="RER")).technosphere
    }
    # RER's row is wetter and colder, so its penalty exceeds one.
    assert wet[NATURAL_GAS] / (0.80 * 1000.0 * 3.5) > 1.0
    assert wet[STEAM] / (1000.0 * 0.40) > 1.0
    assert wet[ELECTRICITY] == pytest.approx(1000.0 * 0.11)


def test_cement_plant_records_its_parameter_provenance(cement_params):
    result = CementPlant(params=cement_params).apply(cement_demand())
    assert result.provenance["location_used"] == "CH"
    assert result.provenance["time_used"] == 2030
    assert result.provenance["source"] == "modelled"


def test_cement_plant_answers_the_full_demanded_amount_without_rescaling(cement_params):
    plant = CementPlant(params=cement_params)
    one = plant.apply(cement_demand(amount=1.0))
    thousand = plant.apply(cement_demand(amount=1000.0))
    one_gas = [d for d in one.technosphere if d.flow.iri == NATURAL_GAS][0]
    many_gas = [d for d in thousand.technosphere if d.flow.iri == NATURAL_GAS][0]
    assert many_gas.amount == pytest.approx(one_gas.amount * 1000.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cement.py -v`
Expected: `ImportError: cannot import name 'CEMENT' from 'trailrunner.models.cement'`.

- [ ] **Step 3: Write the constants and the model**

Append to `trailrunner/models/cement.py`, and add the imports at the top of the module:

```python
from trailrunner.attribution import amortize
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ALLOCATION_RULES
from trailrunner.params.coverage import Coverage
from trailrunner.params.fleet import Fleet

# Real BONSAI vocabulary concepts, verified live against
# https://vocab.sentier.dev on 2026-09-24 and cached by
# dev/warm_pyst_cache.py. An IRI that is not a concept relaxes nothing,
# because skos:broader never has anything to walk -- see the comment in
# trailrunner/models/dac.py for what that failure looks like.
CEMENT = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440"  # "Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers"
LIMESTONE = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_15200"  # "Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement"
NATURAL_GAS = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020"  # "Natural gas, liquefied or in the gaseous state"
ELECTRICITY = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100"  # "electricity"
# The *specific* heat the plant asks for. Nothing in this repository produces
# it, which is the point: the showcase relaxes it one skos:broader step to
# fi_1730, "Steam and hot water", and a generic supplier answers. The
# concession is that a technology was asked for and an average came back.
STEAM = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_6"  # "heat from electric boilers"
# Invented, like dac.py's DAC_PLANT and for the same reason: BONSAI's product
# classification does not carry capital-good infrastructure at this
# granularity. The concepts endpoint answers 404, so this can never relax.
CEMENT_KILN = "https://vocab.sentier.dev/products/cement-kiln"
# Calcination CO2 is geogenic rather than fossil, but every inventory
# convention in use counts it as fossil, and co2-fossil is the IRI
# assessment/dynamic.py and assessment/static.py already characterize.
# Writing it anywhere else would drop it silently out of every score.
CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"

CLINKER_CALCINATION_CO2 = 0.53  # kg CO2 per kg clinker, from CaCO3 -> CaO + CO2
LIMESTONE_PER_CLINKER = 1.5  # kg raw limestone per kg clinker
GAS_CO2_PER_MJ = 0.056  # kg CO2 per MJ of natural gas burned


class CementPlant(Model):
    """Grinds cement, calcines its own clinker, fires its own kiln.

    Monofunctional: one product, so there is nothing to partition and no
    allocation rule changes the answer. Co-production is demonstrated
    separately, in ``examples/coproduction.ipynb``.

    Pass a ``Fleet`` to also account for the kilns doing the calcining.
    Without one the model answers operation only, no capital.
    """

    produces = [CEMENT]
    coverage = Coverage(time_range=(2026, 2050))
    fleet: Fleet | None = None

    supports = ALLOCATION_RULES
    """Every rule, because this model is monofunctional.

    The same reasoning DirectAirCapture.supports carries: with a single
    product ``allocate`` short-circuits and ``substitute`` mints no credits,
    so the answer is identical under all five rules. Declaring only ``none``
    would make the Runner refuse this model at the first node of any
    non-``none`` run, for a problem it does not have.
    """

    def __init__(self, settings=None, params=None, fleet: Fleet | None = None) -> None:
        super().__init__(settings=settings, params=params)
        if fleet is not None:
            self.fleet = fleet

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        penalty = moisture_penalty(row["moisture"], row["temperature"])

        clinker = row["clinker_factor"] * demand.amount
        limestone = LIMESTONE_PER_CLINKER * clinker
        fuel = row["fuel_demand"] * clinker * penalty
        steam = row["steam_demand"] * demand.amount * penalty
        electricity = row["electricity_demand"] * demand.amount

        construction, fleet_provenance = self._construction(demand)

        def here(iri: str) -> Flow:
            return Flow(iri=iri, location=demand.flow.location, time=demand.flow.time)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(flow=here(LIMESTONE), amount=limestone, unit="kg"),
                Demand(flow=here(NATURAL_GAS), amount=fuel, unit=row.unit_of("fuel_demand")),
                Demand(flow=here(STEAM), amount=steam, unit=row.unit_of("steam_demand")),
                Demand(
                    flow=here(ELECTRICITY),
                    amount=electricity,
                    unit=row.unit_of("electricity_demand"),
                ),
                *construction,
            ],
            biosphere=[
                # Two exchanges, not one sum. A reader can see which kilogram
                # came from the rock and which from the flame -- and the
                # measured beat lands on the fact that a stack meter cannot.
                Exchange(
                    flow=here(CO2_FOSSIL),
                    amount=CLINKER_CALCINATION_CO2 * clinker,
                    unit="kg",
                ),
                Exchange(
                    flow=here(CO2_FOSSIL), amount=GAS_CO2_PER_MJ * fuel, unit="kg"
                ),
            ],
            provenance={**row.provenance, "source": "modelled", **fleet_provenance},
        )
```

- [ ] **Step 4: Port the fleet handling**

Append the `_construction` method to `CementPlant`. It is `DirectAirCapture._construction` with `DAC_PLANT` replaced by `CEMENT_KILN`; copy the method and its docstring from `trailrunner/models/dac.py` and change only that constant and the words "plant" to "kiln" in the prose. Do not change the `amortize` call or its arguments.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cement.py -v`
Expected: 14 passed.

- [ ] **Step 6: Run the whole suite to verify nothing else moved**

Run: `uv run pytest -q`
Expected: the same pass count as before this task, plus 14.

- [ ] **Step 7: Commit**

```bash
git add trailrunner/models/cement.py tests/test_cement.py
git commit -m "feat(models): add CementPlant"
```

---

### Task 4: `MeteredCementPlant` and coverage selection

**Files:**
- Modify: `trailrunner/models/cement.py`
- Test: `tests/test_cement.py`

**Interfaces:**
- Consumes: `CEMENT`, `NATURAL_GAS`, `STEAM`, `ELECTRICITY`, `CO2_FOSSIL` from Task 3.
- Produces: `MeteredCementPlant(settings=None, params=None)`. Task 5's parquet writer must supply columns `metered_fuel` (MJ), `metered_steam` (MJ), `metered_electricity` (kWh), `metered_co2` (kg).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cement.py`:

```python
from trailrunner.models.cement import MeteredCementPlant
from trailrunner.orchestration.glossary import Glossary


@pytest.fixture
def metered_params(tmp_path):
    path = tmp_path / "cement_metered.parquet"
    rows = [
        {"location": "CH", "time": 2023, "metered_fuel": 2610.0, "metered_steam": 385.0,
         "metered_electricity": 108.0, "metered_co2": 562.0},
        {"location": "CH", "time": 2024, "metered_fuel": 2560.0, "metered_steam": 372.0,
         "metered_electricity": 106.0, "metered_co2": 551.0},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "integer", "unit": "year", "iri": None},
        {"name": "metered_fuel", "type": "number", "unit": "MJ", "iri": None},
        {"name": "metered_steam", "type": "number", "unit": "MJ", "iri": None},
        {"name": "metered_electricity", "type": "number", "unit": "kWh", "iri": None},
        {"name": "metered_co2", "type": "number", "unit": "kg", "iri": None},
    ]
    write_parameter_parquet(path, rows, fields)
    return ParameterSet.from_parquet(path, hierarchy=HIERARCHY)


def test_metered_plant_returns_the_row_untouched(metered_params):
    result = MeteredCementPlant(params=metered_params).apply(
        cement_demand(time=2023)
    )
    by_iri = {d.flow.iri: d for d in result.technosphere}
    assert by_iri[NATURAL_GAS].amount == pytest.approx(2610.0)
    assert by_iri[STEAM].amount == pytest.approx(385.0)
    assert by_iri[ELECTRICITY].amount == pytest.approx(108.0)


def test_metered_plant_emits_one_merged_stack_figure(metered_params):
    result = MeteredCementPlant(params=metered_params).apply(
        cement_demand(time=2023)
    )
    assert len(result.biosphere) == 1
    assert result.biosphere[0].flow.iri == CO2_FOSSIL
    assert result.biosphere[0].amount == pytest.approx(562.0)
    assert result.biosphere[0].unit == "kg"


def test_metered_plant_still_sends_its_purchased_energy_upstream(metered_params):
    # The emissions behind metered gas, steam and electricity happen off site.
    # A meter at the plant boundary says nothing about them, so they stay
    # technosphere demands and get answered by whoever supplies them.
    result = MeteredCementPlant(params=metered_params).apply(
        cement_demand(time=2023)
    )
    assert {d.flow.iri for d in result.technosphere} == {
        NATURAL_GAS,
        STEAM,
        ELECTRICITY,
    }


def test_metered_plant_scales_its_row_to_the_demanded_amount(metered_params):
    plant = MeteredCementPlant(params=metered_params)
    half = plant.apply(cement_demand(time=2023, amount=500.0))
    assert half.biosphere[0].amount == pytest.approx(281.0)


def test_metered_plant_records_that_it_measured_rather_than_computed(metered_params):
    result = MeteredCementPlant(params=metered_params).apply(
        cement_demand(time=2023)
    )
    assert result.provenance["source"] == "measured"


def test_glossary_picks_the_meter_for_a_past_year(cement_params, metered_params):
    glossary = Glossary(
        [CementPlant(params=cement_params), MeteredCementPlant(params=metered_params)]
    )
    chosen = glossary.resolve(Flow(iri=CEMENT, location="CH", time=2023))
    assert type(chosen) is MeteredCementPlant


def test_glossary_picks_the_model_for_a_future_year(cement_params, metered_params):
    glossary = Glossary(
        [CementPlant(params=cement_params), MeteredCementPlant(params=metered_params)]
    )
    chosen = glossary.resolve(Flow(iri=CEMENT, location="CH", time=2030))
    assert type(chosen) is CementPlant


def test_the_two_coverages_never_overlap(cement_params, metered_params):
    # Two models declaring one product IRI is only safe because their year
    # ranges are disjoint; an overlap would raise AmbiguousModelMatch on a
    # demand nobody thought to test.
    glossary = Glossary(
        [CementPlant(params=cement_params), MeteredCementPlant(params=metered_params)]
    )
    for year in range(2018, 2051):
        glossary.resolve(Flow(iri=CEMENT, location="CH", time=year))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cement.py -v`
Expected: `ImportError: cannot import name 'MeteredCementPlant'`.

- [ ] **Step 3: Write the model**

Append to `trailrunner/models/cement.py`:

```python
class MeteredCementPlant(Model):
    """The same plant, in the years it was measured rather than modelled.

    This computes nothing. It reads one row of metered data and returns it,
    which is enough to make it a model: what makes something a model here is
    that it answers a demand, not that it calculates one.

    What a meter at the plant boundary can and cannot tell you is the whole
    point of the class. It gives one stack figure, calcination and combustion
    together and indistinguishable, so this returns a single biosphere
    exchange where ``CementPlant`` returns two. The gas, steam and electricity
    it also meters are *inputs*: their emissions happen off site, so they go
    out as technosphere demands and get answered by whoever supplies them,
    exactly as the computed model's do.

    The row is per kilogram of the reference output the meter was normalised
    against, so it scales with the demand. A meter reading is not a fixed
    quantity of anything.
    """

    produces = [CEMENT]
    coverage = Coverage(time_range=(2018, 2025))

    supports = ALLOCATION_RULES

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        scale = demand.amount / 1000.0

        def here(iri: str) -> Flow:
            return Flow(iri=iri, location=demand.flow.location, time=demand.flow.time)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(
                    flow=here(NATURAL_GAS),
                    amount=row["metered_fuel"] * scale,
                    unit=row.unit_of("metered_fuel"),
                ),
                Demand(
                    flow=here(STEAM),
                    amount=row["metered_steam"] * scale,
                    unit=row.unit_of("metered_steam"),
                ),
                Demand(
                    flow=here(ELECTRICITY),
                    amount=row["metered_electricity"] * scale,
                    unit=row.unit_of("metered_electricity"),
                ),
            ],
            biosphere=[
                Exchange(
                    flow=here(CO2_FOSSIL),
                    amount=row["metered_co2"] * scale,
                    unit=row.unit_of("metered_co2"),
                )
            ],
            provenance={**row.provenance, "source": "measured"},
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cement.py -v`
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add trailrunner/models/cement.py tests/test_cement.py
git commit -m "feat(models): answer past years from a meter, future years from the model"
```

---

### Task 5: Showcase parameter files

**Files:**
- Modify: `dev/build_showcase_params.py`
- Create (generated): `examples/cement_params.parquet`, `examples/cement_metered_params.parquet`
- Modify: `examples/showcase_models.py`

**Interfaces:**
- Consumes: the column names and units fixed in Tasks 3 and 4.
- Produces: `MODELS` in `examples/showcase_models.py` containing `CementPlant`, `MeteredCementPlant`, `GridElectricity`, `GasPower`, `NaturalGasOffshorePipelineTransport`. Task 6's notebook imports this list.

- [ ] **Step 1: Add the two writers**

In `dev/build_showcase_params.py`, after the existing DAC block, add:

```python
# --- Cement: the showcase's computed years. ---------------------------------
# CH/2030 sits exactly at the model's reference moisture and temperature, so
# its penalty is 1.0 and the numbers the showcase page quotes are the numbers
# in this table. That is deliberate: a reader checking the arithmetic should
# not have to apply a correction factor in their head on beat 1. RER and the
# 2040 rows are off reference, which is what makes the beat-1 sensitivity
# table show anything at all.
CEMENT_ROWS = [
    {"location": "CH", "time": 2030, "clinker_factor": 0.75, "fuel_demand": 3.3,
     "steam_demand": 0.34, "electricity_demand": 0.10,
     "moisture": 0.04, "temperature": 10.0},
    {"location": "CH", "time": 2040, "clinker_factor": 0.68, "fuel_demand": 3.1,
     "steam_demand": 0.31, "electricity_demand": 0.10,
     "moisture": 0.04, "temperature": 11.0},
    {"location": "RER", "time": 2030, "clinker_factor": 0.80, "fuel_demand": 3.5,
     "steam_demand": 0.40, "electricity_demand": 0.11,
     "moisture": 0.06, "temperature": 9.0},
    {"location": "RER", "time": 2040, "clinker_factor": 0.72, "fuel_demand": 3.3,
     "steam_demand": 0.36, "electricity_demand": 0.11,
     "moisture": 0.055, "temperature": 10.0},
]
CEMENT_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "clinker_factor", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "fuel_demand", "type": "number", "unit": "MJ", "iri": None},
    {"name": "steam_demand", "type": "number", "unit": "MJ", "iri": None},
    {"name": "electricity_demand", "type": "number", "unit": "kWh",
     "iri": "https://vocab.sentier.dev/parameters/electricity-demand"},
    {"name": "moisture", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "temperature", "type": "number", "unit": "degC",
     "iri": "https://vocab.sentier.dev/parameters/air-temperature"},
]

# --- Cement: the years a meter covered. -------------------------------------
# Eight years of stack CEMS and utility meters, normalised per 1000 kg of
# cement. The measured CO2 sits a little above what the model computes for a
# comparable year, which is the beat: a stack meter sees calcination and
# combustion as one plume and cannot separate them, and real kilns run above
# stoichiometry.
CEMENT_METERED_ROWS = [
    {"location": "CH", "time": 2018, "metered_fuel": 2810.0, "metered_steam": 410.0,
     "metered_electricity": 116.0, "metered_co2": 601.0},
    {"location": "CH", "time": 2019, "metered_fuel": 2775.0, "metered_steam": 404.0,
     "metered_electricity": 115.0, "metered_co2": 594.0},
    {"location": "CH", "time": 2020, "metered_fuel": 2740.0, "metered_steam": 399.0,
     "metered_electricity": 113.0, "metered_co2": 587.0},
    {"location": "CH", "time": 2021, "metered_fuel": 2702.0, "metered_steam": 396.0,
     "metered_electricity": 112.0, "metered_co2": 580.0},
    {"location": "CH", "time": 2022, "metered_fuel": 2661.0, "metered_steam": 391.0,
     "metered_electricity": 110.0, "metered_co2": 571.0},
    {"location": "CH", "time": 2023, "metered_fuel": 2610.0, "metered_steam": 385.0,
     "metered_electricity": 108.0, "metered_co2": 562.0},
    {"location": "CH", "time": 2024, "metered_fuel": 2560.0, "metered_steam": 372.0,
     "metered_electricity": 106.0, "metered_co2": 551.0},
    {"location": "CH", "time": 2025, "metered_fuel": 2518.0, "metered_steam": 364.0,
     "metered_electricity": 104.0, "metered_co2": 543.0},
]
CEMENT_METERED_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "metered_fuel", "type": "number", "unit": "MJ", "iri": None},
    {"name": "metered_steam", "type": "number", "unit": "MJ", "iri": None},
    {"name": "metered_electricity", "type": "number", "unit": "kWh", "iri": None},
    {"name": "metered_co2", "type": "number", "unit": "kg", "iri": None},
]
```

Then add the two `_write` calls beside the existing ones in `main`:

```python
    _write("cement_params", CEMENT_ROWS, CEMENT_FIELDS)
    _write("cement_metered_params", CEMENT_METERED_ROWS, CEMENT_METERED_FIELDS)
```

- [ ] **Step 2: Update the module docstring**

The docstring currently says "Nothing here invents a number: every row is copied from the notebook or the pipeline model's own module docstring." That stops being true with this task. Replace that sentence with:

```
The DAC, grid and gas-plant rows are copied from ``examples/dac.ipynb``, and
the pipeline rows from the reverse-engineered BAFU/ESU-services tier
constants. The two cement tables are illustrative: plausible figures for a
European plant, chosen so that the showcase's reference row lands exactly on
the model's reference conditions. What they demonstrate is the shape of the
data a model reads, not the performance of any real works.
```

- [ ] **Step 3: Build the parquets**

Run: `uv run python dev/build_showcase_params.py`
Expected: six paths printed, including the two new ones.

- [ ] **Step 4: Rewire the showcase model list**

In `examples/showcase_models.py`, replace the DAC import and parameter load with cement, and leave grid, gas and pipeline untouched:

```python
from trailrunner.models.cement import CementPlant, MeteredCementPlant

_cement_params = ParameterSet.from_parquet(
    _HERE / "cement_params.parquet", hierarchy=_HIERARCHY
)
_cement_metered_params = ParameterSet.from_parquet(
    _HERE / "cement_metered_params.parquet", hierarchy=_HIERARCHY
)

MODELS = [
    CementPlant(params=_cement_params),
    MeteredCementPlant(params=_cement_metered_params),
    GridElectricity(params=_grid_params),
    GasPower(params=_gas_params),
    NaturalGasOffshorePipelineTransport(params=_pipeline_params),
]
```

Update the module docstring's first line to name the cement, grid-electricity and pipeline-transport models. Leave the `dac_params.parquet` file on disk: `examples/dac.ipynb` still reads it.

- [ ] **Step 5: Verify the list loads and resolves both ways**

Run:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'examples')
from showcase_models import MODELS
from trailrunner.core.flow import Flow
from trailrunner.models.cement import CEMENT
from trailrunner.orchestration.glossary import Glossary
g = Glossary(MODELS)
for year in (2023, 2030):
    print(year, type(g.resolve(Flow(iri=CEMENT, location='CH', time=year))).__name__)
"
```

Expected: `2023 MeteredCementPlant` then `2030 CementPlant`.

- [ ] **Step 6: Commit**

```bash
git add dev/build_showcase_params.py examples/cement_params.parquet examples/cement_metered_params.parquet examples/showcase_models.py
git commit -m "feat(examples): add the cement parameter tables and wire them into MODELS"
```

---

### Task 6: Rewrite the showcase notebook

The notebook is the source of truth for every number on the docs page, so it is rewritten whole before anything is quoted from it.

**Files:**
- Modify: `examples/showcase.ipynb` (30 cells today)

**Interfaces:**
- Consumes: `MODELS` from Task 5, the constants from Tasks 3 and 4.
- Produces: an executed notebook whose figure cells keep the tags `figure:sankey`, `figure:curve`, `figure:contributions`, each assigning the variable the tag names. Task 7's asset builder finds cells by those tags and nothing else.

- [ ] **Step 1: Retitle and rewrite beat 1**

Cell 0 keeps its shape; the demand becomes 1000 kg of Portland cement in CH in 2030. Cells 3–6 become: build `CementPlant` from `examples/cement_params.parquet`, `apply` the demand, print the `Result`, then the sensitivity table. The table's columns become `where / when / moisture / degC / penalty / gas [MJ]`, driven by the four rows of `cement_params.parquet`.

- [ ] **Step 2: Rewrite beat 2**

Cells 8–11 keep the `Narrating(ResolutionChain)` subclass verbatim — only the demand it starts from changes. Re-run and let the pop trace be whatever it is; do not hand-edit the output.

- [ ] **Step 3: Rewrite beat 3**

Cells 13–17. `GasCHP` leaves for Task 9's notebook. In its place define a
monofunctional `HeatSupply` in the notebook, registered at the *parent*
concept, so the plant's `fi_1730_6` demand relaxes one step and is answered:

```python
GENERIC_HEAT = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730"


class HeatSupply(Model):
    """Generic steam and hot water, written here rather than shipped.

    Nothing in trailrunner produces fi_1730, and this model is not the point
    of the beat -- the skos:broader walk that reaches it is. Its efficiency is
    illustrative.
    """

    produces = [GENERIC_HEAT]
    supports = ALLOCATION_RULES

    EFFICIENCY = 0.85

    def apply(self, demand):
        gas = demand.amount / self.EFFICIENCY
        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(
                    flow=Flow(
                        iri=cement.NATURAL_GAS,
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=gas,
                    unit="MJ",
                )
            ],
            biosphere=[
                Exchange(
                    flow=Flow(
                        iri=cement.CO2_FOSSIL,
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=gas * cement.GAS_CO2_PER_MJ,
                    unit="kg",
                )
            ],
        )
```

Keep the `heat_node` inspection cell, repointing it from `dac.HEAT` to
`cement.STEAM`:

```python
heat_node = [node for node in report.nodes if node.demand.flow.iri == cement.STEAM][0]
```

Keep the construction-and-background-pack half unchanged except for the kiln
IRI.

- [ ] **Step 4: Replace beat 4 with the measured/modelled beat**

Cells 18–21 are replaced by one code cell and one markdown cell:

```python
def ask(year):
    demand = Demand(
        flow=Flow(iri=cement.CEMENT, location="CH", time=year),
        amount=1000.0,
        unit="kg",
    )
    return Orchestrator(ResolutionChain([ModelProvider(Glossary(MODELS))])).calculate(
        demand
    )


for year in (2023, 2030):
    report = ask(year)
    root = report.nodes[0]
    direct = [
        exchange
        for exchange in root.result.biosphere
        if exchange.flow.iri == cement.CO2_FOSSIL
    ]
    print(f"{year}  answered by {type(root.model).__name__}")
    print(f"      source: {root.result.provenance['source']}")
    print(f"      direct CO2: {sum(e.amount for e in direct):.1f} kg "
          f"in {len(direct)} exchange(s)")
```

The markdown cell below it makes the one point: a stack meter sees calcination
and combustion as one plume and cannot separate them, so the measured year
carries a single exchange and the modelled year carries two — and the report
records which kind of answer you got rather than leaving it to a convention.

If `root.model` or `root.result` is not how the report exposes the answering
model and its Result, read `trailrunner/core/report.py` and use whatever the
node actually carries; do not add an attribute to the library for the sake of
this cell.

- [ ] **Step 5: Rewrite beats 5 and 6**

Cells 22–29 change only in their prose. The dynamic curve is now all-positive — a construction pulse in 2026 and 2029, then the operating year — so the sentence describing it is rewritten. Keep the three figure cell tags exactly as they are.

- [ ] **Step 6: Execute the notebook top to bottom, offline**

Run:

```bash
env -u PYST_AUTH_TOKEN uv run --extra examples --extra viz --extra dynamic \
  jupyter nbconvert --to notebook --execute --inplace examples/showcase.ipynb
```

Expected: every cell runs, no network, no unhandled exception. If a label prints as a bare IRI, an IRI is missing from Task 1's cache — go back rather than working around it.

- [ ] **Step 7: Commit**

```bash
git add examples/showcase.ipynb
git commit -m "docs(showcase): re-base the notebook on a cement plant"
```

---

### Task 7: Regenerate the figures

**Files:**
- Modify (generated): `docs/assets/showcase/sankey.svg`, `curve.svg`, `contributions.svg`

**Interfaces:**
- Consumes: the tagged figure cells from Task 6.
- Produces: three SVGs that Task 8's page embeds.

- [ ] **Step 1: Run the asset builder**

Run:

```bash
uv run --extra examples --extra viz --extra dynamic python dev/build_showcase_assets.py
```

Expected: three paths printed under `docs/assets/showcase/`.

- [ ] **Step 2: Check the curve is all-positive**

Open `docs/assets/showcase/curve.svg` and confirm the cumulative line never goes below zero. If it does, a biosphere sign is wrong in Task 3 — the cement model emits, it does not remove — and that is a bug to fix there, not here.

- [ ] **Step 3: Commit**

```bash
git add docs/assets/showcase/
git commit -m "docs(showcase): regenerate the figures from the cement notebook"
```

---

### Task 8: Rewrite the tour page

**Files:**
- Modify: `docs/showcase.md`

**Interfaces:**
- Consumes: the executed notebook from Task 6 and the SVGs from Task 7.
- Produces: nothing downstream.

- [ ] **Step 1: Rewrite the lead and beats 1 to 3**

The demand line becomes **1000 kg of Portland cement, in Switzerland, in 2030.** Every `text` block is pasted from the executed notebook, not retyped. Beat 3's warning admonition is rewritten: `HeatSupply` is written in the notebook rather than shipped; `cement-kiln` is an invented IRI that the vocabulary answers 404 for, so it can never relax; the background pack still holds no electricity dataset, deliberately, and that paragraph stands unchanged.

- [ ] **Step 2: Write the new beat 4**

Title it "Some data is measured". It carries the two traces, the two CO2 figures, and the sentence the beat exists for. It ends by pointing at `docs/content/attribution.md` and `examples/coproduction.ipynb` for the allocation material that used to live at this position.

- [ ] **Step 3: Rewrite beats 5 and 6 and the closing list**

Beat 5's paragraph describing the curve is rewritten for an all-positive curve. In the closing "What this changes" list, replace the "A model can be a measurement" bullet's supporting sentence with the coverage mechanism, since it now has a beat of its own.

- [ ] **Step 4: Update the presenting note**

The `??? note "Presenting this"` block names beats by number and says what to cut first. Rewrite it for the new running order: beats 1, 2 and 4 are the argument; cut beat 6 first, then the second half of beat 3.

- [ ] **Step 5: Check every quoted number against the notebook**

Run:

```bash
uv run python -c "
import json, re
nb = json.load(open('examples/showcase.ipynb'))
outs = '\n'.join(
    ''.join(o.get('text', ''))
    for c in nb['cells'] for o in c.get('outputs', [])
)
page = open('docs/showcase.md').read()
for block in re.findall(r'\`\`\`text\n(.*?)\`\`\`', page, re.S):
    for line in block.strip().splitlines():
        if line.strip() and line.strip() not in outs:
            print('NOT IN NOTEBOOK:', line)
"
```

Expected: no output. Every line printed is a line that was typed rather than pasted.

- [ ] **Step 6: Commit**

```bash
git add docs/showcase.md
git commit -m "docs(showcase): re-base the tour on a cement plant"
```

---

### Task 9: The co-production notebook

**Files:**
- Create: `examples/coproduction.ipynb`

**Interfaces:**
- Consumes: `MODELS` from Task 5, and the `GasCHP` class lifted out of the old showcase notebook's beat 4.
- Produces: nothing downstream.

- [ ] **Step 1: Write the notebook**

Recover `GasCHP`, the `UnallocatedCoProduction` refusal, the economic and substitution runs, and the node's recorded allocation metadata from `git show HEAD~N:examples/showcase.ipynb` for the last commit before Task 6. Its opening markdown cell states in its own words that `GasCHP`'s efficiencies and prices are illustrative, and that what is demonstrated is the rule's effect on the answer, not the CHP. It does not inherit beat 3's disclaimer, which covered four separate things and only two of them apply here.

The demand it runs is the cement plant's steam demand, so the notebook picks up where the showcase's beat 3 leaves off: the generic supplier the showcase settles for is replaced here by a CHP that co-produces, and now a rule has to be chosen.

- [ ] **Step 2: Execute it offline**

Run:

```bash
env -u PYST_AUTH_TOKEN uv run --extra examples --extra viz --extra dynamic \
  jupyter nbconvert --to notebook --execute --inplace examples/coproduction.ipynb
```

Expected: runs clean, including the deliberate `UnallocatedCoProduction` which must be caught and printed rather than raised.

- [ ] **Step 3: Commit**

```bash
git add examples/coproduction.ipynb
git commit -m "docs(examples): move the co-production walkthrough to its own notebook"
```

---

### Task 10: Sweep the remaining references

**Files:**
- Modify: `README.md`, `docs/content/*.md` as the sweep finds them

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Find pages that describe the old showcase**

Run:

```bash
grep -rn "direct air capture\|DirectAirCapture\|captured from the air\|co2-from-air" \
  README.md docs/ --include="*.md" | grep -v "docs/api/"
```

Expected: a list. Each hit is either about `examples/dac.ipynb` — which is still true and stays — or about the showcase, which is now wrong.

- [ ] **Step 2: Fix only the showcase-describing hits**

`docs/api/models.md` documents `DirectAirCapture` as a library model and stays. `docs/content/writing_a_model.md`, `parameters.md`, `reports.md`, `assessment.md` and `attribution.md` use DAC as a teaching example; leave them unless they specifically claim the showcase runs it.

- [ ] **Step 3: Add the new model to the API docs**

Add `CementPlant` and `MeteredCementPlant` to `docs/api/models.md` beside the existing entries, following whatever mkdocstrings pattern that file already uses.

- [ ] **Step 4: Run the full suite one last time**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/
git commit -m "docs: point the remaining showcase references at the cement example"
```

---

## Notes for the executor

- **Task 1 needs network. Everything after it must run without any.** If you find yourself wanting a network call in Tasks 2 to 10, an IRI is missing from the cache and Task 1 is where to fix it.
- The spec claims `tests/test_cli.py` needs updating. It does not: its only DAC reference is a comment, and it builds its own `Boiler` model inline. No task touches it.
- `examples/dac_params.parquet` stays on disk even though `showcase_models.py` stops reading it. `examples/dac.ipynb` still does.
- Do not edit notebook output cells by hand at any point. Every number on the docs page has to be traceable to an execution, which is the whole reason the asset builder runs the notebook in a live kernel rather than parsing it.
