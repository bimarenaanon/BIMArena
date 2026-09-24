"""Parse a bench case's task.json into the agent invocation it implies.

The dataset is split into THREE SUBSETS, each ONE TREE PER AUTHORING TOOL:
`bench_cases/<subset>/<tool>/<case_id>/` where `<subset>` is `atomic_tasks` (the atomic
capability cases), `reasoning_tasks` (the main bench, driven by source drawings) or
`long-seq_tasks` (the same tasks posed TEXT-ONLY). A case dir (e.g. `bench_cases/reasoning_tasks/archicad/B_element_creation8/`) holds

- `task.json`  — the spec for THAT TOOL ONLY, flat: `{"id", "legacy_id", "category",
  "authoring_tool", "required_capabilities", "instruction", "input", "expected_result",
  "env": {"files": [{"filepath"}]}}`. The two tools' specs genuinely differ (instruction,
  expected_result and reason all vary), so each lives in its own file under its own tree,
- the input drawing(s) named in `input.drawing` (or `"drawing": "text-only"`) — the same
  sheet is COPIED into both trees so a tool tree is self-contained. A drawing that is a figure
  of a copyrighted book is NOT shipped: `input.source[<name>]` carries its page + bounding box
  and `dataset/extract_figures.py` cuts it from the user's own copy,
- `env/` — the live project environment for this tool: the START project in `env/start/`
  (`archicad.pln` / `revit.rvt` + `baseline.json`). The hand-modelled ground-truth MODELS are
  NOT in the dataset: they live outside it, under `gt_root()` (see `gt_dir`). Revit's numbered `.NNNN.rvt` backups are ignored, the real
  `revit.rvt` is picked.

This module reads one such case and extracts:

- `instruction`  the free text fed to the agent via `-i`,
- `drawings`     the input image/PDF paths in the case dir ([] = text-only),
- `pln`          the project file inside the case's env dir, or None.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# the tool trees, and each one's project-file extension. This dict IS the list of known
# tools: `load_case` reads the tool off the path by looking a directory name up in it.
_PROJECT_EXTS = {"archicad": (".pln",), "revit": (".rvt",)}

_HERE = Path(__file__).resolve().parent


def gt_root() -> Path:
    """Where the ground-truth MODELS are kept — outside the dataset, so a released case
    tree never carries its answer: `$BENCH_GT_ROOT`, default `<repo>/0_docs/bench_gt`."""
    import os
    return Path(os.environ.get("BENCH_GT_ROOT") or _HERE.parent / "0_docs" / "bench_gt")


def gt_dir(case_dir: Path) -> Path:
    """One case's GT dir: `<gt_root>/<subset>/<tool>/<id>/`."""
    return gt_root().joinpath(*Path(case_dir).parts[-3:])


@dataclass
class Case:
    id: str                    # e.g. "B_element_creation8"
    dir: Path                  # the case directory (bench_cases/<subset>/<tool>/<id>)
    tool: str                  # "archicad" | "revit"
    instruction: str | None
    drawings: list[Path] = field(default_factory=list)  # [] = text-only
    n_drawings: int = 0           # how many drawings the spec NAMES (== len(drawings) when all exist)
    env_dir: Path | None = None   # <case dir>/env
    pln: Path | None = None       # project file in env_dir/start/ (.pln / .rvt)

    @property
    def name(self) -> str:        # kept for result naming / logs
        return self.id

    @property
    def category(self) -> str:   # "B_element_creation8" -> "B_element_creation"
        return self.id.rstrip("0123456789")

    @property
    def runnable(self) -> bool:
        """A case is live-runnable once it has a project file, an instruction and EVERY
        input drawing its spec names — running a drawing-driven case without its drawing
        would grade the agent on a requirement it was never shown."""
        return (self.pln is not None and bool(self.instruction)
                and len(self.drawings) == self.n_drawings)


# ---- path helpers, so every caller resolves a case the same way ----------------------

def tool_root(bench_root: Path, tool: str) -> Path:
    """One tool's tree inside a subset: `<bench_root>/<tool>/`."""
    return Path(bench_root) / tool


def case_path(bench_root: Path, tool: str, case_id: str) -> Path:
    """The directory holding one case's task.json for one tool."""
    return tool_root(bench_root, tool) / case_id


def read_spec(bench_root: Path, tool: str, case_id: str) -> dict:
    """One case's flat single-tool spec, or {} when it has none."""
    tj = case_path(bench_root, tool, case_id) / "task.json"
    if not tj.is_file():
        return {}
    try:
        return json.loads(tj.read_text(encoding="utf-8"))
    except Exception:
        return {}


def env_of(case_dir: Path, tool: str) -> Path:
    """A case directory's env dir (`<case dir>/env`). `tool` is kept for the callers'
    signature; the tool is already in the path."""
    return Path(case_dir) / "env"


def env_dir(bench_root: Path, tool: str, case_id: str) -> Path:
    """The env dir of one case, resolved from the bench root."""
    return env_of(case_path(bench_root, tool, case_id), tool)


def case_ids(bench_root: Path, tool: str) -> list[str]:
    """Every case id that exists for one tool, in natural order."""
    root = tool_root(bench_root, tool)
    if not root.is_dir():
        return []
    return sorted((p.name for p in root.iterdir()
                   if p.is_dir() and (p / "task.json").is_file()), key=_natkey)


def _resolve_drawings(case_dir: Path, variant: dict) -> list[Path]:
    spec = (variant.get("input") or {}).get("drawing")
    if not spec or spec == "text-only":
        return []
    names = [spec] if isinstance(spec, str) else list(spec)
    sourced = (variant.get("input") or {}).get("source") or {}
    found = []
    for n in names:
        p = case_dir / n
        if p.is_file():
            found.append(p)
        elif n in sourced:
            # a figure of a copyrighted book: not shipped, cut from the user's own copy
            print(f"    ! {case_dir.name}: input drawing {n!r} is not materialized — run "
                  f"`python bench_runner/dataset/extract_figures.py --pdf <your copy>` "
                  f"(p.{sourced[n].get('printed_page')} of {sourced[n].get('document')})")
        else:
            print(f"    ! {case_dir.name}: input drawing {n!r} not found in case dir")
    return found


def _n_drawings(variant: dict) -> int:
    spec = (variant.get("input") or {}).get("drawing")
    if not spec or spec == "text-only":
        return 0
    return 1 if isinstance(spec, str) else len(spec)


def _resolve_env(repo_root: Path, case_dir: Path, variant: dict, tool: str) -> Path | None:
    """The env dir from the spec's env.files[].filepath (repo-root-relative), falling back to
    the conventional `<case dir>/env`."""
    for f in (variant.get("env") or {}).get("files", []):
        fp = (f.get("filepath") or "").strip()
        if fp:
            d = (repo_root / fp).resolve() if not Path(fp).is_absolute() else Path(fp)
            if d.is_dir():
                return d
    fallback = case_dir / "env"
    return fallback if fallback.is_dir() else None


def load_case(case_dir: Path, tool: str = "archicad") -> Case:
    case_dir = Path(case_dir).resolve()
    # bench_cases/<subset>/<tool>/<id> -> repo root. `tool` is taken from the path rather
    # than the argument whenever the path says so, so a caller cannot ask for the archicad
    # variant of a case that lives in the revit tree. The repo root is found by walking up
    # to the `bench_cases` dir itself, so the subset level (atomic_tasks / long-seq_tasks /
    # reasoning_tasks) — and any dataset tree kept elsewhere — resolves the same way.
    if case_dir.parent.name in _PROJECT_EXTS:
        tool = case_dir.parent.name
    repo_root = case_dir.parents[2]             # a dataset tree kept outside `bench_cases`
    for anc in case_dir.parents:
        if anc.name == "bench_cases":
            repo_root = anc.parent
            break
    tj = case_dir / "task.json"
    try:
        data = json.loads(tj.read_text(encoding="utf-8")) if tj.exists() else {}
    except Exception as e:
        # one malformed task.json must not abort a whole sweep — discover_cases parses EVERY
        # case up front, so return a non-runnable Case (no instruction) and let the runner
        # list it as skipped.
        print(f"  ! {case_dir.name}: task.json unreadable ({type(e).__name__}: {e}) — skipping")
        data = {}
    variant = data
    env_dir = _resolve_env(repo_root, case_dir, variant, tool)
    pln = None
    if env_dir:
        # the start project lives in env/start/
        start = env_dir / "start"
        hits = sorted(p for p in (start.iterdir() if start.is_dir() else ())
                      if p.is_file() and p.suffix.lower() in _PROJECT_EXTS[tool])
        # Revit writes numbered backups next to the project (revit.0001.rvt, revit.0002.rvt);
        # they sort BEFORE revit.rvt, so drop any "<name>.NNNN" backup and keep the real file.
        real = [p for p in hits if not re.search(r"\.\d{4}$", p.stem)]
        hits = real or hits          # fall back to the raw list if filtering left nothing
        pln = hits[0] if hits else None
    return Case(
        id=data.get("id", case_dir.name),
        dir=case_dir,
        tool=tool,
        instruction=variant.get("instruction") or None,
        drawings=_resolve_drawings(case_dir, variant),
        n_drawings=_n_drawings(variant),
        env_dir=env_dir,
        pln=pln,
    )


def discover_cases(bench_root: Path, category: str | None = None,
                   only: list[str] | None = None, tool: str = "archicad") -> list[Case]:
    """Every case of ONE tool, parsed, in natural id order.

    `category` filters by the id's alpha prefix (e.g. "B_element_creation"); `only` filters
    by full case ids.
    """
    root = tool_root(bench_root, tool)
    if not root.is_dir():
        return []
    dirs = sorted((p for p in root.iterdir()
                   if p.is_dir() and (p / "task.json").exists()),
                  key=lambda p: _natkey(p.name))
    cases: list[Case] = []
    for cdir in dirs:
        if category and cdir.name.rstrip("0123456789") != category:
            continue
        if only and cdir.name not in only:
            continue
        cases.append(load_case(cdir, tool=tool))
    return cases


def _natkey(s: str):
    return [int(t) if t.isdigit() else t for t in re.findall(r"\d+|\D+", s)]
