"""One command, so a run can be shown without a notebook.

Deliberately stdlib-only argparse: a CLI is a convenience, and a convenience
that adds a dependency to every install is not one.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from trailrunner.core.flow import Demand, Flow
from trailrunner.core.settings import AttributionSettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator


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
    run.add_argument("--max-depth", type=int, default=10)
    run.add_argument("--max-nodes", type=int, default=1000)
    run.add_argument("--out", default=None, help="write the parquet log here")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = Settings(
            attribution=AttributionSettings(allocation=args.allocation, capital=args.capital)
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
        flow=Flow(iri=args.iri, location=args.location, time=args.year),
        amount=args.amount,
        unit=args.unit,
    )
    orchestrator = Orchestrator(
        Glossary(models),
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
            f"{dynamic.total:g} {dynamic.cumulative_unit}"
        )
        # The gaps travel with the number, the same way the static path's do.
        print(dynamic.summary())

    if args.out:
        report.log.to_parquet(args.out)
        print(f"\nwrote {args.out}")
    return 0
