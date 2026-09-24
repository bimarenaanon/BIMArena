#!/usr/bin/env python
"""Prove every REVIT atomic case is BOTH failable and passable against its env.

    python bench_cases/atomic_tasks/validate_env_revit.py               # all cases
    python bench_cases/atomic_tasks/validate_env_revit.py --only flip_element3 move_element4
    python bench_cases/atomic_tasks/validate_env_revit.py --start-only  # no Revit needed

The ArchiCAD twin is `validate_env_archicad.py`; the GRADING half is shared with it (this
file imports it and re-points its case tree), because "does the untouched start already
satisfy the key" is the same question in both applications. What differs is everything
live: the reference solutions below speak the Revit add-in's actions, and a project is
opened through the Revit GUI rather than Tapir.

The solutions are an ANSWER KEY: they live here beside `expected_result`, never anywhere
the agent can read. Read cases (`inspect_project*`, `check_clash*`, `query_*`) have no solution — their automated half only asserts the model was not
touched, and their real deliverable is the text they write, graded from `answer_*` keys.

Geometry here is in METRES (the backend's unit) and states the AUTHORING lines: an envelope
wall is drawn on its exterior face, so the shell is 0..11 x 0..10 even though the snapshot
reports the location curve half a thickness inside. See build_env_revit.py — the two files
share one geometry and are refitted together.
"""
from __future__ import annotations

import argparse
import importlib.util
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

# the shared grading half (see the module docstring)
_spec_ac = importlib.util.spec_from_file_location("_vea", TREE / "validate_env_archicad.py")
_AC = importlib.util.module_from_spec(_spec_ac)
_spec_ac.loader.exec_module(_AC)
_AC.AC = RV                       # every _spec/_baseline/start_state call now reads the Revit tree

# ---------------------------------------------------------------- the model (metres)
# Mirrors build_env_revit.py — import it rather than restate it, so a template reshape
# cannot leave the validator behind.
_spec_b = importlib.util.spec_from_file_location("_bev", TREE / "build_env_revit.py")
B = importlib.util.module_from_spec(_spec_b)
_spec_b.loader.exec_module(B)

X, Y, PX = B.X, B.Y, B.PX
EXT_TYPE, PART_TYPE, FLOOR_TYPE = B.EXT_TYPE, B.PART_TYPE, B.FLOOR_TYPE
DOOR_TYPE, WINDOW_TYPE = B.DOOR_TYPE, B.WINDOW_TYPE
ALT_WINDOW_TYPE, DOUBLE_DOOR_TYPE = B.ALT_WINDOW_TYPE, B.DOUBLE_DOOR_TYPE

WEST_ROOM = [(0.35, 0.35), (PX - 0.1, 0.35), (PX - 0.1, Y - 0.35), (0.35, Y - 0.35)]
WEST_ROOM_N = [(0.35, 5.05), (PX - 0.1, 5.05), (PX - 0.1, Y - 0.35), (0.35, Y - 0.35)]
# the east room shrunk by 5 m2: 42.3 / 9.3 m deep = 4.548 m wide, from the partition face
EAST_ROOM_SMALL = [(5.562, 0.35), (10.11, 0.35), (10.11, 9.65), (5.562, 9.65)]


# ---------------------------------------------------------------- model handles
class Model:
    """The seeded env, addressed the way an instruction addresses it. Walls are resolved by
    ROLE, not by coordinates: Revit reports a wall's location curve, which for an envelope
    wall seated on its exterior face is half a thickness inside the line it was drawn on."""

    def __init__(self, tb):
        from bench_runner.backend.snapshot import model_snapshot
        self.tb = tb
        self.snap = model_snapshot(tb)

    def _walls(self, floor=0):
        return [w for w in self.snap["walls"] if w.get("floor") == floor
                and w.get("begCoordinate") and w.get("endCoordinate")]

    def _mid(self, w):
        b, e = w["begCoordinate"], w["endCoordinate"]
        return ((b["x"] + e["x"]) / 2, (b["y"] + e["y"]) / 2)

    def _side(self, axis, pick, want=EXT_TYPE):
        cand = [w for w in self._walls() if w.get("composite") == want]
        if axis == "x":                       # vertical walls -> east / west
            cand = [w for w in cand
                    if abs(w["begCoordinate"]["x"] - w["endCoordinate"]["x"]) < 1e-6]
            key = lambda w: self._mid(w)[0]
        else:                                 # horizontal walls -> north / south
            cand = [w for w in cand
                    if abs(w["begCoordinate"]["y"] - w["endCoordinate"]["y"]) < 1e-6]
            key = lambda w: self._mid(w)[1]
        if not cand:
            raise SystemExit(f"  ! no {want} wall along {axis}")
        return pick(cand, key=key)

    south = property(lambda s: s._side("y", min))
    north = property(lambda s: s._side("y", max))
    west = property(lambda s: s._side("x", min))
    east = property(lambda s: s._side("x", max))
    partitions = property(lambda s: [w for w in s._walls() if w.get("composite") == PART_TYPE])
    partition = property(lambda s: s.partitions[0])
    upper = property(lambda s: s._walls(floor=1)[0])
    door = property(lambda s: s.snap["doors"][0])
    window = property(lambda s: s.snap["windows"][0])
    slab = property(lambda s: s.snap["slabs"][0])
    room = property(lambda s: s.snap["rooms"][0])

    def near(self, bucket, x, y, tol=0.4):
        hit = [e for e in self.snap[bucket] if e.get("center")
               and abs(e["center"][0] - x) < tol and abs(e["center"][1] - y) < tol]
        if len(hit) != 1:
            raise SystemExit(f"  ! {len(hit)} {bucket} at {(x, y)}, expected exactly one")
        return hit[0]

    def every(self):
        return [e["guid"] for b in ("doors", "windows", "stairs", "objects", "rooms",
                                    "slabs", "walls") for e in self.snap.get(b) or []]


def run(tb, action, **params):
    return B.run(tb, action, **params)


def _move_with_constrain(tb, m, dy=0.5):
    """The constrained move by hand: the north wall goes +dy and the two joined side walls
    are stretched to follow.

    Every endpoint is taken from the wall's CURRENT location curve and shifted — never
    restated from the design lines. An envelope wall drawn on its exterior face reports a
    curve half a thickness inside it, so re-issuing `begin=[X, ...]` would MOVE the wall
    175 mm outward instead of leaving it where it is (measured: the east wall failed its
    own key that way while the north one passed)."""
    def pts(w):
        b, e = w["begCoordinate"], w["endCoordinate"]
        return [[b["x"], b["y"]], [e["x"], e["y"]]]

    n = m.north
    p = pts(n)
    run(tb, "modify_wall", guid=n["guid"], begin=[p[0][0], p[0][1] + dy],
        end=[p[1][0], p[1][1] + dy])
    for w in (m.east, m.west):
        p = pts(w)
        i = 0 if p[0][1] > p[1][1] else 1          # the endpoint that meets the north wall
        p[i][1] += dy
        run(tb, "modify_wall", guid=w["guid"], begin=p[0], end=p[1])


# ---------------------------------------------------------------- reference solutions
def _solutions():
    """case id -> f(tb, m) applying the reference solution (metres at this layer)."""
    S = {}

    # --- empty env: the coordinates come from the INSTRUCTION -----------------------
    S["create_wall1"] = lambda tb, m: [
        run(tb, "create_wall", begin=list(b), end=list(e), composite_name=EXT_TYPE,
            reference="outside")
        for b, e in (((0, 0), (6, 0)), ((6, 0), (6, 4)), ((6, 4), (0, 4)), ((0, 4), (0, 0)))]
    S["create_wall2"] = lambda tb, m: [
        run(tb, "create_wall", begin=list(b), end=list(e), height=6.0,
            composite_name="Exterior - Render on Brick on Block", reference="outside")
        for b, e in (((0, 0), (8, 0)), ((8, 0), (8, 5)), ((8, 5), (0, 5)), ((0, 5), (0, 0)))]
    S["create_wall3"] = lambda tb, m: run(tb, "create_wall", begin=[0.0, 0.0], end=[5.0, 0.0],
                                          composite_name=PART_TYPE, reference="center",
                                          height=4.0)
    S["create_wall_type1"] = lambda tb, m: run(
        tb, "create_composite", name="Insulated CMU 250", use_with=["Wall"],
        skins=[{"material": "Render, Tan, Textured", "type": "Finish", "thickness": 0.01},
               {"material": "Cavity Fill", "type": "Other", "thickness": 0.05},
               {"material": "Brick, Common", "type": "Core", "thickness": 0.1}])
    S["create_slab_type1"] = lambda tb, m: run(
        tb, "create_composite", name="Screed on Cast Concrete 250", use_with=["Slab"],
        skins=[{"material": "Ceramic Tile", "type": "Finish", "thickness": 0.05},
               {"material": "Concrete, Cast In Situ", "type": "Core", "thickness": 0.2}])
    S["create_stair1"] = lambda tb, m: run(tb, "create_stair", baseline_xy=[[0.5, 0.6], [4.5, 0.6]],
                                           z=0.0, total_height=4.0, flight_width=1.0)
    S["create_stories1"] = lambda tb, m: run(tb, "set_stories", stories=[
        {"name": "First Floor", "level": 0.0}, {"name": "Second Floor", "level": 3.2},
        {"name": "Third Floor", "level": 6.4}])

    # --- _env_base: creation --------------------------------------------------------
    S["create_room_zone1"] = lambda tb, m: run(tb, "create_zone", name="Lobby", number="3",
                                          polygon_xy=WEST_ROOM)
    S["create_room_zone2"] = lambda tb, m: run(tb, "create_zone", name="Storage", number="10",
                                          polygon_xy=WEST_ROOM)
    S["create_room_zone3"] = lambda tb, m: [
        run(tb, "create_zone_separation_line", polyline_xy=[[0.0, 5.0], [PX, 5.0]]),
        run(tb, "create_zone", name="Lobby", number="4", polygon_xy=WEST_ROOM_N)]
    S["create_slab1"] = lambda tb, m: run(tb, "create_composite_slab", polygon_xy=B.FOOTPRINT,
                                          composite_name=FLOOR_TYPE, level=0.0)
    S["create_slab_opening1"] = lambda tb, m: run(tb, "create_slab_opening",
                                                  slab_guid=m.slab["guid"], base_xy=[2.5, 4.5],
                                                  width=1.0, height=1.0, z=0.0)
    S["create_door_window_type1"] = lambda tb, m: [
        run(tb, "create_family_type", element_type="Door", family="M_Single-Flush",
            name="0750 x 2000mm", width=0.75, height=2.0),
        run(tb, "place_door", host=m.west["guid"], center=[0.0, 3.0], sill=0.0,
            favorite="M_Single-Flush: 0750 x 2000mm", opens_toward=[1.0, 3.0],
            hinge_toward=[0.0, 3.45])]
    S["create_door_window_type2"] = lambda tb, m: [
        run(tb, "create_family_type", element_type="Window", family="M_Fixed",
            name="1000 x 1200mm", width=1.0, height=1.2),
        run(tb, "place_window", host=m.west["guid"], center=[0.0, 6.0], sill=0.9,
            favorite="M_Fixed: 1000 x 1200mm", faces_toward=[-1.0, 6.0])]
    S["load_library_element_type1"] = lambda tb, m: [
        run(tb, "load_family_type", element_type="Door", family="M_Door-Double-Sliding"),
        run(tb, "place_door", host=m.west["guid"], center=[0.0, 3.0], sill=0.0,
            favorite="M_Door-Double-Sliding: 1700 x 2100mm", opens_toward=[1.0, 3.0],
            hinge_toward=[0.0, 3.45])]
    S["load_library_element_type2"] = lambda tb, m: [
        run(tb, "load_family_type", element_type="Window",
            family="M_Window-Casement-Triple-Side-Transom"),
        run(tb, "place_window", host=m.west["guid"], center=[0.0, 6.0], sill=0.9,
            favorite="M_Window-Casement-Triple-Side-Transom: 2150 x 1500mm",
            faces_toward=[-1.0, 6.0])]
    S["create_door1"] = lambda tb, m: run(tb, "place_door", host=m.west["guid"], center=[0.0, 2.0],
                                         sill=0.0, favorite=DOOR_TYPE, opens_toward=[1.0, 2.0],
                                         hinge_toward=[0.0, 2.45])
    S["create_door2"] = lambda tb, m: [
        run(tb, "place_door", host=m.east["guid"], center=[X, 3.0], sill=0.0, favorite=DOOR_TYPE,
            opens_toward=[X - 1.0, 3.0], hinge_toward=[X, 3.45]),
        run(tb, "place_door", host=m.partition["guid"], center=[PX, 1.0], sill=0.0,
            favorite="M_Single-Flush: 0762 x 2032mm", opens_toward=[PX + 1.0, 1.0],
            hinge_toward=[PX, 0.55])]
    S["create_window1"] = lambda tb, m: run(tb, "place_window", host=m.east["guid"],
                                           center=[X, 2.0], sill=0.9, favorite=WINDOW_TYPE,
                                           faces_toward=[X + 1.0, 2.0])
    S["create_window2"] = lambda tb, m: [
        run(tb, "place_window", host=m.south["guid"], center=[1.0, 0.0], sill=1.2,
            favorite=WINDOW_TYPE, faces_toward=[1.0, -1.0]),
        run(tb, "place_window", host=m.east["guid"], center=[X, 1.0], sill=1.8,
            favorite=ALT_WINDOW_TYPE, faces_toward=[X + 1.0, 1.0])]

    # --- _env_base: edits -----------------------------------------------------------
    S["delete_element1"] = lambda tb, m: [run(tb, "delete_element", guid=d["guid"])
                                          for d in m.snap["doors"]]
    S["delete_element2"] = lambda tb, m: run(tb, "delete_element", guid=m.room["guid"])
    S["flip_element3"] = lambda tb, m: run(tb, "flip_wall", guid=m.south["guid"])
    S["flip_element4"] = lambda tb, m: run(tb, "flip_wall", guid=m.east["guid"])
    S["flip_element1"] = lambda tb, m: run(tb, "modify_door", guid=m.door["guid"],
                                        opens_toward=[4.0, -1.0], hinge_toward=[3.55, 0.0])
    S["flip_element2"] = lambda tb, m: run(tb, "modify_door", guid=m.door["guid"],
                                              opens_toward=[4.0, 1.0], hinge_toward=[4.45, 0.0])
    S["flip_element5"] = lambda tb, m: run(tb, "modify_window", guid=m.window["guid"],
                                          faces_toward=[4.0, Y - 1.0])
    S["replace_element_type1"] = lambda tb, m: run(tb, "modify_zone", guid=m.room["guid"],
                                          name="Meeting Room", number="1",
                                          polygon_xy=EAST_ROOM_SMALL)
    S["move_element1"] = lambda tb, m: run(tb, "modify_slab", guid=m.slab["guid"],
                                          polygon_xy=[(0.0, 0.0), (X + 1.0, 0.0),
                                                      (X + 1.0, Y), (0.0, Y)])
    S["replace_element_type2"] = lambda tb, m: run(tb, "modify_wall", guid=m.partition["guid"],
                                          height=3.6)
    S["replace_element_type3"] = lambda tb, m: run(tb, "modify_window", guid=m.window["guid"], sill=1.1)
    S["move_element2"] = lambda tb, m: run(tb, "modify_door", guid=m.door["guid"],
                                        center=[2.0, 0.0])
    S["move_element4"] = lambda tb, m: run(tb, "modify_wall", guid=m.partition["guid"],
                                        begin=[PX + 1.0, 0.0], end=[PX + 1.0, Y])
    S["move_element5"] = lambda tb, m: run(tb, "modify_window", guid=m.window["guid"],
                                          center=[2.0, Y])
    S["move_with_constraints1"] = _move_with_constrain
    S["replace_element_type4"] = lambda tb, m: run(tb, "replace_door", guid=m.door["guid"],
                                                favorite="M_Single-Flush: 0762 x 2134mm")
    S["replace_element_type7"] = lambda tb, m: run(tb, "replace_window", guid=m.window["guid"],
                                                  favorite=ALT_WINDOW_TYPE, sill=0.9)
    S["replace_element_type5"] = lambda tb, m: run(tb, "modify_slab", guid=m.slab["guid"],
                                                composite_name="Concrete-Domestic 425mm")
    S["replace_element_type6"] = lambda tb, m: run(tb, "modify_wall", guid=m.partition["guid"],
                                                composite_name="Interior - Blockwork 140")
    S["switch_active_story1"] = lambda tb, m: run(tb, "set_active_story", story="Level 2")

    # --- _env_rich ------------------------------------------------------------------
    S["delete_element3"] = lambda tb, m: [run(tb, "delete_element", guid=g) for g in m.every()]
    S["delete_element4"] = lambda tb, m: [run(tb, "delete_element", guid=w["guid"])
                                          for w in m.snap["windows"]]
    S["delete_element5"] = lambda tb, m: run(tb, "delete_element", guid=m.slab["guid"])
    S["delete_element6"] = lambda tb, m: run(tb, "delete_element",
                                             guid=m.near("doors", 2.0, 0.175)["guid"])
    S["delete_element7"] = lambda tb, m: [run(tb, "delete_element", guid=w["guid"])
                                          for w in m.partitions]
    return S


NO_API = {}                      # every Revit atom has an API route (unlike ArchiCAD's library)
READ_ONLY = _AC.READ_ONLY


def _await_revit(revit_io, tries: int = 6, wait: float = 8.0) -> None:
    """Block until the add-in answers, giving Revit the foreground first.

    Revit's external-event queue STALLS while another window holds focus: the add-in then
    answers /health with "Revit job timed out" and every action quietly does nothing. A case
    validated in that state fails for no reason (measured 2026-08-14 — create_room_zone2 came back
    4/6 with its room never created, and one _focus_revit() brought the queue straight back)."""
    import urllib.request
    for _ in range(tries):
        revit_io._focus_revit()
        try:
            if b'"ok":true' in urllib.request.urlopen("http://localhost:48884/health",
                                                      timeout=25).read():
                return
        except Exception:
            pass
        time.sleep(wait)
    print("  [warn] the Revit add-in is not answering — results below are not trustworthy")


# ---------------------------------------------------------------- the live half
def solutions(only=None, open_wait: float = 25.0) -> int:
    from bench_runner.backend import Toolbox
    from bench_runner.backend.snapshot import model_snapshot
    from drivers import revit_io

    tb = Toolbox.connect("revit")
    sols = _solutions()
    work = ROOT / "bench_cases" / "atomic_tasks" / ".validate"
    work.mkdir(exist_ok=True)
    failed, missing = [], []
    for cid in sorted(sols):
        if only and cid not in only:
            continue
        src = RV / cid / "env" / "start" / "revit.rvt"
        if not src.is_file():
            print(f"  {cid:26s} --    NO ENV")
            missing.append(cid)
            continue
        rvt = work / f"{cid}.rvt"
        _await_revit(revit_io)
        revit_io.close_open_docs()
        shutil.copy2(src, rvt)
        revit_io.open_project(rvt, mode="gui", open_wait=open_wait)
        time.sleep(2.0)
        before = {c["name"] for c in tb.list_composites()}
        try:
            sols[cid](tb, Model(tb))
        except SystemExit as e:
            print(f"  {cid:26s} SOLUTION ERROR {e}")
            failed.append(cid)
            continue
        made = [c for c in tb.list_composites() if c["name"] not in before]
        r = _AC._grade(cid, model_snapshot(tb), made)
        bad = [c["id"] for c in r["checkpoints"] if c["score"] == 0.0]
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  {cid:26s} {mark} {r['checkpoints_passed']}/{r['checkpoints_total']}"
              + (f"  {','.join(bad[:6])}" if bad else ""))
        if not r["passed"]:
            failed.append(cid)
    print(f"\n{len(failed)} case(s) whose reference solution does not pass: {failed or 'none'}")
    if missing:
        print(f"{len(missing)} case(s) with no env: {missing}")
    print(f"(working copies under {work} - throwaway, gitignored)")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="case ids to check")
    ap.add_argument("--start-only", action="store_true",
                    help="only the failable direction (no Revit needed)")
    ap.add_argument("--open-wait", type=float, default=25.0)
    a = ap.parse_args()
    only = set(a.only) if a.only else None
    rc = _AC.start_state(only)
    if a.start_only:
        return rc
    print()
    return solutions(only, a.open_wait) or rc


if __name__ == "__main__":
    sys.exit(main())
