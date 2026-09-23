"""How a demand finds something that can answer it."""

from trailrunner.resolution.background import (
    BackgroundDataset,
    BackgroundEntry,
    BackgroundPack,
    BackgroundProvider,
)
from trailrunner.resolution.chain import Offer, Provider, ResolutionChain
from trailrunner.resolution.generalising import (
    GeneralisingProvider,
    StaticTaxonomy,
    Taxonomy,
)
from trailrunner.resolution.models import ModelProvider
from trailrunner.resolution.pyst import PystTaxonomy, default_client

__all__ = [
    "BackgroundDataset",
    "BackgroundEntry",
    "BackgroundPack",
    "BackgroundProvider",
    "GeneralisingProvider",
    "ModelProvider",
    "Offer",
    "Provider",
    "PystTaxonomy",
    "ResolutionChain",
    "StaticTaxonomy",
    "Taxonomy",
    "default_client",
]
