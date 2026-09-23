"""How a demand finds something that can answer it."""

from trailrunner.resolution.chain import Offer, Provider, ResolutionChain
from trailrunner.resolution.generalising import (
    GeneralisingProvider,
    StaticTaxonomy,
    Taxonomy,
)
from trailrunner.resolution.models import ModelProvider

__all__ = [
    "GeneralisingProvider",
    "ModelProvider",
    "Offer",
    "Provider",
    "ResolutionChain",
    "StaticTaxonomy",
    "Taxonomy",
]
