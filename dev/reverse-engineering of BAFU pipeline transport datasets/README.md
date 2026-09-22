aa# Natural gas pipeline transport: from raw EcoSpold data to a trailrunner `Model`

How `trailrunner.models.natural_gas_pipeline_transport.NaturalGasOffshorePipelineTransport`
was reverse-engineered from the raw BAFU-2026 ecoinvent export, end to end.
Six steps, each consuming the previous one's output.

```
raw ecoSpold XML (11,947 files)
        |
        v
parse_processinformation.ipynb  --------------------------> offshore_pipeline_exchanges.csv
        |                                                    (ground truth: what the 14
        |                                                     country-specific processes
        |                                                     actually contain)
        v
processInformation.parquet, *.json
(full-corpus metadata; not used further
 by this case study, but kept as a
 general-purpose derived artifact)

BAFU-2026 v1 LCI Reports (PDF documentation)
        |
        v
build_pipeline_trailpack.py  -------> natural_gas_pipeline_params.parquet (the trailpack)
        |                                        |
        |                                        v
        |                          trailrunner/models/natural_gas_pipeline_transport.py
        |                                        |
        v                                        v
validate_pipeline_model.py  <----------  (reads both: runs the model,
(cross-checks model output          compares its output to the CSV)
 against offshore_pipeline_
 exchanges.csv)

tests/test_natural_gas_pipeline_transport.py
(pytest: pins the model's own arithmetic with a small inline
 fixture, independent of any of the files above)
```

## 1. Raw data

- `dev/BAFU ecospold/raw/ecoSpold files/` — 11,947 raw EcoSpold **v1** XML
  files (`process_<uuid>.xml`), one process each. No namespace; the process's
  core metadata lives under `dataset/metaInformation/processInformation` as
  XML attributes, and its exchanges live under `dataset/flowData` as
  `<exchange>` elements with `name`/`meanValue`/etc. as attributes too (not
  child text — easy to get wrong, see the notebook's second half).
- `dev/BAFU ecospold/raw/BAFU-2026 v1 LCI Reports/` — the ecoinvent
  documentation PDFs. Two turned out to matter:
  - *2007 - Natural gas - Faist-Emmeneger.pdf* — the original methodology
    write-up. Useful for orientation, but its worked formulas (a per-country
    distance x leakage-rate calculation) turned out **not** to match the raw
    corpus's actual numbers once tested — the raw corpus is a later,
    expanded ecoinvent vintage this report doesn't fully describe.
  - *2025 - LCI long-dist. transp. and distrib. natural gas - Bussa.pdf* —
    the report that actually corresponds to the raw corpus. Its methodology
    (a two-tier regional classification, not a per-country distance formula)
    is what `build_pipeline_trailpack.py` implements, and its Tab. 4.7
    worked example (Algeria) is what first confirmed the match.

## 2. `parse_processinformation.ipynb` — explore the corpus, isolate the case study

Run against the full 11,947-file corpus (validated on a sample first; the
notebook's schema-discovery step showed every file has the same five
`processInformation` subsections, so it went straight to the full run).

What it does, in order:
1. Parses every file's `processInformation` section into one wide DataFrame
   (`uuid`, plus every subsection's attributes prefixed by subsection name) →
   `processInformation.parquet`.
2. Exports that DataFrame as JSON, grouped by `referenceFunction_category`
   → `processInformation_by_category.json`, and again nested by a slugified
   `referenceFunction_name` within each category (excluding `notMaintained`
   rows) → `processInformation_by_category_by_name.json`. Slug collisions
   (two raw names cleaning to the same slug) are written out separately to
   `colliding_name_slugs.csv` for a manual look — mostly stripped `<`/`>`
   thresholds, not true duplicates.
3. **Narrows to the case study**: filters to
   `category == "fuels", subCategory == "natural gas"`, finds the exact name
   `"Transport, natural gas, offshore pipeline, long distance"` (14
   processes, one per origin country: AZ, DZ, GB, ID, IR, IT, LY, MY, NL, NO,
   QA, RU, UA, US).
4. Re-opens those 14 raw XML files directly (not through the DataFrame) and
   counts `<exchange>` elements per file: 11 locations have 15 exchanges,
   3 (AZ, IT, UA) have only 6 — the first sign that something is
   systematically different about those three.
5. Parses every exchange's `name`/`meanValue`, pivots to
   exchange name x location, and splits the result into exchanges present at
   all 14 locations ("common": pipeline infrastructure, compressor fuel,
   maintenance/disposal, the reference product itself) versus present at
   only 11 ("non-common": the leakage-driven air emissions — Methane,
   Ethane, Propane, Butane, CO2, Mercury, NMVOC, Halon 1211, HFC-23) →
   **`offshore_pipeline_exchanges.csv`**, the ground-truth table everything
   downstream is checked against.

## 3. `build_pipeline_trailpack.py` — turn the PDF's methodology into parameters

Reads the 2025 Bussa report's tables (3.1 generic gas composition; 4.4/4.6
the two-tier energy-use and leakage-rate constants; 4.7 the Algeria worked
example) and encodes them as a 14-row, location-keyed parquet — the
[trailpack](https://github.com/TimoDiepers/trailpack) format trailrunner
models read via `ParameterSet.from_parquet(...)`. Every location is tagged
`tier = "high"` (AZ, DZ, ID, IR, LY, MY, QA, RU — former Soviet Union,
Middle East, Africa, Asia, Latin America) or `tier = "low"` (GB, IT, NL, NO,
UA, US — Europe, North America); the two tiers carry different leakage and
compressor-energy rate constants, but the same generic gas composition.
Output: **`natural_gas_pipeline_params.parquet`** (gitignored, regenerate
with `python build_pipeline_trailpack.py`).

The module docstring is the fullest account of the derivation, including the
one number (gas-turbine combustion energy, MJ/tkm) that couldn't be
independently re-derived from primitives and is instead taken directly from
the report's own worked example.

## 4. `trailrunner/models/natural_gas_pipeline_transport.py` — the model

`NaturalGasOffshorePipelineTransport(Model)`. Reads one row of the trailpack
per `apply(demand)` call (`self.params.at(location=..., time=...)`) and
derives every exchange from it: the leaked gas volume is
`leakage_rate_per_1000km / gas_density` (the pure function
`leaked_volume_nm3_per_tkm`), the seven composition-driven biosphere flows
are that volume times the generic composition fraction, and the two
gas-turbine/infrastructure/maintenance exchanges are tier constants scaled
by the demand amount. `coverage` is restricted to exactly the 14 locations
the trailpack has rows for. This is the file that actually ships in the
`trailrunner` package (`tests/test_natural_gas_pipeline_transport.py` is its
pytest suite — 8 tests against a small inline fixture, independent of the
real trailpack or CSV).

## 5. `validate_pipeline_model.py` — does the model reproduce reality?

Loads the real trailpack, runs the model for all 14 locations at a 1 tkm
demand, and diffs every resulting exchange against
`offshore_pipeline_exchanges.csv`. Result: 172 of 183 comparable
location x exchange pairs match within 5% (most within 1%, several exact);
the rest are all the NMVOC exchange, consistently ~9.3% high everywhere.
For AZ/IT/UA — which the trailpack's tier/composition data fully covers, but
whose raw XML has no biosphere exchange rows at all — the model computes
values anyway and the script flags this explicitly as "model computes, CSV
has no row," since the CSV's gap looks like a data-export omission rather
than a physical zero (the report says the Halon/HFC-23 constants are used
"for long-distance transport in all countries," yet AZ/IT/UA have none).

Run it: `python validate_pipeline_model.py`.

## Not part of this case study

`query_bafu.ipynb` explores the separate, *processed* EcoSpold2/BAFU
biosphere-mapping dataset — a different investigation from an earlier
session, unrelated to the natural gas pipeline model. It originally read a
companion `BAFU-2026 v1 LCIA Results_corrected.xlsx`, which didn't survive
the later manual move into `dev/` and was deliberately left deleted rather
than restored. `input-data/`, `.venv/`, and `pdf_text/` are gitignored
working files (the BAFU parquet export, this folder's Python environment,
and a scratch PDF-text dump used to locate tables while writing
`build_pipeline_trailpack.py`).
