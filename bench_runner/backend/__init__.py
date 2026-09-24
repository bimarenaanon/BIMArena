"""The BIM application backends behind the API tool family — ONE subpackage per application.

`archicad/` is everything that speaks Tapir (facade, client, attribute readers, actions,
the vendored add-on); `revit/` is the HTTP-forwarding twin. At THIS level live only the
CROSS-TARGET pieces: `Toolbox.connect()` (re-exported here — the factory that returns the
Archicad toolbox or the `revit.toolbox.RevitToolbox`, both exposing the same
`run_actions([{action, params, id?}])` surface), `snapshot.model_snapshot` (dispatches to
`tb.remote_snapshot()` for Revit), `clash.check`, and the shared
`settings`.

This package is agent-INDEPENDENT: the bench harness imports it directly (baselines, ground
truth extraction, materials dumps), so it must never reach into an agent package.
"""
from .archicad.toolbox import Toolbox

__all__ = ["Toolbox"]
