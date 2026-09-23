"""The vocabulary's own names for concepts, cached beside the study.

A traversal is keyed on IRIs, so a report reads as ``fi_2811_21`` unless
something supplies the concept's label. These cover the one rule that matters
for that: a label is presentation, so every way of not having one degrades to
``None`` and the caller's fallback, and none of them raises into a run.
"""

import json

import pytest

from trailrunner.resolution import PystLabels, preferred_label
from trailrunner.resolution.pyst import SKOS_PREF_LABEL

CO2 = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_2811_21"
INVENTED = "https://vocab.sentier.dev/products/electricity-wind"


def payload(iri, labels):
    return {"@id": iri, SKOS_PREF_LABEL: labels}


class StubClient:
    """Answers the concepts endpoint, counting calls so a cache hit is provable."""

    def __init__(self, concepts):
        self.concepts = concepts
        self.calls = 0

    def concept_payload(self, iri):
        self.calls += 1
        if iri not in self.concepts:
            raise OSError("404")
        return self.concepts[iri]


def test_a_cached_label_is_read_without_the_network(tmp_path):
    cache = tmp_path / "labels.json"
    cache.write_text(json.dumps({CO2: "Carbon dioxide"}))

    labels = PystLabels(cache, client=None)

    assert labels.label(CO2) == "Carbon dioxide"


def test_an_uncached_label_offline_is_none_not_an_error(tmp_path):
    assert PystLabels(tmp_path / "labels.json", client=None).label(CO2) is None


def test_a_fetched_label_is_cached_to_disk(tmp_path):
    cache = tmp_path / "labels.json"
    client = StubClient({CO2: payload(CO2, [{"@value": "Carbon dioxide", "@language": "en"}])})

    labels = PystLabels(cache, client=client)
    assert labels.label(CO2) == "Carbon dioxide"
    assert labels.label(CO2) == "Carbon dioxide"

    assert client.calls == 1, "the second lookup must come from the cache"
    assert json.loads(cache.read_text()) == {CO2: "Carbon dioxide"}


def test_an_iri_the_vocabulary_does_not_have_yields_none_and_is_not_cached(tmp_path):
    """Every invented IRI this project's own models use lands here."""
    cache = tmp_path / "labels.json"
    client = StubClient({})

    labels = PystLabels(cache, client=client)

    assert labels.label(INVENTED) is None
    assert not cache.exists(), "nothing may be written for a concept that does not exist"


def test_a_damaged_cache_costs_names_not_the_run(tmp_path):
    cache = tmp_path / "labels.json"
    cache.write_text("{ this is not json")

    assert PystLabels(cache, client=None).label(CO2) is None


def test_a_client_without_the_concepts_endpoint_is_tolerated(tmp_path):
    class RelationshipsOnly:
        def concept_get(self, iri):
            return []

    labels = PystLabels(tmp_path / "labels.json", client=RelationshipsOnly())

    assert labels.label(CO2) is None


ENGLISH = {"@value": "electricity", "@language": "en"}
ROMANIAN = {"@value": "electricitate", "@language": "ro"}


@pytest.mark.parametrize(
    "body, expected",
    [
        (payload(CO2, [ENGLISH]), "electricity"),
        # The service answers a concept as a one-item list as readily as an object.
        ([payload(CO2, [ENGLISH])], "electricity"),
        # A label in another language is not an English label: the caller's
        # fallback reads better than a node printed in Romanian.
        (payload(CO2, [ROMANIAN]), None),
        (payload(CO2, [ROMANIAN, ENGLISH]), "electricity"),
        (payload(CO2, []), None),
        (payload(CO2, [{"@language": "en"}]), None),
    ],
)
def test_preferred_label_reads_only_the_language_asked_for(body, expected):
    assert preferred_label(body) == expected


def test_preferred_label_survives_a_payload_of_the_wrong_shape():
    assert preferred_label(None) is None
    assert preferred_label("not a concept") is None
    assert preferred_label([]) is None


def test_the_committed_example_cache_names_the_concepts_the_showcase_prints():
    """The showcase reads its names offline; this is what "offline" rests on."""
    from pathlib import Path

    cache = Path(__file__).resolve().parent.parent / "examples" / "pyst_labels.json"
    labels = PystLabels(cache, client=None)

    assert labels.label(CO2) == "Carbon dioxide"
    assert labels.label(INVENTED) is None
