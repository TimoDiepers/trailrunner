"""Warm ``examples/pyst_cache.json`` from the live PyST vocabulary service.

Run by hand, once, whenever the examples need a broader concept the cache
does not already have. This needs network access to reach
``https://vocab.sentier.dev``. A token is optional -- the service answers
public concepts without one -- but if one is available it should be set as
``PYST_AUTH_TOKEN`` in the environment. Never write the token to a file, and
never pass it as an argument, since either would put it where `git status`
can see it:

    uv run python dev/warm_pyst_cache.py
    # or, with a token available:
    PYST_AUTH_TOKEN=<your token> uv run python dev/warm_pyst_cache.py

No extra install is needed: ``trailrunner.resolution.pyst`` talks to PyST
with the standard library alone (see that module's docstring for why: the
``pyst-client`` package on PyPI cannot actually be imported).

The cache this writes is not an optimisation: it is committed beside the
examples so a run reproduces on a plane, in a lecture hall, or in two years'
time without needing the network or the token again. See
``trailrunner/resolution/pyst.py`` for the taxonomy that reads it back.
"""

from trailrunner.resolution import PystTaxonomy, default_client

IRIS = [
    "https://vocab.sentier.dev/products/co2-captured",
    "https://vocab.sentier.dev/products/heat",
    "https://vocab.sentier.dev/products/electricity",
    "https://vocab.sentier.dev/products/natural-gas",
]


def main() -> None:
    taxonomy = PystTaxonomy("examples/pyst_cache.json", client=default_client())
    for iri in IRIS:
        print(iri, "->", taxonomy.broader(iri))
    taxonomy.save()


if __name__ == "__main__":
    main()
