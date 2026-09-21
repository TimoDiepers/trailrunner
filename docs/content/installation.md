---
tags:
  - installation
---

# Installation

`trailrunner` needs Python 3.11 or newer. Its only runtime dependency is
[`pyarrow`](https://arrow.apache.org/docs/python/), used to read trailpack parquet files.

## From source

`trailrunner` is not on PyPI yet, so install it from the repository:

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
