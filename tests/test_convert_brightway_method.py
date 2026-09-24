"""The offline Brightway converter's two silent-wrong-answer traps.

The script itself needs ``bw2data`` to run, but the two functions that decide
what ends up in the file are pure and importable without it. They are the two
places a converted method goes quietly wrong: a flow identity that collides
two different flows, and a unit spelling that matches nothing.
"""

import importlib.util
from pathlib import Path

import pytest

from trailrunner.assessment import Method
from trailrunner.core.errors import DuplicateFactor

from .conftest import write_method_parquet
from trailrunner.core.units import KG

SCRIPT = Path(__file__).resolve().parent.parent / "dev" / "convert_brightway_method.py"


def load_converter():
    spec = importlib.util.spec_from_file_location("convert_brightway_method", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


converter = load_converter()


def test_the_compartment_is_part_of_the_flow_identity():
    """ecoinvent has many same-named biosphere flows in different
    compartments, and they are not one flow. A slug built from the name alone
    collides them."""
    air = converter.flow_iri(
        "https://vocab.sentier.dev/flows/",
        {"name": "Carbon dioxide, fossil", "categories": ("air", "urban air close to ground")},
    )
    water = converter.flow_iri(
        "https://vocab.sentier.dev/flows/",
        {"name": "Carbon dioxide, fossil", "categories": ("water",)},
    )
    assert air != water
    assert air == "https://vocab.sentier.dev/flows/carbon-dioxide-fossil/air/urban-air-close-to-ground"
    assert water == "https://vocab.sentier.dev/flows/carbon-dioxide-fossil/water"


def test_a_flow_with_no_compartment_keeps_the_bare_slug():
    assert (
        converter.flow_iri("https://x/", {"name": "Carbon dioxide, fossil"})
        == "https://x/carbon-dioxide-fossil"
    )


def test_brightway_unit_spellings_are_normalised_to_what_models_emit():
    """Matching is string equality, so a method written for ``"kilogram"``
    against models that emit ``"kg"`` matches nothing at all — an honest but
    guaranteed-empty score on first use."""
    unknown: set[str] = set()
    assert converter.normalise_unit("kilogram", unknown) == "kg"
    assert converter.normalise_unit("cubic meter", unknown) == "m3"
    assert converter.normalise_unit("megajoule", unknown) == "MJ"
    assert converter.normalise_unit("kilowatt hour", unknown) == "kWh"
    assert converter.normalise_unit("square meter", unknown) == "m2"
    assert converter.normalise_unit("ton", unknown) == "tonne"
    assert converter.normalise_unit("metric ton", unknown) == "tonne"
    assert unknown == set()


def test_an_unrecognised_unit_is_left_alone_and_named():
    """Guessing at it is how a factor of 1000 gets into a score; the operator
    gets told instead."""
    unknown: set[str] = set()
    assert converter.normalise_unit("becquerel", unknown) == "becquerel"
    assert unknown == {"becquerel"}


def test_two_rows_with_one_key_raise_rather_than_last_wins(tmp_path):
    """The converter used to build both of these rows from one name, and
    ``Method`` used to keep whichever came last -- a wrong CF that showed up
    nowhere."""
    path = tmp_path / "collided.parquet"
    write_method_parquet(
        path,
        [
            {
                "flow_iri": "https://x/carbon-dioxide-fossil",
                "flow_unit": KG,
                "location": "GLO",
                "cf": 1.0,
            },
            {
                "flow_iri": "https://x/carbon-dioxide-fossil",
                "flow_unit": KG,
                "location": "GLO",
                "cf": 0.0,
            },
        ],
        [
            {"name": "flow_iri", "type": "string", "unit": None, "iri": None},
            {"name": "flow_unit", "type": "string", "unit": None, "iri": None},
            {"name": "location", "type": "string", "unit": None, "iri": None},
            {"name": "cf", "type": "number", "unit": KG, "iri": None},
        ],
    )
    with pytest.raises(DuplicateFactor):
        Method.from_parquet(path)
