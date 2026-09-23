"""``skos:broader`` from the sentier vocabulary, cached to disk.

The cache is not an optimisation. A run that needs the network to reproduce is
a run that cannot be reproduced on a plane, in a lecture hall, or in two years'
time, and the generalisation a study took is part of its result. So every
lookup is written to a plain JSON file that can be committed beside the study.

The token comes from ``PYST_AUTH_TOKEN``. It is never written to the cache.

This talks to PyST with nothing beyond the standard library. ``pyst-client``
on PyPI (1.2.0) cannot actually be imported: its own ``__init__`` reaches into
``pyst_client.api`` and ``pyst_client.models`` subpackages that the published
wheel does not ship (``ModuleNotFoundError: No module named 'pyst_client.api'``,
confirmed against the real install). Depending on a package that cannot be
imported buys nothing, so this speaks HTTP to the one endpoint the taxonomy
needs directly. That also means the product dimension no longer needs
Python >= 3.12 -- ``urllib.request`` works the same on 3.11.
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PYST_TOKEN_ENV = "PYST_AUTH_TOKEN"
DEFAULT_BASE_URL = "https://vocab.sentier.dev"
CONCEPT_PATH_TEMPLATE = "/api/v1/concepts/{iri}"

# The service answers in JSON-LD, keyed by full predicate URIs rather than
# prefixed names -- a concept fetched from the real service came back with
# keys like ``@id`` and ``http://www.w3.org/2004/02/skos/core#prefLabel``, not
# ``skos:prefLabel``. ``broader`` lives under this key.
SKOS_BROADER = "http://www.w3.org/2004/02/skos/core#broader"


class PystHttpClient:
    """A minimal client for the one PyST endpoint this module needs.

    ``GET /api/v1/concepts/{iri}`` with the IRI percent-encoded (nothing left
    unescaped -- an IRI is itself a URL and contains ``/`` and ``:``). Returns
    the concept's raw JSON-LD as a ``dict``.

    A token is optional: the service answered a public concept with a 200 even
    with no token sent, so this sends ``x-pyst-auth-token`` when
    ``PYST_AUTH_TOKEN`` is set and omits it otherwise, rather than refusing to
    run without one.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        token = os.environ.get(PYST_TOKEN_ENV)
        self._headers = {"x-pyst-auth-token": token} if token else {}

    def concept_get(self, iri: str) -> dict:
        encoded = urllib.parse.quote(iri, safe="")
        url = f"{self.base_url}{CONCEPT_PATH_TEMPLATE.format(iri=encoded)}"
        request = urllib.request.Request(url, headers=self._headers)
        with urllib.request.urlopen(request) as response:  # noqa: S310 -- fixed host, no user input in the URL beyond the IRI
            return json.loads(response.read())


def default_client(base_url: str = DEFAULT_BASE_URL) -> Any:
    """A configured client for the PyST concept endpoint.

    A plain function rather than the class directly so a cached run needs
    neither the token nor a client passed in at all -- ``PystTaxonomy`` never
    calls this itself; the caller decides whether to go online.
    """
    return PystHttpClient(base_url)


def _raw_broader(concept: Any) -> Any:
    """Pull whatever ``broader`` value a concept carries, in whatever shape.

    Two shapes are expected: the stub client tests use, which hands back an
    object with a ``.broader`` attribute, and the real service's JSON-LD
    ``dict``, whose key is the full predicate URI (or, defensively, a plain
    ``"broader"`` or ``"skos:broader"``, since the service's own serialisation
    is not something this module controls). A concept with no broader concept
    at all -- a top concept -- simply omits the key; that is normal, not an
    error, and is read the same as an empty list.
    """
    if isinstance(concept, dict):
        for key in (SKOS_BROADER, "broader", "skos:broader"):
            if key in concept:
                return concept[key]
        return None
    return getattr(concept, "broader", None)


def _normalise_broader(raw: Any) -> list[str]:
    """Coerce a raw ``broader`` value into a list of IRI strings.

    It may be a list of ``{"@id": ...}`` objects, a list of plain strings, or
    a single object or string instead of a list at all. A display-and-
    generalisation path must not crash on a shape nobody anticipated, so
    anything unrecognisable is skipped rather than raised on.
    """
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    parents = []
    for item in items:
        if isinstance(item, dict):
            iri = item.get("@id")
        elif isinstance(item, str):
            iri = item
        else:
            iri = None
        if iri:
            parents.append(iri)
    return parents


class PystTaxonomy:
    """``Taxonomy`` backed by PyST, answering from a JSON cache first.

    A miss with no client is an empty list, not an error: an offline run
    generalises less, and says so through the report's proxies, which is a
    better failure than refusing to run at all.
    """

    def __init__(
        self,
        cache_path: str | Path,
        client: Any | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.client = client
        self.base_url = base_url
        self._cache: dict[str, list[str]] = self._load()

    def _load(self) -> dict[str, list[str]]:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            # A damaged cache is a slow run, not a failed one.
            return {}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=2, sort_keys=True))

    def broader(self, iri: str) -> list[str]:
        if iri in self._cache:
            return list(self._cache[iri])
        if self.client is None:
            return []
        concept = self.client.concept_get(iri)
        parents = _normalise_broader(_raw_broader(concept))
        self._cache[iri] = parents
        self.save()
        return list(parents)
