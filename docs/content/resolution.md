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

Walks a [`Taxonomy`](../api/resolution.md)'s `skos:broader` relation upward,
breadth-first: every concept one level up is tried before any concept two levels up, so
"truck, green" generalises to "truck" before anything wider and the most specific model
still standing wins. A concept with two broader concepts contributes both, and both are
one level up.

```python
from trailrunner.resolution import StaticTaxonomy

taxonomy = StaticTaxonomy({
    "https://vocab.sentier.dev/products/truck-green": ["https://vocab.sentier.dev/products/truck"],
    "https://vocab.sentier.dev/products/truck": ["https://vocab.sentier.dev/products/road-vehicle"],
})
# with max_steps={"product": 2}, a demand for "truck, green" is re-asked at
# "truck", then at "road-vehicle"
```

A step means the same thing here as everywhere else: `max_steps["product"]` is how many
*levels up the vocabulary* the walk may climb, exactly as `max_steps["location"]` is how
many levels up the hierarchy the region may widen. Real vocabulary chains are several
levels deep — `fi_17100 → fi_1710 → fi_171` is three — and a budget of 2 reaches the
second of them.

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

That reason is only given when candidates actually existed and were tried — its detail
counts them, e.g. `candidates tried: location(2), product(3)`. A demand with no location,
no year and no taxonomy behind it has nothing to relax whatever `max_steps` permits, and
this tier says nothing at all about it, so the chain reports `no_model_found`: the reader
is pointed at a missing model rather than at a budget that could not have helped.

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

Two things are refused on load rather than carried into a run. A `basis` that is neither
`"cumulative"` nor `"unit_process"` raises `ValueError` where it is written, because
`complete` is derived from it and an unrecognised word would quietly read as an incomplete
borrow nobody declared. And two datasets for one `(product_iri, product_unit, location)`
raise [`DuplicateBackgroundEntry`](../api/errors.md), naming both: that triple is the
pack's only lookup key, there is no rule that picks between two answers, and keeping
whichever row came last would put an unexplained number in the inventory *and* label it
with the other dataset's name in the very field a reader checks it against. It is the same
refusal `Glossary.resolve` makes with `AmbiguousModelMatch` and a method file makes with
`DuplicateFactor`.

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

### A borrowed dataset may not be the product you asked for

Some products have no dataset under their own name that carries any of the tracked
elementary flows directly — the literally-named dataset turns out to be a further
blending or processing step with nothing but technosphere inputs one level up (see
`dev/build_background_pack.py` for the full account). For those, the pack borrows the
nearest upstream dataset that *does* emit directly instead: as of the current pack,
**clinker** answers a demand for cement, **liquid aluminium at plant** answers primary
aluminium, and **converter/electric steel** answers "steel, low-alloyed". These are near
neighbours of the product demanded, not the product under its own name.

`resolution["dataset"]` always names the dataset that actually answered the demand, so
this is never hidden — but a reader trusting a number without checking that field would
not know the row came from a different-sounding process. Before trusting a borrowed
number, check `resolution["dataset"]` (or the corresponding line in `report.tree()`)
against the product you actually demanded.

### What a resolution says, in every tier

A resolution dict is read by people and by code that never knows which tier wrote it, so
four keys mean the same thing in all three:

| key | meaning |
| --- | --- |
| `tier` | `"model"`, `"generalising"` or `"background"` — copied from `Offer.tier`, never set independently |
| `model` | class name of the model that produced the Result (tier 3's is `BackgroundDataset`) |
| `asked` | the demand as it came in: full IRI, location and year |
| `answered` | the demand the model was actually applied to — equal to `asked` where nothing was relaxed, rather than absent |

Each tier then adds its own: `relaxations` for tier 2, and `dataset`, `source`, `basis`
and `complete` for tier 3. The relaxation notes are written for a `tree()` line, so a
product note shortens both IRIs to their last segment; the full pair is in `asked` and
`answered`, and so in `report.proxies` and the log parquet.

### Reading `report.proxies`

Every node whose resolution's `tier` is not `"model"` — a generalised match or a borrowed
one — lands in `report.proxies`, keyed by node id, holding the full resolution dict:

```python
for node_id, resolution in report.proxies.items():
    if resolution.get("complete") is False:
        print(node_id, "incomplete borrow:", resolution["dataset"])
```

`report.summary()` reports the count; `report.tree()` shows where in the traversal each one
sits, and reads a borrow's incompleteness from the same `complete` key `summary()` counts,
so the two views cannot disagree.

Every `Offer` carries its tier into its resolution, so a provider cannot answer with a
concession the report then prints as an exact match — the failure that made this promise
worth checking. A resolution dict written straight into a `Log` by hand with no `tier` key
at all is still read as `"model"` in both views: that default is uniform, not inferred, and
anything trailrunner's own chain produces says which tier it came from outright.

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

### A failure degrades the dimension, it does not end the run

An unreachable service, a request that times out, a body that is not JSON: each answers
`[]`, the same thing an offline run gets, and nothing is written to the cache, so a later
run asks again rather than inheriting one outage as a fact about the vocabulary. A
traversal must not die because one of three relaxation dimensions could not be reached.

The one failure that *is* raised is a response of the wrong shape — the relationships
endpoint answers a list, and something else means the API changed under this client, which
is a bug to fix rather than a dimension to do without.

### "No such concept" is not "no parents"

`GET /api/v1/concepts/<iri>` answers **404** for an IRI the vocabulary does not have, while
`GET /api/v1/relationships/?iri=<iri>` answers **200 with an empty list** for that same
IRI — exactly as it does for a real top concept that genuinely has nothing above it. So
`broader()` alone cannot tell the two apart, and an invented product IRI relaxes nothing
while appearing to work.

`broader()` still answers `[]` for both, because a missing concept should degrade the
product dimension and not kill a traversal. The difference is recorded rather than
discarded:

```python
taxonomy.broader("https://vocab.sentier.dev/products/electricity")  # []
taxonomy.known("https://vocab.sentier.dev/products/electricity")    # False -- not a concept
taxonomy.unknown_iris                                               # every 404 this instance hit
```

`known()` answers `None` when nobody could ask — an offline run, a cache hit, a client that
cannot check, a network failure while checking — because "nobody asked" is not "the
vocabulary says no". `dev/warm_pyst_cache.py` prints the unknown IRIs in a block nobody can
miss, and caches nothing for them: an IRI that is not a concept must not end up in a
committed cache file looking like one.
