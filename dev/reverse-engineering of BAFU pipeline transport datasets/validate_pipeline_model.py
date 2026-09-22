"""Cross-check NaturalGasOffshorePipelineTransport against the parsed ecoinvent CSV.

Runs the model for all 14 locations at a unit (1 tkm) demand and compares
every technosphere/biosphere amount it produces against the corresponding
row in offshore_pipeline_exchanges.csv, which holds the real ecoinvent
values this model is trying to explain.
"""

import csv
from pathlib import Path

from trailrunner.core.flow import Demand, Flow
from trailrunner.params.parameter_set import ParameterSet

from trailrunner.models.natural_gas_pipeline_transport import (
    BUTANE,
    CARBON_DIOXIDE_FOSSIL,
    DOCUMENTED_LOCATIONS,
    ETHANE,
    FREIGHT_LORRY,
    HALON_1211,
    HFC_23,
    MERCURY,
    MINERAL_OIL_DISPOSAL,
    METHANE_FOSSIL,
    NATURAL_GAS_AT_PRODUCTION,
    NATURAL_GAS_BURNED_IN_GAS_TURBINE,
    NMVOC,
    PIPELINE_INFRASTRUCTURE,
    PROPANE,
    TRANSPORT,
    NaturalGasOffshorePipelineTransport,
)

HERE = Path(__file__).parent
ALL_LOCATIONS = ["AZ", "DZ", "GB", "ID", "IR", "IT", "LY", "MY", "NL", "NO", "QA", "RU", "UA", "US"]

CSV_NAME_TO_IRI = {
    "Disposal, used mineral oil, 10% water, to hazardous waste incineration": MINERAL_OIL_DISPOSAL,
    "Natural gas, at production": NATURAL_GAS_AT_PRODUCTION,
    "Natural gas, burned in gas turbine": NATURAL_GAS_BURNED_IN_GAS_TURBINE,
    "Pipeline, natural gas, long distance, high capacity, offshore": PIPELINE_INFRASTRUCTURE,
    "Transport, freight, lorry, 16t-32t gross weight, fleet average": FREIGHT_LORRY,
    "Transport, natural gas, offshore pipeline, long distance": TRANSPORT,
    "Butane": BUTANE,
    "Carbon dioxide, fossil": CARBON_DIOXIDE_FOSSIL,
    "Ethane": ETHANE,
    "Mercury": MERCURY,
    "Methane, bromochlorodifluoro-, Halon 1211": HALON_1211,
    "Methane, fossil": METHANE_FOSSIL,
    "Methane, trifluoro-, HFC-23": HFC_23,
    "NMVOC, non-methane volatile organic compounds, unspecified origin": NMVOC,
    "Propane": PROPANE,
}


def load_csv_values() -> dict[str, dict[str, float]]:
    """iri -> {location: amount}, parsed from offshore_pipeline_exchanges.csv."""
    values: dict[str, dict[str, float]] = {}
    with open(HERE / "offshore_pipeline_exchanges.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = None
    for row in rows:
        if not row or not row[0]:
            continue
        if row[0] == "exchange_name":
            header = row[1:]
            continue
        if row[0] == "non-common exchanges" or header is None:
            continue
        name = row[0]
        iri = CSV_NAME_TO_IRI.get(name)
        if iri is None:
            continue
        by_loc = {}
        for loc, cell in zip(header, row[1:]):
            if cell:
                by_loc[loc] = float(cell)
        values[iri] = by_loc
    return values


def run_model():
    params = ParameterSet.from_parquet(HERE / "natural_gas_pipeline_params.parquet")
    model = NaturalGasOffshorePipelineTransport(params=params)
    results = {}
    for loc in ALL_LOCATIONS:
        demand = Demand(flow=Flow(iri=TRANSPORT, location=loc, time=2025), amount=1.0, unit="tkm")
        result = model.apply(demand)
        by_iri = {e.flow.iri: e.amount for e in result.technosphere}
        by_iri.update({e.flow.iri: e.amount for e in result.biosphere})
        by_iri[TRANSPORT] = result.production[0].amount
        results[loc] = by_iri
    return results


def main():
    csv_values = load_csv_values()
    model_values = run_model()

    iri_to_name = {v: k for k, v in CSV_NAME_TO_IRI.items()}
    print(f"{'exchange':<45} {'loc':<4} {'model':>14} {'csv':>14} {'ratio':>10}")
    print("-" * 92)
    n_compared = 0
    n_within_5pct = 0
    for iri, name in iri_to_name.items():
        for loc in ALL_LOCATIONS:
            modeled = model_values.get(loc, {}).get(iri)
            actual = csv_values.get(iri, {}).get(loc)
            if modeled is None and actual is None:
                continue
            ratio = None if not modeled or not actual else modeled / actual
            if ratio is not None:
                n_compared += 1
                if 0.95 <= ratio <= 1.05:
                    n_within_5pct += 1
            ratio_str = "" if ratio is None else f"{ratio:.3f}"
            m_str = f"{modeled:.4e}" if modeled is not None else "  --  "
            a_str = f"{actual:.4e}" if actual is not None else "  --  "
            flag = "" if actual is not None else "  <- model computes, CSV has no row (AZ/IT/UA data gap)"
            print(f"{name:<45} {loc:<4} {m_str:>14} {a_str:>14} {ratio_str:>10}{flag}")
    print("-" * 92)
    print(f"{n_within_5pct}/{n_compared} location x exchange pairs within 5% of the CSV")
    print(f"model coverage: {sorted(DOCUMENTED_LOCATIONS)} ({len(DOCUMENTED_LOCATIONS)} of 14 locations)")


if __name__ == "__main__":
    main()
