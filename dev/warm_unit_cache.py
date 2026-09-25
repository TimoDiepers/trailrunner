"""Refresh ``trailrunner/core/units.json`` from the live vocabulary.

Asks the vocabulary about every unit constant in ``trailrunner.core.units``
and writes what it answers into the bundled cache. Prints any constant the
vocabulary does not have: that is an invented IRI, and it has to go.

    uv run python dev/warm_unit_cache.py

Fetches happen into a temporary cache file first, never into the bundled
file directly, and the bundled file is replaced only once every constant
has resolved -- either confirmed in the vocabulary or confirmed 404. A
single network hiccup part-way through must never leave the committed
``units.json`` empty or partial, so nothing is written to it until the
whole run has succeeded.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from trailrunner.core import units
from trailrunner.core.units import BUNDLED, VOCAB, UnitCatalog
from trailrunner.resolution.pyst import default_client


def _constants() -> list[str]:
    return sorted(
        value for name, value in vars(units).items()
        if name.isupper() and isinstance(value, str) and value.startswith(VOCAB) and value != VOCAB
    )


def refresh(client: object, constants: list[str] | None = None, bundled_path: Path = BUNDLED) -> int:
    """Fetch every constant and replace ``bundled_path`` only if all resolved.

    Returns 0 if the vocabulary confirmed every constant, 1 if some are not
    in the vocabulary (a bundled file is still written; those IRIs need
    fixing in the source) or some could not be resolved at all (the bundled
    file is left untouched).
    """
    if constants is None:
        constants = _constants()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cache = Path(tmpdir) / "units.json"
        catalog = UnitCatalog(cache_path=tmp_cache, client=client)
        for iri in constants:
            catalog.info(iri)
        unresolved = [iri for iri in constants if iri not in catalog.unknown_iris and catalog.info(iri) is None]
        if unresolved:
            print(f"{bundled_path} left unchanged; could not resolve:", file=sys.stderr)
            for iri in sorted(unresolved):
                print(f"  {iri}", file=sys.stderr)
            return 1
        catalog.save()
        shutil.copyfile(tmp_cache, bundled_path)
    for iri in sorted(catalog.unknown_iris):
        print(f"NOT IN THE VOCABULARY: {iri}", file=sys.stderr)
    return 1 if catalog.unknown_iris else 0


def main() -> int:
    return refresh(default_client())


if __name__ == "__main__":
    raise SystemExit(main())
