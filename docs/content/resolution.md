---
icon: lucide/route
tags:
  - concepts
---

# Resolution

Every demand the traversal pops has to be answered by something. A
[`ResolutionChain`](../api/resolution.md) asks its providers in order and takes the first
offer:

| Tier | Provider | Answers with | Recorded as |
| --- | --- | --- | --- |
| 1 | `ModelProvider` | a model that produces this exact IRI and covers this place and year | `[model: ...]` |
| 2 | `GeneralisingProvider` | a model found by relaxing the demand: a wider region, a nearby year, a broader product | `[proxy: ...]` |
| 3 | `BackgroundProvider` | a row of coefficients borrowed from a curated background pack | `[background: ...]` |

Only tier 1 is an exact answer. Every later tier is a **concession**, and it writes what it
conceded into the node's resolution, `report.proxies` and `report.tree()`.

`Orchestrator(glossary)` is shorthand for a chain with tier 1 alone. That is what the
[CLI](getting_started/cli.md) uses, and why it never produces a proxy.

## Building a chain

This is the chain the [5-minute tour](../showcase.md) runs:

```python
from trailrunner import Glossary, LocationHierarchy, ModelProvider, Orchestrator, ResolutionChain
from trailrunner.resolution import (
    BackgroundPack,
    BackgroundProvider,
    GeneralisingProvider,
    PystTaxonomy,
)

hierarchy = LocationHierarchy({"CH": "RER", "DK": "RER", "FR": "RER", "RER": "GLO"})

tier1 = ModelProvider(Glossary(models))
tier2 = GeneralisingProvider(
    tier1,
    hierarchy=hierarchy,
    taxonomy=PystTaxonomy("examples/pyst_cache.json"),  # offline: answers from the file only
)
tier3 = BackgroundProvider(
    BackgroundPack.from_parquet("examples/background_pack.parquet", hierarchy=hierarchy)
)

report = Orchestrator(ResolutionChain([tier1, tier2, tier3])).calculate(demand)
```

**The tier order is yours to declare.** `ResolutionChain` doesn't reorder anything, and no
tier knows the others exist. Whether a relaxed demand beats a borrowed dataset, or the
other way round, is a modelling decision. A study that prefers the background tier builds
the chain in that order.

When every tier declines, the demand becomes a cutoff, and the chain asks each tier in the
same order why it declined. Tier 1 reports `coverage_excluded` if a model declares the
product but its coverage misses. Tier 2 reports `generalisation_exhausted` if it had
candidates and none matched. Otherwise the reason is `no_model_found`.

## Tier 2: generalising a demand

[`GeneralisingProvider`](../api/resolution.md) relaxes one dimension of the demand at a
time and asks tier 1 again. [`ProxySettings`](../api/settings.md), on `Settings.proxy`
or passed as `settings=`, controls which dimensions are tried, in what order, and how far:

```python
from trailrunner import ProxySettings

ProxySettings(
    order=("time", "location", "product"),                 # the default order
    max_steps={"time": 1, "location": 3, "product": 2},    # the default budgets
    time_tolerance=5,                                      # years
)
```

A dimension missing from `max_steps`, or set to 0, is never relaxed. A step means the same
in every dimension: one level up the location hierarchy, one level up the taxonomy, or one
year snapped to. Each candidate that answers records a note such as
`"location: CH -> RER"`, and it shows up in the tree as `[proxy: location: CH -> RER]`.

**Location** widens along the [`LocationHierarchy`](../api/location.md), most specific
first. With `{"CH": "RER", "RER": "GLO"}`, a demand at `CH` with no `CH` model is asked
again at `RER`, then at `GLO`.

**Time** snaps to the nearest year that some model declaring the product actually covers,
within `time_tolerance`. A demand for 2030 with a model covering 2035–2050 and a tolerance
of 5 is asked again for 2035. Years nothing claims are never tried.

**Product** climbs a [`Taxonomy`](../api/resolution.md)'s `skos:broader` relation,
breadth-first: every concept one level up is tried before any concept two levels up, so the
most specific model still standing wins. A concept with two broader concepts contributes
both, at the same level.

```python
from trailrunner.resolution import StaticTaxonomy

taxonomy = StaticTaxonomy({
    "https://vocab.sentier.dev/products/truck-green": ["https://vocab.sentier.dev/products/truck"],
    "https://vocab.sentier.dev/products/truck": ["https://vocab.sentier.dev/products/road-vehicle"],
})
# with max_steps={"product": 2}, a demand for truck-green is asked again
# as truck, then as road-vehicle
```

`StaticTaxonomy` is for tests and hand-written hierarchies. In a real study,
[`PystTaxonomy`](#the-vocabulary-cache-and-offline-runs) reads the sentier vocabulary.

The tour shows what this costs. The cement plant demands BONSAI `fi_37420` ("Quicklime,
slaked lime and hydraulic lime"), which nobody produces. Two levels up is `fi_374`
("Plaster, lime and cement"), and a supplier there answers:

```text
10 kg Quicklime, slaked lime and hydraulic lime @DK/2030  [proxy: product: fi_37420 -> fi_374]
```

That is the best answer available, and a poor one in substance: `fi_374` averages over a
category that contains the cement being made. The concession is written at the node so a
reader can judge it.

### Relaxations don't compose

Each dimension is tried starting from the *original* demand. A demand that needs both a
wider region *and* a different year isn't answered. The combined search would need a second
preference order (region first or year first?), and choosing one silently is exactly what
this tier avoids. Such a demand falls through and shows up as a `generalisation_exhausted`
cutoff whose detail counts the candidates tried, e.g. `candidates tried: location(2),
product(3)`.

A demand with nothing to relax (no location, no year, no taxonomy behind it) gets no
explanation from this tier, so it is reported as `no_model_found`. That points the reader
at a missing model rather than at a budget that couldn't have helped.

## Tier 3: borrowing from a background pack

[`BackgroundProvider`](../api/resolution.md) is the last resort. It answers with a row of
per-unit coefficients, the kind of static dataset trailrunner otherwise replaces with
models, so every node it answers says so, including how much of the upstream the row
actually covers.

### The pack format

A [`BackgroundPack`](../api/resolution.md) loads from a long parquet table, one row per
`(product, location, dataset, flow)`:

| Column | Meaning |
| --- | --- |
| `product_iri`, `product_unit` | the demand this row answers |
| `location` | looked up through a `LocationHierarchy`, ending at its root |
| `dataset` | the name of the borrowed process |
| `source` | a citation: dataset UUID, DOI, whatever traces the row back |
| `basis` | `"cumulative"` or `"unit_process"`, see below |
| `flow_iri`, `flow_unit`, `amount` | one biosphere exchange, **per unit of product** |

The lookup key is `(product_iri, product_unit, location)`. Two datasets for one key raise
[`DuplicateBackgroundEntry`](../api/errors.md) on load, naming both, since there is no rule
to pick between them. A borrowed row is a `BackgroundDataset` model that supports every
allocation rule and never demands anything upstream.

### `basis`: complete or not

- **`cumulative`**: the whole upstream is already summed into these exchanges, the shape a
  Brightway `lca.inventory` would give. The subtree genuinely ends here, and the resolution
  says `"complete": True`.
- **`unit_process`**: only the dataset's own **direct** emissions. Its inputs were never
  resolved (trailrunner has no matrix to solve them with), so the upstream is **missing**,
  and the resolution says `"complete": False`.

```text
0.1 kg steel-low-alloyed @DK/2026  [background: unit_process, incomplete]
1 kg clinker @GLO/-  [background: cumulative]
```

`examples/background_pack.parquet`, built by `dev/build_background_pack.py` from EcoSpold
1 process data, is entirely `unit_process`. Some of its rows carry *zero* tracked emissions,
not because the process emits nothing, but because everything it emits sits in inputs this
tier doesn't resolve. `complete: False` keeps that from looking like a finished answer.

!!! warning "A borrowed dataset may not be the product you asked for"

    Some products have no dataset under their own name that emits anything directly. For
    those, the shipped pack borrows the nearest upstream dataset that does: **clinker**
    answers cement, **liquid aluminium at plant** answers primary aluminium, and
    **converter/electric steel** answers low-alloyed steel. `resolution["dataset"]`
    always names the dataset that actually answered. Check it before trusting a borrowed
    number.

## What a resolution records

Every node's resolution is a dict. Four keys mean the same thing in every tier:

| Key | Meaning |
| --- | --- |
| `tier` | `"model"`, `"generalising"` or `"background"` |
| `model` | class name of the model that produced the result (`BackgroundDataset` for tier 3) |
| `asked` | the demand as it came in: full IRI, `@location/year` |
| `answered` | the demand the model was applied to: equal to `asked` unless something was relaxed |

Tier 2 adds `relaxations`. Tier 3 adds `dataset`, `source`, `basis`, `complete`,
`location_used` and `location_fallback`.

`report.resolutions` holds this for every node. `report.proxies` holds the subset whose
tier isn't `"model"`:

```python
for node_id, resolution in report.proxies.items():
    if resolution.get("complete") is False:
        print(node_id, "incomplete borrow:", resolution["dataset"])
```

`report.summary()` counts proxies and incomplete borrows (`5 proxies (4 incomplete)`), and
`report.tree()` shows where each one sits. Both read the same keys, so they can't disagree.

## The vocabulary cache and offline runs

[`PystTaxonomy`](../api/resolution.md) answers `broader()` from a JSON cache file first,
and only calls `https://vocab.sentier.dev` on a miss, and only if it was given a client. The
cache is committed beside the study it serves, so a run reproduces without a network or a
token:

```python
from trailrunner.resolution import PystTaxonomy, default_client

# offline: answers only from the cache, [] for anything not in it
taxonomy = PystTaxonomy("examples/pyst_cache.json")

# online, to warm the cache with new IRIs (dev/warm_pyst_cache.py does this)
taxonomy = PystTaxonomy("examples/pyst_cache.json", client=default_client())
taxonomy.broader(new_iri)   # fetched and cached in memory
taxonomy.save()             # written back to the JSON file
```

`PYST_AUTH_TOKEN` is read from the environment, sent only in the request header, and never
written to the cache.

A network failure, a timeout or a non-JSON body degrades the product dimension instead of
ending the run. `broader()` answers `[]` and nothing is cached, so a later run asks again.
Only a response of the wrong shape raises, because that means the API changed.

**"No such concept" isn't "no parents".** The vocabulary answers an unknown IRI and a real
top-level concept the same way, with an empty parent list. `broader()` returns `[]` for
both, and `known()` tells them apart:

```python
taxonomy.broader(iri)   # [] either way
taxonomy.known(iri)     # False: not a concept. None: nobody could check (offline, cached, failure)
taxonomy.unknown_iris   # every IRI this instance found missing
```

`dev/warm_pyst_cache.py` prints unknown IRIs prominently and caches nothing for them, so an
invented IRI never ends up in a committed cache looking like a real concept.

### Names from the same vocabulary

[`PystLabels`](../api/resolution.md) reads each concept's `skos:prefLabel` on the same
terms (cache first, network only on a miss), and
[`Report.tree(labels=...)`](reports.md#summary-and-tree) prints those names instead of IRI
segments:

```python
from trailrunner.resolution import PystLabels

vocab = PystLabels("examples/pyst_labels.json")
vocab.label("https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9")
# 'heat from main producers of heat'

print(report.tree(labels=vocab.label))
```

A missing label (offline, a failure, no English label, not a concept) answers `None`, and
the tree falls back to the IRI's last segment. So a tree line that still reads like an
identifier is a flow no vocabulary concept backs, which is also why the product dimension
can't relax it.
