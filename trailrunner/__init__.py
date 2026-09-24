"""Model-based supply chain traversal for life cycle inventories."""

from trailrunner.core.errors import (
    AmbiguousModelMatch,
    DuplicateBackgroundEntry,
    DuplicateFactor,
    MissingColumns,
    MissingProperty,
    MissingUnit,
    NoModelFound,
    ParameterNotFound,
    TrailrunnerError,
    UnallocatedCoProduction,
    UnsupportedAttribution,
    ValidationError,
)
from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import AttributionSettings, ProxySettings, Settings
from trailrunner.orchestration.glossary import Glossary
from trailrunner.orchestration.orchestrator import Orchestrator
from trailrunner.orchestration.report import Report
from trailrunner.orchestration.runner import Runner
from trailrunner.params.coverage import ContextRange, Coverage
from trailrunner.params.fleet import Fleet, FleetSelection
from trailrunner.params.location import LocationHierarchy
from trailrunner.params.parameter_set import ParameterSet
from trailrunner.resolution import ModelProvider, Offer, ResolutionChain

__version__ = "0.1.0"

__all__ = [
    # Errors. Orchestrator.calculate propagates AmbiguousModelMatch,
    # ValidationError and ParameterNotFound straight to the caller, so they
    # belong here rather than behind trailrunner.core.errors. The three
    # attribution errors reach the caller by exactly the same route -- the
    # docs tell a reader to handle them -- so they are exported on the same
    # criterion rather than left for an import from trailrunner.core.errors.
    "AmbiguousModelMatch",
    "DuplicateBackgroundEntry",
    "DuplicateFactor",
    "MissingColumns",
    "MissingProperty",
    "MissingUnit",
    "NoModelFound",
    "ParameterNotFound",
    "TrailrunnerError",
    "UnallocatedCoProduction",
    "UnsupportedAttribution",
    "ValidationError",
    # Types and components.
    "AttributionSettings",
    "ContextRange",
    "Coverage",
    "Demand",
    "Exchange",
    "Fleet",
    "FleetSelection",
    "Flow",
    "Glossary",
    "LocationHierarchy",
    "Model",
    "ModelProvider",
    "Offer",
    "Orchestrator",
    "ParameterSet",
    "Property",
    "ProxySettings",
    "Report",
    "ResolutionChain",
    "Result",
    "Runner",
    "Settings",
]
