"""Revit twin of gt_extract.py: fill each case's REVIT expected_result from a
hand-modelled revitgt.rvt.

A .rvt is an opaque binary, so — unlike the Archicad path — the two snapshots
cannot be read offline. They are captured LIVE from the BimAgent add-in's HTTP
routes (the add-in must be loaded in a running Revit, serving $REVIT_ROUTES_URL,
default http://localhost:48884), one open document at a time. The flow is:

  capture  — with a .rvt OPEN in Revit, GET /snapshot + /composites and save them
             into the case's env/revit tree:
               --slot baseline -> env/revit/start/baseline.json (the PRE-state)
               --slot gt       -> env/revit/gt/gt_snapshot.json  (the ground truth)
             The capture reads whatever document is ACTIVE, so open the right file
             first and eyeball the printed element counts before trusting it.

  derive   — fully OFFLINE. For every case that has both env/revit/start/baseline.json
             and env/revit/gt/gt_snapshot.json, diff GT against the baseline (the
             SAME derive_expected() the Archicad path uses) and write the draft
             into task.json's Revit variant. Review the git diff afterwards — the
             composite/type NAMES come straight from the Revit model, the geometry
             mirrors the Archicad case.

Run from the repo root, e.g.:
  python bench_runner/verifier/revit_gt.py capture --case B_element_creation6 --slot baseline
  python bench_runner/verifier/revit_gt.py capture --case B_element_creation6 --slot gt
  python bench_runner/verifier/revit_gt.py derive --only B_element_creation6 --buckets walls
  python bench_runner/verifier/revit_gt.py derive            # every ready case
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))   # verifier package siblings
sys.path.insert(0, str(ROOT))          # authoring_framework.*

BENCH_CASES = ROOT / "bench_cases" / "reasoning_tasks"

from verifier import baselines                       # noqa: E402
from verifier.gt_extract import derive_expected, filter_buckets  # noqa: E402


def _counts(snap: dict) -> str:
    return ", ".join(f"{b}={len(snap.get(b) or [])}"
                     for b in ("stories", "walls", "doors", "windows",
                               "slabs", "rooms", "stairs", "objects"))


# ---------------------------------------------------------------- capture (live)

def _fetch_live():
    """Pull {snapshot, composites} from the running add-in's active document."""
    from bench_runner.backend.revit.client import RevitClient
    c = RevitClient.connect()                 # SystemExit if the server is dead
    return c.snapshot(), c.composites()


def capture(case_id: str, slot: str) -> str:
    import case_io
    env = case_io.env_dir(BENCH_CASES, "revit", case_id)
    if not env.exists():
        return f"SKIP: no {env.relative_to(ROOT)}"
    snap, comps = _fetch_live()
    if slot == "baseline":
        out = baselines._write(case_id, "revit", snap, comps, "live @ revit add-in")
    else:  # gt
        gt_dir = case_io.gt_dir(env.parent)
        gt_dir.mkdir(parents=True, exist_ok=True)
        out = gt_dir / "gt_snapshot.json"
        out.write_text(json.dumps({"snapshot": snap, "composites": comps},
                                  ensure_ascii=False), encoding="utf-8")
    return f"{slot}: {out.relative_to(ROOT)}  ({len(comps)} composites; {_counts(snap)})"


# ---------------------------------------------------------------- derive (offline)

def _gt_path(case_dir: Path) -> Path:
    import case_io
    return case_io.gt_dir(case_dir) / "gt_snapshot.json"


def derive_case(case_dir: Path, force: bool, buckets=None) -> str:
    cid = case_dir.name
    gt_file = _gt_path(case_dir)
    if not gt_file.exists():
        return "SKIP: no gt_snapshot.json under the GT root (capture --slot gt first)"

    tj = case_dir / "task.json"
    data = json.loads(tj.read_text(encoding="utf-8"))
    variant = data            # a task.json is single-tool and FLAT: the spec IS the file
    if isinstance(variant.get("expected_result"), dict) and variant["expected_result"] \
            and not force:
        return "kept (expected_result already set; --force to overwrite)"

    base = baselines.load(cid, "revit")
    if not base or base.get("composites") is None:
        return "SKIP: no env/revit/start/baseline.json with composites (capture --slot baseline first)"

    gt = json.loads(gt_file.read_text(encoding="utf-8"))
    gt_snap, gt_comps = gt.get("snapshot") or {}, gt.get("composites")

    er = derive_expected(base, gt_snap, gt_comps, base.get("composites"))
    if buckets:
        er = filter_buckets(er, buckets)
    variant["expected_result"] = er
    tj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_cp = sum(len(v) if isinstance(v, list) else 1 for v in er.values())
    return f"expected_result drafted ({n_cp} top-level entries)"


# ------------------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="save the OPEN Revit doc's snapshot into a slot")
    cap.add_argument("--case", required=True)
    cap.add_argument("--slot", required=True, choices=["baseline", "gt"])

    der = sub.add_parser("derive", help="diff saved GT vs baseline -> Revit expected_result")
    der.add_argument("--only", nargs="*", default=None)
    der.add_argument("--force", action="store_true", help="overwrite an existing expected_result")
    der.add_argument("--buckets", nargs="*", default=None,
                     help="limit the draft to these buckets (e.g. --buckets walls)")

    a = p.parse_args(argv)
    if a.cmd == "capture":
        print(capture(a.case, a.slot))
        return 0

    import case_io
    cases = [d for d in sorted(case_io.tool_root(BENCH_CASES, 'revit').iterdir())
             if d.is_dir() and _gt_path(d).exists()
             and (not a.only or d.name in a.only)]
    print(f"{len(cases)} case(s) with a Revit GT snapshot: {[c.name for c in cases]}")
    for c in cases:
        try:
            msg = derive_case(c, a.force, buckets=a.buckets)
        except Exception as e:   # keep the batch going
            msg = f"ERROR: {e}"
        print(f"  {c.name:22s} {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
