---
tags:
  - concepts
---

# Resolution

A demand for a product IRI can be answered three ways, tried in order: an exact model
match, a generalised demand, or a dataset borrowed from a curated pack. Passing a
[`ResolutionChain`](../api/resolution.md) to [`Orchestrator`](../api/orchestrator.md) in
place of a bare [`Glossary`](../api/glossary.md) opts into all three tiers you register;
`Orchestrator(Glossary([...]))` still works exactly as before, with no chain in sight.

```python
from trailrunner.resolution import ModelProvider, ResolutionChain

chain = ResolutionChain([
    ModelProvider(glossary),          # tier 1: the models
    GeneralisingProvider(...),        # tier 2: relax the demand
    BackgroundProvider(pack),         # tier 3: borrow a dataset, and say so
])
```

## Tier order is the practitioner's to declare

Nothing in `ResolutionChain` picks this order for you: it asks each provider in turn and
takes the first offer. That is deliberate. Whether a widened region is preferable to a
borrowed background row — or the other way around — is a modelling decision, not something
a library should default silently. A study that wants the background tier tried before
generalisation just builds the chain in that order; the code does not care, and neither
tier knows the other exists.

`explain()` is reused the same way when every tier declines: tier 1's coverage misses are
tried first, because "no model produces this" is more useful to a reader than
"generalisation ran out" — the two rarely point at the same fix.

## Tier 2: generalising a demand

[`GeneralisingProvider`](../api/resolution.md) relaxes one dimension of a demand and
re-asks tier 1. [`ProxySettings`](../api/settings.md) governs which dimensions are tried,
in what order, and how far — a practitioner's budget, not a library default.

### Location

Widens along a [`LocationHierarchy`](../api/location.md), most specific step first:

```python
from trailrunner.core.flow import Demand, Flow
from trailrunner.params.location import LocationHierarchy

hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
# a demand at CH, with no CH model registered, is re-asked at RER, then GLO
```

The resolution records the note itself, e.g. `"location: CH -> RER"`, not just that a
relaxation happened.

### Time

Snaps to the nearest year some registered model actually declares coverage for, within
`ProxySettings.time_tolerance` — never further, and never to a year nothing claims:

```python
# a demand at time=2030 with a model covering 2035-2050 and tolerance=5
# is re-asked at time=2035, not simply "the closest year in general"
```

### Product

Walks a [`Taxonomy`](../api/resolution.md)'s `skos:broader` relation one step at a time —
"truck, green" generalises to "truck" before anything wider, so the most specific model
still standing wins:

```python
from trailrunner.resolution import StaticTaxonomy

taxonomy = StaticTaxonomy({"https://vocab.sentier.dev/products/truck-green":
                            ["https://vocab.sentier.dev/products/truck"]})
```

In production this is backed by [`PystTaxonomy`](../api/resolution.md) instead of a
hand-written map — see [below](#the-pyst-cache-and-offline-runs).

### Relaxations do not compose

Each dimension is tried starting from the *original* demand, in the declared order. A
demand that needs both a wider region and an earlier year is not answered — not because
that combination is impossible to search, but because the composed search is a
cross-product whose preference order (wider-region-first? earlier-year-first?) is a second
normative choice, and inventing one silently is exactly what this tier exists to prevent.
The demand falls through instead, and shows up as a `generalisation_exhausted` cutoff:
deferred, not forgotten, and visible either way.

## Tier 3: borrowing from a background pack

[`BackgroundProvider`](../api/resolution.md) is the last resort. It answers with a row of
coefficients — exactly the thing trailrunner exists to avoid modelling as a black box — so
every node it answers is labelled `linear_background`, and the label carries enough detail
that a reader never has to guess how much of the upstream that row actually covers.

### The pack's format

A [`BackgroundPack`](../api/resolution.md) loads from a long/tidy parquet file, one row per
`(product, location, dataset, flow)`:

| column | meaning |
| --- | --- |
| `product_iri`, `product_unit` | the demand this row answers |
| `location` | looked up through a `LocationHierarchy`, same as tier 2 |
| `dataset` | the human-readable name of the borrowed process |
| `source` | a citation — a dataset UUID, a DOI, whatever traces the row back to where it came from |
| `basis` | `"cumulative"` or `"unit_process"` — see below |
| `flow_iri`, `flow_unit`, `amount` | one biosphere exchange, **per unit of product** |

```python
from trailrunner.resolution import BackgroundPack, BackgroundProvider

pack = BackgroundPack.from_parquet("examples/background_pack.parquet")
provider = BackgroundProvider(pack)
```

### `basis`, and what a node's resolution says about it

A borrowed row is one of two things, and a reader needs to know which:

- **`"cumulative"`** — the whole upstream of the product is already netted into these
  exchanges. This is the shape a Brightway-backed provider would return from
  `lca.inventory`; the subtree genuinely terminates, and the node's resolution says
  `"complete": True`.
- **`"unit_process"`** — these are the dataset's own **direct** exchanges only; its
  technosphere inputs were never resolved. The subtree still terminates — trailrunner has
  no matrix to solve those inputs with — but its upstream is **missing**, not merely
  deferred, and the resolution says `"complete": False`.

Both terminate with no technosphere children; only `"cumulative"` may honestly claim
`complete`. `examples/background_pack.parquet` (built by `dev/build_background_pack.py`
from real EcoSpold 1 process data) is entirely `"unit_process"`, and several of its rows
show why the distinction matters: a borrowed "steel" or "cement" row can carry *zero*
biosphere exchanges of the tracked substances, not because the real process emits nothing,
but because everything it emits is embodied in a technosphere input this tier does not
resolve. A cutoff at that point would be visible; a `unit_process` row that looked complete
would not be, which is exactly what `complete: False` prevents.

`report.tree()` tags the two differently:

```text
1 kg natural-gas @US/-  [background: unit_process, incomplete]
1 kg clinker @GLO/-  [background: cumulative]
```

### Reading `report.proxies`

Every node whose resolution's `tier` is not `"model"` — a generalised match or a borrowed
one — lands in `report.proxies`, keyed by node id, holding the full resolution dict:

```python
for node_id, resolution in report.proxies.items():
    if resolution.get("basis") == "unit_process":
        print(node_id, "incomplete borrow:", resolution["dataset"])
```

`report.summary()` reports the count; `report.tree()` shows where in the traversal each one
sits. Nothing has to be inferred from the absence of a `[model: ...]` tag — an unrecognised
tier is never mistaken for an exact match, in either view.

## The PyST cache and offline runs

`PystTaxonomy` answers `broader()` from a JSON cache file first, and only calls the network
(`https://vocab.sentier.dev`, via [`default_client()`](../api/resolution.md)) on a genuine
miss — and a run built without a client at all just gets `[]` for anything not already
cached, which the generalising tier reads as "nothing to relax to," not an error. The cache
is not an optimisation: it is committed beside the examples it serves precisely so a run
reproduces on a plane, in a lecture hall, or two years from now, without the network or a
token. `PYST_AUTH_TOKEN` is read from the environment, used only in the request header, and
never written to the cache file — nothing under version control should ever carry it.

```python
from trailrunner.resolution import PystTaxonomy, default_client

# offline: answers only from examples/pyst_cache.json, [] on a genuine miss
taxonomy = PystTaxonomy("examples/pyst_cache.json")

# online, to warm the cache with a new IRI (see dev/warm_pyst_cache.py):
taxonomy = PystTaxonomy("examples/pyst_cache.json", client=default_client())
```
