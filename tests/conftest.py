import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

HEAT_DEMAND_IRI = "https://vocab.sentier.dev/parameters/heat-demand"
TEMPERATURE_IRI = "https://vocab.sentier.dev/parameters/air-temperature"
HUMIDITY_IRI = "https://vocab.sentier.dev/parameters/relative-humidity"


def write_parameter_parquet(path, rows, fields, nested=True):
    """Write a trailpack-compatible parquet file.

    ``rows`` is a list of dicts. ``fields`` is a list of
    ``{"name", "type", "unit", "iri"}`` dicts; ``unit`` and ``iri`` may be None.

    ``nested`` picks where the field list goes: under ``resource["schema"]``,
    which is what Frictionless specifies and what trailpack writes, or straight
    on the resource, which is the flatter shape hand-written tables often use.
    Both are read; the default is the one real files have.
    """
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
    resource = {"name": "parameters", "path": str(path)}
    if nested:
        resource["schema"] = {"fields": field_descriptors}
    else:
        resource["fields"] = field_descriptors
    datapackage = {"name": "test-parameters", "resources": [resource]}
    schema = table.schema.with_metadata(
        {"datapackage.json": json.dumps(datapackage).encode("utf-8")}
    )
    pq.write_table(table.cast(schema), path)
    return path


CO2_IRI = "https://vocab.sentier.dev/flows/co2-fossil"
CH4_IRI = "https://vocab.sentier.dev/flows/ch4-fossil"


def write_method_parquet(path, rows, fields):
    """Write a method parquet with the same embedded metadata trailpack writes."""
    return write_parameter_parquet(path, rows, fields)


@pytest.fixture
def method_parquet_file(tmp_path):
    """GWP100-shaped: a global CO2 factor, a regional CH4 one, both per kg."""
    path = tmp_path / "gwp100.parquet"
    rows = [
        {"flow_iri": CO2_IRI, "flow_unit": "kg", "location": "GLO", "cf": 1.0},
        {"flow_iri": CH4_IRI, "flow_unit": "kg", "location": "GLO", "cf": 29.8},
        {"flow_iri": CH4_IRI, "flow_unit": "kg", "location": "RER", "cf": 27.0},
    ]
    fields = [
        {"name": "flow_iri", "type": "string", "unit": None, "iri": None},
        {"name": "flow_unit", "type": "string", "unit": None, "iri": None},
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "cf", "type": "number", "unit": "kg CO2eq", "iri": None},
    ]
    write_method_parquet(path, rows, fields)
    return path


@pytest.fixture
def dac_parameter_file(tmp_path):
    """Two locations, two years each, so fallback and interpolation can be tested."""
    path = tmp_path / "dac_params.parquet"
    rows = [
        {"location": "CH", "time": 2020, "heat_demand": 6.0, "temperature": 9.0, "humidity": 0.75},
        {"location": "CH", "time": 2030, "heat_demand": 5.0, "temperature": 10.0, "humidity": 0.70},
        {"location": "RER", "time": 2020, "heat_demand": 6.6, "temperature": 11.0, "humidity": 0.68},
        {"location": "RER", "time": 2030, "heat_demand": 5.5, "temperature": 12.0, "humidity": 0.65},
    ]
    fields = [
        {"name": "location", "type": "string", "unit": None, "iri": None},
        {"name": "time", "type": "integer", "unit": "year", "iri": None},
        {"name": "heat_demand", "type": "number", "unit": "MJ", "iri": HEAT_DEMAND_IRI},
        {"name": "temperature", "type": "number", "unit": "degC", "iri": TEMPERATURE_IRI},
        {"name": "humidity", "type": "number", "unit": "dimensionless", "iri": HUMIDITY_IRI},
    ]
    write_parameter_parquet(path, rows, fields)
    return path
