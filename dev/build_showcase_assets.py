"""Render the showcase figures from ``examples/showcase.ipynb`` to committed SVGs.

The showcase page is presented on stage, so it must need no build, no compute
and no network at presentation time. That means the figures are files in the
repository rather than something the docs build produces -- and it means they
have to come from the *same* run the page quotes its numbers from, or the
picture and the text would be two different studies.

So this script executes the notebook in a live kernel with ``nbclient``, and
then, in that same kernel, asks each figure-producing cell's variable to save
itself. The cells are found by tag (``figure:sankey``, ``figure:curve``,
``figure:contributions``); the tag names the variable the cell assigns, so
nothing here has to parse the notebook's source.

**No token is passed to the kernel.** ``PYST_AUTH_TOKEN`` is stripped from the
environment before the kernel starts, for the same reason CI runs the notebook
without one: a figure that quietly needed the network to build is a figure that
cannot be rebuilt on a plane.

**Layout is adjusted before saving**, and only here. The figures themselves set
a transparent canvas (``trailrunner.viz.figures._layout``), which is what lets
one file sit on both docs themes -- but plotly's default template still draws
its text and grid lines in a near-navy that disappears on a dark background, and
its default 700x500 canvas clips a Sankey's node labels. A mid grey reads on
both themes; the per-figure sizes in ``FIGURES`` fix the clipping. This is
presentation styling of a committed asset, not a change to what a figure means,
which is why it lives in the asset builder and not in ``trailrunner.viz``.

Run: ``uv run --extra examples --extra viz --extra dynamic python dev/build_showcase_assets.py``
Writes: ``docs/assets/showcase/{sankey,curve,contributions}.svg``
"""

import json
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "examples" / "showcase.ipynb"
ASSETS = ROOT / "docs" / "assets" / "showcase"

FIGURES = {
    # tag -> (variable the tagged cell assigns, file to write, extra layout)
    #
    # The extra layout is sizing only, and only what a 700x500 default gets
    # wrong for this particular figure: a Sankey whose node labels run off the
    # right edge, or a legend sitting on top of the secondary axis. Nothing
    # here changes a number or a colour that carries meaning.
    "figure:sankey": (
        "sankey_figure",
        "sankey.svg",
        {"width": 1500, "height": 700, "margin": {"l": 30, "r": 40, "t": 60, "b": 30}},
    ),
    "figure:curve": (
        "curve_figure",
        "curve.svg",
        {
            "width": 1000,
            "height": 560,
            "margin": {"l": 70, "r": 80, "t": 90, "b": 60},
            "legend": {"orientation": "h", "y": 1.12, "x": 0},
        },
    ),
    "figure:contributions": (
        "contributions_figure",
        "contributions.svg",
        {"width": 1000, "height": 560, "margin": {"l": 80, "r": 30, "t": 60, "b": 130}},
    ),
}

# Mid grey: ~4.5:1 against the docs' light background and against its slate
# one, so every axis title, tick and node label is legible on both.
INK = "#6c757d"
GRID = "rgba(134,142,150,0.35)"

SAVE = """
import json as _json

from trailrunner.viz import save as _save

_fig = {variable}.update_layout(
    font=dict(color="{ink}"),
    xaxis=dict(gridcolor="{grid}", zerolinecolor="{grid}"),
    yaxis=dict(gridcolor="{grid}", zerolinecolor="{grid}"),
    **_json.loads(r'''{extra}'''),
)
_save(_fig, r"{path}")
print("wrote {path}")
"""


def tagged_cells(notebook) -> dict[str, int]:
    """Tag -> index, for the tags this script knows about."""
    found = {}
    for index, cell in enumerate(notebook.cells):
        for tag in cell.get("metadata", {}).get("tags", []):
            if tag in FIGURES:
                found[tag] = index
    return found


def main() -> int:
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    present = tagged_cells(notebook)
    missing = sorted(set(FIGURES) - set(present))
    if missing:
        raise SystemExit(
            f"{NOTEBOOK.name} has no cell tagged {', '.join(missing)}; the asset "
            "builder finds figures by tag, so a retagged cell has to be retagged here too"
        )

    ASSETS.mkdir(parents=True, exist_ok=True)

    environment = {key: value for key, value in os.environ.items() if key != "PYST_AUTH_TOKEN"}
    client = NotebookClient(
        notebook,
        timeout=900,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK.parent)}},
    )
    with client.setup_kernel(env=environment):
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type == "code":
                client.execute_cell(cell, index)
        for tag, (variable, filename, extra) in FIGURES.items():
            source = SAVE.format(
                variable=variable,
                ink=INK,
                grid=GRID,
                extra=json.dumps(extra),
                path=(ASSETS / filename).as_posix(),
            )
            saver = nbformat.v4.new_code_cell(source=source)
            # Appended, then dropped again: nbclient writes the executed cell
            # back into ``notebook.cells[index]``, so the index has to exist --
            # and the notebook object must not grow a cell nobody wrote.
            notebook.cells.append(saver)
            try:
                client.execute_cell(saver, len(notebook.cells) - 1)
            finally:
                notebook.cells.pop()
            print(f"{tag:>22} -> {ASSETS / filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
