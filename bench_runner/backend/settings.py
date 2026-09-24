"""Backend-level constants for the BIM API layer.

Deliberately tiny and agent-INDEPENDENT: the backend (Archicad/Tapir + Revit) is imported by
the agent AND by the bench harness, so it must not reach into an agent package for config.
"""
from authoring_framework.tools.target import (BIM_TARGETS, REVIT_ROUTES_URL, bim_target,
                                              set_target_override)

# Default wall height (m) for created walls when the caller gives none.
WALL_HEIGHT = 2.7

__all__ = ["WALL_HEIGHT", "BIM_TARGETS", "REVIT_ROUTES_URL", "bim_target", "set_target_override"]
