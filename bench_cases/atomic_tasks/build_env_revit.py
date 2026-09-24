#!/usr/bin/env python
"""Author the atomic tree's shared REVIT env templates through the BimAgent add-in.

    python bench_cases/atomic_tasks/build_env_revit.py --which base
    python bench_cases/atomic_tasks/build_env_revit.py --which rich
    python bench_cases/atomic_tasks/build_env_revit.py --which clash

The ArchiCAD templates are hand-drawn; the Revit ones are authored HERE, through the
add-in's `/action` routes, because that is the only deterministic way to reach a Revit
document from a script. The geometry does NOT copy ArchiCAD's (11129 x 10205, hand-stretched)
— the two trees pose the same tasks in each application's own vocabulary and do not have to
share coordinates — but it does match ArchiCAD's SCALE, on round numbers: an 11000 x 10000
envelope with the partition at x=5500 and Level 2 at 4000 mm. Every Revit case's
expected_result states the same figures; the two are refitted together or not at all.

  _env_base    the built model every edit / read atom points at — 4 exterior walls + the
               partition + one wall on Level 2, 1 door, 1 window, 1 floor, 1 room
  _env_rich    the same shell with a SET to pick from: 2 partitions, 3 doors, 3 windows —
               and NO floor and NO room, so create_slab1 has an empty enclosure to cover
  _env_clash   _env_base plus the three seeded defects clash_check has to find

Each is built from `_env_empty`, which stays the untouched stock template: the project file
is BYTE-COPIED into place first, opened through the Revit GUI (`revit_io` in `gui` mode),
authored over the API, saved back, and its baseline.json captured from the live snapshot.

Prereq: Revit open with the BimAgent add-in answering /health, no modal dialog, and the
desktop free (open/save go through the GUI). Geometry here is in METRES (the backend's
unit); the README's tables and every task.json are in millimetres.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parent
ROOT = TREE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench_runner"))

RV = TREE / "revit"

# ---------------------------------------------------------------- the model (metres)
# EVERY number here is READ OFF the case specs, not chosen: 38 base cases, 5 rich cases and
# check_clash1 were written against this geometry (the tree README's Revit tables state the
# same figures in mm), so the builder and the expected_results are two halves of one
# statement. Refitted 2026-08-14 — the first version of this file authored a 12 x 9 m shell
# on round numbers that matched no case.
EXT_TYPE = "Exterior - Brick on Mtl. Stud"          # 350 mm, the envelope
PART_TYPE = "Interior - Blockwork 100"              # 124 mm, the interior partitions
FLOOR_TYPE = "Insitu Concrete 225mm"
DOOR_TYPE = "M_Single-Flush: 0915 x 2134mm"         # the stock single-flush the cases name
WINDOW_TYPE = "M_Fixed: 0915 x 1220mm"
# Types the cases require to be ALREADY LOADED, so their instruction ("already loaded in
# this project") is true. They are loaded/derived here and left unplaced.
ALT_WINDOW_TYPE = "M_Fixed: 0610 x 1220mm"          # replace_element_type7's target
DOUBLE_DOOR_TYPE = "M_Door-Passage-Double-Flush: 2100 x 2100mm"   # replace_element_type4's

LEVELS = [{"name": "Level 1", "level": 0.0}, {"name": "Level 2", "level": 4.0}]

# --- _env_base: the built model every edit / read atom points at -------------------
# Sized to match the ArchiCAD templates (11129 x 10205 there) so the two trees pose their
# tasks at the same scale — a 6 x 4 m shell made the "move a wall 1000 mm" atoms a sixth of
# the building. Round numbers here because this shell is authored, not hand-drawn.
X, Y = 11.0, 10.0                    # envelope, counterclockwise from (0, 0)
PX = 5.5                             # the one interior partition, running the full depth
LOOP = [((0, 0), (X, 0)), ((X, 0), (X, Y)), ((X, Y), (0, Y)), ((0, Y), (0, 0))]
FOOTPRINT = [(0.0, 0.0), (X, 0.0), (X, Y), (0.0, Y)]
EAST_ROOM = [(PX, 0.0), (X, 0.0), (X, Y), (PX, Y)]      # the enclosure east of the partition
DOOR_C = [4.0, 0.0]                  # south wall — 'the door on the south wall'
WINDOW_C = [4.0, Y]                  # north wall — 'the window on the north wall'
UPPER_WALL = ((0.0, 0.0), (5.0, 0.0))                   # delete_element2's Level 2 wall

# --- _env_rich: the same shell with a SET to pick from -----------------------------
RX, RY = X, Y
R_LOOP = LOOP
R_PART_A = ((PX, 0.0), (PX, RY))     # midpoint (5500, 5000) — delete_element7 names it there
R_PART_B = ((PX, 5.0), (RX, 5.0))    # midpoint (8250, 5000)
R_DOOR_ENTRANCE = [2.0, 0.0]         # in the SOUTH exterior wall — the one delete_element6 takes
R_DOOR_A = [PX, 2.5]                 # in partition A
R_DOOR_B = [8.25, 5.0]               # in partition B


def _ok(label, result):
    """Every action must report ok; a silent failure would ship a broken template.

    `run` hands us the INNER result, so `ok` and `guid` are where they look. Reading the
    outer {action, id, result} envelope instead is not a theoretical mistake: it made
    `.get("guid")` None, the two interior doors were placed with no host, and the build
    only noticed at the final count (2026-08-14)."""
    if not isinstance(result, dict) or result.get("ok") is False or "error" in result:
        raise SystemExit(f"  ! {label}: {json.dumps(result, ensure_ascii=False)[:300]}")
    print(f"  + {label}")
    return result


def run(tb, action, **params):
    res = tb.run_actions([{"action": action, "params": params}])
    rec = res[0] if isinstance(res, list) and res else res
    if isinstance(rec, dict) and isinstance(rec.get("result"), dict):
        return rec["result"]
    return rec


def _guid(result, label):
    g = (result or {}).get("guid")
    if not g:
        raise SystemExit(f"  ! {label}: the action returned no guid: "
                         f"{json.dumps(result, ensure_ascii=False)[:200]}")
    return g


def _shell(tb, loop, ext_type=EXT_TYPE):
    """The four exterior walls, counterclockwise, returned in LOOP order."""
    out = []
    for i, (b, e) in enumerate(loop):
        r = _ok(f"exterior wall {i} {b}->{e}",
                run(tb, "create_wall", begin=list(b), end=list(e),
                    composite_name=ext_type, reference="outside"))
        out.append(_guid(r, f"exterior wall {i}"))
    return out


def _preload_types(tb):
    """The types a case's instruction calls 'already loaded'. Loaded, never placed: a
    replace_* atom must have somewhere to go without the run authoring the type first."""
    # Both are LOADED, not authored: the stock metric library already ships them
    # (M_Door-Passage-Double-Flush carries a 2100 x 2100mm type of its own, which is why
    # duplicating one under that name fails — "the name is already in use").
    _ok(f"preload {ALT_WINDOW_TYPE}",
        run(tb, "load_family_type", element_type="Window", family=ALT_WINDOW_TYPE))
    _ok(f"preload {DOUBLE_DOOR_TYPE}",
        run(tb, "load_family_type", element_type="Door", family=DOUBLE_DOOR_TYPE))


# ---------------------------------------------------------------- builders
def build_base(tb):
    _ok("levels", run(tb, "set_stories", stories=LEVELS))
    _ok("active level = Level 1", run(tb, "set_active_story", story="Level 1"))
    walls = _shell(tb, LOOP)
    _ok("interior partition", run(tb, "create_wall", begin=[PX, 0.0], end=[PX, Y],
                                  composite_name=PART_TYPE, reference="center"))
    # the 6th wall: delete_element2 asks for "the wall that sits on Level 2", so one wall
    # stands alone up there — homed by its ELEVATION, like every other create.
    _ok("Level 2 wall (delete_element2's target)",
        run(tb, "create_wall", begin=list(UPPER_WALL[0]), end=list(UPPER_WALL[1]),
            composite_name=EXT_TYPE, reference="outside", z=4.0))
    _ok("door (south wall, opens into the building, hinge on the west jamb)",
        run(tb, "place_door", host=walls[0], center=DOOR_C, width=0.915, height=2.134,
            sill=0.0, favorite=DOOR_TYPE, opens_toward=[DOOR_C[0], 1.0],
            hinge_toward=[DOOR_C[0] - 0.45, 0.0]))
    _ok("window (north wall, glazing facing out, 900 sill)",
        run(tb, "place_window", host=walls[2], center=WINDOW_C, width=0.915, height=1.22,
            sill=0.9, favorite=WINDOW_TYPE, faces_toward=[WINDOW_C[0], Y + 1.0]))
    _ok("floor", run(tb, "create_composite_slab", polygon_xy=FOOTPRINT,
                     composite_name=FLOOR_TYPE, level=0.0))
    _ok("room 'Office' 1 (eastern enclosure)",
        run(tb, "create_zone", name="Office", number="1", polygon_xy=EAST_ROOM))
    # SEEDED DEFECT for flip_element3 / flip_element4: two envelope walls whose exterior brick face
    # points INTO the building. Flipping is a pure orientation change — the location curve
    # stays put, so every other base case sees the same geometry it always did.
    _ok("seed: south wall faces the wrong way (flip_element3's defect)",
        run(tb, "flip_wall", guid=walls[0]))
    _ok("seed: east wall faces the wrong way (flip_element4's defect)",
        run(tb, "flip_wall", guid=walls[1]))
    _preload_types(tb)
    _expect(tb, {"walls": 6, "doors": 1, "windows": 1, "slabs": 1, "rooms": 1})


def build_rich(tb):
    _ok("levels", run(tb, "set_stories", stories=LEVELS))
    _ok("active level = Level 1", run(tb, "set_active_story", story="Level 1"))
    walls = _shell(tb, R_LOOP)
    pa = _ok("partition A (vertical, x=5500)",
             run(tb, "create_wall", begin=list(R_PART_A[0]), end=list(R_PART_A[1]),
                 composite_name=PART_TYPE, reference="center"))
    pb = _ok("partition B (horizontal, y=5000)",
             run(tb, "create_wall", begin=list(R_PART_B[0]), end=list(R_PART_B[1]),
                 composite_name=PART_TYPE, reference="center"))
    # three doors, each nameable in one phrase: the ENTRANCE in an exterior wall (the one
    # delete_element6 removes) and one in each partition (the two that go with the walls).
    _ok("entrance door (south exterior wall)",
        run(tb, "place_door", host=walls[0], center=R_DOOR_ENTRANCE, width=0.915,
            height=2.134, sill=0.0, favorite=DOOR_TYPE,
            opens_toward=[R_DOOR_ENTRANCE[0], 1.0],
            hinge_toward=[R_DOOR_ENTRANCE[0] - 0.45, 0.0]))
    _ok("interior door in partition A",
        run(tb, "place_door", host=_guid(pa, "partition A"), center=R_DOOR_A, width=0.915,
            height=2.134, sill=0.0, favorite=DOOR_TYPE,
            opens_toward=[5.0, R_DOOR_A[1]], hinge_toward=[4.0, R_DOOR_A[1] - 0.45]))
    _ok("interior door in partition B",
        run(tb, "place_door", host=_guid(pb, "partition B"), center=R_DOOR_B, width=0.915,
            height=2.134, sill=0.0, favorite=DOOR_TYPE,
            opens_toward=[R_DOOR_B[0], 4.0], hinge_toward=[R_DOOR_B[0] - 0.45, 3.0]))
    # three windows, one per exterior wall that has no door — same rule
    _ok("window north", run(tb, "place_window", host=walls[2], center=[8.0, RY], width=0.915,
                            height=1.22, sill=0.9, favorite=WINDOW_TYPE,
                            faces_toward=[8.0, RY + 1.0]))
    _ok("window east", run(tb, "place_window", host=walls[1], center=[RX, 7.5], width=0.915,
                           height=1.22, sill=0.9, favorite=WINDOW_TYPE,
                           faces_toward=[RX + 1.0, 7.5]))
    _ok("window west", run(tb, "place_window", host=walls[3], center=[0.0, 7.5], width=0.915,
                           height=1.22, sill=0.9, favorite=WINDOW_TYPE,
                           faces_toward=[-1.0, 7.5]))
    # NO floor and NO room, mirroring ArchiCAD's _env_rich: `create_slab1` covers this
    # enclosure and needs it empty, and a set-picking env has no business seeding the very
    # element another atom creates. The floor/room atoms point at _env_base instead.
    _preload_types(tb)
    _expect(tb, {"walls": 6, "doors": 3, "windows": 3, "slabs": 0, "rooms": 0})


# Three defects on top of _env_base, each nameable in one phrase, mirroring the ArchiCAD
# _env_clash so both trees pose the same three pairs:
#   1. a redundant wall buried in the south exterior wall   -> wall vs wall
#   2. a stub wall standing in front of the south door      -> wall vs door
#   3. a door overlapping the north window on the same wall -> window vs door
DUP_WALL = ((1.0, 0.15), (5.0, 0.15))
STUB_WALL = ((4.0, 1.5), (4.0, 0.0))
CLASH_DOOR_CENTER = [4.6, Y]   # overlaps the north window (at x=4000, 915 wide) by 320 mm —
                               # clash.check ignores an overlap under 20 mm, and 4.9 left only that


def build_clash(tb):
    from bench_runner.backend.snapshot import model_snapshot
    snap = model_snapshot(tb)
    # The NORTHMOST horizontal wall. Not "y == Y": Revit reports a wall's LOCATION CURVE,
    # and an envelope wall seated on its exterior finish face reports its centreline — half
    # a thickness inside the line it was authored on (175 mm here).
    horiz = [w for w in snap["walls"]
             if w.get("begCoordinate") and w.get("endCoordinate")
             and abs(w["begCoordinate"]["y"] - w["endCoordinate"]["y"]) < 1e-6
             and w.get("floor") == 0]
    north = max(horiz, key=lambda w: w["begCoordinate"]["y"], default=None)
    if north is None or north["begCoordinate"]["y"] < Y / 2:
        raise SystemExit("  ! no north wall - is this a copy of the built _env_base?")
    _ok("defect 1/3 duplicate wall inside the south wall",
        run(tb, "create_wall", begin=list(DUP_WALL[0]), end=list(DUP_WALL[1]),
            composite_name=PART_TYPE, reference="center"))
    _ok("defect 2/3 stub wall blocking the south door",
        run(tb, "create_wall", begin=list(STUB_WALL[0]), end=list(STUB_WALL[1]),
            composite_name=PART_TYPE, reference="center"))
    _ok("defect 3/3 door overlapping the north window",
        run(tb, "place_door", host=north["guid"], center=CLASH_DOOR_CENTER, width=0.915,
            height=2.134, sill=0.0, favorite=DOOR_TYPE,
            opens_toward=[CLASH_DOOR_CENTER[0], Y - 1.0],
            hinge_toward=[CLASH_DOOR_CENTER[0] - 0.45, Y]))
    from bench_runner.backend import clash
    issues = clash.check(model_snapshot(tb), tb, active_floor=0)
    print(f"  = clash.check reports {len(issues)} issue(s):")
    for i in issues:
        print("    -", json.dumps(i, ensure_ascii=False))
    if not issues:
        raise SystemExit("  ! the seeded defects are not detected - do not ship this template")
    print("  ! set check_clash1's answer_pairs from the pairs above before shipping")


BUILD = {"base": build_base, "clash": build_clash, "rich": build_rich}
# clash starts from the BUILT base, everything else from the stock empty template
SOURCE = {"base": "_env_empty", "rich": "_env_empty", "clash": "_env_base"}


def _expect(tb, want):
    from bench_runner.backend.snapshot import model_snapshot
    got = {k: len(v) for k, v in model_snapshot(tb).items() if isinstance(v, list)}
    print(f"  = {got}")
    bad = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
    if bad:
        raise SystemExit(f"  ! built model does not match the spec (got, want): {bad}")


def write_baseline(tb, start: Path):
    from bench_runner.backend.snapshot import model_snapshot
    out = start / "baseline.json"
    out.write_text(json.dumps({"source": f"live @ {start.parent.parent.name}",
                               "snapshot": model_snapshot(tb),
                               "composites": tb.list_composites()},
                              ensure_ascii=False), encoding="utf-8")
    print(f"  + baseline.json ({out.stat().st_size} bytes)")


def make(kind: str, tb, open_wait: float, save_wait: float):
    from drivers import revit_io
    dest_dir = RV / f"_env_{kind}" / "start"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "revit.rvt"
    src = RV / SOURCE[kind] / "start" / "revit.rvt"
    if not src.is_file():
        raise SystemExit(f"  ! source template missing: {src}")
    print(f"\n=== _env_{kind}  (from {SOURCE[kind]}) ===")
    # Revit may still hold THIS file from an earlier build (a failed one leaves it open and
    # modified); Windows then refuses the copy with WinError 32.
    revit_io.close_open_docs()
    shutil.copy2(src, dest)
    revit_io.open_project(dest, mode="gui", open_wait=open_wait)
    time.sleep(2.0)
    BUILD[kind](tb)
    revit_io.save_as(dest, mode="gui", save_wait=save_wait)
    write_baseline(tb, dest_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--which", choices=sorted(BUILD), required=True,
                    help="which template to build (overwrites it)")
    ap.add_argument("--open-wait", type=float, default=25.0)
    ap.add_argument("--save-wait", type=float, default=12.0)
    a = ap.parse_args()

    from bench_runner.backend import Toolbox
    tb = Toolbox.connect("revit")
    make(a.which, tb, a.open_wait, a.save_wait)
    return 0


if __name__ == "__main__":
    sys.exit(main())
