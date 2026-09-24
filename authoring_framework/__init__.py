"""The BIM authoring agent: a computer-use ReAct loop over a BIM application's GUI.

It brings a BIM model in Archicad or Revit to the state a task requires — given as a written
specification and/or architectural drawings — using only mouse and keyboard. There is ONE
role and ONE loop (`react.py`):

    see the screen -> reason -> act -> see the screen -> ... -> answer

The action space is the TOOL LAYER (`authoring_framework/tools/`): the GUI operations plus
the retrieval lookups. `--tools gui-raw | gui-docs | gui-support` is the support axis — official
documentation only, or that plus the hand-written operational skills.
"""
