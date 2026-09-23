"""Write a trailrunner method parquet from a Brightway LCIA method.

Run by hand, once, per method. trailrunner never imports bw2data: the point of
the parquet is that the method travels with the study rather than living in
someone's local project directory.

    uv run --extra brightway python dev/convert_brightway_method.py \
        --project ecoinvent-3.10 \
        --method "EF v3.1" "climate change" "global warming potential (GWP100)" \
        --iri-prefix https://vocab.sentier.dev/flows/ \
        --out gwp100.parquet

Flow identity is the hard part and is deliberately dumb here: each Brightway
biosphere flow becomes `<iri-prefix><slugified name>`. Check the output against
the IRIs your models actually emit before trusting a number that comes out of
it -- a CF attached to an IRI nothing emits is silently no CF at all, which the
Assessment will tell you about in `uncharacterized`.
"""

import argparse
import json
import re

import pyarrow as pa
import pyarrow.parquet as pq


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--method", required=True, nargs="+")
    parser.add_argument("--iri-prefix", default="https://vocab.sentier.dev/flows/")
    parser.add_argument("--unit", default=None, help="score unit; read from the method if omitted")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import bw2data as bd

    bd.projects.set_current(args.project)
    method = bd.Method(tuple(args.method))
    metadata = method.metadata
    unit = args.unit or metadata.get("unit", "unit")

    rows = []
    for key, cf in method.load():
        flow = bd.get_node(key=key) if not isinstance(key, int) else bd.get_node(id=key)
        rows.append(
            {
                "flow_iri": f"{args.iri_prefix}{slug(flow['name'])}",
                "flow_unit": flow.get("unit", "kg"),
                "location": "GLO",
                "cf": float(cf),
            }
        )

    table = pa.Table.from_pylist(rows)
    datapackage = {
        "name": " | ".join(args.method),
        "resources": [
            {
                "name": "method",
                "path": args.out,
                "schema": {
                    "fields": [
                        {"name": "flow_iri", "type": "string"},
                        {"name": "flow_unit", "type": "string"},
                        {"name": "location", "type": "string"},
                        {"name": "cf", "type": "number", "unit": {"name": unit}},
                    ]
                },
            }
        ],
    }
    schema = table.schema.with_metadata(
        {"datapackage.json": json.dumps(datapackage).encode("utf-8")}
    )
    pq.write_table(table.cast(schema), args.out)
    print(f"wrote {len(rows)} factors to {args.out} (unit: {unit})")


if __name__ == "__main__":
    main()
