"""Model-based supply chain traversal for life cycle inventories."""

from trailrunner.core.errors import (
    AmbiguousModelMatch,
    NoModelFound,
    ParameterNotFound,
    TrailrunnerError,
    ValidationError,
)
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.orchestration.report import Report
from trailrunner.orchestration.runner import Runner
from trailrunner.params.coverage import Coverage
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet

__version__ = "0.1.0"

__all__ = [
    # Errors. Orchestrator.calculate propagates AmbiguousModelMatch,
    # ValidationError and ParameterNotFound straight to the caller, so they
    # belong here rather than behind trailrunner.core.errors.
    "AmbiguousModelMatch",
    "NoModelFound",
    "ParameterNotFound",
    "TrailrunnerError",
    "ValidationError",
    # Types and components.
    "Coverage",
    "Demand",
    "Exchange",
    "Flow",
    "Glossary",
    "LocationHierarchy",
    "Model",
    "Orchestrator",
    "ParameterSet",
    "Report",
    "Result",
    "Runner",
    "Settings",
]
