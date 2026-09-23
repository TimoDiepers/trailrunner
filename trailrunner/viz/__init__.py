"""Pictures of a Report or an Assessment.

Behind the ``[viz]`` extra: ``plotly`` (and ``kaleido``, for ``save()``) are
imported lazily inside each function, so ``import trailrunner`` keeps working
with pyarrow alone, and importing ``trailrunner.viz`` itself costs nothing
until a figure is actually drawn.
"""

from trailrunner.viz.figures import TIER_COLOURS, contributions, curve, sankey, save

__all__ = ["TIER_COLOURS", "contributions", "curve", "sankey", "save"]
