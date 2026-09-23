import json
import urllib.request

from trailrunner.resolution import PystTaxonomy, default_client
from trailrunner.resolution.pyst import SKOS_BROADER

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


class FakeHttpResponse:
    """Stands in for the ``http.client.HTTPResponse`` ``urlopen`` returns.

    Only what ``PystHttpClient.concept_get`` uses: a context manager whose
    ``read()`` gives raw bytes.
    """

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self) -> bytes:
        return self._body


def test_the_real_clients_broader_key_is_a_full_uri(tmp_path, monkeypatch):
    """The live service answers JSON-LD keyed by full predicate URIs, not
    prefixed names -- ``skos:broader`` lives under
    ``http://www.w3.org/2004/02/skos/core#broader``. No network call is made:
    ``urlopen`` itself is stubbed."""
    payload = {"@id": GREEN_TRUCK, SKOS_BROADER: [{"@id": TRUCK}, {"@id": VEHICLE}]}
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, *a, **kw: FakeHttpResponse(payload)
    )
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=default_client())
    assert taxonomy.broader(GREEN_TRUCK) == [TRUCK, VEHICLE]


def test_a_concept_with_no_broader_key_has_no_parents(tmp_path, monkeypatch):
    """A top concept's response simply omits the ``broader`` key entirely --
    that is normal, not an error, and must not raise."""
    payload = {"@id": VEHICLE, "@type": "skos:Concept"}
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, *a, **kw: FakeHttpResponse(payload)
    )
    taxonomy = PystTaxonomy(tmp_path / "cache.json", client=default_client())
    assert taxonomy.broader(VEHICLE) == []
