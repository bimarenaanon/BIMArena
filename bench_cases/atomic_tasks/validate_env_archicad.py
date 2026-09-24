#!/usr/bin/env python
"""Prove every ArchiCAD atomic case is BOTH failable and passable against its env.

    python bench_cases/atomic_tasks/validate_env_archicad.py            # all cases
    python bench_cases/atomic_tasks/validate_env_archicad.py --only flip_element1 move_element4

For each case with a scripted reference solution below: open its seeded `env/start`, apply
the solution through the API, snapshot, and grade the result against the case's own
`expected_result`. A case that does NOT come out PASS is a defect in the pair (env, spec) —
either the instruction asks for something the env cannot supply, or the expected_result pins
something the atom does not produce.

The complement (every case must FAIL on the untouched start state, or it grades nothing) is
checked by `--start-only`, which needs no live application at all.

The solutions are an ANSWER KEY: they live here beside `expected_result`, never anywhere the
agent can read. Read cases (`inspect_project*`, `check_clash*`, `query_*`) have no solution here — their automated half only asserts the model was
not touched, and their real answer is the final text they write. That text is MACHINE-GRADED
(`answer_values` / `answer_items` / `answer_pairs`), so those cases are failable like any
other and are checked here with an EMPTY answer — which is what "did nothing" means for a
read atom.
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

AC = TREE / "archicad"

# The templates' geometry, in METRES (the specs state it in mm). _env_base and _env_rich
# share ONE envelope — the 2026-08-13 reshape — so the wall handles below serve both; the
# numbers are the walls' REFERENCE LINES, which is what the snapshot reports.
# Re-read them off `<template>/start/baseline.json` if a template is ever re-authored: every
# constant here also appears in a case's expected_result, so the two must move together.
ENV_X, ENV_Y = 11.129, 10.205          # exterior rectangle, counterclockwise from (0, 0)
PARTITION_X = 5.784                    # _env_base's one interior wall, running full depth
WALL_T = 0.275                         # exterior wall thickness -> where the inner faces sit

FOOTPRINT = [(0.0, 0.0), (ENV_X, 0.0), (ENV_X, ENV_Y), (0.0, ENV_Y)]
# Zone polygons: inside the wall faces, so the zone lands in the enclosure it names. Kept
# clear of the faces by more than the tolerance rather than traced onto them.
WEST_ENCLOSURE = [(0.3, 0.3), (PARTITION_X - 0.1, 0.3),
                  (PARTITION_X - 0.1, ENV_Y - 0.3), (0.3, ENV_Y - 0.3)]
INNER = [(0.3, 0.3), (ENV_X - 0.3, 0.3), (ENV_X - 0.3, ENV_Y - 0.3), (0.3, ENV_Y - 0.3)]


# ---------------------------------------------------------------- model handles
class Model:
    """The seeded _env_base, addressed the way an instruction addresses it."""

    def __init__(self, tb):
        from bench_runner.backend.snapshot import model_snapshot
        self.tb = tb
        self.snap = model_snapshot(tb)

    def _wall(self, x0, y0, x1, y1, floor=0):
        for w in self.snap["walls"]:
            b, e = w["begCoordinate"], w["endCoordinate"]
            got = {(round(b["x"], 3), round(b["y"], 3)), (round(e["x"], 3), round(e["y"], 3))}
            if got == {(x0, y0), (x1, y1)} and w.get("floor") == floor:
                return w
        raise SystemExit(f"  ! no wall {(x0, y0)}-{(x1, y1)} on floor {floor}")

    # The four sides of the envelope _env_base and _env_rich share, named the way an
    # instruction names them. (There is no `upper` handle any more: _env_base's isolated
    # First-Floor wall was removed 2026-08-13 and `delete_element2` re-aimed at the zone.)
    south = property(lambda s: s._wall(0.0, 0.0, ENV_X, 0.0))
    east = property(lambda s: s._wall(ENV_X, 0.0, ENV_X, ENV_Y))
    north = property(lambda s: s._wall(ENV_X, ENV_Y, 0.0, ENV_Y))
    west = property(lambda s: s._wall(0.0, ENV_Y, 0.0, 0.0))
    partition = property(lambda s: s._wall(PARTITION_X, 0.0, PARTITION_X, ENV_Y))
    door = property(lambda s: s.snap["doors"][0])
    window = property(lambda s: s.snap["windows"][0])
    slab = property(lambda s: s.snap["slabs"][0])
    zone = property(lambda s: s.snap["rooms"][0])

    # Every wall that is not part of the exterior envelope. Keyed on "not the exterior
    # composite" rather than on the partition's own type: since 2026-08-14 _env_base's
    # partition is a BASIC wall (so its thickness can be edited — see the tree README),
    # and it carries no composite name to match on.
    partitions = property(lambda s: [w for w in s.snap["walls"]
                                     if w.get("composite") != "100 Block Insulated Cavity"])

    def near(self, bucket, x, y, tol=0.3):
        """The one element of `bucket` whose centre is at [x, y] — how an instruction that
        says "the entrance door in the south wall" resolves to a guid."""
        hit = [e for e in self.snap[bucket] if e.get("center")
               and abs(e["center"][0] - x) < tol and abs(e["center"][1] - y) < tol]
        if len(hit) != 1:
            raise SystemExit(f"  ! {len(hit)} {bucket} at {(x, y)}, expected exactly one")
        return hit[0]

    def every(self):
        """Every element in the model, in delete order (openings before their hosts)."""
        return [e["guid"] for b in ("doors", "windows", "stairs", "objects", "rooms",
                                    "slabs", "walls") for e in self.snap.get(b) or []]


# ---------------------------------------------------------------- reference solutions
def _delete_composite(tb, name):
    """Delete a composite ATTRIBUTE by name. The packaged tool layer has no
    delete-composite tool (deliberate — see delete_element8's reason), so this speaks the
    official JSON interface directly (API.DeleteAttributes), the raw-code arm's route."""
    import urllib.request
    acc = tb.client.acc
    ids = acc.GetAttributesByType("Composite")
    comps = acc.GetCompositeAttributes(ids)
    guid = next((str(i.attributeId.guid) for i, d in zip(ids, comps)
                 if d.compositeAttribute.name == name), None)
    if guid is None:
        raise SystemExit(f"composite '{name}' not found")
    payload = {"command": "API.DeleteAttributes",
               "parameters": {"attributeIds": [{"attributeId": {"guid": guid}}]}}
    req = urllib.request.Request("http://127.0.0.1:19723",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode("utf-8"))
    execs = (resp.get("result") or {}).get("executionResults") or []
    if not resp.get("succeeded") or any(not e.get("success") for e in execs):
        raise SystemExit(f"API.DeleteAttributes failed: {resp}")


def _solutions():
    """case id -> f(tb, m) applying the reference solution (metres at this layer).

    Every coordinate here is the one the case's `expected_result` states, converted to
    metres: this file and the keys are two halves of one statement, so a template reshape
    (or a spec edit) has to land in both. Refitted 2026-08-14 to the current templates.
    """
    S = {}

    # --- creation atoms, empty env (their coordinates come from the INSTRUCTION, not
    #     from a template, so they are unaffected by an env reshape) ---
    S["create_wall1"] = lambda tb, m: [
        tb.create_wall(b, e, composite_name="100 Block Insulated Cavity", reference="outside")
        for b, e in (((0, 0), (6, 0)), ((6, 0), (6, 4)), ((6, 4), (0, 4)), ((0, 4), (0, 0)))]
    S["create_wall2"] = lambda tb, m: tb.create_wall(
        (0.0, 0.0), (5.0, 0.0), composite_name="Double 50 Block Cavity Plastered",
        reference="center")
    S["create_wall_type1"] = lambda tb, m: tb.create_composite(
        "Insulated Stud Partition 126",
        [{"material": "Plaster - Gypsum", "type": "Finish", "thickness": 0.013},
         {"material": "Insulation - Mineral Soft", "type": "Core", "thickness": 0.1},
         {"material": "Plaster - Gypsum", "type": "Finish", "thickness": 0.013}],
        use_with=("Wall",))
    S["create_slab_type1"] = lambda tb, m: tb.create_composite(
        "Timber Deck Floor 270",
        [{"material": "Timber - Floor", "type": "Finish", "thickness": 0.02},
         {"material": "Brick", "type": "Other", "thickness": 0.05},
         {"material": "Reinforced Concrete - Structural", "type": "Core", "thickness": 0.2}],
        use_with=("Slab",))
    # step_num alone is enough since 2026-08-14: the backend converts it to a riser HEIGHT,
    # which is the only one of the two Tapir honours (see actions/stairs.py).
    S["create_stair1"] = lambda tb, m: tb.create_stair([(1.0, 1.0), (4.0, 1.0)], z=0.0,
                                                       total_height=3.0, flight_width=0.8,
                                                       step_num=15)
    S["create_stories1"] = lambda tb, m: tb.set_stories(
        [{"name": "Ground Floor level", "level": 0.0},
         {"name": "First Floor level", "level": 3.2},
         {"name": "Top Floor level", "level": 6.4}])
    # append = rewrite the WHOLE stack (SetStories replaces it): the three seeded
    # storeys verbatim (two are unnamed) plus the new top at 6.0 + 2.7
    S["create_stories2"] = lambda tb, m: tb.set_stories(
        [{"name": "Ground Floor", "level": 0.0},
         {"name": "", "level": 3.0},
         {"name": "", "level": 6.0},
         {"name": "Third Floor", "level": 8.7}])

    # --- creation atoms, built env ---
    S["create_slab1"] = lambda tb, m: tb.create_composite_slab(
        composite_name="Concrete Floor with 10mm Tile", polygon_xy=FOOTPRINT, level=0.0)
    # a 1 x 1 m hole in the middle of the WEST enclosure - clear of every wall by metres
    S["create_slab_opening1"] = lambda tb, m: tb.create_slab_opening(
        m.slab["guid"], (2.5, 4.5), 1.0, 1.0, z=0.0)
    S["create_room_zone1"] = lambda tb, m: tb.create_zone("Lobby", "02", WEST_ENCLOSURE)
    S["create_room_zone2"] = lambda tb, m: tb.create_zone("Storage", "10", INNER)
    # no hinge_toward: the hinge halves were removed from both specs 2026-08-21 — hinge
    # grading on a NEW inward-opening door is route-inconsistent until the reflected XOR
    # oSide mirror lands in decode+encode (see the cases' reasons)
    S["create_door1"] = lambda tb, m: tb.place_door(m.west["guid"], [0.0, 2.0], 1.2, 2.1,
                                                   sill=0.0, opens_toward=[1.0, 2.0])
    S["create_door2"] = lambda tb, m: [
        tb.place_door(m.east["guid"], [ENV_X, 3.0], 1.0, 2.1, sill=0.0,
                      opens_toward=[ENV_X - 1.0, 3.0]),
        tb.place_door(m.partition["guid"], [PARTITION_X, 1.0], 0.8, 2.0, sill=0.0,
                      opens_toward=[PARTITION_X + 1.0, 1.0])]
    S["create_window1"] = lambda tb, m: tb.place_window(m.east["guid"], [ENV_X, 2.0], 1.2, 1.2,
                                                       sill=0.9,
                                                       faces_toward=[ENV_X + 1.0, 2.0])
    S["create_window2"] = lambda tb, m: [
        tb.place_window(m.south["guid"], [1.0, 0.0], 0.9, 1.5, sill=1.2,
                        faces_toward=[1.0, -1.0]),
        tb.place_window(m.east["guid"], [ENV_X, 1.0], 1.5, 1.0, sill=1.8,
                        faces_toward=[ENV_X + 1.0, 1.0])]

    # --- deletion atoms ---
    S["delete_element1"] = lambda tb, m: [tb.delete_element(d["guid"])
                                          for d in m.snap["doors"]]
    S["delete_element2"] = lambda tb, m: tb.delete_element(m.zone["guid"])
    S["delete_element3"] = lambda tb, m: [tb.delete_element(g) for g in m.every()]
    S["delete_element4"] = lambda tb, m: [tb.delete_element(w["guid"])
                                          for w in m.snap["windows"]]
    S["delete_element5"] = lambda tb, m: tb.delete_element(m.slab["guid"])
    S["delete_element6"] = lambda tb, m: tb.delete_element(m.near("doors", 4.0, 0.0)["guid"])
    S["delete_element7"] = lambda tb, m: [tb.delete_element(w["guid"]) for w in m.partitions]
    S["delete_element8"] = lambda tb, m: _delete_composite(tb, "100 Block Insulated Cavity")

    # --- edit atoms ---
    S["flip_element3"] = lambda tb, m: [tb.flip_wall(w["guid"]) for w in m.snap["walls"]]
    S["flip_element4"] = lambda tb, m: tb.flip_wall(m.south["guid"])
    # hinge stays on the EAST jamb — the ER's 2026-08-20 correction (a GUI flip keeps the
    # hinge side); 3.55 here predated it and drove the hinge to the west jamb.
    S["flip_element1"] = lambda tb, m: tb.modify_door(m.door["guid"], opens_toward=[4.0, -1.0],
                                                   hinge_toward=[4.45, 0.0])
    S["flip_element2"] = lambda tb, m: tb.modify_door(m.door["guid"],
                                                         opens_toward=[4.0, 1.0],
                                                         hinge_toward=[4.45, 0.0])
    # the window sits in the NORTH wall, so "inward" is -y
    S["flip_element5"] = lambda tb, m: tb.modify_window(m.window["guid"],
                                                       faces_toward=[4.0, ENV_Y - 1.0])
    S["replace_element_type1"] = lambda tb, m: tb.modify_door(m.door["guid"], width=1.2, height=2.2)
    S["replace_element_type2"] = lambda tb, m: tb.modify_door(m.door["guid"], sill=0.05)
    S["replace_element_type4"] = lambda tb, m: tb.modify_window(m.window["guid"], width=1.5,
                                                         height=1.4, sill=1.0)
    # One in-place edit: the partition is a BASIC wall, so its thickness is a field, and its
    # reference line is already the centre the case asks it to keep (a delete+recreate would
    # have to pass reference="center" — create_wall defaults to the outside face).
    S["replace_element_type3"] = lambda tb, m: tb.modify_wall(m.partition["guid"], height=2.4,
                                                     thickness=0.4)
    # same story for the slab's reference plane: create-time only, so the outline change
    # rides along with a recreate at the CORE BOTTOM plane (200 mm below the old Core Top).
    S["move_element1"] = lambda tb, m: [
        tb.delete_element(m.slab["guid"]),
        tb.create_composite_slab(composite_name="Concrete Floor with 10mm Tile",
                                 polygon_xy=[(0.0, 0.0), (ENV_X + 1.0, 0.0),
                                             (ENV_X + 1.0, ENV_Y), (0.0, ENV_Y)],
                                 level=-0.2, reference_plane="CoreBottom")]
    # 30 m2 inside the east enclosure, still covering the zone's own stamp point
    S["replace_element_type5"] = lambda tb, m: tb.modify_zone(
        m.zone["guid"], name="Meeting Room", number="02",
        polygon_xy=[(5.9, 2.0), (10.8, 2.0), (10.8, 8.12), (5.9, 8.12)])
    S["move_element4"] = lambda tb, m: tb.modify_wall(m.partition["guid"],
                                                   begin=(PARTITION_X + 1.0, 0.0),
                                                   end=(PARTITION_X + 1.0, ENV_Y))
    S["move_element2"] = lambda tb, m: tb.modify_door(m.door["guid"], center=(2.0, 0.0))
    S["move_element5"] = lambda tb, m: tb.modify_window(m.window["guid"], center=(2.0, ENV_Y))
    # the constrained move by hand: the north wall goes +500 and everything joined to it is
    # stretched to follow - the two side walls, the partition, the slab and the zone.
    S["move_with_constraints1"] = lambda tb, m: [
        tb.modify_wall(m.north["guid"], begin=(ENV_X, ENV_Y + 0.5), end=(0.0, ENV_Y + 0.5)),
        tb.modify_wall(m.east["guid"], begin=(ENV_X, 0.0), end=(ENV_X, ENV_Y + 0.5)),
        tb.modify_wall(m.west["guid"], begin=(0.0, ENV_Y + 0.5), end=(0.0, 0.0)),
        tb.modify_wall(m.partition["guid"], begin=(PARTITION_X, 0.0),
                       end=(PARTITION_X, ENV_Y + 0.5)),
        tb.modify_slab(m.slab["guid"],
                       polygon_xy=[(0.0, 0.0), (ENV_X, 0.0),
                                   (ENV_X, ENV_Y + 0.5), (0.0, ENV_Y + 0.5)]),
        tb.modify_zone(m.zone["guid"], name="Office", number="01",
                       polygon_xy=[(PARTITION_X + 0.05, WALL_T),
                                   (ENV_X - WALL_T, WALL_T),
                                   (ENV_X - WALL_T, ENV_Y + 0.5 - WALL_T),
                                   (PARTITION_X + 0.05, ENV_Y + 0.5 - WALL_T)])]
    S["replace_element_type6"] = lambda tb, m: tb.replace_door(
        m.door["guid"], favorite="Double Entrance Door", width=2.1, height=2.1)
    S["replace_element_type9"] = lambda tb, m: tb.replace_window(
        m.window["guid"], favorite="Sliding Window", width=1.5, height=1.5, sill=0.9)
    S["replace_element_type8"] = lambda tb, m: tb.modify_wall(
        m.partition["guid"], composite_name="Double 50 Block Cavity Plastered")
    S["replace_element_type7"] = lambda tb, m: tb.modify_slab(
        m.slab["guid"], composite_name="Concrete Floor Insulated with Parquet")
    S["switch_active_story1"] = lambda tb, m: tb.set_active_story("First Floor")
    return S


NO_API = {                        # atoms with no API route — GUI demonstrations only
    "load_library_element_type1": "Tapir cannot load a library part",
    "load_library_element_type2": "Tapir cannot load a library part",
}
READ_ONLY = ("inspect_project", "check_clash", "query_")   # the read-only capabilities


# ---------------------------------------------------------------- grading
def _spec(cid):
    return json.loads((AC / cid / "task.json").read_text(encoding="utf-8"))


def _baseline(cid):
    return json.loads((AC / cid / "env" / "start" / "baseline.json").read_text(encoding="utf-8"))


def _grade(cid, final, composites, answer=None, composites_final=None):
    from verifier.grade import grade, normalize_composites
    base = _baseline(cid)
    return grade(_spec(cid)["expected_result"], base.get("snapshot") or {}, final,
                 normalize_composites(composites), answer=answer,
                 composites_final=composites_final)


ANSWER_KEYS = ("answer_values", "answer_items", "answer_pairs")


def _answer_graded(cid) -> bool:
    """Does this case's expected_result carry an automatically-graded ANSWER key?
    Such a read atom is failable like any other: an untouched start with no answer
    written scores zero on every answer checkpoint."""
    er = _spec(cid).get("expected_result") or {}
    return any(er.get(k) for k in ANSWER_KEYS)


def start_state(only=None) -> int:
    """Every case must FAIL on its untouched start — a case the start already satisfies
    grades nothing. Read atoms whose answer is graded by hand are exempt: their automated
    half IS a preservation check. One whose answer key is machine-graded is NOT exempt —
    it is graded here with an EMPTY answer, which is what "did nothing" means for it."""
    bad, no_env = [], []
    for d in sorted(p for p in AC.iterdir() if p.is_dir() and not p.name.startswith("_")):
        cid = d.name
        if only and cid not in only:
            continue
        if not (AC / cid / "env" / "start" / "baseline.json").exists():
            # An UNAUTHORED (or half-deleted) case: report it and keep going —
            # one incomplete dir must not stop the sweep over every other case.
            print(f"  {cid:26s} --    NO ENV (no baseline.json)")
            no_env.append(cid)
            continue
        base = _baseline(cid)
        graded_answer = _answer_graded(cid)
        r = _grade(cid, base["snapshot"], [], answer="" if graded_answer else None,
                   composites_final=base.get("composites"))
        read_only = any(cid.startswith(p) for p in READ_ONLY) and not graded_answer
        mark = "read" if read_only else ("PASSES ALREADY" if r["passed"] else "fails")
        print(f"  {cid:26s} {r['checkpoints_passed']}/{r['checkpoints_total']}  {mark}")
        if r["passed"] and not read_only:
            bad.append(cid)
    print(f"\n{len(bad)} case(s) satisfied by their own start state: {bad or 'none'}")
    if no_env:
        print(f"{len(no_env)} case(s) with no env authored: {no_env}")
    return 1 if bad else 0


def solutions(only=None) -> int:
    from bench_runner.backend import Toolbox
    from bench_runner.backend.snapshot import model_snapshot
    from bench_runner.backend.archicad.inventory import list_composites

    tb = Toolbox.connect("archicad")
    sols = _solutions()
    work = Path(ROOT / "bench_cases" / "atomic_tasks" / ".validate")
    work.mkdir(exist_ok=True)
    failed = []
    for cid in sorted(sols):
        if only and cid not in only:
            continue
        pln = work / f"{cid}.pln"
        shutil.copy2(AC / cid / "env" / "start" / "archicad.pln", pln)
        tb.tap("OpenProject", {"projectFilePath": str(pln)})
        time.sleep(12.0)
        before = {c["name"] for c in list_composites(tb.client)}
        try:
            sols[cid](tb, Model(tb))
        except SystemExit as e:
            print(f"  {cid:26s} SOLUTION ERROR {e}")
            failed.append(cid)
            continue
        after = list_composites(tb.client)
        made = [c for c in after if c["name"] not in before]
        r = _grade(cid, model_snapshot(tb), made, composites_final=after)
        bad = [c["id"] for c in r["checkpoints"] if c["score"] == 0.0]
        print(f"  {cid:26s} {'PASS' if r['passed'] else 'FAIL'} "
              f"{r['checkpoints_passed']}/{r['checkpoints_total']}"
              f"{'  ' + ','.join(bad) if bad else ''}")
        if not r["passed"]:
            failed.append(cid)
    print(f"\n{len(failed)} case(s) whose reference solution does not pass: {failed or 'none'}")
    print(f"(working copies under {work.relative_to(ROOT)} — throwaway, gitignored)")
    for cid in NO_API:
        print(f"  {cid:26s} SKIPPED — {NO_API[cid]} (GUI-route atom)")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="case ids to check")
    ap.add_argument("--start-only", action="store_true",
                    help="only check that each start state fails (no live application needed)")
    a = ap.parse_args()
    rc = start_state(a.only)
    if a.start_only:
        return rc
    print()
    return solutions(a.only) | rc


if __name__ == "__main__":
    sys.exit(main())
