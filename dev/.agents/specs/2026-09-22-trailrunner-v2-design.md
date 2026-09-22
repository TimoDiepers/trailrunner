# trailrunner v2 — Design

Date: 2026-09-22
Status: approved design, ready for implementation planning
Supersedes nothing; extends `2026-09-21-trailrunner-design.md`, which remains
the description of the core traversal and is unchanged by this document.

## Purpose

v1 walks a supply chain of models and returns an honest inventory. v2 adds the
four things a practitioner needs before that inventory is an answer rather than
an artifact:

1. **Assessment** — characterization to a score, including a time-explicit one.
2. **Resolution** — a declared way to answer a demand nothing models exactly.
3. **Attribution** — the normative choices of LCA as enforced, recorded flags.
4. **Surfaces** — a report you can read, a picture you can show, a command you
   can run.

Plus a fifth deliverable that is not code: a five-minute showcase page that
walks one demand end to end, suitable for a hackathon stage.

## Guiding constraint

Every phase ends with `examples/` runnable and the showcase regenerated. The
project is never more than one phase away from being presentable. Features that
cannot be demonstrated in that page are not in this design.

## Non-goals (v2)

- **No score-based traversal.** The Queue stays FIFO / breadth-first. No
  priority function, no score-based cutoff. Assessment does not feed back into
  the walk.
- No cycle convergence. Loops remain truncated and reported, as in v1.
- No concurrent Runner.
- No live Brightway background at runtime. The background tier is a curated
  parquet pack; a Brightway-backed provider is future work behind the same
  interface.
- No frontend beyond a CLI and static figures.

## Architecture

```
trailrunner/
├── core/            flow, model, result, settings        (extended)
├── params/          parameter_set, fleet, coverage, location
├── orchestration/   glossary, runner, queue (FIFO), log, report
├── resolution/      NEW  provider chain
├── assessment/      NEW  Report in, score / curve out
├── attribution/     NEW  amortization helpers
├── viz/             NEW  optional, plotly
└── cli.py           NEW
```

**Dependency direction is one way.** `assessment` imports `core` and
`orchestration.report`. `orchestration` never imports `assessment`. The
inventory is a complete, valid deliverable on its own; characterization is a
separate reading of it. This is the direct consequence of dropping score-based
traversal, and it is what makes the assessment module independently testable
and independently shippable.

## 1. Assessment

`trailrunner.assessment`. Reads a finished `Report`. Three pieces.

### Method

Characterization factors from a trailpack-style parquet, the same shape and the
same reader machinery as `ParameterSet`: columns carry PyST concept IRIs and
units from the embedded `datapackage.json`.

```python
method = Method.from_parquet("gwp100.parquet",
                             hierarchy=LocationHierarchy({"CH": "RER", "RER": "GLO"}))
```

One row per (flow IRI, optional location, optional time) giving a CF and its
unit. Location falls back through the hierarchy exactly as parameters do, and
every fallback is recorded.

A flow with no CF is **not** silently zero. It lands in
`assessment.uncharacterized`, mirroring `report.unresolved`. Unknown inventory
and unknown characterization are both reported; neither is absorbed into the
number.

### Static assessment

```python
assessment = assess(report, method)
```

Returns an `Assessment`:

| Field | Meaning |
|---|---|
| `score` | total, in the method's unit |
| `by_flow` | contribution per `(Flow, unit)` |
| `by_node` | contribution per node, direct and cumulative-by-subtree (walking `report.edges`) |
| `uncharacterized` | inventory entries the method had no CF for |
| `provenance` | CF fallbacks taken |

### Dynamic assessment

```python
dynamic = assess_dynamic(report, metric="radiative_forcing", horizon=100)
```

Every `Exchange` already carries `flow.time`, so the inventory *is* a time
series. This reshapes it into the DataFrame `dynamic_characterization.characterize()`
expects (`date`, `amount`, `flow`, `activity`) and calls it.

- metrics: `radiative_forcing`, `GWP`, and the prospective `pGWP` / `pGTP` /
  `prospective_radiative_forcing`
- `horizon` in years; `fixed_time_horizon` exposed, so Levasseur and the
  conventional convention are both reachable and neither is implied
- returns the characterized series and its cumulative curve

`Flow.time` is a year, and `characterize` wants a timestamp: a year `Y` becomes
`datetime(Y, 1, 1)`. Stated here because it is an assumption, not a fact — a
finer `Flow.time` would change it, and the conversion lives in one function so
that change is one edit.

IRI → characterization function is a small declared table shipped in the module
(`{CO2_FOSSIL: ipcc_ar6.characterize_co2, CH4_FOSSIL: ..., N2O: ...}`),
overridable per call. No Brightway involved in this path.

### Dependencies

- `Method` + `assess` — pyarrow only, works on 3.11.
- `assess_dynamic` — extra `[dynamic]`: `dynamic_characterization`, `pandas`.
  Imported lazily; absent, it raises naming the extra.
- Brightway method import — extra `[brightway]`, an **offline** converter
  script turning a `bw2data` method into the parquet format. Nothing at
  runtime.

## 2. Resolution

`trailrunner.resolution`. `Glossary` becomes one tier of an ordered chain.

```python
class Provider(Protocol):
    def offer(self, demand: Demand) -> Offer | None: ...


@dataclass(frozen=True)
class Offer:
    answer: Model | Callable[[Demand], Result]
    tier: str
    provenance: Mapping[str, Any]   # exactly how this was matched
```

Tiers are asked in order; the first offer wins. Ambiguity *within* a tier is an
error, as in v1. Precedence *across* tiers is not silent: the user declared the
order.

### Tier 1 — ModelProvider

A thin `Provider` wrapper over today's `Glossary`, whose semantics are
unchanged: exact IRI plus coverage; 0 hits pass to the next tier, 2+ raise
`AmbiguousModelMatch`. `Glossary` stays in `orchestration/`, keeps its current
public API, and works standalone for anyone who wants tier 1 alone.

### Tier 2 — GeneralisingProvider

theory.md §Proxy settings, made executable. When nothing matches exactly,
relax the demand one step along one dimension and re-ask tier 1.

| Dimension | Step |
|---|---|
| time | snap to the nearest year a model covers, within `time_tolerance` |
| location | walk `LocationHierarchy` up (`CH → RER → GLO`) |
| product | walk PyST `skos:broader` from the demand IRI via `pyst_client.ConceptApi` |

Order and budget are settings, because the hierarchy is a normative choice and
belongs to the practitioner:

```python
ProxySettings(
    order=("time", "location", "product"),
    max_steps={"time": 1, "location": 3, "product": 2},
    time_tolerance=5,
)
```

Every step is recorded. `report.proxies` gets one row per node: which dimension
was relaxed, from what to what, and which tier finally answered. Budget
exhausted → unresolved leaf, reason `generalisation_exhausted`, detail naming
how far it got.

**PyST access.** Token from the `PYST_AUTH_TOKEN` environment variable, never
in the repository. Every concept lookup is memoized to an on-disk JSON cache;
the examples ship a pre-warmed cache so the demo runs with the network
unplugged. `pyst-client` requires ≥3.12, so it is an extra, `[pyst]`; without
it tier 2 relaxes time and location only, and says so rather than pretending
the product dimension was tried.

### Tier 3 — BackgroundProvider

Last resort. A parquet *background pack*: one row per
`(product IRI, location, unit)` plus its **cumulative** biosphere exchanges per
unit of product. It answers linearly and terminates — no technosphere
children, so no depth blowup. Provenance marks the node `linear_background`:
this subtree is matrix LCA, and the report says so.

The pack ships hand-curated at roughly 20 datasets, covering what the demo
chain actually hits (electricity mixes, steel, concrete, transport). A future
Brightway-backed provider is the same interface fed by `lca.inventory`;
nothing above tier 3 changes when it arrives.

### Orchestrator changes

One call site: `chain.offer(demand)` in place of `glossary.resolve(flow)`, plus
logging `offer.provenance`. The loop, the Queue and the depth/node budgets are
untouched.

## 3. Attribution

`Settings` gains two typed fields beside its existing free-form `values`
mapping:

```python
@dataclass(frozen=True)
class Settings:
    values: dict[str, Any] = field(default_factory=dict)
    attribution: AttributionSettings = AttributionSettings()
    proxy: ProxySettings = ProxySettings()
```

`values` stays what it is — the open namespace a model may read keys from. The
two new fields are closed and typed, because they are the run's normative
choices and a typo in a dict key must not silently select a different ethics.

The Orchestrator owns the run's `Settings` and hands them to the Runner at
construction (`Runner(chain, settings=...)`), which is how allocation reaches
the place that enforces it. Models continue to receive their own `Settings` at
construction as they do today.

Run-wide, enforced, recorded.

```python
@dataclass(frozen=True)
class AttributionSettings:
    allocation: str = "none"        # none | mass | economic | energy | substitution
    capital:    str = "per_output"  # per_output | per_year | first_life
    reuse:      str = "first_life"  # first_life | shared
```

### Co-product properties

Partitioning needs the quantity being partitioned on, so `Exchange` gains:

```python
@dataclass(frozen=True)
class Property:
    name: str
    value: float
    unit: str

# on Exchange:
properties: tuple[Property, ...] = ()
```

A tuple rather than a mapping so `Exchange` stays hashable: `Flow` is an
aggregation key and `QueueItem` is a frozen dataclass, and a dict field would
make the hashability of both depend on which fields happen to be populated.

### Runner enforcement

The Runner already checks that production covers the demand. It now also
applies the allocation rule before the Result is logged:

| `allocation` | Behaviour |
|---|---|
| `none` | Co-products in `production` are an error. Model it monofunctionally or choose a rule. |
| `mass` / `economic` / `energy` | Compute the demanded product's share from the named property; scale the **whole** Result — technosphere and biosphere — by that share. |
| `substitution` | The co-product is pushed onto the queue as a **negative** demand: the avoided burden, traversed like any other and subtracted. |

A co-product missing the property the rule needs raises `MissingProperty`,
naming the model and the co-product. Never a guessed default.

`substitution` is the only rule that changes the traversal, by admitting
negative demands. The production check still applies to the demanded product
only.

### Model capability declaration

```python
class Model:
    supports: frozenset[str] = frozenset({"none"})
```

A run whose `allocation` a model does not support raises
`UnsupportedAttribution`, naming both. theory.md is explicit that a model may
limit how far user settings reach; this makes that limit audible instead of
letting the model quietly do something else.

### Capital and reuse

The amortization currently inside the DAC fleet model moves to
`trailrunner.attribution.amortize(...)` so every model does it identically:

- `per_output` — over the asset's lifetime output
- `per_year` — equal annual share
- `first_life` — all of it in the build year

`reuse` answers theory.md's second-life question the same way: whether initial
production is attributed entirely to the first life or shared across lives.

### Recording

Each node records the rule applied and the shares computed.
`report.attribution` summarizes them into one table: which normative choices
produced this number. That table is the point — the value judgements are
machine-readable rather than buried in a methods appendix.

## 4. Surfaces

Three thin readers. None owns logic.

### Report ergonomics

- `report.summary()` — one printed block: nodes visited, inventory size,
  unresolved counts by reason, proxies used, attribution rules applied,
  truncated or not.
- `report.tree()` — indented text tree of the traversal, each line tagged
  `[model]`, `[proxy: location CH→RER]`, `[background]`,
  `[cutoff: no_model_found]`. One screenful showing both the supply chain and
  how honestly each node was answered.
- `report.to_dataframe()`, `assessment.to_dataframe()` — pandas out. pandas is
  not a core dependency; these import it lazily and raise naming the extras
  that provide it (`[dynamic]`, `[viz]`). The parquet log remains the
  dependency-free way out.

### viz

Extra `[viz]`, plotly:

- `sankey(report, assessment=None)` — width by contribution when an assessment
  is given; proxy nodes grey, background nodes hatched.
- `curve(dynamic_assessment)` — the characterized time series and its
  cumulative integral.
- `contributions(assessment)` — ranked bars, per flow and per node.

### CLI

`trailrunner/cli.py`, stdlib `argparse`, no new dependency:

```
trailrunner run <product-iri> --amount 1000 --unit kg --location CH --year 2030 \
    --models mymodels.py --method gwp100.parquet --dynamic radiative_forcing \
    --allocation economic --out report.parquet
```

Prints `report.summary()` and the tree; writes the parquet log.

## 5. Showcase

`docs/showcase.md`, in the nav as *5-minute tour*. One demand — **1000 kg CO₂
captured, Switzerland, 2030** — in seven beats. Each beat is a section: one
code cell, its real output, one punchline.

| # | ~time | Beat | Punchline |
|---|---|---|---|
| 1 | 0:30 | A matrix row is a fixed coefficient | Real processes depend on where and when. That cannot live in a number. |
| 2 | 0:45 | `DirectAirCapture.apply()` — ambient penalty, full demand not unit demand | The process *is* the code. |
| 3 | 0:45 | `report.tree()` — heat → gas → pipeline transport, cutoffs tagged inline | Every node says how honestly it was answered. |
| 4 | 0:45 | Nothing matches → PyST `skos:broader` walk, then the background tier | We generalise on purpose, along a declared hierarchy, and we log it. |
| 5 | 0:45 | `allocation="economic"` → `"substitution"` | Value judgements are flags, not appendices. |
| 6 | 1:00 | `assess_dynamic("radiative_forcing")` — the 2027 construction pulse against 2030+ capture | Nothing else produces this without rebuilding a matrix. |
| 7 | 0:20 | `report.summary()` | Parquet in, parquet out, every choice on the record. |

Beat 6 is the argument; the rest is craft. If time is cut on stage, beats 1, 2,
6 survive.

**Mechanics.** Figures are pre-rendered and committed — no network and no
compute at build or presentation time. `dev/build_showcase_assets.py`
regenerates them from `examples/showcase.ipynb`, which contains the same code
the page displays. Presenter notes live in collapsed `??? note` blocks so the
page reads correctly to a stranger and still cues the speaker.

## Phases

Four weeks. Each phase ends with `examples/` runnable and the showcase
regenerated.

### Phase 0 — foundations (~3 days)

`Property` and `Exchange.properties`; typed `AttributionSettings` on `Settings`
(carried, not yet enforced); provenance plumbing widened to carry tier and
relaxation records; `report.summary()` and `report.tree()`.

Pitch state: beats 1–3 presentable.

### Phase 1 — assessment (~1 week)

`Method` parquet reader and `uncharacterized`; `assess()`; `assess_dynamic()`
over `dynamic_characterization`; the IRI → characterization-function table;
extras `[dynamic]` and `[brightway]` with the offline method converter.

Pitch state: beat 6 exists. The hardest beat is done first, deliberately.

### Phase 2 — resolution (~1 week)

`Provider` protocol and `Offer`; `ModelProvider` refactor keeping the
`Glossary` API; `GeneralisingProvider` — time and location first, then the PyST
product walk with its on-disk cache and a pre-warmed cache in `examples/`;
`BackgroundProvider` and the curated pack; `generalisation_exhausted`;
`report.proxies`.

Pitch state: beat 4.

### Phase 3 — attribution (~4 days)

Runner enforcement of `none`, `mass`, `economic`, `energy`; then
`substitution` — negative demands through the FIFO queue — **last**, so a slip
there costs the flourish and not the phase; `amortize()` extracted from the DAC
fleet logic; `Model.supports`; `report.attribution`.

Pitch state: beat 5.

### Phase 4 — surfaces (~3 days)

`viz` (sankey, curve, contributions); the `trailrunner run` CLI.

Pitch state: the slides have pictures.

### Phase 5 — showcase and release (~3 days)

Write the page; render and commit the assets; rehearse against the clock and
cut what overruns; align the README — `tests/test_readme.py` executes the
README's code, so it has to stay true; API reference pages for the new
modules; tag 0.2.0.

## Testing

Test-driven throughout, pytest, matching v1's discipline.

- **Method**: exact CF hit, location fallback, missing CF lands in
  `uncharacterized` rather than contributing zero, provenance contents.
- **assess**: score arithmetic, `by_flow`, cumulative `by_node` over a known
  two-level graph.
- **assess_dynamic**: the DataFrame handed to `characterize` has the expected
  shape and dates; a one-emission inventory reproduces the library's own curve;
  the missing-extra path raises naming the extra.
- **Providers**: each tier in isolation against a stub chain; tier order
  respected; within-tier ambiguity still raises; `generalisation_exhausted`
  after the budget.
- **GeneralisingProvider**: location walk, time snap inside and outside
  tolerance, product `broader` walk against a **stubbed** PyST client — no test
  touches the network — and one cache-hit test proving the second lookup does
  not call out.
- **BackgroundProvider**: a pack row answers, scales linearly, terminates, and
  is tagged `linear_background`.
- **Runner allocation**: each rule on a two-co-product model; `none` with
  co-products raises; missing property raises `MissingProperty`; unsupported
  rule raises `UnsupportedAttribution`; `substitution` produces a negative
  demand that reaches the queue.
- **amortize**: the three capital rules against hand-computed figures; the DAC
  fleet result is unchanged by the extraction.
- **Surfaces**: `tree()` and `summary()` against a known report (string
  contents, not formatting); CLI end to end on the example, asserting exit code
  and that the parquet was written.
- **Showcase**: `examples/showcase.ipynb` executes in CI.

## Risks

| Risk | Mitigation |
|---|---|
| No network on stage | Every PyST lookup cached to disk, cache committed, figures pre-rendered. Non-negotiable. |
| `substitution` overruns | Last item in Phase 3; cuttable without touching anything else. |
| Background pack is manual effort | Keep it to what the demo chain hits. Resist growth. |
| Python ≥3.12 for `pyst-client` and `dynamic_characterization` | Both behind extras, lazily imported, with errors naming the extra. Core stays pyarrow-only on 3.11. |
| Six subsystems in four weeks, no slack | If something slips, cut Phase 4's viz before cutting Phase 1 or Phase 2. |

## Deferred

- Score-based Queue priority and score-based cutoff. The seam exists; nothing
  uses it.
- A live Brightway background provider.
- Concurrent Runner; linear-model result caching; cycle convergence.
- Uncertainty and Monte Carlo.
