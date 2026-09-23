"""Tier 3: borrow a dataset from a curated pack, and say what it is.

The last resort is a row of coefficients -- exactly the thing trailrunner
exists to avoid -- so every node it answers is labelled ``linear_background``
in its resolution, along with a ``basis`` that says what kind of row this
was. A reader can then see precisely where the modelled foreground stops and
the borrowed data starts, which is a more honest picture than either a
cutoff or a seamless number.

A borrowed row is one of two things, and the difference matters:

- ``"cumulative"`` -- the whole upstream of the product is already netted
  into these exchanges. The subtree is genuinely complete and terminates
  honestly. This is the shape a Brightway-backed provider would return from
  ``lca.inventory``, so nothing above this tier changes when one arrives.
- ``"unit_process"`` -- these are the dataset's own **direct** exchanges
  only; its technosphere inputs are not resolved. The subtree still
  terminates here (trailrunner has no matrix to solve them with), but its
  upstream is genuinely **missing** from the inventory, not merely deferred.

Both terminate with no technosphere children -- that is what "the last
resort" means -- but only ``"cumulative"`` may honestly claim ``complete``.
A ``"unit_process"`` row that looked complete would be worse than a cutoff,
because a cutoff is visible and a wrong claim of completeness is not.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.params.location import LocationHierarchy
from trailrunner.resolution.chain import Offer

CUMULATIVE = "cumulative"
UNIT_PROCESS = "unit_process"


@dataclass(frozen=True)
class BackgroundEntry:
    """One borrowed dataset: what it makes, what it emits per unit, and how
    honestly complete that picture is."""

    product_iri: str
    product_unit: str
    location: str | None
    dataset: str
    source: str
    basis: str
    """``"cumulative"`` or ``"unit_process"`` -- see the module docstring."""
    exchanges: tuple[tuple[str, str, float], ...]
    """(flow IRI, unit, amount per unit of product)."""

    @property
    def complete(self) -> bool:
        """Whether this row's upstream is actually accounted for.

        Only a ``cumulative`` row may claim this: a ``unit_process`` row's
        technosphere inputs were never resolved, so its biosphere is only
        ever part of the true picture, however small that part is.
        """
        return self.basis == CUMULATIVE


class BackgroundPack:
    """Borrowed datasets, indexed by (product IRI, unit, location).

    Loaded from a long/tidy parquet file: one row per (product, location,
    dataset, flow), with ``source`` (a citation -- a dataset UUID, a DOI,
    whatever identifies where the row came from) and ``basis`` carried on
    every row so nothing here can lose track of where a number came from or
    how complete it is.
    """

    def __init__(
        self,
        entries: Sequence[BackgroundEntry],
        hierarchy: LocationHierarchy | None = None,
        source: str | None = None,
    ) -> None:
        self.source = source
        self._hierarchy = hierarchy if hierarchy is not None else LocationHierarchy()
        self._entries = {
            (entry.product_iri, entry.product_unit, entry.location): entry for entry in entries
        }

    @classmethod
    def from_parquet(
        cls, path: str | Path, hierarchy: LocationHierarchy | None = None
    ) -> "BackgroundPack":
        grouped: dict[tuple[str, str, str | None, str], list[tuple[str, str, float]]] = {}
        meta: dict[tuple[str, str, str | None, str], tuple[str, str]] = {}
        for row in pq.read_table(path).to_pylist():
            key = (row["product_iri"], row["product_unit"], row.get("location"), row["dataset"])
            grouped.setdefault(key, []).append(
                (row["flow_iri"], row["flow_unit"], float(row["amount"]))
            )
            meta[key] = (row["source"], row["basis"])
        entries = []
        for (product_iri, product_unit, location, dataset), exchanges in grouped.items():
            source, basis = meta[(product_iri, product_unit, location, dataset)]
            entries.append(
                BackgroundEntry(
                    product_iri=product_iri,
                    product_unit=product_unit,
                    location=location,
                    dataset=dataset,
                    source=source,
                    basis=basis,
                    exchanges=tuple(exchanges),
                )
            )
        return cls(entries, hierarchy=hierarchy, source=str(path))

    def lookup(self, demand: Demand) -> tuple[BackgroundEntry, str | None, bool] | None:
        """The entry for this demand, the location used, and whether it fell back."""
        chain = list(self._hierarchy.chain(demand.flow.location))
        if self._hierarchy.root not in chain:
            chain.append(self._hierarchy.root)
        for index, location in enumerate(chain):
            entry = self._entries.get((demand.flow.iri, demand.unit, location))
            if entry is not None:
                return entry, location, index > 0
        return None


class BackgroundDataset(Model):
    """A borrowed dataset as a Model, so the Runner validates it like any other.

    Always terminates: it never pushes a technosphere demand onto the
    traversal queue. For a ``cumulative`` row that is correct because there
    is nothing left to resolve; for a ``unit_process`` row it is the honest
    consequence of not having resolved its inputs at all -- the resolution's
    ``complete: False`` is what tells the reader which one happened.
    """

    def __init__(self, entry: BackgroundEntry) -> None:
        super().__init__()
        self.entry = entry
        self.produces = [entry.product_iri]

    def apply(self, demand: Demand) -> Result:
        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=[],
            biosphere=[
                Exchange(
                    flow=Flow(iri=iri, location=demand.flow.location, time=demand.flow.time),
                    amount=amount * demand.amount,
                    unit=unit,
                )
                for iri, unit, amount in self.entry.exchanges
            ],
        )


class BackgroundProvider:
    """Tier 3. Answers linearly, terminates, and labels itself -- including
    how much of the upstream the label actually covers."""

    def __init__(self, pack: BackgroundPack) -> None:
        self.pack = pack

    def offer(self, demand: Demand) -> Offer | None:
        found = self.pack.lookup(demand)
        if found is None:
            return None
        entry, location, fell_back = found
        return Offer(
            model=BackgroundDataset(entry),
            demand=demand,
            tier="background",
            resolution={
                "tier": "background",
                "kind": "linear_background",
                "dataset": entry.dataset,
                "source": entry.source,
                "basis": entry.basis,
                "complete": entry.complete,
                "location_used": location,
                "location_fallback": fell_back,
            },
        )

    def explain(self, demand: Demand) -> tuple[str, str] | None:
        """Never explains: a demand the background cannot answer is better
        described by the tiers above, which know what was actually attempted."""
        return None
