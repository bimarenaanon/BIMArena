"""Regenerate bench_cases/README.md from the per-case task.json files.

The README is auto-generated - never hand-edit it; run this after changing any case:

  python bench_runner/dataset/gen_cases_readme.py

The dataset is split one tree per authoring tool (`bench_cases/<tool>/<id>/task.json`,
single-tool and flat), so this script RE-JOINS the two trees to produce a case-level
document. A case's `Status` says which tool trees pose it (a few cases are single-tool by
design) and whether its drawing is a SOURCED figure (`input.source`: cut from the user's own
copy of a copyrighted book by `extract_figures.py`, not shipped).
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "bench_cases"          # output root (README.md)
TREE = CASES / "reasoning_tasks"             # the main-bench subset the document describes
# (long-seq_tasks is the text-only variant of the same cases; atomic_tasks has its own README.)

# category slug -> (sort key, display name). A case id is <letter>_<slug><n>, the leading
# letter being the category so the flat directory listing comes out in category order.
#
# These are the SIX BIM-authoring categories the dataset was re-classified into (see
# bench_cases/CASE_ID_MIGRATION.json for the old -> new id mapping). The nine former
# categories (A_setup_types / B_walls / C_openings / D_slabs_stairs_rooms / E_cross_view /
# F_design_change / G_model_check / H_domain_reasoning / I_long_sequence) are gone, and
# `A_setup_types` was REUSED with fresh numbering — so an old id is not a reliable reference to
# a case any more. Each task.json carries `legacy_id` for that.
CATEGORIES = {
    "A_setup_types": ("A", "Project Initialization (1)"),
    "B_element_creation": ("B", "Model Authoring (2)"),
    "C_model_editing": ("C", "Model Revision (3)"),
    "D_model_completion": ("D", "Model Completion (4)"),
    "E_model_checking": ("E", "Model Checking (5)"),
    "F_end_to_end": ("F", "End-to-End Modeling (6)"),
}


def split_id(cid: str):
    slug = cid.rstrip("0123456789")
    num = int(cid[len(slug):] or 0)
    return slug, num


TOOLS = {"archicad": ("ArchiCAD", "*.pln"), "revit": ("Revit", "*.rvt")}


def load_cases():
    """One record per CASE, gathering that case's per-tool task.json files.

    The dataset is split one tree per tool (`bench_cases/reasoning_tasks/<tool>/<id>/task.json`),
    each file holding a single tool's flat spec, so a case-level document like this README
    has to re-join them: `tools` maps the tool key to that tool's spec and directory."""
    merged = {}
    for tool in TOOLS:
        for tj in sorted((TREE / tool).glob("*/task.json")):
            spec = json.loads(tj.read_text(encoding="utf-8"))
            cid = spec.get("id", tj.parent.name)
            rec = merged.setdefault(cid, {"id": cid, "tools": {}})
            rec["tools"][tool] = {"spec": spec, "dir": tj.parent}
            # case-level identity comes from whichever file states it (both agree)
            for k in ("legacy_id", "category", "v2_template"):
                if spec.get(k) and not rec.get(k):
                    rec[k] = spec[k]

    def key(rec):
        slug, num = split_id(rec["id"])
        return (CATEGORIES.get(slug, ("Z", slug))[0], num)
    return sorted(merged.values(), key=key)


def any_spec(case) -> dict:
    """One of the case's per-tool specs — for the fields both tools agree on
    (the drawing list)."""
    return next(iter(case["tools"].values()))["spec"] if case["tools"] else {}


def drawing_of(case) -> str:
    dr = (any_spec(case).get("input") or {}).get("drawing")
    if dr == "text-only" or not dr:
        return "text-only"
    return ", ".join(dr)


def status_of(case) -> str:
    """Which tool trees pose the case, and whether its drawing is a sourced figure."""
    tools = [TOOLS[t][0] for t in TOOLS if t in case["tools"]]
    parts = ["+".join(tools) if len(tools) == len(TOOLS) else f"{tools[0]} only"]
    if any((e["spec"].get("input") or {}).get("source") for e in case["tools"].values()):
        parts.append("sourced figure")
    return ", ".join(parts)


def quote(text: str) -> str:
    return "\n".join("> " + ln for ln in text.splitlines())


def gen_readme(cases) -> str:
    n = len(cases)
    n_drawing = sum(1 for c in cases if drawing_of(c) != "text-only")
    out = []
    out.append("# Benchmark cases overview\n")
    out.append("> Auto-generated from the per-case `task.json` files by "
               "`bench_runner/dataset/gen_cases_readme.py` - do not edit by hand; regenerate after "
               "changing a case.\n")
    out.append(f"**{n} cases**, each present ONCE PER AUTHORING TOOL: "
               "`bench_cases/reasoning_tasks/archicad/<id>/` and `bench_cases/reasoning_tasks/revit/<id>/`, each with its own "
               "single-tool `task.json` (the two tools' instructions and expected_results "
               "genuinely differ) and its own `env/`. "
               f"{n_drawing} cases are drawing-driven, {n - n_drawing} are text-only. Each "
               "carries `required_capabilities` - the fundamental capabilities "
               "(`bench_cases/CAPABILITIES.md`) it needs, with occurrence counts. `v2_template` names the V2 template a case instantiates and "
               "`legacy_id` its pre-re-classification id. `Status` names the tool trees a case "
               "exists in and flags a drawing that is a sourced figure (`input.source`, not "
               "shipped - see `bench_runner/dataset/extract_figures.py`).\n")
    out.append("## Case index\n")
    out.append("| Case | V2 | Category | Input | Status |")
    out.append("|---|---|---|---|---|")
    for c in cases:
        slug, _ = split_id(c["id"])
        cat = CATEGORIES.get(slug, ("Z", slug))[1]
        out.append(f"| [{c['id']}](#{c['id'].lower()}) | {c.get('v2_template', '-')} | {cat} | "
                   f"`{drawing_of(c)}` | {status_of(c)} |")
    out.append("")
    cur = None
    for c in cases:
        slug, _ = split_id(c["id"])
        cat = CATEGORIES.get(slug, ("Z", slug))[1]
        if cat != cur:
            out.append(f"## {cat}\n")
            cur = cat
        out.append(f"### {c['id']}\n")
        tpl = f" - **V2 template:** {c['v2_template']}" if c.get("v2_template") else ""
        if c.get("legacy_id") and c["legacy_id"] != c["id"]:
            tpl += f" - **was:** `{c['legacy_id']}`"
        out.append(f"- **Input:** `{drawing_of(c)}`{tpl}")
        for t, e in c["tools"].items():
            out.append(f"- **Required capabilities ({TOOLS[t][0]}):** "
                       f"{e['spec'].get('required_capabilities', '-')}")
        if status_of(c) != "+".join(TOOLS[t][0] for t in TOOLS):
            out.append(f"- **Status:** {status_of(c)}")
        out.append("")
        by_tool = {TOOLS[t][0]: e["spec"].get("instruction", "")
                   for t, e in c["tools"].items()}
        vals = list(by_tool.values())
        if len(set(vals)) == 1:
            out.append("**Instruction (both tools):**\n")
            out.append(quote(vals[0]) + "\n")
        else:
            for tool, instr in by_tool.items():
                out.append(f"**{tool} instruction:**\n")
                out.append(quote(instr) + "\n")
    return "\n".join(out).rstrip() + "\n"


def main():
    cases = load_cases()
    (CASES / "README.md").write_text(gen_readme(cases), encoding="utf-8")
    single = [c["id"] for c in cases if len(c["tools"]) < len(TOOLS)]
    print(f"README.md regenerated: {len(cases)} cases"
          + (f" ({len(single)} single-tool: {', '.join(single)})" if single else ""))


if __name__ == "__main__":
    main()
