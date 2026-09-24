"""Convert the notebooks under examples/ to Markdown pages for the docs.

examples/ is the single source of truth. The notebooks are what CI executes
(see .github/workflows/showcase.yml) and what a reader can run on a plane, so
the docs pages are generated from them rather than written beside them -- a
hand-kept copy drifts, and the tour quotes numbers, which makes drift a wrong
answer rather than a stale sentence.

Everything the docs need but a notebook shouldn't carry is adapted here, on
the way out:

- plotly figures become interactive divs the docs' own JS renders
  (docs/javascripts/plotly-figures.js), because nbconvert's Markdown exporter
  has no idea what a plotly mime bundle is and silently drops it
- ANSI escapes from coloured output are stripped
- a cell's several output blocks are welded into one, as Jupyter shows them
- cells tagged ``hide-input`` are folded into a collapsed admonition
- notebook-relative links (to a sibling notebook, to a docs page, to a data
  file) are pointed at whatever the docs serve instead
- the page gets the YAML front-matter Zensical wants, and a hidden div that
  sends the edit/view buttons to the notebook rather than to this script's
  output (see docs/javascripts/source-overrides.js)

Run it from the project root before building the docs:

    python docs/convert_notebooks.py && zensical build

The generated pages are committed, so GitHub and the docs show the same thing
and a docs build needs no notebook toolchain. CI regenerates them and fails on
a diff, which is what keeps "committed" from meaning "stale".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
NOTEBOOKS_ROOT = REPO_ROOT / "examples"
DOCS_ROOT = REPO_ROOT / "docs"
GITHUB_REPO = "https://github.com/TimoDiepers/trailrunner"


def source_ref() -> str:
    """The git ref the links on a generated page point into.

    "main", because the generated pages are committed: a page written from a
    branch would otherwise carry that branch's name into main, and CI (which
    regenerates the pages and fails on a diff) would see every page differ by
    its GitHub links alone. DOCS_SOURCE_REF overrides it for a preview built
    from somewhere else.
    """
    return os.environ.get("DOCS_SOURCE_REF") or "main"


SOURCE_REF = source_ref()
GITHUB_BLOB = f"{GITHUB_REPO}/blob/{SOURCE_REF}"

# Notebook (relative to examples/) -> (page relative to docs/, icon, tags).
#
# The page path is explicit rather than derived: showcase.ipynb is the tour
# linked from the front page and the README, so it keeps the URL it has always
# had, while the two longer notebooks sit in the Examples section. Both paths
# are also in zensical.toml's nav, which is the only other place that has to
# learn about a new notebook.
NOTEBOOK_META: dict[str, tuple[str, str, list[str]]] = {
    "showcase.ipynb": (
        "showcase.md",
        "lucide/footprints",
        ["tutorial", "notebook"],
    ),
    "coproduction.ipynb": (
        "content/examples/coproduction.md",
        "lucide/split",
        ["example", "notebook", "attribution"],
    ),
    "dac.ipynb": (
        "content/examples/dac.md",
        "lucide/wind",
        ["example", "notebook", "parameters"],
    ),
}

PAGES: dict[str, Path] = {
    notebook: Path(page) for notebook, (page, _, _) in NOTEBOOK_META.items()
}

# Plotly's mime type, as stored in a notebook's display_data output.
PLOTLY_MIME = "application/vnd.plotly.v1+json"

# A figure cell's tag names the figure: `figure:sankey`. dev/build_showcase_assets.py
# reads the same tags to write the committed SVGs the pitch pages use.
FIGURE_TAG = re.compile(r"^figure:(.+)$")

# Height in CSS pixels per figure, and the bottom margin a figure with long
# category labels needs. Width is never set: the docs' JS renders these
# responsively, so the figure follows the column and the Sankey's node labels
# -- the thing the static SVGs have to fight a fixed canvas for -- have the
# reader's full window to sit in.
FIGURE_LAYOUT: dict[str, dict[str, object]] = {
    # A Sankey's node labels sit to the right of their node, so the right-hand
    # column's labels need a margin to run into rather than the canvas edge to
    # be clipped against; the height is what keeps the small nodes at the
    # bottom of the chain from stacking their labels on top of each other.
    "sankey": {"height": 780, "margin": {"l": 20, "r": 150, "t": 60, "b": 20}},
    "curve": {"height": 480, "margin": {"l": 70, "r": 70, "t": 80, "b": 60}},
    "contributions": {"height": 520, "margin": {"l": 70, "r": 20, "t": 60, "b": 150}},
}
DEFAULT_FIGURE_HEIGHT = 480

# Assets a notebook links to that the docs can render. Anything else (a parquet
# file, say) is linked on GitHub instead.
RENDERABLE_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

# Markdown lines carrying this marker are dropped from the docs page - for
# notebook-only asides that would read as nonsense once rendered.
HIDE_IN_DOCS = "<!-- hide-in-docs -->"

# Jupyter renders ```{mermaid} (the MyST spelling); the docs renderer wants a
# plain ```mermaid fence.
MERMAID_FENCE = re.compile(r"^(\s*)```\{mermaid\}", re.MULTILINE)

# A markdown link or an HTML src=/href= pointing at a notebook-relative path.
MARKDOWN_LINK = re.compile(r"(!?)\[([^\]]*)\]\((?!https?:|#|mailto:)([^)\s]+)\)")
HTML_ATTR_LINK = re.compile(r"""(src|href)=(["'])(?!https?:|#|data:)([^"']+)\2""")

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mK]")

# Pandas wraps a DataFrame's <table> in <div><style scoped>...</style>...</div>,
# and nbconvert's Markdown output does not always carry the closing </div>.
# Matching both tags in one regex silently fails when the closing tag is
# missing, which leaves an unclosed <div> and a raw <style> block in the page
# and corrupts everything after it -- so strip each half independently.
PANDAS_TABLE_STYLE_OPEN = re.compile(r"<div>\s*<style scoped>.*?</style>\s*", re.DOTALL)
PANDAS_TABLE_STYLE_CLOSE = re.compile(
    r"(</table>\s*(?:<p>[\d,]+ rows [x×] [\d,]+ columns</p>\s*)?)</div>", re.DOTALL
)

# An nbconvert output line: the 4-space indent that makes Markdown treat it as
# a code block, plus something other than whitespace on it.
INDENTED_OUTPUT_LINE = re.compile(r"^ {4}.*\S")

# A cell's whole output, as it follows the cell's code block: blank lines, then
# the indented lines Markdown reads as a code block.
CELL_OUTPUT_BLOCK = re.compile(r"\n*(?:^ {4}.*$\n?)+", re.MULTILINE)


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def figure_name(cell) -> str | None:
    """The name a cell's ``figure:<name>`` tag gives its figure, if any."""
    for tag in cell.get("metadata", {}).get("tags", []):
        match = FIGURE_TAG.match(tag)
        if match:
            return match.group(1)
    return None


def embed_plotly_figures(notebook) -> int:
    """Turn every plotly output into HTML the docs' own JS can render.

    nbconvert's Markdown exporter knows about PNG, SVG, HTML and text; a
    plotly mime bundle matches none of those blocks and vanishes without a
    warning. Rewriting the output to ``text/html`` puts it through the
    exporter's ``data_html`` block, which passes its contents through
    verbatim.

    What goes in is the figure's own JSON, unchanged, inside a
    ``<script type="application/json">`` the browser never executes. Rendering
    it is left to docs/javascripts/plotly-figures.js, for two reasons: an
    inline ``<script>`` that calls ``Plotly.newPlot`` would not run again after
    the theme's instant navigation swapped the page under it, and the figure's
    text and grid colours have to be read off the page's own palette, which
    only exists at render time -- one committed colour cannot serve both the
    light and the slate theme (the reason the static SVGs settle for a
    compromise grey; see dev/build_showcase_assets.py).

    Returns how many figures were embedded, so a notebook whose figures
    silently stopped being figures shows up as a number rather than as
    silence.
    """
    embedded = 0
    for cell in notebook.get("cells", []):
        name = figure_name(cell)
        for output in cell.get("outputs", []):
            data = output.get("data", {})
            if PLOTLY_MIME not in data:
                continue

            layout = dict(FIGURE_LAYOUT.get(name or "", {}))
            height = layout.pop("height", DEFAULT_FIGURE_HEIGHT)
            figure = json.dumps(data[PLOTLY_MIME], separators=(",", ":"))
            # A "</script>" anywhere inside the JSON (a label, a hovertemplate)
            # would end the data block early; escaping the slash is invisible
            # to JSON.parse and inert to the HTML parser.
            figure = figure.replace("</", "<\\/")

            attributes = [
                'class="plotly-figure"',
                f'data-plotly-height="{height}"',
            ]
            if name:
                attributes.append(f'data-plotly-name="{name}"')
            if layout:
                attributes.append(
                    f"data-plotly-layout='{json.dumps(layout, separators=(',', ':'))}'"
                )

            # One line, no blank lines inside: Markdown only leaves a raw HTML
            # block alone while it is unbroken.
            output["data"] = {
                "text/html": (
                    f"<div {' '.join(attributes)}>"
                    f'<script type="application/json">{figure}</script>'
                    "</div>"
                )
            }
            # A display_data output must carry a metadata dict; the plotly
            # one described a figure that is no longer here.
            output["metadata"] = {}
            embedded += 1

    return embedded


def tighten_output_blocks(body: str) -> str:
    """Drop the blank lines nbconvert leaves between a cell's output blocks.

    Outputs of different types (a stream and an execute_result, say) cannot be
    merged in the notebook, so nbconvert emits them as separate indented blocks
    separated by blank lines -- and Markdown folds adjacent indented blocks into
    one code block, turning each separator into an empty line inside the
    output. Removing every blank line that sits between two output lines makes
    a cell's outputs one contiguous block, as in Jupyter.

    Fenced blocks are skipped, so indented content inside them (the Mermaid
    diagram in the tour) is left untouched.
    """
    lines = body.split("\n")
    result: list[str] = []
    in_fence = False
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            result.append(line)
            index += 1
            continue

        if in_fence or line.strip():
            result.append(line)
            index += 1
            continue

        # A run of blank (or whitespace-only) lines: keep a single empty line,
        # unless output lines sit on both sides of it.
        end = index
        while end < len(lines) and not lines[end].strip():
            end += 1

        previous = result[-1] if result else ""
        following = lines[end] if end < len(lines) else ""
        if not (
            INDENTED_OUTPUT_LINE.match(previous)
            and INDENTED_OUTPUT_LINE.match(following)
        ):
            result.append("")
        index = end

    return "\n".join(result)


def merge_stream_outputs(notebook) -> None:
    """Merge a cell's consecutive stream outputs into one.

    Anything that flushes per line produces one ``stream`` output per line.
    nbconvert renders each as its own indented block joined by a blank line,
    and Markdown folds those into one code block full of blank lines, so a
    printed table arrives double-spaced. Concatenating adjacent streams
    (stdout and stderr alike, they render identically) collapses them.
    """
    for cell in notebook.get("cells", []):
        outputs = cell.get("outputs")
        if not outputs:
            continue

        merged = []
        for output in outputs:
            if (
                output.get("output_type") == "stream"
                and merged
                and merged[-1].get("output_type") == "stream"
            ):
                previous = merged[-1]
                previous_text = previous["text"]
                if isinstance(previous_text, list):
                    previous_text = "".join(previous_text)
                text = output["text"]
                if isinstance(text, list):
                    text = "".join(text)
                if previous_text and not previous_text.endswith("\n"):
                    previous_text += "\n"
                previous["text"] = previous_text + text
            else:
                merged.append(output)

        cell["outputs"] = merged


def collapse_hidden_input_cells(body: str, notebook_path: Path) -> str:
    """Fold code cells tagged ``hide-input`` into a collapsed admonition.

    Jupyter's own ``source_hidden`` only collapses a cell inside JupyterLab;
    nbconvert renders it as an ordinary code block, so a bootstrap cell the
    reader is meant to skip would open the page. Wrapping it in a ``???``
    block gets it rendered collapsed instead, titled from the cell's
    ``docs_summary`` metadata.
    """
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))

    for cell in notebook["cells"]:
        metadata = cell.get("metadata", {})
        if cell["cell_type"] != "code" or "hide-input" not in metadata.get("tags", []):
            continue

        source = "".join(cell["source"])
        code_block = f"```python\n{source}\n```"
        if code_block not in body:
            print(
                f"WARNING: could not fold the hide-input cell of {notebook_path.name} "
                "- its exported code block was not found verbatim",
                file=sys.stderr,
            )
            continue

        title = metadata.get("docs_summary", "Show the code")
        # The cell's outputs follow its code block as 4-space indented lines,
        # which is what makes Markdown read them as a code block. Inside the
        # admonition that indent is the content's own baseline, so they would
        # arrive as a wrapped paragraph -- they go in with the code, one indent
        # deeper, and stay a block of output.
        start = body.index(code_block)
        end = start + len(code_block)
        outputs = CELL_OUTPUT_BLOCK.match(body, end)
        if outputs:
            end = outputs.end()

        folded = indent_block(code_block)
        if outputs:
            # A blank line between them, or Markdown reads the output as more of
            # the fenced block's own text rather than as a block of its own.
            folded += "\n\n" + indent_block(outputs.group(0).strip("\n"))
        body = body[:start] + f'??? note "{title}"\n\n{folded}\n' + body[end:]

    return body


def indent_block(block: str) -> str:
    """*block*, one admonition level deeper, leaving blank lines blank."""
    return "\n".join(
        f"    {line}" if line.strip() else "" for line in block.split("\n")
    )


def drop_hidden_lines(body: str) -> str:
    """Drop the markdown lines a notebook marks as notebook-only."""
    return "\n".join(line for line in body.split("\n") if HIDE_IN_DOCS not in line)


def rewrite_target(target: str, notebook_rel: str, copied: set[Path]) -> str | None:
    """Rewrite one notebook-relative link *target* for the docs page.

    A notebook links to its siblings and to the docs with paths that work
    while reading it in Jupyter or on GitHub. On a docs page those paths mean
    nothing, so:

    - a link to a published notebook becomes a link to its page,
    - a link to a docs page becomes a link relative to this page,
    - a renderable asset (an image) is copied next to the pages and linked
      there,
    - anything else in examples/ (a parquet file, a module) becomes a GitHub
      link.

    Returns None for targets that are not repository-relative (nbconvert's own
    output_N_M.png refs, anchors, ...), which the caller leaves untouched.
    """
    path, _, anchor = target.partition("#")
    if not path:
        return None

    resolved = (NOTEBOOKS_ROOT / path).resolve()
    page_dir = (DOCS_ROOT / PAGES[notebook_rel]).parent
    suffix = f"#{anchor}" if anchor else ""

    def relative_to_page(destination: Path) -> str:
        return os.path.relpath(destination, page_dir) + suffix

    try:
        rel_to_docs = resolved.relative_to(DOCS_ROOT.resolve())
    except ValueError:
        pass
    else:
        if not resolved.exists():
            print(
                f"WARNING: {notebook_rel} links to {target}, which is not in docs/",
                file=sys.stderr,
            )
            return None
        return relative_to_page(DOCS_ROOT / rel_to_docs)

    try:
        rel_to_notebooks = resolved.relative_to(NOTEBOOKS_ROOT.resolve())
    except ValueError:
        return None
    if not resolved.exists():
        print(
            f"WARNING: {notebook_rel} links to {target}, which does not exist",
            file=sys.stderr,
        )
        return None

    rel_posix = rel_to_notebooks.as_posix()

    if rel_posix in PAGES:
        return relative_to_page(DOCS_ROOT / PAGES[rel_posix])

    if resolved.suffix.lower() in RENDERABLE_ASSET_SUFFIXES:
        destination = DOCS_ROOT / "assets" / "examples" / resolved.name
        if destination not in copied:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolved, destination)
            copied.add(destination)
        return relative_to_page(destination)

    return f"{GITHUB_BLOB}/examples/{rel_posix}{suffix}"


def rewrite_notebook_relative_links(
    body: str, notebook_rel: str, files_dir_name: str, copied: set[Path]
) -> str:
    """Point every notebook-relative link in *body* at something the docs serve."""

    def markdown(match: re.Match) -> str:
        bang, text, target = match.groups()
        if target.startswith(f"{files_dir_name}/"):
            return match.group(0)  # an image nbconvert just extracted
        rewritten = rewrite_target(target, notebook_rel, copied)
        return match.group(0) if rewritten is None else f"{bang}[{text}]({rewritten})"

    def html(match: re.Match) -> str:
        attribute, quote, target = match.groups()
        rewritten = rewrite_target(target, notebook_rel, copied)
        if rewritten is None:
            return match.group(0)
        return f"{attribute}={quote}{rewritten}{quote}"

    body = MARKDOWN_LINK.sub(markdown, body)
    return HTML_ATTR_LINK.sub(html, body)


def convert(notebook_rel: str, icon: str, tags: list[str], copied: set[Path]) -> Path:
    """Convert one notebook to its docs page and return the page's path."""
    try:
        import nbformat
        from nbconvert.exporters import MarkdownExporter
    except ImportError:
        print(
            "nbconvert is not installed. Run: uv sync --extra docs",
            file=sys.stderr,
        )
        sys.exit(1)

    notebook_path = NOTEBOOKS_ROOT / notebook_rel
    md_path = DOCS_ROOT / PAGES[notebook_rel]
    output_dir = md_path.parent
    files_dir_name = f"{md_path.stem}_files"
    files_dir = output_dir / files_dir_name

    notebook = nbformat.read(str(notebook_path), as_version=4)
    merge_stream_outputs(notebook)
    figures = embed_plotly_figures(notebook)

    exporter = MarkdownExporter()
    # from_notebook_node rather than from_filename, so the rewritten outputs
    # above are what gets exported. Leaving resources["unique_key"] unset keeps
    # extracted image names at output_<cell>_<index>.png.
    body, resources = exporter.from_notebook_node(
        notebook, resources={"metadata": {"path": str(notebook_path.parent)}}
    )

    body = strip_ansi(body)

    # Squeeze out the blank lines between a cell's output blocks. Runs before
    # the hide-input folding below, whose indented admonition bodies rely on
    # their own blank lines.
    body = tighten_output_blocks(body)
    body = collapse_hidden_input_cells(body, notebook_path)

    # Unwrap a pandas DataFrame down to its bare <table>, matching what the
    # Markdown table extension emits: the theme's own JS wraps every <table> at
    # runtime, so a pre-wrapped one ends up double-wrapped and mis-aligned.
    body = PANDAS_TABLE_STYLE_OPEN.sub("", body)
    body = PANDAS_TABLE_STYLE_CLOSE.sub(r"\1", body)
    body = body.replace('<table border="1" class="dataframe">', "<table>")

    # Rewrite bare image refs ![png](output_N_M.png)
    # -> ![png](<stem>_files/output_N_M.png)
    body = re.sub(
        r"!\[([^\]]*)\]\((?!http)(output_[^)]+\.png)\)",
        rf"![\1]({files_dir_name}/\2)",
        body,
    )

    # An image pasted into a markdown cell is extracted under its own filename
    # rather than the output_N_M.png convention above, so the regex misses it.
    for output_filename in resources.get("outputs", {}):
        if output_filename.startswith("output_"):
            continue
        body = re.sub(
            rf"!\[([^\]]*)\]\((?!http){re.escape(output_filename)}\)",
            rf"![\1]({files_dir_name}/{output_filename})",
            body,
        )

    body = rewrite_notebook_relative_links(body, notebook_rel, files_dir_name, copied)
    body = MERMAID_FENCE.sub(r"\1```mermaid", body)
    body = drop_hidden_lines(body)

    # The edit/view buttons point at the notebook this page was generated from,
    # not at the generated Markdown (see docs/javascripts/source-overrides.js).
    source_path = f"examples/{notebook_rel}"
    source_override = (
        "\n"
        f'<div hidden data-source-edit-url="{GITHUB_REPO}/edit/{SOURCE_REF}/{source_path}" '
        f'data-source-view-url="{GITHUB_BLOB}/{source_path}"></div>\n'
        # Markdown ends a raw HTML block at a blank line, and not before: without
        # this one the notebook's opening heading is swallowed into the div.
        "\n"
    )

    tags_yaml = "\n".join(f"  - {tag}" for tag in tags)
    frontmatter = (
        "---\n"
        f"icon: {icon}\n"
        f"tags:\n{tags_yaml}\n"
        "---\n"
        "\n"
        f"<!-- Generated from examples/{notebook_rel} by docs/convert_notebooks.py.\n"
        "     Edit the notebook, then re-run the script; edits here are lost. -->\n"
    )

    body = frontmatter + source_override + body

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(body, encoding="utf-8")

    output_images = resources.get("outputs", {})
    if output_images:
        files_dir.mkdir(parents=True, exist_ok=True)
        for filename, data in output_images.items():
            (files_dir / filename).write_bytes(data)

    print(
        f"Converted examples/{notebook_rel} -> {md_path.relative_to(REPO_ROOT)}"
        + (f" ({figures} figures)" if figures else "")
    )
    return md_path


def main() -> None:
    copied: set[Path] = set()
    for notebook_rel, (_, icon, tags) in NOTEBOOK_META.items():
        if not (NOTEBOOKS_ROOT / notebook_rel).exists():
            print(f"WARNING: notebook not found: {notebook_rel}", file=sys.stderr)
            continue
        convert(notebook_rel, icon, tags, copied)


if __name__ == "__main__":
    main()
