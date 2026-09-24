"""Create <case dir>/env/start/baseline.json — the env's PRE-state.

The baseline lets the grader tell CREATED elements from pre-existing ones
(guid diff) and check "do not modify existing" constraints.

It is taken LIVE: each case's env/start/*.pln is opened in the running Archicad and a
fresh snapshot + composite list is written.

Run from the repo root:
  python bench_runner/verifier/baselines.py live [--only case1 case2] [--io-mode gui]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))   # case_io / drivers
sys.path.insert(0, str(ROOT))          # authoring_framework.*

BENCH_CASES = ROOT / "bench_cases" / "reasoning_tasks"


def _write(case_id: str, tool: str, snapshot: dict, composites, source: str) -> Path:
    import case_io
    start = case_io.env_dir(BENCH_CASES, tool, case_id) / "start"
    start.mkdir(parents=True, exist_ok=True)
    out = start / "baseline.json"
    out.write_text(json.dumps({"source": source, "snapshot": snapshot,
                               "composites": composites},
                              ensure_ascii=False), encoding="utf-8")
    return out


def load(case_id: str, tool: str = "archicad") -> dict:
    import case_io
    bj = case_io.env_dir(BENCH_CASES, tool, case_id) / "start" / "baseline.json"
    if not bj.exists():
        return {}
    return json.loads(bj.read_text(encoding="utf-8"))


def live(tool: str = "archicad", only=None, io_mode: str = "gui",
         open_wait: float = 15.0) -> int:
    from drivers import archicad_io
    from bench_runner.backend import Toolbox
    from bench_runner.backend.archicad.inventory import list_composites
    from bench_runner.backend.snapshot import model_snapshot

    import case_io
    n = 0
    for case_dir in sorted(case_io.tool_root(BENCH_CASES, tool).iterdir()):
        if not case_dir.is_dir() or (only and case_dir.name not in only):
            continue
        plns = sorted((case_io.env_of(case_dir, tool) / "start").glob("*.pln"))
        if not plns:
            continue
        archicad_io.open_project(plns[0], mode=io_mode, open_wait=open_wait)
        tb = Toolbox.connect()
        snap = model_snapshot(tb)
        comps = list_composites(tb.client)
        out = _write(case_dir.name, tool, snap, comps, f"live @ {plns[0].name}")
        print(f"  + {case_dir.name}: {out.relative_to(ROOT)} "
              f"({len(comps)} composites)")
        n += 1
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    lv = sub.add_parser("live", help="snapshot each case env in the running Archicad")
    lv.add_argument("--tool", default="archicad")
    lv.add_argument("--only", nargs="*", default=None)
    lv.add_argument("--io-mode", choices=["gui", "manual", "tapir"], default="gui")
    lv.add_argument("--open-wait", type=float, default=15.0)
    a = p.parse_args(argv)
    n = live(tool=a.tool, only=a.only, io_mode=a.io_mode, open_wait=a.open_wait)
    print(f"wrote {n} baseline(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
