"""Regenerate `TOOLS.md` — the human-readable tool catalog — from the live registry.

Run from the project root after ANY tool-spec change:

    python -m authoring_framework.tools.gen_tools_md

The catalog is documentation ONLY: the agent never reads it (it gets the same specs as
provider-native function declarations). Keeping it generated is what stops it drifting
from the specs. The knowledge lookups (search_standards / search_web) are deliberately NOT
listed — they change nothing in the model and are outside the action-space comparison.
"""
import collections
import io

from . import gui


HEADER = """# Tool Catalog — `authoring_framework/tools`

Auto-generated from the tool registry (`Tool` specs) by `gen_tools_md.py`. This is the
exact action space the agent is handed as function declarations — one entry per registered
tool, with every parameter exactly as declared. The action space is the application's USER
INTERFACE: mouse / keyboard operations plus the retrieval lookups. The screen itself is NOT a
tool — the loop captures it at the start of every turn and shows the current and the previous
capture.

**Total: {total} GUI tools.**

Which lookups a run gets is the `--tools` MODE: `gui-raw` = the GUI operations alone (no
retrieval tool); `gui-docs` = plus `documentation_retrieval` (the vendors' official help);
`gui-support` = that PLUS
`operational_skill_retrieval` (the hand-written per-capability procedures). (The knowledge
lookups `search_standards`/`search_web` ride along when enabled and are not listed here.)

## How to read the entries

- **(read-only)** marks a tool that changes NOTHING in the model or UI — the lookups.
  Everything else acts on the UI.
- **Usage** is the tool's own guidance text, verbatim from the declaration the model reads.
- Parameters are split into **required** and **optional** — an optional parameter can be
  omitted entirely (its behaviour when omitted is in its description).
- Parameter **types**: `int`/`number` (a number), `string`, `bool`, `keys` = a list of key
  names.
- **Units**: `px` params are SCREEN pixels, read off the current screenshot (or points on a
  0-1000 grid under `GUI_COORD_WORDING=norm1000`). Model lengths are TYPED into the
  application as their raw millimetre number.
"""


_TYPE = {"point": "point `[x, y]`",
         "points": "points `[[x, y], ...]`",
         "segments": "segments `[[x1, y1, x2, y2], ...]`",
         "keys": "list of key names"}


def _item_shape(schema):
    """One line describing a `list` param's item schema, readable without JSON-Schema eyes."""
    if not schema:
        return ""
    if schema.get("type") == "object":
        req = set(schema.get("required", []))
        parts = []
        for k, v in (schema.get("properties") or {}).items():
            enum = " — one of " + " / ".join(f"`{e}`" for e in v["enum"]) if "enum" in v else ""
            parts.append(f"`{k}` ({v.get('type', 'any')}, "
                         f"{'required' if k in req else 'optional'}{enum})")
        return "each item is an object: " + "; ".join(parts)
    return f"each item: {schema.get('type', 'any')}"


def _param_rows(out, params):
    out.write("| parameter | type | unit | description |\n|---|---|---|---|\n")
    for name, p in params:
        doc = (p.doc or "").replace("|", "\\|").replace("\n", " ")
        t = _TYPE.get(p.type, p.type)
        out.write(f"| `{name}` | {t} | {p.unit or '—'} | {doc} |\n")
    out.write("\n")
    for name, p in params:
        if p.type == "list" and p.items:
            out.write(f"  - `{name}`: {_item_shape(p.items)}\n\n")


def _tool_entry(out, tool):
    ro = "" if tool.writes else " *(read-only)*"
    out.write(f"**`{tool.name}`**{ro} — {tool.summary}\n\n")
    if tool.notes:
        out.write(f"> **Usage:** {tool.notes}\n\n")
    req = [(n, p) for n, p in tool.params.items() if p.required]
    opt = [(n, p) for n, p in tool.params.items() if not p.required]
    if req:
        out.write("*Required:*\n\n")
        _param_rows(out, req)
    if opt:
        out.write("*Optional:*\n\n")
        _param_rows(out, opt)
    if not tool.params:
        out.write("*No parameters.*\n\n")


def _grouped(out, tools, heading_level="####"):
    groups = collections.OrderedDict()
    for t in tools:
        groups.setdefault(t.group, []).append(t)
    for g, ts in groups.items():
        out.write(f"{heading_level} {g}\n\n")
        for t in ts:
            _tool_entry(out, t)


def main():
    # The "skills" variant is the SUPERSET (gui-support is additive over gui-raw): render that.
    gui_tools = gui.tools({"gui_learning": "skills"})
    total = len(gui_tools)
    out = io.StringIO()
    out.write(HEADER.format(total=total))
    out.write(f"\n## GUI tools (computer-use) ({total})\n\n")
    out.write("Every mode gets the mouse / keyboard operations. `documentation_retrieval` "
              "(the official help corpus) is served in `gui-docs` and `gui-support`; "
              "`operational_skill_retrieval` (the hand-written `software_skills/` "
              "procedures) only in `gui-support`.\n\n")
    _grouped(out, gui_tools, "###")
    import pathlib
    path = pathlib.Path(__file__).parent / "TOOLS.md"
    path.write_text(out.getvalue(), encoding="utf-8")
    print(f"wrote {path} ({total} tools)")


if __name__ == "__main__":
    main()
