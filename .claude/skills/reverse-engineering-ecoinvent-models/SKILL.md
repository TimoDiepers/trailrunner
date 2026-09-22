---
name: reverse-engineering-ecoinvent-models
description: Use when building a trailrunner Model backed by real BAFU/ecoinvent EcoSpold data and PDF documentation, or when a derived model's numbers don't reproduce the real dataset and you're not sure why.
---

# Reverse-Engineering ecoinvent Models

## Overview

Turning a raw BAFU/ecoinvent EcoSpold export plus its PDF documentation into a
validated trailrunner `Model` is archaeology, not transcription. The PDF
whose title matches your process family is often not the one that generated
the numbers actually in your corpus — there can be several vintages
covering the same process with different, incompatible methodologies. The
only way to know which one is right is to check it against real parsed
exchange data, before building anything on top of it.

## When to use

- Building a new trailrunner `Model` (see `trailrunner/core/model.py`,
  `trailrunner/models/dac.py`) whose parameters come from a real BAFU/ecoinvent
  dataset rather than being invented.
- A derived model's output doesn't match the real data and the cause isn't
  obvious — usually means the wrong PDF/methodology was trusted.
- You have two or more candidate documentation PDFs for one process family.

## The procedure

1. **Parse the raw XML into a ground-truth table first**, before touching
   any PDF. Find the process family (filter by category/name), pull every
   `<exchange>` for every location/variant, and pivot into one table:
   exchange x location. This is what everything downstream gets checked
   against — build it before you have a theory to confirm.
2. **Locate candidate PDFs, then verify — don't assume the newest or the
   best-titled one is right.** Pick a couple of characteristic real values
   from the ground-truth table and check them against each candidate
   report's own worked example/tables. The report whose formula reproduces
   real numbers is the source; a similarly-titled report that doesn't is
   documentation for a different dataset generation. This one check would
   have saved a full rebuild in the reference case (see below): a
   plausible-looking older report's per-country formula didn't reproduce the
   corpus at all; a later report's genuinely different methodology (a
   regional-tier classification, not a distance formula) matched to <1%.
3. **Derive the trailpack.** Encode the verified report's tables/formulas
   into a location-keyed parquet, with inline comments citing exactly which
   table/section each constant came from. Where a number can't be
   independently re-derived from primitives, say so and take it from the
   report's own worked example rather than reverse-engineering a plausible
   but unconfirmed formula for it.
4. **Implement the `Model`.** Follows trailrunner's existing pattern exactly:
   `self.params.at(location=, time=)` row lookup, any nonlinear/derived
   relationship as a small pure function, `Result(production=, technosphere=,
   biosphere=, provenance=)`. `coverage` should name exactly the locations
   the trailpack has rows for — not "all locations the corpus has," if the
   documentation doesn't actually cover all of them.
5. **Validate against the ground-truth table**, not just against the PDF's
   worked example. Run the model for every location the trailpack covers,
   diff every exchange against the ground-truth table, and report a
   match-rate summary. When the model computes something the ground truth
   lacks (or vice versa), don't silently drop or fabricate it — flag it
   explicitly and figure out whether it's a real physical difference or a
   gap in the source export before deciding what to do.
6. **Pin the model's own arithmetic with pytest**, independent of the real
   trailpack/CSV — a small inline fixture (2-3 rows) that asserts the
   formulas, so a later refactor can't silently drift even once the real
   data files are gone from disk.

## EcoSpold XML quirks

- **v1**: no namespace. `processInformation` subsections and `<exchange>`
  elements both carry their data as **attributes** (`elem.get("meanValue")`),
  not child text — easy to get backwards if an earlier parse in the same
  session used a different section that happened to use child elements.
- **v2**: namespaced, different structure entirely. Check which version you
  actually have before writing parsing code — don't assume from a sibling
  script.
- If in-session PDF page-rendering fails (e.g. `pdftoppm`/poppler missing),
  fall back to `pypdf` (or `pdfplumber`) text extraction and read tables
  from the extracted text directly; install the dependency into the
  project's own venv, not globally.

## Where things live

| Artifact | Lives in |
|---|---|
| Ground-truth table (parsed from raw XML) | research/derivation workspace |
| Trailpack-builder script | research/derivation workspace |
| Trailpack parquet (generated) | research/derivation workspace, gitignored; a small committed copy + short usage example can go in `examples/` once proven |
| `Model` subclass | the shipped package (e.g. `trailrunner/models/`) — no data-generation logic or raw-data dependency here |
| Validation script | research/derivation workspace |
| pytest suite | `tests/`, with an inline fixture |

The shipped package should only ever import the *finished* trailpack via
`ParameterSet`. Point back to the derivation workspace from the model's
docstring for provenance, rather than pulling raw XML/PDF-parsing code into
the package.

## Common mistakes

| Mistake | Fix |
|---|---|
| Trusting the first/best-titled PDF without checking its numbers against real data | Verify against the ground-truth table (step 2) before building anything |
| Assuming `<exchange>` child text instead of attributes (or vice versa) | Check the actual raw XML for *this* file, don't carry over a pattern from a different section/version |
| Building the trailpack before the ground-truth table exists | You'll have nothing to check the formula against — build ground truth first |
| Fitting a plausible-but-approximate formula and stopping | A formula that's off by an order of magnitude for some locations means the methodology is wrong, not that the data is noisy — keep looking for the report that actually matches |
| Silently dropping or fabricating values where model and ground truth disagree | Flag the divergence explicitly in the validation output and explain it (real difference vs. source data gap) |
| Putting the derivation script next to the `Model` in the shipped package | Keep raw-data-dependent code out of the package; only the model + finished trailpack ship |

## Reference example

`dev/reverse-engineering of BAFU pipeline transport datasets/README.md` in
the `trailrunner` repo walks this whole procedure end to end for a natural
gas pipeline transport model, including the PDF-verification failure and
recovery described in step 2 above.
