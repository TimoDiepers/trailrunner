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
biosphere flow becomes `<iri-prefix><slugified name>/<slugified categories>` --
name *and* compartment, because ecoinvent has many same-named biosphere flows
in different compartments and a slug built from the name alone would collide
them into one row. Check the output against the IRIs your models actually emit
before trusting a number that comes out of it -- a CF attached to an IRI
nothing emits is silently no CF at all, which the Assessment will tell you
about in `uncharacterized`.

Check the **`flow_unit`** column too, not only `flow_iri`. Matching in
`Method.factor` is string equality in both, so a factor written for
`"kilogram"` against a model that emits `"kg"` is just as invisible as a
mismatched IRI. This script normalises the Brightway spellings it knows
(`UNIT_SPELLINGS` below) to the short forms trailrunner's models use, prints
every spelling it did not recognise, and leaves those untouched for you to
decide about. That normalisation happens once, here, at authoring time -- it
is not a runtime conversion, and nothing in `trailrunner.assessment` ever
converts between units.
"""

import argparse
import json
import re

import pyarrow as pa
import pyarrow.parquet as pq


UNIT_SPELLINGS = {
    "kilogram": "kg",
    "cubic meter": "m3",
    "cubic metre": "m3",
    "megajoule": "MJ",
    "kilowatt hour": "kWh",
    "square meter": "m2",
    "square metre": "m2",
    "ton": "tonne",
    "metric ton": "tonne",
}
"""Brightway's spellings -> the short forms trailrunner's models emit.

Authoring-time spelling normalisation, not unit conversion: every pair here
names one quantity twice. A unit this table does not know is left exactly as
it was and printed, because guessing at it is how a factor of 1000 gets into
a score.
"""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def flow_iri(prefix: str, flow) -> str:
    """`<prefix><name>/<compartment>`, so two compartments stay two flows.

    ecoinvent has "Carbon dioxide, fossil" in air, in water and in soil, among
    others, and they are not one flow. Dropping the compartment would make
    them one key -- and `Method` now raises on a duplicate key rather than
    keeping whichever row came last, so the collision would surface here as an
    error instead of as a wrong number later.
    """
    categories = "/".join(slug(part) for part in (flow.get("categories") or ()) if part)
    return f"{prefix}{slug(flow['name'])}" + (f"/{categories}" if categories else "")


def normalise_unit(unit: str, unknown: set) -> str:
    """The short spelling, or the original with a note for the operator."""
    mapped = UNIT_SPELLINGS.get(unit.strip().lower())
    if mapped is None:
        unknown.add(unit)
        return unit
    return mapped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--method", required=True, nargs="+")
    parser.add_argument("--iri-prefix", default="https://vocab.sentier.dev/flows/")
    parser.add_argument("--unit", default=None, help="score unit; read from the method if omitted")
    parser.add_argument(
        "--location",
        default="GLO",
        help="where these factors hold; 'GLO' unless the method is regional",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import bw2data as bd

    bd.projects.set_current(args.project)
    method = bd.Method(tuple(args.method))
    metadata = method.metadata
    unit = args.unit or metadata.get("unit", "unit")

    rows = []
    unknown_units: set[str] = set()
    for key, cf in method.load():
        flow = bd.get_node(key=key) if not isinstance(key, int) else bd.get_node(id=key)
        rows.append(
            {
                "flow_iri": flow_iri(args.iri_prefix, flow),
                "flow_unit": normalise_unit(flow.get("unit", "kg"), unknown_units),
                # The method's own geography, not the flow's: an LCIA method
                # states where its factors hold, and most state it globally.
                "location": args.location,
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
    if unknown_units:
        # Named rather than guessed at: matching is string equality, so an
        # unrecognised spelling means those factors quietly match nothing.
        print(
            "unrecognised flow units, written through unchanged -- check them "
            "against what your models emit: " + ", ".join(sorted(unknown_units))
        )


if __name__ == "__main__":
    main()
