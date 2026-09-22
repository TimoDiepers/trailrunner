"""Build the trailpack for NaturalGasOffshorePipelineTransport.

Source: ESU-services (Bussa et al. 2025), "Life cycle inventories of
long-distance transport and distribution of natural gas", in
`data/raw/BAFU-2026 v1 LCI Reports/2025 - LCI long-dist. transp. and
distrib. natural gas - Bussa.pdf`. This supersedes an earlier attempt at
this trailpack grounded in the 2007 ecoinvent report (Faist Emmenegger et
al.), whose chapter-7 per-country distance formula turned out not to match
the real corpus at all -- this 2025 report is the actual methodology behind
`database/offshore_pipeline_exchanges.csv`.

Key finding: there is no per-country distance term in this process. Every
country is classified into one of two regional tiers, and the functional
unit is 1 tkm (a tonne of gas moved one km) -- distance is whatever the
downstream demand asks for in tkm, not something this process computes
itself. Tab. 4.4/4.6 ("This study" column):

    tier "high" (FSU, Middle East, Africa, Asia, Latin America):
        compressor energy use   2.2 % per 1000 km
        pipeline leakage rate   0.204 % per 1000 km
    tier "low" (Europe/RER, North America/RNA):
        compressor energy use   0.9 % per 1000 km
        pipeline leakage rate   0.019 % per 1000 km

Tier assignment for the 14 locations in the raw corpus, by real-world
geography (matches the report's regional groupings in Tab. 2.5/2.6, where
Ukraine is grouped with Europe/RER despite its Soviet history):
    high: AZ, DZ, ID, IR, LY, MY, QA, RU
    low:  GB, IT, NL, NO, UA, US
This reproduces the CSV's two-value clustering for every one of the 14
locations exactly -- confirmation that tier, not distance, is what the raw
corpus actually varies by.

Formula, validated against Tab. 4.7 ("Algerian natural gas transport",
tier "high") and cross-checked against the parsed CSV for the tier "low"
locations:

    leaked_volume_nm3_per_tkm = leakage_rate_per_1000km / gas_density
        e.g. high tier: 0.00204 / 0.735 = 0.0027755 Nm3/tkm
             -- matches CSV's DZ "Natural gas, at production" (0.0027755)
                and the report's own Tab. 4.7 value (2.78E-03) exactly.
    biosphere_substance_kg_per_tkm = leaked_volume_nm3_per_tkm * generic_composition_kg_per_nm3
        -- reproduces CH4, Hg exactly and the rest within ~1-9% (Tab. 3.1's
           generic composition, applied identically to every country per
           the report's own stated simplification, not a country-specific
           composition as the 2007 report used).

"Natural gas, burned in gas turbine" (MJ/tkm) could not be independently
re-derived from calorific-value primitives in the extracted text within
reasonable effort, so its two tier values are taken directly: the high-tier
figure from the report's own Tab. 4.7 (0.795, Algeria), and the low-tier
figure from the parsed CSV (0.32733, GB/NL/NO/US/IT/UA -- these six are
identical in the CSV, consistent with a single tier-level constant). Their
ratio (2.43) is close to the documented energy-rate ratio (2.2/0.9 = 2.44),
consistent with -- but not a from-scratch derivation of -- the same
tier split.

Global constants (same for every location, ch. 4.2.2.3 and Tab. 4.7):
    infra_factor                  1.78e-09 unit/tkm  (offshore pipeline, GLO)
    lorry_factor                  1.16e-07 tkm/tkm    (construction-material transport)
    mineral_oil_disposal_factor   1.16e-06 kg/tkm      (Hg-laden condensate disposal)
    halon1211_rate_kg_per_tkm     2.24e-09 kg/tkm      (compressor-station refrigerant)
    hfc23_rate_kg_per_tkm         8.95e-08 kg/tkm      (compressor-station refrigerant)

Generic gas composition and density (Tab. 3.1, SWISSGAS 2019 / Schori 2012)
-- explicitly used identically for every country of origin in this study:
    ch4=0.6629  c2h6=0.0549  c3h8=0.0124  c4h10=0.0064
    co2=0.0229  hg=1.00e-8   nmvoc=0.0005  density=0.735 kg/Nm3
"""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SOURCE = "ESU-services, Bussa et al. 2025, 'LCI of long-distance transport and distribution of natural gas' (Tab. 3.1, 4.4, 4.6, 4.7)"

HIGH_TIER_LOCATIONS = ["AZ", "DZ", "ID", "IR", "LY", "MY", "QA", "RU"]
LOW_TIER_LOCATIONS = ["GB", "IT", "NL", "NO", "UA", "US"]

TIER_RATES = {
    "high": {"energy_rate_per_1000km": 0.022, "leakage_rate_per_1000km": 0.00204, "gas_turbine_mj_per_tkm": 0.795},
    "low": {"energy_rate_per_1000km": 0.009, "leakage_rate_per_1000km": 0.00019, "gas_turbine_mj_per_tkm": 0.32733},
}

GENERIC_COMPOSITION = {
    "ch4_frac": 0.6629, "c2h6_frac": 0.0549, "c3h8_frac": 0.0124, "c4h10_frac": 0.0064,
    "co2_frac": 0.0229, "hg_frac": 1e-8, "nmvoc_frac": 0.0005,
}
GENERIC_DENSITY = 0.735

GLOBAL_CONSTANTS = {
    "infra_factor": 1.78e-9,
    "lorry_factor": 1.16e-7,
    "mineral_oil_disposal_factor": 1.16e-6,
    "halon1211_rate_kg_per_tkm": 2.24e-9,
    "hfc23_rate_kg_per_tkm": 8.95e-8,
}


def build_rows() -> list[dict]:
    rows = []
    for tier, locations in (("high", HIGH_TIER_LOCATIONS), ("low", LOW_TIER_LOCATIONS)):
        for location in locations:
            row = {
                "location": location, "time": 2025, "tier": tier,
                "gas_density_kg_per_nm3": GENERIC_DENSITY,
                **TIER_RATES[tier],
                **GENERIC_COMPOSITION,
                **GLOBAL_CONSTANTS,
                "source": SOURCE,
            }
            rows.append(row)
    return rows


FIELDS = [
    {"name": "location", "type": "string", "unit": None},
    {"name": "time", "type": "integer", "unit": "year"},
    {"name": "tier", "type": "string", "unit": None},
    {"name": "gas_density_kg_per_nm3", "type": "number", "unit": "kg/Nm3"},
    {"name": "energy_rate_per_1000km", "type": "number", "unit": "dimensionless"},
    {"name": "leakage_rate_per_1000km", "type": "number", "unit": "dimensionless"},
    {"name": "gas_turbine_mj_per_tkm", "type": "number", "unit": "MJ/tkm"},
    {"name": "ch4_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "c2h6_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "c3h8_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "c4h10_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "co2_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "hg_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "nmvoc_frac", "type": "number", "unit": "kg/Nm3"},
    {"name": "infra_factor", "type": "number", "unit": "unit/tkm"},
    {"name": "lorry_factor", "type": "number", "unit": "tkm/tkm"},
    {"name": "mineral_oil_disposal_factor", "type": "number", "unit": "kg/tkm"},
    {"name": "halon1211_rate_kg_per_tkm", "type": "number", "unit": "kg/tkm"},
    {"name": "hfc23_rate_kg_per_tkm", "type": "number", "unit": "kg/tkm"},
    {"name": "source", "type": "string", "unit": None},
]


def write_parameter_parquet(path: Path, rows: list[dict], fields: list[dict]) -> Path:
    """Write a trailpack-compatible parquet file (schema + embedded datapackage.json)."""
    table = pa.Table.from_pylist(rows)
    datapackage = {
        "name": "natural-gas-pipeline-transport-params",
        "resources": [
            {
                "name": "parameters",
                "path": str(path),
                "fields": [
                    {
                        "name": field["name"],
                        "type": field["type"],
                        **({"unit": {"name": field["unit"]}} if field.get("unit") else {}),
                    }
                    for field in fields
                ],
            }
        ],
    }
    schema = table.schema.with_metadata(
        {"datapackage.json": json.dumps(datapackage).encode("utf-8")}
    )
    pq.write_table(table.cast(schema), path)
    return path


if __name__ == "__main__":
    out_path = Path(__file__).parent / "natural_gas_pipeline_params.parquet"
    rows = build_rows()
    write_parameter_parquet(out_path, rows, FIELDS)
    print(f"wrote {out_path} ({len(rows)} rows)")
