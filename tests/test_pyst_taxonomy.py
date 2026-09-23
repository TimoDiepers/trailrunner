import json

from trailrunner.resolution import PystTaxonomy

GREEN_TRUCK = "https://vocab.sentier.dev/products/truck-green"
TRUCK = "https://vocab.sentier.dev/products/truck"
VEHICLE = "https://vocab.sentier.dev/products/road-vehicle"


class StubConcept:
    def __init__(self, broader):
        self.broader = [{"@id": iri} for iri in broader]


class StubClient:
    """Stands in for pyst_client.ConceptApi. Counts calls, so a cache hit is
    provable rather than assumed."""

    def __init__(self, concepts):
        self.concepts = concepts
        self.calls = 0

    def concept_get(self, iri):
        self.calls += 1
        return StubConcept(self.concepts.get(iri, []))


def test_broader_reads_the_concept(tmp_path):
    client = StubClient({GREEN_TRUCK: [TRUCK]})
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=client)
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK]


def test_an_unknown_concept_has_no_parents(tmp_path):
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=StubClient({}))
    assert taxonomy.broader(GREEN_TRUCK) == []


def test_several_parents_are_all_returned(tmp_path):
    client = StubClient({GREEN_TRUCK: [TRUCK, VEHICLE]})
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=client)
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK, VEHICLE]


def test_the_second_lookup_does_not_call_out(tmp_path):
    client = StubClient({GREEN_TRUCK: [TRUCK]})
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=client)
    taxonomy.broader(GREEN_TRUCK)
    taxonomy.broader(GREEN_TRUCK)
    assert client.calls == 1


def test_the_cache_is_written_and_reread_without_a_client(tmp_path):
    path = tmp_path / "cache.json"
    client = StubClient({GREEN_TRUCK: [TRUCK]})
    PystTaxonomy(path, client=client).broader(GREEN_TRUCK)

    offline = PystTaxonomy(path, client=None)
    assert offline.broader(GREEN_TRUCK) == [TRUCK]


def test_a_cache_miss_without_a_client_is_empty_not_an_error(tmp_path):
    offline = PystTaxonomy(tmp_path / "cache.json", client=None)
    assert offline.broader(VEHICLE) == []


def test_a_corrupt_cache_file_does_not_crash_the_run(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json")
    taxonomy = PystTaxonomy(path, client=StubClient({GREEN_TRUCK: [TRUCK]}))
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK]


def test_the_cache_file_is_plain_readable_json(tmp_path):
    path = tmp_path / "cache.json"
    PystTaxonomy(path, client=StubClient({GREEN_TRUCK: [TRUCK]})).broader(GREEN_TRUCK)
    assert json.loads(path.read_text())[GREEN_TRUCK] == [TRUCK]
