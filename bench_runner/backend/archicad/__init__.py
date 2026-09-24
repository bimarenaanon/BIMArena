"""The ARCHICAD backend — everything that speaks Tapir.

`toolbox.Toolbox` is the facade (its `connect()` classmethod is also the cross-target
factory); `client.ArchicadClient` the connection + Tapir wrapper; `attributes` / `inventory`
the attribute-library readers; `actions/` the single-Tapir-op building blocks. The vendored
Tapir add-on (`tapir_addon/`) and the native C++ zone add-on (`native/`) live here too.
The Revit twin is the sibling package `..revit`; the cross-target snapshot/clash entry
points stay one level up (`..snapshot`, `..clash`).
"""
