---
tags:
  - installation
---

# Installation

`trailrunner` needs Python 3.11 or newer. Its only runtime dependency is
[`pyarrow`](https://arrow.apache.org/docs/python/), used to read trailpack parquet files.
Writing those files is [trailpack](https://github.com/TimoDiepers/trailpack)'s job, not
trailrunner's, so trailpack is an extra rather than a dependency.

The distribution is named `sentier-trailrunner`; the import name stays `trailrunner`.

## From source

`sentier-trailrunner` is not on PyPI yet, so install it from the repository:

```bash
git clone https://github.com/TimoDiepers/trailrunner.git
cd trailrunner
uv sync --extra dev
```

`uv sync` creates a virtual environment in `.venv` and installs the package in editable
mode together with the test dependencies.

Without `uv`:

```bash
python -m pip install -e ".[dev]"
```

## Running the example notebook

`examples/dac.ipynb` writes its own parameter files with trailpack, so it needs the
`examples` extra as well:

```bash
uv sync --extra dev --extra examples
uv run jupyter lab examples/dac.ipynb
```

trailpack needs Python 3.12 or newer, which is why the extra is marked accordingly — on
3.11 the rest of the extra installs and the notebook is the only thing you cannot run.

Without `uv`:

```bash
python -m pip install -e ".[dev,examples]"
```

## Running the tests

```bash
uv run pytest
```

## Building these docs

The documentation is built with [Zensical](https://zensical.org). Install the docs
dependencies and build or serve the site from the repository root:

=== "Serve with live reload"

    ```bash
    uv run --with-requirements docs/requirements.txt zensical serve
    ```

=== "Build once"

    ```bash
    uv run --with-requirements docs/requirements.txt zensical build
    ```

`zensical build` writes the static site to `site/`.
