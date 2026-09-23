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
imported buys nothing, so this speaks HTTP to the endpoints the taxonomy needs
directly. That also means the product dimension no longer needs
Python >= 3.12 -- ``urllib.request`` works the same on 3.11.

**Broader lives on ``/api/v1/relationships/``, not ``/api/v1/concepts/{iri}``.**
Verified against the live service: a concept's own payload carries its labels,
notes, ``inScheme``, ``topConceptOf`` and ``xkos#depth`` -- but no ``broader``
key at all, even for a concept several levels deep. Do not "simplify" this
client back to the concept endpoint; that silently disables the whole product
dimension, since a concept with real ancestors becomes indistinguishable from
one with none. The relationships endpoint (``GET /api/v1/relationships/?iri=``)
answers with a *list* of relationship objects, each keyed by full predicate
URI, which is where this module actually reads ``skos:broader`` from.

**A non-list response is an error, not a guess.** An earlier version of this
module let a response that was not a list through unchanged, to keep an older
stub-client shape working. That meant any real response that was not a list --
a changed API shape, or an error body that still happens to parse as JSON --
would be silently treated as a single relationship entry and normalised down
to "no parents": the same "wrong shape decodes to empty and looks like
success" failure the endpoint correction above exists to remove, just
narrower. So ``_select_relationship`` now raises ``TypeError`` on anything
that is not a list, and every client this module talks to -- the real
``PystHttpClient`` and the stub the tests use -- returns the real list shape.
There is no passthrough left that has to be kept in sync with two different
contracts.

**A concept that does not exist is not a concept with no parents.** Probed
against the live service: ``GET /api/v1/concepts/<iri>`` answers **404** for
``https://vocab.sentier.dev/products/electricity``, which is not a concept in
the vocabulary at all -- while ``GET /api/v1/relationships/?iri=`` answers
**200 with an empty list** for that same IRI, exactly as it would for a real
top concept that genuinely has no broader concept. ``broader()`` alone
therefore cannot tell "there is nothing above this" from "there is no such
thing", and several IRIs this project's own models use are invented rather
than vocabulary concepts -- for those the product dimension relaxes nothing
while appearing to work, the same class of failure as the wrong-endpoint bug
above. So the taxonomy asks the concepts endpoint when, and only when, the
relationships answer was ambiguous, records the IRIs the service says it does
not have (``unknown_iris``, ``known()``), and caches nothing for them.
A missing concept still only degrades the product dimension: it never raises
during a traversal, because a demand with an unrelaxable product is a demand
other dimensions and later tiers may still answer.

**A network failure degrades the dimension; it does not end the run.** The
timeout above turns a hang into a fast failure, and this module turns that
failure into the same ``[]`` an offline run gets: ``OSError`` (which covers
``urllib``'s ``URLError`` and a socket timeout) and ``json.JSONDecodeError``
are caught around the call, and nothing is written to the cache, so a later
run with the network back asks again. The ``TypeError`` from
``_select_relationship`` is deliberately *not* caught: an API whose response
shape changed is not a degraded dimension, it is a client that has to be
fixed.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PYST_TOKEN_ENV = "PYST_AUTH_TOKEN"
DEFAULT_BASE_URL = "https://vocab.sentier.dev"
RELATIONSHIPS_PATH = "/api/v1/relationships/"
CONCEPTS_PATH = "/api/v1/concepts/"

# Seconds. This is the module's only network boundary; a hung request must
# not block a run indefinitely just because the taxonomy is one dimension
# among several a demand can still be answered without.
DEFAULT_TIMEOUT = 10.0

# The service answers in JSON-LD, keyed by full predicate URIs rather than
# prefixed names -- a relationship entry fetched from the real service came
# back with keys like ``@id`` and
# ``http://www.w3.org/2004/02/skos/core#broader``, not ``skos:broader``.
SKOS_BROADER = "http://www.w3.org/2004/02/skos/core#broader"


class PystHttpClient:
    """A minimal client for the one PyST endpoint this module needs.

    ``GET /api/v1/relationships/?iri=<percent-encoded iri>`` (nothing left
    unescaped in the IRI -- it is itself a URL and contains ``/`` and ``:``).
    Returns the raw JSON-LD list the service answers with.

    Named ``concept_get`` rather than ``relationships_get`` on purpose: it is
    the method name ``PystTaxonomy`` (and the stub client the tests use)
    calls to get "whatever tells us this IRI's broader concepts", not a
    promise about which HTTP path backs it -- that has already moved once.

    A token is optional: the service answered a public concept's
    relationships with a 200 even with no token sent, so this sends
    ``x-pyst-auth-token`` when ``PYST_AUTH_TOKEN`` is set and omits it
    otherwise, rather than refusing to run without one.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        token = os.environ.get(PYST_TOKEN_ENV)
        self._headers = {"x-pyst-auth-token": token} if token else {}

    def concept_get(self, iri: str) -> list:
        query = urllib.parse.urlencode({"iri": iri})
        url = f"{self.base_url}{RELATIONSHIPS_PATH}?{query}"
        request = urllib.request.Request(url, headers=self._headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 -- fixed host, no user input in the URL beyond the IRI
            return json.loads(response.read())

    def concept_exists(self, iri: str) -> bool:
        """Whether the vocabulary has this concept at all.

        ``GET /api/v1/concepts/<percent-encoded iri>`` answers 404 for an IRI
        the vocabulary does not have, where the relationships endpoint answers
        200 with an empty list -- see the module docstring. Only 404 means
        "no such concept": any other HTTP error is a failure to find out, and
        propagates to the caller, which reads it as "not determined" rather
        than as an answer.

        ``urlopen`` raises ``HTTPError`` for every non-2xx status, so getting
        a response back at all is the "it exists" answer; the status is not
        re-read from it.

        The path shape is the one the 404 above was observed on. Should it
        ever move, the resulting error is not a 404, so it propagates to
        ``PystTaxonomy._concept_exists``, which reads any failure as "not
        determined" -- the behaviour before this check existed. A moved
        endpoint therefore costs the distinction, never the run.
        """
        url = f"{self.base_url}{CONCEPTS_PATH}{urllib.parse.quote(iri, safe='')}"
        request = urllib.request.Request(url, headers=self._headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):  # noqa: S310 -- fixed host, no user input in the URL beyond the IRI
                return True
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return False
            raise


def default_client(base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> Any:
    """A configured client for the PyST relationships endpoint.

    A plain function rather than the class directly so a cached run needs
    neither the token nor a client passed in at all -- ``PystTaxonomy`` never
    calls this itself; the caller decides whether to go online.
    """
    return PystHttpClient(base_url, timeout)


def _select_relationship(response: Any, iri: str) -> Any:
    """Pick the entry describing ``iri`` out of a relationships response.

    ``/api/v1/relationships/`` always answers a *list* -- every client this
    module talks to, real or stubbed, returns that shape, so a response that
    is not a list is not a shape to guess at; it is a sign the API changed
    underneath this client, and raising beats silently reading it as "no
    parents".

    Within the list, this looks for the entry whose ``@id`` matches the one
    requested. If none matches but exactly one entry came back, that entry is
    used anyway -- a defensive fallback for a serialisation quirk, not the
    expected case. Anything else (no match among several, or none at all)
    yields ``None``, read downstream as "no parents" rather than guessed at.
    """
    if not isinstance(response, list):
        raise TypeError(
            "expected a list from the PyST relationships endpoint, got "
            f"{type(response).__name__}; the API's response shape may have changed"
        )
    for entry in response:
        if isinstance(entry, dict) and entry.get("@id") == iri:
            return entry
    if len(response) == 1:
        return response[0]
    return None


def _raw_broader(entry: Any) -> Any:
    """Pull whatever ``broader`` value a relationship entry carries.

    ``entry`` is a JSON-LD ``dict`` -- or ``None``, when
    ``_select_relationship`` found nothing to select -- keyed by the full
    predicate URI, or, defensively, a plain ``"broader"`` or ``"skos:broader"``,
    since the service's own serialisation is not something this module
    controls. A concept with no broader concept at all -- a top concept --
    simply omits the key; that is normal, not an error, and is read the same
    as ``None``.
    """
    if isinstance(entry, dict):
        for key in (SKOS_BROADER, "broader", "skos:broader"):
            if key in entry:
                return entry[key]
    return None


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
    better failure than refusing to run at all. A network failure and an IRI
    the vocabulary has never heard of are the same for ``broader()`` -- an
    empty list -- and deliberately *not* the same for anyone asking about the
    lookup itself: ``known()`` and ``unknown_iris`` say which IRIs the
    service answered 404 for, which is what ``dev/warm_pyst_cache.py`` prints
    and what tells an author their product IRI is invented rather than
    parentless.
    """

    def __init__(
        self,
        cache_path: str | Path,
        client: Any | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.client = client
        self._cache: dict[str, list[str]] = self._load()
        self._known: set[str] = set()
        self._unknown: set[str] = set()

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
        try:
            response = self.client.concept_get(iri)
        except (OSError, json.JSONDecodeError):
            # URLError, a socket timeout, an unreadable body: the product
            # dimension is degraded for this run, exactly as it is offline.
            # Nothing is cached, so the next run asks again rather than
            # inheriting this run's outage as a fact about the vocabulary.
            return []
        # Not inside the try: a response of the wrong *shape* means the API
        # changed under this client, which is a bug to fix, not a dimension
        # to degrade. See ``_select_relationship``.
        entry = _select_relationship(response, iri)
        parents = _normalise_broader(_raw_broader(entry))
        if entry is not None:
            # An answer that names the concept is proof it exists; the second
            # endpoint is only worth asking when the first was ambiguous.
            self._known.add(iri)
        else:
            exists = self._concept_exists(iri)
            if exists is False:
                self._unknown.add(iri)
                # Caching this would write an IRI the vocabulary does not
                # have into a file committed beside a study, as though it
                # were a concept with no parents.
                return []
            if exists is True:
                self._known.add(iri)
        self._cache[iri] = parents
        self.save()
        return list(parents)

    def known(self, iri: str) -> bool | None:
        """Whether the vocabulary has this concept: ``None`` if not determined.

        Three states, because there are three: the service said yes, the
        service said 404, or nobody asked -- an offline run, a cache hit, a
        client without a ``concept_exists``, or a network failure while
        asking. Collapsing the third into ``False`` would claim a concept is
        invented on the strength of a run that never checked.

        A pure accessor over what ``broader()`` already learned: it never
        reaches for the network itself, because a predicate that quietly makes
        an HTTP request is a predicate nobody can call safely.
        """
        if iri in self._unknown:
            return False
        if iri in self._known:
            return True
        return None

    @property
    def unknown_iris(self) -> frozenset[str]:
        """Every IRI this instance asked about and the vocabulary does not have."""
        return frozenset(self._unknown)

    def _concept_exists(self, iri: str) -> bool | None:
        """Ask the client whether the concept exists; ``None`` if it cannot say.

        Optional on the client on purpose: a taxonomy handed a minimal client
        (or a stub) that only knows ``concept_get`` still works, and simply
        never learns the difference, rather than failing on an attribute.
        """
        check = getattr(self.client, "concept_exists", None)
        if check is None:
            return None
        try:
            return bool(check(iri))
        except (OSError, json.JSONDecodeError):
            return None
