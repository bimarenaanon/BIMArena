"""Turn a hand-modelled gt.pln into expected_result checkpoints.

For every bench case with a `gt.pln` (the ground-truth model the author built
by hand), this tool — with Archicad RUNNING:

  1. reopens the case's env project and refreshes its baseline.json
     (snapshot + composite list) unless one with composites already exists,
  2. opens gt.pln, takes a Tapir snapshot + composite list
     (raw copy saved as bench_cases/<id>/gt_snapshot.json),
  3. diffs GT against the baseline and writes a draft `expected_result`
     into task.json's ArchiCAD variant (only when it is still empty;
     --force overwrites).

The draft is meant to be REVIEWED (git diff) — element types from the GT model
are recorded as informational "gt_type" (not checked); promote them to
"type_contains" by hand where the type matters.

Run from the repo root:
  python bench_runner/verifier/gt_extract.py [--only case ...] [--io-mode gui]
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

from verifier.grade import normalize, normalize_composites  # noqa: E402


def _round_pt(p, snap=1):
    return [round(p[0] / snap) * snap, round(p[1] / snap) * snap]


def _created(base_mm, gt_mm, bucket):
    base_guids = {el.get("guid") for el in (base_mm.get(bucket) or [])}
    return [el for el in (gt_mm.get(bucket) or []) if el.get("guid") not in base_guids]


def _unchanged_buckets(base_mm, gt_mm):
    """Buckets whose pre-existing elements the GT model left untouched."""
    from verifier.checkers import _GEOM_KEYS, _geom_equal
    out = []
    for bucket, keys in _GEOM_KEYS.items():
        base = base_mm.get(bucket) or []
        if not base:
            continue
        live = {el.get("guid"): el for el in (gt_mm.get(bucket) or [])}
        if all(el.get("guid") in live and _geom_equal(el, live[el["guid"]], keys)
               for el in base):
            out.append(bucket)
    return out


def derive_expected(baseline: dict, gt: dict, gt_comps, base_comps) -> dict:
    """Build the expected_result draft (mm) from a GT snapshot diff."""
    base_mm, gt_mm = normalize(baseline.get("snapshot") or {}), normalize(gt)
    er: dict = {}

    # stories: only when the GT changed the stack
    def stack(s):
        return [(x.get("name"), x.get("elevation_mm")) for x in
                sorted(s.get("stories") or [], key=lambda y: y.get("elevation_mm", 0))]
    if stack(base_mm) != stack(gt_mm):
        er["stories"] = [{"name": n, "elevation_mm": e} for n, e in stack(gt_mm)]
        er["stories_exact"] = True

    # composites created in the GT model
    new_comps = []
    if gt_comps is not None and base_comps is not None:
        base_names = {c.get("name") for c in base_comps}
        for c in normalize_composites(
                [c for c in gt_comps if c.get("name") not in base_names]) or []:
            new_comps.append(c.get("name"))
            er.setdefault("composites", []).append({
                "name_contains": [c.get("name")],
                "skins": [{"material_contains": [s.get("material")],
                           "thickness_mm": s.get("thickness_mm")}
                          for s in c.get("skins") or []]})
        if new_comps:
            er["no_extra_composites"] = True

    def wall_entry(w, extra=None):
        return {"beg": _round_pt(w["beg"]), "end": _round_pt(w["end"]),
                **(extra or {}),
                **({"composite": "$new"} if w.get("composite") in new_comps
                   else ({"composite": w["composite"]} if w.get("composite") else {}))}

    from verifier.checkers import _geom_equal
    base_walls = {el.get("guid"): el for el in (base_mm.get("walls") or [])}
    moved = [w for w in (gt_mm.get("walls") or [])
             if w.get("guid") in base_walls
             and not _geom_equal(base_walls[w["guid"]], w, ("beg", "end"))]
    walls = _created(base_mm, gt_mm, "walls")
    if moved:
        # an ADJUST-walls task: the GT moved existing walls, so the expected
        # layout is EVERY final wall, matched regardless of guid
        er["walls"] = [wall_entry(w, {"match": "any"})
                       for w in (gt_mm.get("walls") or []) if w.get("beg") and w.get("end")]
    elif walls:
        er["walls"] = [wall_entry(w) for w in walls if w.get("beg") and w.get("end")]
        er["no_extra_walls"] = True

    for kind in ("doors", "windows"):
        made = _created(base_mm, gt_mm, kind)
        if not made:
            continue
        entries = []
        for o in made:
            if not o.get("center"):
                continue
            e = {"center": _round_pt(o["center"])}
            if o.get("width") is not None:
                e["width_mm"] = round(o["width"])
            if o.get("height") is not None:
                e["height_mm"] = round(o["height"])
            if kind == "windows" and o.get("sill") is not None:
                e["sill_mm"] = round(o["sill"])
            if o.get("type"):
                e["gt_type"] = o["type"]          # informational, not checked
            entries.append(e)
        if entries:
            er[kind] = entries
            er.setdefault("opening_pos_tolerance_mm", 300)   # a bit of buffer

    slabs = _created(base_mm, gt_mm, "slabs")
    if slabs:
        er["slabs"] = []
        for s in slabs:
            e = {"floor": s.get("floor"),
                 "outline": [_round_pt(p) for p in (s.get("polygonOutline") or [])]}
            if s.get("level") is not None:
                e["level_mm"] = round(s["level"])
            if s.get("composite"):
                e["composite"] = "$new" if s["composite"] in new_comps else s["composite"]
            holes = s.get("holes") or []
            if holes:                       # a GT hole (stairwell) = a keep-clear region
                xs = [p[0] for p in holes[0]]
                ys = [p[1] for p in holes[0]]
                e["exclude_region"] = [round(min(xs)), round(min(ys)),
                                       round(max(xs)), round(max(ys))]
            er["slabs"].append(e)

    rooms = _created(base_mm, gt_mm, "rooms")
    if rooms:
        from shapely.geometry import Polygon
        er["rooms"] = []
        for r in rooms:
            e = {"name": r.get("name")}
            poly = [p for p in (r.get("polygonOutline") or []) if p]
            if len(poly) >= 3:
                pg = Polygon(poly)
                pt = pg.representative_point()
                e["inside"] = _round_pt([pt.x, pt.y])
                e["area_m2"] = round(pg.area / 1e6, 1)   # mm² -> m² ("roughly right" check)
            er["rooms"].append(e)

    stairs = _created(base_mm, gt_mm, "stairs")
    if stairs:
        er["stairs"] = []
        for s in stairs:
            e = {"floor": s.get("floor")}
            fp = s.get("footprint")
            if fp:
                pad = 300                          # a bit of buffer around the GT spot
                e["region"] = [round(fp[0] - pad), round(fp[1] - pad),
                               round(fp[2] + pad), round(fp[3] + pad)]
                e["axis"] = "y" if (fp[3] - fp[1]) >= (fp[2] - fp[0]) else "x"
            er["stairs"].append(e)

    # no wall count: how many segments a loop is drawn as is arbitrary —
    # no_extra_walls already forbids extras
    counts = {b: len(gt_mm.get(b) or [])
              for b in ("doors", "windows", "slabs", "rooms", "stairs")
              if _created(base_mm, gt_mm, b)}
    if counts:
        er["exact_counts"] = counts

    # preserve buckets the GT left untouched AND the task creates nothing in
    preserve = [b for b in _unchanged_buckets(base_mm, gt_mm)
                if not _created(base_mm, gt_mm, b)]
    if preserve:
        er["preserve"] = preserve
    return er


_BUCKET_KEYS = {
    "walls": ("walls", "no_extra_walls"),
    "doors": ("doors", "opening_pos_tolerance_mm"),
    "windows": ("windows", "opening_pos_tolerance_mm"),
    "slabs": ("slabs",),
    "rooms": ("rooms",),
    "stairs": ("stairs",),
    "composites": ("composites", "no_extra_composites"),
    "stories": ("stories", "stories_exact", "active_story"),
}


def filter_buckets(er: dict, buckets: list[str]) -> dict:
    """Limit a draft to the given buckets (e.g. an adjust-WALLS task where
    zones are explicitly out of scope)."""
    keep = {k for b in buckets for k in _BUCKET_KEYS.get(b, (b,))}
    out = {k: v for k, v in er.items() if k in keep}
    if "exact_counts" in er:
        counts = {b: n for b, n in er["exact_counts"].items() if b in buckets}
        if counts:
            out["exact_counts"] = counts
    if "preserve" in er:
        pres = [p for p in er["preserve"]
                if (p if isinstance(p, str) else p.get("bucket")) in buckets]
        if pres:
            out["preserve"] = pres
    return out


# ---------------------------------------------------------------- live driver

def _snap_live(pln, io):
    from drivers import archicad_io
    from bench_runner.backend import Toolbox
    from bench_runner.backend.archicad.inventory import list_composites
    from bench_runner.backend.snapshot import model_snapshot
    archicad_io.open_project(Path(pln), **io)
    tb = Toolbox.connect()
    return model_snapshot(tb), list_composites(tb.client)


def gt_pln_path(case_dir: Path, tool: str = "archicad") -> Path:
    """The hand-modelled GT project — kept OUTSIDE the dataset (`case_io.gt_dir`)."""
    import case_io
    return case_io.gt_dir(case_dir) / "gt.pln"


def snapshot_case(case_dir: Path, io: dict, force: bool = False) -> str:
    """Capture ONLY gt_snapshot.json (beside the case's gt.pln, under the GT root) —
    no baseline, no expected_result derivation (for gt.pln files promoted from
    bench results, whose task.json already carries a reviewed expected_result)."""
    gt_pln = gt_pln_path(case_dir)
    out = gt_pln.parent / "gt_snapshot.json"
    if out.exists() and not force:
        return "kept (gt_snapshot.json already exists; --force to recapture)"
    gt_snap, gt_comps = _snap_live(gt_pln, io)
    out.write_text(
        json.dumps({"snapshot": gt_snap, "composites": gt_comps}, ensure_ascii=False),
        encoding="utf-8")
    counts = ", ".join(f"{b}={len(gt_snap.get(b) or [])}"
                       for b in ("stories", "walls", "doors", "windows",
                                 "slabs", "rooms", "stairs", "objects"))
    return f"gt_snapshot.json captured ({len(gt_comps)} composites; {counts})"


def extract_case(case_dir: Path, io: dict, force: bool, buckets=None) -> str:
    from verifier import baselines
    cid = case_dir.name
    gt_pln = gt_pln_path(case_dir)
    import case_io
    tj = case_dir / "task.json"
    data = json.loads(tj.read_text(encoding="utf-8"))
    variant = data            # a task.json is single-tool and FLAT: the spec IS the file
    if isinstance(variant.get("expected_result"), dict) and variant["expected_result"] \
            and not force:
        return "kept (expected_result already set; --force to overwrite)"

    base = baselines.load(cid, "archicad")
    if not base or base.get("composites") is None:
        env_pln = sorted((case_io.env_of(case_dir, "archicad") / "start").glob("*.pln"))
        if not env_pln:
            return "SKIP: no env .pln"
        snap, comps = _snap_live(env_pln[0], io)
        baselines._write(cid, "archicad", snap, comps, f"live @ {env_pln[0].name}")
        base = baselines.load(cid, "archicad")

    gt_snap, gt_comps = _snap_live(gt_pln, io)
    (gt_pln.parent / "gt_snapshot.json").write_text(
        json.dumps({"snapshot": gt_snap, "composites": gt_comps}, ensure_ascii=False),
        encoding="utf-8")

    er = derive_expected(base, gt_snap, gt_comps, base.get("composites"))
    if buckets:
        er = filter_buckets(er, buckets)
    variant["expected_result"] = er
    tj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_cp = sum(len(v) if isinstance(v, list) else 1 for v in er.values())
    return f"expected_result drafted ({n_cp} top-level entries)"


def main(argv=None):
    p = argparse.ArgumentParser(description="gt.pln -> expected_result draft")
    p.add_argument("--only", nargs="*", default=None)
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing expected_result")
    p.add_argument("--buckets", nargs="*", default=None,
                   help="limit the draft to these buckets (e.g. --buckets walls "
                        "for an adjust-walls task where zones are out of scope)")
    p.add_argument("--snapshot-only", action="store_true",
                   help="only capture missing gt_snapshot.json from each gt.pln; "
                        "do not touch baselines or task.json expected_result")
    p.add_argument("--io-mode", choices=["gui", "manual", "tapir"], default="gui")
    p.add_argument("--open-wait", type=float, default=15.0)
    p.add_argument("--dialog-delay", type=float, default=1.5)
    p.add_argument("--focus-countdown", type=float, default=5.0)
    a = p.parse_args(argv)
    io = dict(mode=a.io_mode, open_wait=a.open_wait, dialog_delay=a.dialog_delay)

    import case_io
    cases = [d for d in sorted(case_io.tool_root(BENCH_CASES, 'archicad').iterdir())
             if d.is_dir() and gt_pln_path(d).exists()
             and (not a.only or d.name in a.only)]
    print(f"{len(cases)} case(s) with gt.pln: {[c.name for c in cases]}")
    if a.io_mode == "gui" and a.focus_countdown > 0 and cases:
        import time
        print(f"Make sure Archicad is OPEN; starting in {a.focus_countdown:.0f}s ...")
        time.sleep(a.focus_countdown)
    for c in cases:
        try:
            if a.snapshot_only:
                msg = snapshot_case(c, io, a.force)
            else:
                msg = extract_case(c, io, a.force, buckets=a.buckets)
        except Exception as e:  # keep the batch going; the case stays unfilled
            msg = f"ERROR: {e}"
        print(f"  {c.name:22s} {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
