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
all. Nothing here invents a number: every row is copied from the notebook or
the pipeline model's own module docstring.

Run: ``uv run python dev/build_showcase_params.py``
Writes: ``examples/dac_params.parquet``, ``examples/grid_electricity_params.parquet``,
``examples/gas_power_params.parquet``, ``examples/pipeline_transport_params.parquet``.
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
PIPELINE_ROWS = [
    {
        "location": location, "time": 2025, "tier": tier,
        "gas_density_kg_per_nm3": 0.735,
        **TIER_RATES[tier], **GENERIC_COMPOSITION, **GLOBAL_CONSTANTS,
    }
    for tier, locations in (("high", ["DZ", "RU"]), ("low", ["NO", "GB"]))
    for location in locations
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


def main() -> None:
    _write("dac_params", DAC_ROWS, DAC_FIELDS)
    _write("grid_electricity_params", GRID_ROWS, GRID_FIELDS)
    _write("gas_power_params", GAS_ROWS, GAS_FIELDS)
    _write("pipeline_transport_params", PIPELINE_ROWS, PIPELINE_FIELDS)


if __name__ == "__main__":
    main()
