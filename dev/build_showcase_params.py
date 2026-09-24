"""Build the parameter parquet files ``examples/showcase_models.py`` reads.

``examples/dac.ipynb`` writes its own DAC/grid/gas-plant parameter rows with
``trailpack`` into a temp directory, because that notebook's point is showing
the trailpack round trip. The CLI showcase has a different point -- a demand
runs against a committed set of models with no notebook and no trailpack
install -- so its parameters have to already exist as files in the repo.

This script writes exactly the rows the notebook demonstrates (DAC, grid
electricity, gas power) and the four representative pipeline-transport
countries from the reverse-engineered BAFU/ESU-services tier constants (see
``dev/reverse-engineering of BAFU pipeline transport datasets/README.md``),
using plain pyarrow with a hand-built ``datapackage.json`` -- the same
flatter shape ``tests/conftest.py``'s ``write_parameter_parquet`` writes, and
the shape ``ParameterSet.from_parquet`` reads without needing trailpack at
all.

The DAC, grid and gas-plant rows are copied from ``examples/dac.ipynb``, and
the pipeline rows from the reverse-engineered BAFU/ESU-services tier
constants. The two cement tables are illustrative: plausible figures for a
European works, chosen so that the showcase's reference row lands exactly on
the model's reference conditions. What they demonstrate is the shape of the
data a model reads, not the performance of any real plant.

Run: ``uv run python dev/build_showcase_params.py``
Writes: ``examples/dac_params.parquet``, ``examples/grid_electricity_params.parquet``,
``examples/gas_power_params.parquet``, ``examples/pipeline_transport_params.parquet``,
``examples/natural_gas_supply_params.parquet``,
``examples/natural_gas_extraction_params.parquet``,
``examples/cement_params.parquet``, ``examples/cement_metered_params.parquet``.
"""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

EXAMPLES = Path(__file__).parent.parent / "examples"


def _write(name: str, rows: list[dict], fields: list[dict]) -> Path:
    path = EXAMPLES / f"{name}.parquet"
    table = pa.Table.from_pylist(rows)
    field_descriptors = [
        {
            "name": field["name"],
            "type": field["type"],
            **({"unit": {"name": field["unit"]}} if field.get("unit") else {}),
            **({"rdfType": field["iri"]} if field.get("iri") else {}),
        }
        for field in fields
    ]
    datapackage = {
        "name": name,
        "resources": [
            {"name": name, "path": path.name, "schema": {"fields": field_descriptors}}
        ],
    }
    schema = table.schema.with_metadata(
        {"datapackage.json": json.dumps(datapackage).encode("utf-8")}
    )
    pq.write_table(table.cast(schema), path)
    print(path)
    return path


LOCATION_FIELD = {"name": "location", "type": "string", "unit": None, "iri": None}
TIME_FIELD = {"name": "time", "type": "integer", "unit": "year", "iri": None}


# --- DAC: examples/dac.ipynb's DAC_ROWS, verbatim. ---------------------------
DAC_ROWS = [
    {"location": "CH", "time": 2020, "heat_demand": 6.0, "electricity_demand": 0.50,
     "temperature": 9.0, "humidity": 0.75},
    {"location": "CH", "time": 2030, "heat_demand": 5.0, "electricity_demand": 0.40,
     "temperature": 10.0, "humidity": 0.70},
    {"location": "RER", "time": 2020, "heat_demand": 6.6, "electricity_demand": 0.55,
     "temperature": 11.0, "humidity": 0.68},
    {"location": "RER", "time": 2030, "heat_demand": 5.5, "electricity_demand": 0.45,
     "temperature": 12.0, "humidity": 0.65},
]
DAC_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "heat_demand", "type": "number", "unit": "MJ",
     "iri": "https://vocab.sentier.dev/parameters/heat-demand"},
    {"name": "electricity_demand", "type": "number", "unit": "kWh",
     "iri": "https://vocab.sentier.dev/parameters/electricity-demand"},
    {"name": "temperature", "type": "number", "unit": "degC",
     "iri": "https://vocab.sentier.dev/parameters/air-temperature"},
    {"name": "humidity", "type": "number", "unit": "dimensionless",
     "iri": "https://vocab.sentier.dev/parameters/relative-humidity"},
]

# --- Grid electricity: examples/dac.ipynb's GRID_ROWS, verbatim. -------------
GRID_ROWS = [
    {"location": "CH", "time": 2020, "share_gas": 0.06, "share_wind": 0.04,
     "share_hydro": 0.90, "grid_loss": 0.070},
    {"location": "CH", "time": 2030, "share_gas": 0.02, "share_wind": 0.18,
     "share_hydro": 0.80, "grid_loss": 0.060},
    {"location": "RER", "time": 2020, "share_gas": 0.50, "share_wind": 0.30,
     "share_hydro": 0.20, "grid_loss": 0.080},
    {"location": "RER", "time": 2030, "share_gas": 0.25, "share_wind": 0.55,
     "share_hydro": 0.20, "grid_loss": 0.070},
    # Denmark, where the showcase's works sits. Given its own rows rather than
    # left to fall back to RER: a Danish kilowatt hour is most of the way to
    # wind already, and answering it with a European average would put a
    # visibly wrong number under the one demand the whole tour is about.
    {"location": "DK", "time": 2020, "share_gas": 0.20, "share_wind": 0.56,
     "share_hydro": 0.24, "grid_loss": 0.060},
    {"location": "DK", "time": 2030, "share_gas": 0.08, "share_wind": 0.80,
     "share_hydro": 0.12, "grid_loss": 0.055},
]
GRID_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "share_gas", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "share_wind", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "share_hydro", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "grid_loss", "type": "number", "unit": "dimensionless", "iri": None},
]

# --- Gas power plant: examples/dac.ipynb's GAS_ROWS, verbatim. No CH row --
# on purpose, exactly as the notebook's comment says: the plant parameters
# are European, and the lookup borrows through the hierarchy and says so.
GAS_ROWS = [
    {"location": "RER", "time": 2020, "efficiency": 0.55, "co2_factor": 0.056},
    {"location": "RER", "time": 2030, "efficiency": 0.62, "co2_factor": 0.056},
]
GAS_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "efficiency", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "co2_factor", "type": "number", "unit": "kg", "iri": None},
]

# --- Pipeline transport: examples/dac.ipynb section 10's four representative
# countries and Tab. 4.4/4.6/3.1/4.7 tier constants, verbatim. -----------------
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
PIPELINE_YEARS = (2018, 2025, 2050)
"""2025 is the source's own year; the other two exist so a lookup resolves.

The tier constants carry no time dimension in Bussa et al. -- one leakage
rate and one compressor-energy figure per tier, full stop -- so the outer
years are the 2025 values repeated, which states that absence rather than
inventing a trend. Without them a demand for gas transport in any other year
falls out of the table entirely: ``ParameterSet`` interpolates between
bracketing rows and refuses to extrapolate past the last one, which is the
behaviour that should not be worked around with a fake gradient.
"""
PIPELINE_ROWS = [
    {
        "location": location, "time": year, "tier": tier,
        "gas_density_kg_per_nm3": 0.735,
        **TIER_RATES[tier], **GENERIC_COMPOSITION, **GLOBAL_CONSTANTS,
    }
    for tier, locations in (("high", ["DZ", "RU"]), ("low", ["NO", "GB"]))
    for location in locations
    for year in PIPELINE_YEARS
]
PIPELINE_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "tier", "type": "string", "unit": None, "iri": None},
    {"name": "gas_density_kg_per_nm3", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "leakage_rate_per_1000km", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "gas_turbine_mj_per_tkm", "type": "number", "unit": "MJ/tkm", "iri": None},
    {"name": "ch4_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "c2h6_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "c3h8_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "c4h10_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "co2_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "hg_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "nmvoc_frac", "type": "number", "unit": "kg/Nm3", "iri": None},
    {"name": "infra_factor", "type": "number", "unit": "unit/tkm", "iri": None},
    {"name": "lorry_factor", "type": "number", "unit": "tkm/tkm", "iri": None},
    {"name": "mineral_oil_disposal_factor", "type": "number", "unit": "kg/tkm", "iri": None},
    {"name": "halon1211_rate_kg_per_tkm", "type": "number", "unit": "kg/tkm", "iri": None},
    {"name": "hfc23_rate_kg_per_tkm", "type": "number", "unit": "kg/tkm", "iri": None},
]


# --- Natural gas supply: which field the gas comes from, and how far. --------
# Illustrative routes, chosen because they are the ones that make the pipeline
# model's tier split visible: Danish gas lands from the Norwegian shelf, a
# short low-leakage leg, and the European average arrives from Russia, four
# times as far and in the high-leakage tier. Energy content and density are
# pipeline-quality gas (the density is the one the BAFU tier table uses).
SUPPLY_ROWS = [
    {"location": "DK", "time": 2020, "origin": "NO", "transport_distance_km": 1000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
    {"location": "DK", "time": 2050, "origin": "NO", "transport_distance_km": 1000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
    {"location": "RER", "time": 2020, "origin": "RU", "transport_distance_km": 4000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
    {"location": "RER", "time": 2050, "origin": "RU", "transport_distance_km": 4000.0,
     "energy_content_mj_per_nm3": 36.0, "gas_density_kg_per_nm3": 0.735},
]
SUPPLY_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "origin", "type": "string", "unit": None, "iri": None},
    {"name": "transport_distance_km", "type": "number", "unit": "km", "iri": None},
    {"name": "energy_content_mj_per_nm3", "type": "number", "unit": "MJ/Nm3", "iri": None},
    {"name": "gas_density_kg_per_nm3", "type": "number", "unit": "kg/Nm3", "iri": None},
]

# --- Natural gas extraction: the two flows a field cannot avoid. -------------
# Rows for the two origins SUPPLY_ROWS names, since neither NO nor RU has a
# parent in the showcase's location hierarchy to fall back to. Illustrative
# factors: the CO2 is flaring, venting and compressor fuel together, and the
# extracted volume exceeds the delivered one because the field runs on some of
# its own gas. The Russian figures are the higher pair, and the 2050 rows the
# lower, which is a stated assumption about where field practice is going --
# not a measurement.
EXTRACTION_ROWS = [
    {"location": "NO", "time": 2020, "co2_kg_per_nm3": 0.075, "extracted_nm3_per_nm3": 1.02},
    {"location": "NO", "time": 2050, "co2_kg_per_nm3": 0.055, "extracted_nm3_per_nm3": 1.02},
    {"location": "RU", "time": 2020, "co2_kg_per_nm3": 0.110, "extracted_nm3_per_nm3": 1.05},
    {"location": "RU", "time": 2050, "co2_kg_per_nm3": 0.090, "extracted_nm3_per_nm3": 1.05},
]
EXTRACTION_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "co2_kg_per_nm3", "type": "number", "unit": "kg", "iri": None},
    {"name": "extracted_nm3_per_nm3", "type": "number", "unit": "Nm3", "iri": None},
]


# --- Cement: the showcase's computed years. ---------------------------------
# DK/2030 sits exactly at the model's reference moisture and temperature, so
# its penalty is 1.0 and the numbers the showcase page quotes are the numbers
# in this table. That is deliberate: a reader checking the arithmetic should
# not have to apply a correction factor in their head on beat 1. RER and the
# 2040 rows are off reference, which is what makes the beat-1 sensitivity
# table show anything at all.
CEMENT_ROWS = [
    {"location": "DK", "time": 2030, "clinker_factor": 0.75, "fuel_demand": 3.3,
     "lime_demand": 0.010, "electricity_demand": 0.10,
     "moisture": 0.04, "temperature": 10.0},
    {"location": "DK", "time": 2040, "clinker_factor": 0.68, "fuel_demand": 3.1,
     "lime_demand": 0.010, "electricity_demand": 0.10,
     "moisture": 0.04, "temperature": 11.0},
    {"location": "RER", "time": 2030, "clinker_factor": 0.80, "fuel_demand": 3.5,
     "lime_demand": 0.012, "electricity_demand": 0.11,
     "moisture": 0.06, "temperature": 9.0},
    {"location": "RER", "time": 2040, "clinker_factor": 0.72, "fuel_demand": 3.3,
     "lime_demand": 0.012, "electricity_demand": 0.11,
     "moisture": 0.055, "temperature": 10.0},
]
CEMENT_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "clinker_factor", "type": "number", "unit": "dimensionless", "iri": None},
    {"name": "fuel_demand", "type": "number", "unit": "MJ", "iri": None},
    {"name": "lime_demand", "type": "number", "unit": "kg", "iri": None},
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
    {"location": "DK", "time": 2018, "metered_fuel": 2810.0, "metered_lime": 11.7,
     "metered_electricity": 116.0, "metered_co2": 601.0},
    {"location": "DK", "time": 2019, "metered_fuel": 2775.0, "metered_lime": 11.5,
     "metered_electricity": 115.0, "metered_co2": 594.0},
    {"location": "DK", "time": 2020, "metered_fuel": 2740.0, "metered_lime": 11.4,
     "metered_electricity": 113.0, "metered_co2": 587.0},
    {"location": "DK", "time": 2021, "metered_fuel": 2702.0, "metered_lime": 11.3,
     "metered_electricity": 112.0, "metered_co2": 580.0},
    {"location": "DK", "time": 2022, "metered_fuel": 2661.0, "metered_lime": 11.2,
     "metered_electricity": 110.0, "metered_co2": 571.0},
    {"location": "DK", "time": 2023, "metered_fuel": 2610.0, "metered_lime": 11.0,
     "metered_electricity": 108.0, "metered_co2": 562.0},
    {"location": "DK", "time": 2024, "metered_fuel": 2560.0, "metered_lime": 10.6,
     "metered_electricity": 106.0, "metered_co2": 551.0},
    {"location": "DK", "time": 2025, "metered_fuel": 2518.0, "metered_lime": 10.4,
     "metered_electricity": 104.0, "metered_co2": 543.0},
]
CEMENT_METERED_FIELDS = [
    LOCATION_FIELD,
    TIME_FIELD,
    {"name": "metered_fuel", "type": "number", "unit": "MJ", "iri": None},
    {"name": "metered_lime", "type": "number", "unit": "kg", "iri": None},
    {"name": "metered_electricity", "type": "number", "unit": "kWh", "iri": None},
    {"name": "metered_co2", "type": "number", "unit": "kg", "iri": None},
]


def main() -> None:
    _write("dac_params", DAC_ROWS, DAC_FIELDS)
    _write("grid_electricity_params", GRID_ROWS, GRID_FIELDS)
    _write("gas_power_params", GAS_ROWS, GAS_FIELDS)
    _write("pipeline_transport_params", PIPELINE_ROWS, PIPELINE_FIELDS)
    _write("natural_gas_supply_params", SUPPLY_ROWS, SUPPLY_FIELDS)
    _write("natural_gas_extraction_params", EXTRACTION_ROWS, EXTRACTION_FIELDS)
    _write("cement_params", CEMENT_ROWS, CEMENT_FIELDS)
    _write("cement_metered_params", CEMENT_METERED_ROWS, CEMENT_METERED_FIELDS)


if __name__ == "__main__":
    main()
