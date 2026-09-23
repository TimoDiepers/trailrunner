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
import re
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
    # A Sankey's node labels are the one place where the canvas size is a
    # legibility decision rather than a clipping one. The docs render this SVG
    # into a column around 800px wide, so a 1500px canvas scales every glyph
    # down by nearly half: 12px text arrives at about 6px and cannot be read
    # from a seat. A narrower canvas with larger text lands close to 1:1.
    "figure:sankey": (
        "sankey_figure",
        "sankey.svg",
        {
            "width": 1150,
            "height": 760,
            "margin": {"l": 30, "r": 40, "t": 60, "b": 30},
            "font": {"size": 18},
        },
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

# Mid grey: 4.66:1 against the docs' light background and 3.5:1 against its
# slate one. No colour passes 4.5:1 against both -- white needs a luminance
# below 0.183 and slate needs one above 0.236 -- so the type size carries the
# rest of the way; see BASE_LAYOUT.
INK = "#6c757d"
GRID = "rgba(134,142,150,0.35)"

BASE_LAYOUT = {
    # 14px rather than plotly's 12px default. INK is 4.66:1 against the docs'
    # light background and 3.5:1 against its slate one, and no single colour
    # can pass 4.5:1 against both -- the luminance windows do not overlap. At
    # 14px and up that 3.5:1 clears the large-text threshold on the dark theme
    # while staying comfortably above 4.5:1 on the light one, which a
    # media-query inside the SVG could not guarantee: the docs also offer a
    # manual theme toggle that a prefers-color-scheme rule cannot see.
    "font": {"color": INK, "size": 14},
    "xaxis": {"gridcolor": GRID, "zerolinecolor": GRID},
    "yaxis": {"gridcolor": GRID, "zerolinecolor": GRID},
}


def layout_for(extra: dict) -> dict:
    """``BASE_LAYOUT`` with one figure's overrides merged one level deep.

    One level is the whole requirement and the reason this is not a plain
    ``{**BASE_LAYOUT, **extra}``: a figure that sets its own font size would
    otherwise replace the whole font dict and silently drop the INK colour
    that makes the text legible on both docs themes.
    """
    merged = {key: dict(value) for key, value in BASE_LAYOUT.items()}
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


SAVE = """
import json as _json

from trailrunner.viz import save as _save

_fig = {variable}.update_layout(**_json.loads(r'''{layout}'''))
_save(_fig, r"{path}")
print("wrote {path}")
"""


TEXT_SHADOW = re.compile(r"text-shadow: [^;\"]*;?\s*")


def strip_text_shadow(path: Path) -> int:
    """Remove plotly's white halo from a saved SVG's text.

    Plotly draws Sankey node labels with a hardcoded four-way white
    ``text-shadow``, so that a label sitting on top of a coloured node bar
    stays readable. It is not reachable from ``update_layout``: it is written
    straight into the element's style.

    Here it does only harm. These labels sit *beside* their nodes, on the
    canvas, never on top of them -- and the canvas is transparent, because one
    committed file has to sit on both docs themes. So the halo is a white blur
    around grey text on the light theme, and a white glow around grey text on
    the dark one. Both read as badly rendered rather than as emphasis.

    Returns how many declarations were removed, so a plotly version that stops
    emitting them shows up as a zero rather than as silence.
    """
    svg = path.read_text()
    cleaned, count = TEXT_SHADOW.subn("", svg)
    if count:
        path.write_text(cleaned)
    return count


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
                layout=json.dumps(layout_for(extra)),
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
            removed = strip_text_shadow(ASSETS / filename)
            halo = f"  (stripped {removed} text-shadow)" if removed else ""
            print(f"{tag:>22} -> {ASSETS / filename}{halo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
