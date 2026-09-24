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

Check the **`flow_unit`** column too, not only `flow_iri`. `Method` refuses to
construct at all if a row's `flow_unit` is not a vocabulary IRI the catalog
confirms, so a factor written for Brightway's `"kilogram"` against a model
that emits the `KG` IRI would otherwise be an outright construction error, not
a quietly empty score. This script maps the Brightway spellings it knows
(`UNIT_SPELLINGS` below) to the vocabulary IRIs trailrunner's models emit, and
fails the whole conversion -- naming every spelling it did not recognise --
rather than writing an unmapped spelling through. That mapping happens once,
here, at authoring time -- it is not a runtime conversion, and nothing in
`trailrunner.assessment` ever converts between units.
"""

import argparse
import json
import re

import pyarrow as pa
import pyarrow.parquet as pq

from trailrunner.core.units import KG, KWH, M3, MJ, TONNE

SQUARE_METRE = "https://vocab.sentier.dev/units/unit/M2"
"""Not a constant in ``trailrunner.core.units`` -- confirmed to exist in the
vocabulary (``GET /api/v1/concepts/...M2`` -> 200) but not yet bundled there,
so it lives here rather than being added speculatively."""

UNIT_SPELLINGS = {
    "kilogram": KG,
    "cubic meter": M3,
    "cubic metre": M3,
    "megajoule": MJ,
    "kilowatt hour": KWH,
    "square meter": SQUARE_METRE,
    "square metre": SQUARE_METRE,
    "ton": TONNE,
    "metric ton": TONNE,
}
"""Brightway's spellings -> the vocabulary IRIs trailrunner's models emit.

Authoring-time spelling normalisation, not unit conversion: every pair here
names one quantity twice. A unit this table does not know is not written
through -- it is collected and the conversion fails, naming every spelling it
could not map, because guessing at it is how a factor of 1000 gets into a
score in a method file that looks perfectly valid.
"""

CO2_EQ_MASS_UNITS = {"kg co2-eq", "kg co2 eq", "kg co2eq", "kg co2-equivalent"}
"""Brightway metadata spellings of "a mass of CO2-equivalent", read case- and
punctuation-loosely. The only metadata unit this script will turn into an IRI
on its own; anything else needs ``--unit``."""


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
    """The vocabulary IRI for a known Brightway spelling.

    An unmapped spelling is recorded in ``unknown`` and returned unchanged --
    still not an IRI -- so that a single pass over every flow in the method
    can collect every spelling that needs a decision before ``check_units``
    fails the whole conversion in one message, rather than stopping at the
    first row.
    """
    mapped = UNIT_SPELLINGS.get(unit.strip().lower())
    if mapped is None:
        unknown.add(unit)
        return unit
    return mapped


def check_units(unknown: set) -> None:
    """Fail the conversion, naming every unmapped spelling at once.

    Writing an unmapped spelling through used to be the quiet failure: a
    method's ``flow_unit`` that matches no model's ``KG``-style IRI is now not
    a small number, it is ``Method`` refusing to construct at all -- so this
    stops it here instead, before anything is written, with the full list.
    """
    if not unknown:
        return
    raise ValueError(
        "unrecognised flow units, not written -- add them to UNIT_SPELLINGS "
        "in this script or convert this method by hand: " + ", ".join(sorted(unknown))
    )


def resolve_score_unit(unit_arg: str | None, metadata_unit: str) -> str:
    """The IRI to write into the ``cf`` column's metadata.

    An explicit ``--unit`` is trusted as the IRI it is asked to be. Failing
    that, the only guess this script makes on its own is a CO2-eq mass --
    Brightway's own convention for climate change methods -- because a wrong
    default here silently mislabels every score the method ever produces.
    Anything else needs a human to say what the number means.
    """
    if unit_arg:
        if not unit_arg.startswith("http"):
            raise ValueError(f"--unit must be a unit IRI, got {unit_arg!r}")
        return unit_arg
    if metadata_unit.strip().lower() in CO2_EQ_MASS_UNITS:
        return KG
    raise ValueError(
        f"the method's metadata unit is {metadata_unit!r}, which trailrunner "
        "cannot turn into a unit IRI on its own; pass --unit IRI (e.g. "
        f"--unit {KG})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--method", required=True, nargs="+")
    parser.add_argument("--iri-prefix", default="https://vocab.sentier.dev/flows/")
    parser.add_argument(
        "--unit",
        default=None,
        help=(
            "score unit, as a vocabulary IRI; defaulted to KG when the "
            "method's metadata unit is a CO2-eq mass, otherwise required"
        ),
    )
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
    unit = resolve_score_unit(args.unit, metadata.get("unit", ""))

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
    check_units(unknown_units)

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
