"""One command, so a run can be shown without a notebook.

Deliberately stdlib-only argparse: a CLI is a convenience, and a convenience
that adds a dependency to every install is not one.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from trailrunner.core.errors import UnknownUnit
from trailrunner.core.flow import Demand, Flow
from trailrunner.core.settings import AttributionSettings, ProxySettings, Settings
from trailrunner.core.time import in_year
from trailrunner.core.units import default_catalog, symbol
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.resolution import GeneralisingProvider, ModelProvider, ResolutionChain


def load_models(path: Path) -> list:
    """Import a .py file by path and return its ``MODELS`` list."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"cannot import models from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    models = getattr(module, "MODELS", None)
    if models is None:
        raise AttributeError(f"{path} defines no MODELS list")
    return list(models)


def parse_context_tolerance(values: list[str] | None) -> dict[str, tuple[float, float, str]]:
    """``["pressure=0:1e5 Pa"]`` -> ``{"pressure": (0.0, 1e5, PA)}``: below, above, unit.

    The unit is resolved through ``default_catalog()``, so it may be written
    as a symbol (``Pa``), a vocabulary id (``PA``) or the full IRI. A
    condition given twice is refused rather than the last one winning: two
    tolerances for one condition is a typo, not a preference.
    """
    tolerance: dict[str, tuple[float, float, str]] = {}
    for value in values or []:
        name, sep, rest = value.partition("=")
        bounds, _, unit_text = rest.partition(" ")
        below, colon, above = bounds.partition(":")
        if name in tolerance:
            raise ValueError(f"context tolerance for {name!r} is given more than once")
        malformed = ValueError(
            f"{value!r} is not a context tolerance; write NAME=BELOW:ABOVE UNIT, "
            "e.g. pressure=0:1e5 Pa"
        )
        if not (name and sep and colon and unit_text):
            raise malformed
        try:
            below_bound, above_bound = float(below), float(above)
        except ValueError:
            raise malformed from None
        try:
            unit = default_catalog().resolve(unit_text)
        except UnknownUnit as exc:
            raise ValueError(f"{value!r} is not a context tolerance: {exc}") from None
        tolerance[name] = (below_bound, above_bound, unit)
    return tolerance


def parse_proxy_order(value: str | None) -> tuple[str | tuple[str, ...], ...]:
    """``"context.pressure,context.pressure+context.temperature"`` -> an order.

    Commas separate entries, tried left to right; ``+`` joins the members of
    one combined entry. Only context dimensions: the CLI has no location
    hierarchy or product taxonomy to relax along, and an order naming them
    would promise relaxations it cannot make.
    """
    if value is None:
        return ("context",)
    order: list[str | tuple[str, ...]] = []
    for entry in value.split(","):
        members = tuple(member.strip() for member in entry.split("+"))
        for member in members:
            if member != "context" and not member.startswith("context."):
                raise ValueError(
                    f"{member!r} is not a context dimension; --proxy-order takes "
                    "context and context.<name> only"
                )
        order.append(members[0] if len(members) == 1 else members)
    return tuple(order)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trailrunner", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="traverse a demand and report")
    run.add_argument("iri", help="product IRI to demand")
    run.add_argument("--amount", type=float, required=True)
    run.add_argument("--unit", required=True)
    run.add_argument("--location", default=None)
    run.add_argument("--year", type=int, default=None)
    run.add_argument("--models", required=True, help="a .py file exposing MODELS")
    run.add_argument("--method", default=None, help="a method parquet; prints a score")
    run.add_argument("--dynamic", default=None, help="a dynamic metric, e.g. radiative_forcing")
    run.add_argument("--horizon", type=int, default=100)
    run.add_argument("--allocation", default="none")
    run.add_argument("--capital", default="per_output")
    run.add_argument(
        "--context-tolerance",
        action="append",
        metavar="NAME=BELOW:ABOVE UNIT",
        help="let a context condition be met this far below/above what was asked, "
        'in the unit named (symbol, vocabulary id or IRI), e.g. "pressure=0:1e5 Pa"; '
        "repeatable",
    )
    run.add_argument(
        "--proxy-order",
        default=None,
        metavar="ORDER",
        help="which context relaxations to try, in order: comma-separated, + to relax "
        "together, e.g. context.pressure,context.pressure+context.temperature "
        "(default: context, one condition at a time)",
    )
    run.add_argument("--max-depth", type=int, default=10)
    run.add_argument("--max-nodes", type=int, default=1000)
    run.add_argument("--out", default=None, help="write the parquet log here")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        context_tolerance = parse_context_tolerance(args.context_tolerance)
        settings = Settings(
            attribution=AttributionSettings(allocation=args.allocation, capital=args.capital),
            # Context only. The CLI has no location hierarchy or taxonomy to
            # relax along, and a flag about pressure should not quietly start
            # moving years as well.
            proxy=ProxySettings(
                order=parse_proxy_order(args.proxy_order),
                context_tolerance=context_tolerance,
            ),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        models = load_models(Path(args.models))
    except (FileNotFoundError, AttributeError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    demand = Demand(
        flow=Flow(
            iri=args.iri,
            location=args.location,
            **(in_year(args.year) if args.year is not None else {}),
        ),
        amount=args.amount,
        # A stop-gap: Task 11 replaces this with proper error handling for a
        # unit the catalog does not know.
        unit=default_catalog().resolve(args.unit),
    )
    tier1 = ModelProvider(Glossary(models))
    providers = [tier1]
    if context_tolerance:
        providers.append(GeneralisingProvider(tier1, settings=settings.proxy))
    orchestrator = Orchestrator(
        ResolutionChain(providers),
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        settings=settings,
    )
    report = orchestrator.calculate(demand)

    print(report.summary())
    print()
    print(report.tree())

    if args.method:
        from trailrunner.assessment import Method, assess

        assessment = assess(report, Method.from_parquet(args.method))
        print()
        print(assessment.summary())

    if args.dynamic:
        from trailrunner.assessment import assess_dynamic

        dynamic = assess_dynamic(report, metric=args.dynamic, horizon=args.horizon)
        print()
        # cumulative_unit, not unit: total is the integral of the series, and
        # for radiative forcing those are different dimensions.
        print(
            f"{dynamic.metric} over {dynamic.horizon} years: "
            f"{dynamic.total:g} {symbol(dynamic.cumulative_unit)}"
        )
        # The gaps travel with the number, the same way the static path's do.
        print(dynamic.summary())

    if args.out:
        report.log.to_parquet(args.out)
        print(f"\nwrote {args.out}")
    return 0
