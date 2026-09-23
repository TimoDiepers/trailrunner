"""The two constraints the whole package layout rests on.

Both were verified by hand, once, with grep. Three more phases get written on
top of them, and a constraint that nothing checks is a constraint that holds
until the first person who has not read the plan. So: checked here, on every
run.
"""

import ast
import io
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "trailrunner"
TRAVERSAL = ("orchestration", "core", "params")


def traversal_sources():
    for package in TRAVERSAL:
        for path in sorted((PACKAGE / package).rglob("*.py")):
            yield path, path.read_text()


def code_only(source: str) -> list[tuple[int, str]]:
    """``(line number, token)`` for every token that is not a comment or a string.

    Docstrings and comments are prose, and prose is allowed to name the
    assessment — ``Report``'s own docstring says what characterizes it, which
    is useful to a reader and is not a dependency. Everything else is code.
    """
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [
        (token.start[0], token.string)
        for token in tokens
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ]


def test_the_traversal_never_imports_the_assessment():
    """``assessment`` imports from ``orchestration``; the reverse is never
    true. An inventory is a complete deliverable on its own, and the moment a
    Queue or a Model knows what a score is, changing how flows are
    characterized becomes a reason to re-run the traversal.

    Parsed rather than grepped so that an import *inside a function* counts —
    it is still the dependency this forbids, it just does not show up in
    ``sys.modules`` until it is too late.
    """
    offenders = []
    for path, source in traversal_sources():
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [alias.name for alias in node.names]
            if any("assessment" in name for name in names):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], "the traversal must not import the assessment:\n" + "\n".join(
        offenders
    )


def test_the_traversal_never_names_the_assessment_in_code():
    """The import check alone would miss an attribute reference reached some
    other way. Comments and docstrings are exempt: naming the package in prose
    is a cross-reference, not a dependency."""
    offenders = []
    for path, source in traversal_sources():
        for number, token in code_only(source):
            if "assessment" in token:
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {token}")
    assert offenders == [], "the traversal must not reach for the assessment:\n" + "\n".join(
        offenders
    )


def test_importing_the_assessment_does_not_pull_in_pandas():
    """``method.py`` and ``static.py`` read parquet with pyarrow alone, and
    ``dynamic.py`` imports pandas lazily inside ``_require``. That is what
    lets a study score an inventory without the ``dynamic`` extra installed,
    and a stray module-scope ``import pandas`` would take it away silently —
    the tests would all still pass, in an environment that happens to have
    pandas.

    In a subprocess because pandas may well already be in *this* process's
    ``sys.modules``, put there by another test.
    """
    source = "import sys; import trailrunner.assessment; print('pandas' in sys.modules)"
    finished = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    assert finished.stdout.strip() == "False", finished.stdout + finished.stderr
