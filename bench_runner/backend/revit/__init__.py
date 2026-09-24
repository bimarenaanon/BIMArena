"""Revit backend for the API tool family.

The agent's pipeline is unchanged: the actor still emits the same `{action, params}` action
space (see `prompt/toolbox.md`, all mm/metres). When `--target revit` is selected,
`Toolbox.connect()` returns a `RevitToolbox` (this package) instead of the Tapir-backed one.

`RevitToolbox` is a THIN forwarder: it resolves `$id.field` cross-references (same as the
Archicad toolbox) and POSTs each action over HTTP to a **Revit add-in's local server** (the
contract is documented in `client.py`). That add-in — to be built with the **Revit native C# API**
— is the real "Revit toolbox": it maps each action name to the Revit API and hides the
Revit-specific details (mm/m→feet, type-vs-instance, room separation lines, transactions). Reads
(snapshot, materials, composites, favorites) are served by the same endpoints so the planner/
verifier work too.

(The Revit-side add-in itself is TODO — to be built with the native C# Revit API; only this Python
HTTP client + the route contract are in place for it to implement.)
"""
