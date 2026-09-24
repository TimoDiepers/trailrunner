import json
import urllib.error

import pytest

from trailrunner.core.errors import UnknownUnit
from trailrunner.core.units import (
    DEG_C,
    KELVIN,
    KG,
    KILOMETRE,
    KWH,
    M3,
    METRE,
    MJ,
    NUM,
    TONNE,
    VOCAB,
    UnitCatalog,
    UnitInfo,
    default_catalog,
    parse_unit_payload,
    symbol,
)

QUDT = "http://qudt.org/schema/qudt/"
SKOS_NOTATION = "http://www.w3.org/2004/02/skos/core#notation"


def payload(iri, kind, multiplier, ucum):
    """The shape GET /api/v1/concepts/<iri> answers with (trimmed)."""
    return [
        {
            "@id": iri,
            QUDT + "hasQuantityKind": [{"@id": f"https://vocab.sentier.dev/units/quantity-kind/{kind}"}],
            QUDT + "conversionMultiplier": [
                {"@type": "http://www.w3.org/2001/XMLSchema#decimal", "@value": str(multiplier)}
            ],
            SKOS_NOTATION: [{"@type": QUDT + "ucumCode", "@value": ucum}],
        }
    ]


class StubClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def concept_payload(self, iri):
        self.calls.append(iri)
        if iri not in self.payloads:
            raise urllib.error.HTTPError(iri, 404, "Not Found", {}, None)
        return self.payloads[iri]


def test_parse_reads_kind_multiplier_and_ucum_symbol():
    info = parse_unit_payload(MJ, payload(MJ, "Energy", 1000000.0, "MJ"))
    assert info == UnitInfo(
        iri=MJ,
        quantity_kind="https://vocab.sentier.dev/units/quantity-kind/Energy",
        multiplier=1000000.0,
        offset=0.0,
        symbol="MJ",
    )


def test_parse_rejects_a_non_object():
    assert parse_unit_payload(MJ, "nope") is None
    assert parse_unit_payload(MJ, []) is None


def test_bundled_catalog_knows_the_constants_offline():
    catalog = default_catalog()
    for iri in (KG, TONNE, MJ, KWH, M3, KILOMETRE, NUM):
        assert catalog.known(iri) is True, iri


def test_mass_converts_by_multiplier():
    catalog = default_catalog()
    assert catalog.convertible(TONNE, KG)
    assert catalog.factor(TONNE, KG) == pytest.approx(1000.0)
    assert catalog.convert(2.5, TONNE, KG) == pytest.approx(2500.0)
    assert catalog.convert(3.6, MJ, KWH) == pytest.approx(1.0)


def test_different_kinds_do_not_convert():
    catalog = default_catalog()
    assert not catalog.convertible(M3, KG)
    assert catalog.try_convert(1.0, M3, KG) is None
    with pytest.raises(ValueError):
        catalog.factor(M3, KG)


def test_temperature_never_converts_even_though_the_vocab_says_it_could():
    # Review focus 1: the vocab gives DEG_C and K the same kind and
    # multiplier 1 with no conversionOffset, so 10 degC would become 10 K.
    catalog = default_catalog()
    assert not catalog.convertible(DEG_C, KELVIN)
    assert catalog.convertible(DEG_C, DEG_C)


def test_a_non_vocab_string_is_known_false():
    assert default_catalog().known("kg") is False
    assert default_catalog().known("https://example.org/units/kg") is False


def test_a_miss_asks_the_client_and_caches_to_disk(tmp_path):
    grams = VOCAB + "GM-TEST"
    client = StubClient({grams: payload(grams, "Mass", 0.001, "g")})
    cache = tmp_path / "units.json"
    catalog = UnitCatalog(cache_path=cache, client=client)
    assert catalog.convert(1000.0, grams, KG) == pytest.approx(1.0)
    assert json.loads(cache.read_text())[grams]["symbol"] == "g"
    # A second catalog reads the file; no client needed.
    assert UnitCatalog(cache_path=cache).known(grams) is True


def test_a_404_is_unknown_and_not_cached(tmp_path):
    missing = VOCAB + "BAR"
    cache = tmp_path / "units.json"
    catalog = UnitCatalog(cache_path=cache, client=StubClient({}))
    assert catalog.known(missing) is False
    assert missing in catalog.unknown_iris
    assert not cache.exists() or missing not in json.loads(cache.read_text())


def test_offline_miss_is_undetermined():
    assert UnitCatalog().known(VOCAB + "LB") is None


def test_symbol_prefers_the_display_override_then_ucum_then_last_segment():
    assert symbol(KG) == "kg"
    assert symbol(TONNE) == "t"
    assert symbol(KWH) == "kWh"
    assert symbol(VOCAB + "NOT-CACHED") == "NOT-CACHED"
    assert symbol("W·yr/m2") == "W·yr/m2"  # not an IRI: shown as written


def test_resolve_accepts_iri_id_and_symbol():
    catalog = default_catalog()
    assert catalog.resolve(KG) == KG
    assert catalog.resolve("KiloGM") == KG
    assert catalog.resolve("kg") == KG
    assert catalog.resolve("t") == TONNE


def test_resolve_refuses_what_it_cannot_confirm():
    with pytest.raises(UnknownUnit, match="tkm"):
        default_catalog().resolve("tkm")
    with pytest.raises(UnknownUnit):
        default_catalog().resolve("https://example.org/kg")


def test_a_damaged_cache_is_ignored(tmp_path):
    cache = tmp_path / "units.json"
    cache.write_text("{not json")
    assert UnitCatalog(cache_path=cache).known(KG) is True  # bundled still loads


def test_metre_and_kilometre_convert():
    assert default_catalog().convert(1500.0, METRE, KILOMETRE) == pytest.approx(1.5)


def test_one_tonne_a_year_over_a_year_is_a_thousand_kilograms():
    from trailrunner.core.units import KG, TONNE_PER_YEAR, default_catalog

    assert default_catalog().over_a_year(1.0, TONNE_PER_YEAR, KG) == pytest.approx(1000.0)


def test_a_mass_rate_is_not_read_as_a_volume():
    from trailrunner.core.units import M3, TONNE_PER_YEAR, default_catalog

    assert default_catalog().over_a_year(1.0, TONNE_PER_YEAR, M3) is None


def test_an_amount_is_not_a_rate():
    from trailrunner.core.units import KG, default_catalog

    assert default_catalog().over_a_year(1.0, KG, KG) is None
