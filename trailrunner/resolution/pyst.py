"""``skos:broader`` from the sentier vocabulary, cached to disk.

The cache is not an optimisation. A run that needs the network to reproduce is
a run that cannot be reproduced on a plane, in a lecture hall, or in two years'
time, and the generalisation a study took is part of its result. So every
lookup is written to a plain JSON file that can be committed beside the study.

The token comes from ``PYST_AUTH_TOKEN``. It is never written to the cache.
"""

import json
import os
from pathlib import Path
from typing import Any

PYST_TOKEN_ENV = "PYST_AUTH_TOKEN"
DEFAULT_BASE_URL = "https://vocab.sentier.dev"


def default_client(base_url: str = DEFAULT_BASE_URL) -> Any:
    """A configured ``pyst_client.ConceptApi``.

    Imported here rather than at module top so that ``trailrunner.resolution``
    imports with pyarrow alone, and so a cached run needs neither the extra
    nor the token.
    """
    try:
        from pyst_client import ApiClient, ConceptApi, Configuration
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "pyst-client is needed to look up broader concepts; install it with "
            "`uv sync --extra pyst`, or pass a pre-warmed cache and no client"
        ) from exc

    configuration = Configuration(host=base_url)
    client = ApiClient(configuration)
    token = os.environ.get(PYST_TOKEN_ENV)
    if token:
        # PyST authenticates with its own header, not a bearer token.
        client.default_headers["x-pyst-auth-token"] = token
    return ConceptApi(client)


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
        parents = [
            entry.get("@id") if isinstance(entry, dict) else str(entry)
            for entry in (getattr(concept, "broader", None) or [])
        ]
        parents = [parent for parent in parents if parent]
        self._cache[iri] = parents
        self.save()
        return list(parents)
