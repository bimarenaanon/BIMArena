"""Seed every atomic case's `env/start/` from its tool's shared template.

The atomic tree carries the main trees' per-case layout (`<case>/env/start/`), but its
start projects are byte-copies of ONE template per tool — `_env_empty` / `_env_base` /
`_env_rich` / `_env_clash`, named by each case's `env_template` — so they are gitignored
(see .gitignore: `bench_cases/atomic_tasks/*/*/env/**/*.pln|rvt`) and are recreated by this
script instead of living in history. Only the templates under `<tool>/_env_*/start/` are
versioned.

    python bench_cases/atomic_tasks/seed_envs.py                  # fill in what is missing
    python bench_cases/atomic_tasks/seed_envs.py --force          # overwrite existing copies
    python bench_cases/atomic_tasks/seed_envs.py --tool revit
    python bench_cases/atomic_tasks/seed_envs.py --baselines-only # the 10 kB half only

`--baselines-only` writes `baseline.json` and skips the project file. The two halves are
NOT the same kind of asset: a `.pln`/`.rvt` is a gitignored 15 MB local copy, while
`baseline.json` is VERSIONED — the verifier reads it as the case's pre-state, so a case
missing one cannot be graded at all. Use this after adding a case, and the full seed only
when you are about to run the bench.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

TREE = Path(__file__).resolve().parent
PROJECT = {"archicad": "archicad.pln", "revit": "revit.rvt"}
TEMPLATE_DIR = {"empty": "_env_empty", "base": "_env_base", "clash": "_env_clash",
                "rich": "_env_rich"}


def template_for(tool_dir: Path, want: str) -> Path:
    """The start/ dir to copy from. Every template is versioned, so a missing one is an
    error, never a silent fallback."""
    d = tool_dir / TEMPLATE_DIR.get(want, "") / "start"
    if want not in TEMPLATE_DIR or not d.is_dir():
        raise SystemExit(f"{tool_dir.name}: template {want!r} not found under {tool_dir}")
    return d


def seed(tool: str, force: bool, baselines_only: bool = False) -> tuple[int, int]:
    tool_dir = TREE / tool
    proj = PROJECT[tool]
    written = skipped = 0
    for case in sorted(p for p in tool_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        spec_file = case / "task.json"
        if not spec_file.is_file():
            continue
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        want = spec.get("env_template", "empty")
        src = template_for(tool_dir, want)
        start = case / "env" / "start"
        start.mkdir(parents=True, exist_ok=True)
        for name in (("baseline.json",) if baselines_only else (proj, "baseline.json")):
            dst = start / name
            if dst.exists() and not force:
                skipped += 1
                continue
            if not (src / name).is_file():
                print(f"  ! {case.name}: {name} missing from {src}")
                continue
            shutil.copy2(src / name, dst)
            written += 1
    return written, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tool", choices=sorted(PROJECT), action="append",
                    help="seed only this tool tree (repeatable; default: all)")
    ap.add_argument("--force", action="store_true", help="overwrite copies that already exist")
    ap.add_argument("--baselines-only", action="store_true",
                    help="write baseline.json only, skipping the 15 MB project file")
    args = ap.parse_args()

    for tool in args.tool or sorted(PROJECT):
        written, skipped = seed(tool, args.force, args.baselines_only)
        print(f"{tool}: {written} file(s) written, {skipped} left in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
