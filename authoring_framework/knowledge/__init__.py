"""The vendors' official application HELP — the corpus behind `documentation_retrieval`.

`archicad_help` indexes the Archicad 29 Help and the Revit 2027 help together (the lookup never
says which application the run drives). The corpora are NOT versioned: build them with
`fetch_archicad_help.py` (from the committed URL manifest) and `fetch_revit_help.py`.
It is served in the `gui-docs` and `gui-support` modes; `gui-raw` has no retrieval tool.
"""
from . import archicad_help

__all__ = ["archicad_help"]
