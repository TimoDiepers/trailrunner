"""Characterization: a finished Report in, a score or a curve out.

This package imports from ``orchestration.report``; ``orchestration`` never
imports from here. The inventory is a complete, valid deliverable on its own,
and characterization is a separate reading of it.
"""

from trailrunner.assessment.method import CharacterizationFactor, Method
from trailrunner.assessment.static import Assessment, assess

__all__ = ["Assessment", "CharacterizationFactor", "Method", "assess"]
