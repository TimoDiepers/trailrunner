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
from trailrunner.core.units import KG, KWH, M3, MJ, SQUARE_METRE, TONNE, default_catalog

from .conftest import write_method_parquet

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


def test_brightway_unit_spellings_are_normalised_to_vocabulary_iris():
    """``Method`` refuses to construct on a ``flow_unit`` that is not a
    vocabulary IRI it can confirm, so a method written for Brightway's
    ``"kilogram"`` needs the IRI, not the short form ``"kg"``."""
    unknown: set[str] = set()
    assert converter.normalise_unit("kilogram", unknown) == KG
    assert converter.normalise_unit("cubic meter", unknown) == M3
    assert converter.normalise_unit("megajoule", unknown) == MJ
    assert converter.normalise_unit("kilowatt hour", unknown) == KWH
    assert converter.normalise_unit("square meter", unknown) == SQUARE_METRE
    assert converter.normalise_unit("ton", unknown) == TONNE
    assert converter.normalise_unit("metric ton", unknown) == TONNE
    assert unknown == set()


def test_square_metre_is_confirmed_by_the_bundled_catalog():
    """The mapping is only honest if a method built with it loads offline
    without ``UnknownUnit`` -- confirming it needs the bundled catalog to
    know the IRI, not just the converter to write it."""
    assert default_catalog().known(SQUARE_METRE) is True


def test_an_unrecognised_unit_is_left_unmapped_and_named():
    """Recorded rather than translated, so ``check_units`` can fail the whole
    conversion in one message naming every spelling it did not recognise."""
    unknown: set[str] = set()
    assert converter.normalise_unit("becquerel", unknown) == "becquerel"
    assert unknown == {"becquerel"}


def test_an_unrecognised_unit_fails_the_conversion_instead_of_being_written():
    """Guessing at it is how a factor of 1000 gets into a score; the operator
    gets told instead, and nothing is written."""
    with pytest.raises(ValueError, match="becquerel"):
        converter.check_units({"becquerel"})


def test_no_unrecognised_units_is_not_an_error():
    converter.check_units(set())


def test_the_score_unit_defaults_to_kg_for_a_co2_eq_metadata_unit():
    assert converter.resolve_score_unit(None, "kg CO2-Eq") == KG
    assert converter.resolve_score_unit(None, "kg CO2eq") == KG


def test_an_explicit_unit_argument_is_resolved_offline_against_the_catalog():
    """``--unit kg`` should not force the operator to look up the IRI by
    hand: the bundled catalog already knows the short forms."""
    assert converter.resolve_score_unit("kg", "anything") == KG


def test_an_explicit_unit_argument_is_used_as_is_when_already_an_iri():
    assert converter.resolve_score_unit(KG, "anything") == KG


def test_an_unresolvable_explicit_unit_argument_fails_at_the_typo():
    """Caught here, offline, rather than surfacing later as ``UnknownUnit``
    the first time the written method is loaded."""
    with pytest.raises(ValueError, match="nonsense"):
        converter.resolve_score_unit("http://nonsense", "anything")


def test_a_non_co2_eq_metadata_unit_without_unit_argument_fails():
    """No default guess for a unit that is not a known CO2-eq mass -- a wrong
    guess here would silently mislabel every score the method produces."""
    with pytest.raises(ValueError, match="--unit"):
        converter.resolve_score_unit(None, "kg NMVOC-Eq")


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
