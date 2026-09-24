---
icon: lucide/download
tags:
  - installation
---

# Installation

`trailrunner` needs Python 3.11 or newer. Its only runtime dependency is
[`pyarrow`](https://arrow.apache.org/docs/python/), which reads the parquet files
parameters, methods and background packs come in and writes the run log out. Everything
else is an optional extra.

The distribution is named `sentier-trailrunner`; the import name and the command are both
`trailrunner`.

## From source

`sentier-trailrunner` is not on PyPI yet, so install it from the repository:

```bash
git clone https://github.com/TimoDiepers/trailrunner.git
cd trailrunner
uv sync --extra dev
```

`uv sync` creates a virtual environment in `.venv` and installs the package in editable
mode, together with the test dependencies and the `trailrunner` command. Check it:

```bash
uv run trailrunner --help
```

Without `uv`:

```bash
python -m pip install -e ".[dev]"
```

## Extras

Add whichever of these you need to the `uv sync` line (`uv sync --extra dev --extra viz`)
or the pip brackets (`".[dev,viz]"`):

| Extra | Pulls in | Needed for |
| --- | --- | --- |
| `dev` | pytest | running the test suite |
| `dynamic` | [`dynamic_characterization`](https://github.com/brightway-lca/dynamic_characterization), pandas | [`assess_dynamic()`](assessment.md#assess_dynamic-a-time-explicit-reading) and `trailrunner run --dynamic` |
| `viz` | plotly, kaleido, pandas | the [figures](figures.md), and `Report.to_dataframe()` |
| `examples` | [trailpack](https://github.com/TimoDiepers/trailpack), pandas, JupyterLab | the notebooks in `examples/` that write their own parameter files |
| `brightway` | bw2data | `dev/convert_brightway_method.py`, an offline converter; trailrunner never imports bw2data at runtime |
| `docs` | Zensical, mkdocstrings | building this site |

`dynamic_characterization`, trailpack and bw2data require Python 3.12 or newer (trailpack
also below 3.14), and their extras carry matching markers: on an older interpreter the
rest of the extra installs and only the feature that needs that package is unavailable.

Writing trailpack files is trailpack's job, not trailrunner's, so trailpack is an extra
rather than a dependency: trailrunner reads the files it writes with pyarrow alone.

## Running the examples

```bash
uv sync --extra dev --extra examples --extra viz --extra dynamic
uv run jupyter lab examples/
```

| Notebook | What it shows |
| --- | --- |
| `examples/showcase.ipynb` | the [5-minute tour](../showcase.md): one cement demand through all three resolution tiers, a dated inventory and its curve |
| `examples/coproduction.ipynb` | the same demand with a co-producing CHP behind its electricity, under three [allocation rules](attribution.md) |
| `examples/dac.ipynb` | direct air capture end to end, including writing the parameter files with trailpack |

`examples/showcase_models.py` wires the shipped cement, electricity and gas models to the
parameter files beside it. It is also what the [CLI tutorial](getting_started/cli.md)
runs.

## Running the tests

```bash
uv run pytest
```

## Building these docs

The documentation is built with [Zensical](https://zensical.org). From the repository
root:

=== "Serve with live reload"

    ```bash
    uv run --with-requirements docs/requirements.txt zensical serve
    ```

=== "Build once"

    ```bash
    uv run --with-requirements docs/requirements.txt zensical build
    ```

`zensical build` writes the static site to `site/`.
