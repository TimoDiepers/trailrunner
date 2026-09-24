"""Refresh ``trailrunner/core/units.json`` from the live vocabulary.

Asks the vocabulary about every unit constant in ``trailrunner.core.units``
and writes what it answers into the bundled cache. Prints any constant the
vocabulary does not have: that is an invented IRI, and it has to go.

    uv run python dev/warm_unit_cache.py
"""

import sys

from trailrunner.core import units
from trailrunner.core.units import BUNDLED, VOCAB, UnitCatalog
from trailrunner.resolution.pyst import default_client


def main() -> int:
    constants = sorted(
        value for name, value in vars(units).items()
        if name.isupper() and isinstance(value, str) and value.startswith(VOCAB) and value != VOCAB
    )
    # Start empty so a stale entry cannot survive a refresh.
    BUNDLED.write_text("{}")
    catalog = UnitCatalog(cache_path=BUNDLED, client=default_client())
    for iri in constants:
        catalog.info(iri)
    catalog.save()
    for iri in sorted(catalog.unknown_iris):
        print(f"NOT IN THE VOCABULARY: {iri}", file=sys.stderr)
    return 1 if catalog.unknown_iris else 0


if __name__ == "__main__":
    raise SystemExit(main())
