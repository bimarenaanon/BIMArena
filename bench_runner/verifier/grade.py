"""Grading core: (expected_result, baseline, final snapshot) -> checkpoint report.

Snapshots arrive in the model_snapshot schema (element geometry in METRES);
`normalize()` converts every coordinate/length to MILLIMETRES once, so the
checkers and the expected_result share one unit.

Checkpoint model: every check is one binary point; the case PASSES only when
ALL checkpoints pass; score = passed / total is reported alongside.

Checkpoints are split into two disjoint classes, one per metric: C (goal —
what the task asks to add or change) feeds PCS, P (preservation — what must
survive untouched) feeds CFR, and a case succeeds only when both are fully
satisfied. Goal checkpoints the START state already satisfies are restated
preservation duties rather than goals, so callers pass them as `trivial=`
and they are graded under P — see the C/P section below `_UNIT_RE`.

Alignment: when the task is to CREATE walls (expected walls with coordinates
and no pre-existing walls anchoring the drawing), the created geometry is
translated as a whole so its wall-set bounding box matches the expected one —
a GUI run drawn elsewhere on the canvas is judged on its RELATIVE layout, not
on the arbitrary global origin.
"""
from __future__ import annotations

import copy
import math
import re

from .checkers import ALL_CHECKS

DEFAULTS = {
    # deliberately buffered — "roughly right" passes; precise cases tighten
    # these per-case in their expected_result
    "tolerance_mm": 150,          # generic (levels, regions)
    "wall_tolerance_mm": 300,     # wall segment matching
    "opening_pos_tolerance_mm": 500,
    "size_tolerance_mm": 30,
    "iou_min": 0.80,              # slab outline match
    "room_area_ratio": 0.25,      # zone area within ±25% of the GT ("roughly right")
}

_BUCKETS = ("walls", "doors", "windows", "slabs", "rooms", "stairs", "objects")


def _mm(v):
    return None if v is None else round(v * 1000.0, 1)


def _pt(c):
    """{x,y} dict or [x,y] in metres -> [x,y] mm."""
    if c is None:
        return None
    if isinstance(c, dict):
        return [_mm(c.get("x", 0)), _mm(c.get("y", 0))]
    return [_mm(c[0]), _mm(c[1])]


def _remitre(walls: list) -> None:
    """Put the corners back after the canonical-line shift below has moved each wall SIDEWAYS.

    A sideways offset cannot move an endpoint ALONG its wall, so two walls that met at a shared
    location-curve corner do not meet any more once each has been slid onto its own canonical
    line: one stops short of the new corner point, the other runs past it, both by up to half a
    thickness (exactly half at a right angle, more at a shallower one). That is an artifact of
    offsetting segment by segment — a real mitred corner reaches its corner point exactly — and
    it lands squarely in `checkers.walls.N.geom`, whose coverage rule is relative: the loss is a
    FIXED length, so a long run absorbs it (8875 mm wall, 145 mm lost -> 98%) while a short one
    reads a third short (425 mm wall, same 145 mm -> 66%) and fails. Measured on
    B_element_creation3, whose L-shaped notch has two such legs.

    So snap both walls of every two-wall corner back onto where their canonical lines actually
    cross. Only a corner shared by EXACTLY TWO walls is mitred: a free end has nothing to meet,
    and a 3+-wall junction has no single crossing point. A T-junction is untouched by
    construction — the partition's endpoint lands in the MIDDLE of the other wall's curve, so
    the two never shared a corner in the first place.
    """
    corners = {}
    for w in walls:
        if not (w.get("beg") and w.get("end")):
            continue
        for end in ("beg", "end"):
            raw = w.get("loc_" + end) or w[end]          # the pre-shift location curve
            corners.setdefault((round(raw[0], 3), round(raw[1], 3)), []).append((w, end))
    # how far a mitre may legitimately move an endpoint: half a thickness at a right angle,
    # more as the corner sharpens. Two thicknesses covers everything down to ~30 degrees and
    # keeps a degenerate near-parallel solution from teleporting a wall across the model.
    def _thick(w):
        o = w.get("orient") or {}
        return w.get("width") or ((o.get("left_mm") or 0) + (o.get("right_mm") or 0)) or 0
    cap = 2.0 * max([_thick(w) for w in walls] or [0])
    if cap <= 0:
        return
    for pair in corners.values():
        if len(pair) != 2:
            continue
        (wa, ea), (wb, eb) = pair
        if wa is wb:
            continue
        pa, ua = wa["beg"], (wa["end"][0] - wa["beg"][0], wa["end"][1] - wa["beg"][1])
        pb, ub = wb["beg"], (wb["end"][0] - wb["beg"][0], wb["end"][1] - wb["beg"][1])
        den = ua[0] * ub[1] - ua[1] * ub[0]
        la = math.hypot(*ua) or 1.0
        lb = math.hypot(*ub) or 1.0
        if abs(den) < 1e-6 * la * lb:                    # collinear / parallel: no corner
            continue
        t = ((pb[0] - pa[0]) * ub[1] - (pb[1] - pa[1]) * ub[0]) / den
        x, y = pa[0] + ua[0] * t, pa[1] + ua[1] * t
        if (math.dist((x, y), wa[ea]) > cap) or (math.dist((x, y), wb[eb]) > cap):
            continue                                     # not a local correction — leave it
        # never let the mitre invert a segment or collapse it onto its other end
        other = {"beg": "end", "end": "beg"}
        if (math.dist((x, y), wa[other[ea]]) < 1e-6
                or math.dist((x, y), wb[other[eb]]) < 1e-6):
            continue
        wa[ea], wb[eb] = [x, y], [x, y]


def normalize(snapshot: dict) -> dict:
    """Deep-copy a model snapshot converting geometry m -> mm."""
    s = copy.deepcopy(snapshot or {})
    for w in s.get("walls") or []:
        w["beg"], w["end"] = _pt(w.pop("begCoordinate", None)), _pt(w.pop("endCoordinate", None))
        for k in ("height", "width"):
            if w.get(k) is not None:
                w[k] = _mm(w[k])
    # ONE CANONICAL LINE PER WALL, in the convention the INSTRUCTION itself uses (2026-08-12):
    #
    #   ENVELOPE wall  ->  its OUTER FACE      (a plan dimensions the outside of the building)
    #   INTERIOR wall  ->  its BODY CENTRELINE (partition positions are given as centrelines —
    #                      2026-08-06: B_element_creation4's own GT graded 65-71 mm off its
    #                      expected_result when partitions were face-shifted)
    #
    # Both are derived from the MEASURED body extents (`orient.left_mm/right_mm`), never from
    # which reference line the authoring route happened to use — that is the whole point.
    # Before this the two conventions were route-dependent and only half-normalized: ArchiCAD
    # walls were never touched at all (no `exterior` key, so neither old pass could reach
    # them), and on Revit only envelope walls were, leaving an interior wall graded on
    # whatever its location curve meant. The same correct partition therefore read up to a
    # full thickness apart between the API, GUI and hand-built routes.
    #
    # Envelope vs interior is decided GEOMETRICALLY (probe each side against the floor's
    # enclosed region), not from `orient.exterior`: that vector points at whichever side the
    # type's layer 0 sits on, which is meaningless for a partition and mirror-sensitive on a
    # hand-drawn wall. A wall on no enclosure (single walls, open layouts) canonicalizes to
    # its centreline — with nothing enclosed there is no "outside" to dimension from.
    import math as _math
    _by_floor = {}
    for w in s.get("walls") or []:
        _by_floor.setdefault(w.get("floor"), []).append(w)
    for _group in _by_floor.values():
        from .geometry import walls_footprint as _wfp
        _fp = _wfp(_group)                # from the LOCATION curves — nothing is shifted yet
        _poly = None
        if _fp and len(_fp) >= 4:
            from shapely.geometry import Point, Polygon
            _poly = Polygon(_fp)
        for w in _group:
            o = w.get("orient") or {}
            left, right = o.get("left_mm"), o.get("right_mm")
            if left is None or right is None or not (w.get("beg") and w.get("end")):
                continue
            dx, dy = w["end"][0] - w["beg"][0], w["end"][1] - w["beg"][1]
            dl = _math.hypot(dx, dy)
            if dl < 1e-9:
                continue
            lx, ly = -dy / dl, dx / dl                    # left of begin->end, in plan
            mid = ((w["beg"][0] + w["end"][0]) / 2, (w["beg"][1] + w["end"][1]) / 2)
            shift = None
            if _poly is not None:
                l_out = not _poly.contains(Point(mid[0] + lx * (left + 100),
                                                 mid[1] + ly * (left + 100)))
                r_out = not _poly.contains(Point(mid[0] - lx * (right + 100),
                                                 mid[1] - ly * (right + 100)))
                if l_out != r_out:                        # ENVELOPE -> the OUTER face
                    shift = (left, lx, ly) if l_out else (right, -lx, -ly)
            if shift is None:                             # INTERIOR -> the body centreline
                d = (left - right) / 2.0                  # 0 when the line is already central
                shift = (abs(d), lx, ly) if d >= 0 else (abs(d), -lx, -ly)
            off, ox, oy = shift
            if off < 1e-9:
                continue
            # keep the raw location curve — the orient extents are measured about IT, so
            # body-geometry consumers (walls_outer_footprint) must not re-apply them around
            # the canonicalized segment
            w["loc_beg"], w["loc_end"] = list(w["beg"]), list(w["end"])
            w["beg"] = [w["beg"][0] + ox * off, w["beg"][1] + oy * off]
            w["end"] = [w["end"][0] + ox * off, w["end"][1] + oy * off]
        _remitre(_group)
    for kind in ("doors", "windows"):
        for o in s.get(kind) or []:
            o["center"] = _pt(o.get("center"))
            for k in ("width", "height", "sill", "center_offset"):
                if o.get(k) is not None:
                    o[k] = _mm(o[k])
            # Revit reports the swing as world-space direction VECTORS
            # (FacingOrientation / HandOrientation, both already corrected for
            # flips); ArchiCAD reports Tapir's oSide/reflected flags in
            # `swing_raw`. Fold the Revit form into the same field so the swing
            # and hinge checkpoints read ONE place — without this the vectors
            # arrived in the snapshot and every swing check scored "unchecked".
            if "swing_raw" not in o and (o.get("facing") or o.get("hand")):
                sw = {}
                if o.get("facing"):
                    sw["facing"] = o["facing"]
                if o.get("hand"):
                    sw["hand"] = o["hand"]
                o["swing_raw"] = sw
            # Revit: instance params carry no dims (they live on the TYPE) —
            # fall back to the "2150 x 1350mm"-style dims in the type name
            if o.get("width") is None or o.get("height") is None:
                m = re.search(r"(\d{3,4})\s*x\s*(\d{3,4})\s*mm", o.get("type") or "", re.I)
                if m:
                    if o.get("width") is None:
                        o["width"] = float(m.group(1))
                    if o.get("height") is None:
                        o["height"] = float(m.group(2))
    for sl in s.get("slabs") or []:
        sl["polygonOutline"] = [_pt(p) for p in (sl.get("polygonOutline") or [])]
        sl["holes"] = [[_pt(p) for p in h] for h in (sl.get("holes") or [])]
        for k in ("level", "thickness", "offset_from_top"):
            if sl.get(k) is not None:
                sl[k] = _mm(sl[k])
    for r in s.get("rooms") or []:
        r["polygonOutline"] = [_pt(p) for p in (r.get("polygonOutline") or [])]
    for st in s.get("stairs") or []:
        if st.get("footprint"):
            st["footprint"] = [_mm(v) for v in st["footprint"]]
        for k in ("height", "flight_width", "run", "riser_height", "going"):
            if st.get(k) is not None:
                st[k] = _mm(st[k])   # `risers` is a COUNT — left alone
    for o in s.get("objects") or []:
        if o.get("center"):
            o["center"] = _pt(o["center"])
    return s


def normalize_composites(composites) -> list | None:
    """list_composites output (m) -> [{name, skins:[{material, thickness_mm}]}]."""
    if composites is None:
        return None
    out = []
    for c in composites:
        out.append({
            "name": c.get("name"),
            "skins": [{"material": sk.get("material"),
                       "thickness_mm": _mm(sk.get("thickness_m") or 0),
                       # Core/Finish/Other — lets the slab reference-plane check
                       # derive where THIS composite's Core Top actually sits
                       "type": sk.get("type")}
                      for sk in (c.get("skins_outer_to_inner") or [])],
        })
    return out


# ---------------------------------------------------------------- alignment

def _alignment_shift(expected: dict, created_walls: list, existing_walls: list):
    """[dx, dy] to move the CREATED geometry onto the expected coordinates.

    Only when the run itself drew the walls: expected wall entries carry
    coordinates and nothing pre-existing anchors the origin. Matched on the
    wall-set bounding boxes' SW corners; sub-50 mm shifts snap to zero.
    A SINGLE expected wall aligns too — the shift absorbs only translation,
    so orientation and length stay graded by coverage (a GUI run cannot know
    where the model origin sits on an empty canvas)."""
    exp_walls = [e for e in (expected.get("walls") or [])
                 if e.get("beg") and not e.get("existing")]
    if not exp_walls or existing_walls or not created_walls:
        return [0.0, 0.0]
    exp_pts = [p for e in exp_walls for p in (e["beg"], e["end"])]
    got_pts = [p for w in created_walls for p in (w.get("beg"), w.get("end")) if p]
    if not got_pts:
        return [0.0, 0.0]
    dx = min(p[0] for p in exp_pts) - min(p[0] for p in got_pts)
    dy = min(p[1] for p in exp_pts) - min(p[1] for p in got_pts)
    if abs(dx) < 50 and abs(dy) < 50:
        return [0.0, 0.0]
    return [dx, dy]


def _shift_elements(created: dict, shift):
    dx, dy = shift
    if not dx and not dy:
        return

    def mv(p):
        return [p[0] + dx, p[1] + dy] if p else p

    for w in created.get("walls") or []:
        w["beg"], w["end"] = mv(w.get("beg")), mv(w.get("end"))
        if w.get("loc_beg"):
            w["loc_beg"], w["loc_end"] = mv(w["loc_beg"]), mv(w["loc_end"])
    for kind in ("doors", "windows", "objects"):
        for o in created.get(kind) or []:
            o["center"] = mv(o.get("center"))
    for sl in created.get("slabs") or []:
        sl["polygonOutline"] = [mv(p) for p in (sl.get("polygonOutline") or [])]
        sl["holes"] = [[mv(p) for p in h] for h in (sl.get("holes") or [])]
    for r in created.get("rooms") or []:
        r["polygonOutline"] = [mv(p) for p in (r.get("polygonOutline") or [])]
    for st in created.get("stairs") or []:
        if st.get("footprint"):
            f = st["footprint"]
            st["footprint"] = [f[0] + dx, f[1] + dy, f[2] + dx, f[3] + dy]


def build_context(expected: dict, baseline: dict, final: dict,
                  composites_created=None, anchor: bool = True,
                  answer: str | None = None, composites_final=None) -> dict:
    base_mm, final_mm = normalize(baseline), normalize(final)
    # Anchor the WHOLE world on the pre-existing building: expected coordinates
    # use the drawing frame (SW exterior corner = origin), and env projects are
    # authored with the building there — but a hand-drawn env can sit anywhere.
    # Translate BOTH snapshots so the baseline walls' closed-envelope SW corner
    # lands on (0,0): a pure change of coordinates, so every internal comparison
    # (preserve, clash, footprints) is unaffected. Origin-aligned envs yield a
    # sub-50mm shift that snaps to zero (no behavior change), and the anchor is
    # the polygonized envelope, NOT the raw min — a seeded defect wall placed
    # outside the loop (E cases) must not hijack the origin.
    # `anchor=False` — the ARCHICAD convention: its ERs are written in RAW model
    # coordinates (envs are API-authored wherever they sit), so the drawing-frame
    # translation belongs to Revit's hand-drawn envs ONLY. Anchoring an off-origin
    # archicad env shifted every geometry checkpoint by metres (found 2026-08-03:
    # C1 walls all "coverage 0%" while the model was correct).
    from . import geometry as _g
    _fp = _g.walls_footprint(base_mm.get("walls") or []) if anchor else None
    if _fp and len(_fp) >= 4:
        ax = min(x for x, _ in _fp)
        ay = min(y for _, y in _fp)
        if abs(ax) >= 50 or abs(ay) >= 50:
            _shift_elements(base_mm, [-ax, -ay])
            _shift_elements(final_mm, [-ax, -ay])
    created, existing = {}, {}
    for b in _BUCKETS:
        base_guids = {el.get("guid") for el in (base_mm.get(b) or [])}
        created[b] = [el for el in (final_mm.get(b) or []) if el.get("guid") not in base_guids]
        existing[b] = [el for el in (final_mm.get(b) or []) if el.get("guid") in base_guids]
    shift = _alignment_shift(expected, created["walls"], existing["walls"])
    # created lists share element dicts with final_mm, so shifting them moves
    # the same objects the checkers see through ctx["final"] — consistent view
    _shift_elements(created, shift)
    return {
        "exp": expected,
        "final": final_mm,
        "base": base_mm,
        # A READ atom's real output is the agent's final natural-language text,
        # not the model — the answer checkers read this instead of a snapshot.
        "answer": answer,
        "created": created,
        "existing": existing,
        "shift": shift,
        "composites_created": composites_created,
        # The final project's WHOLE composite inventory (names are what matters) —
        # attribute-deletion checkpoints need it; None = source served no list.
        "composites_final": composites_final,
        "tol": expected.get("tolerance_mm", DEFAULTS["tolerance_mm"]),
        "wall_tol": expected.get("wall_tolerance_mm", DEFAULTS["wall_tolerance_mm"]),
        "pos_tol": expected.get("opening_pos_tolerance_mm", DEFAULTS["opening_pos_tolerance_mm"]),
        "size_tol": expected.get("size_tolerance_mm", DEFAULTS["size_tolerance_mm"]),
        "iou_min": expected.get("iou_min", DEFAULTS["iou_min"]),
        "room_area_ratio": expected.get("room_area_ratio", DEFAULTS["room_area_ratio"]),
    }


# checkpoint id -> reward unit: "<bucket>.<i>" (one element / one storey) or
# "composites.<i>.skin<k>" (one layer). Constraint checkpoints (exact counts,
# no_extra, preserve, stories.count, active_story) match neither and stay out
# of the reward — it measures how much of the asked-for content was built.
_UNIT_RE = re.compile(
    r"^(stories|composites_absent|composites|walls|doors|windows|slabs|rooms|stairs)"
    r"\.(\d+)(?:\.(skin\d+))?\.")


# --- the C / P split -------------------------------------------------------
# Every checkpoint belongs to exactly one of two classes, and the two metrics
# read one class each:
#   C (goal)         what the instruction asks the agent to ADD or CHANGE  -> PCS
#   P (preservation) what must survive the run UNCHANGED                   -> CFR
# A case SUCCEEDS only when C and P are both fully satisfied, so SR is the
# conjunction and no checkpoint is counted twice.
#
# The split cannot be read off the checkpoint id alone. A key restates the
# elements a task must leave alone (an edit task lists every wall, including
# the ones already correct), and those restated checkpoints are satisfied
# before the agent acts: they are preservation duties wearing a goal's id.
# `trivial` names them — the ids a NO-OP run (start state graded against
# itself) already passes — and they are moved from C into P. Without the move
# they inflate PCS by a floor of ~56-58% that carries no information about the
# run, while leaving damage to them visible only through SR.
def _klass(cp_id: str) -> str:
    return "P" if cp_id.startswith("preserve.") else "C"


def trivial_from_report(report: dict | None) -> set[str]:
    """The C-class checkpoint ids a NO-OP run already satisfies, read off a
    report produced by grading a start state against ITSELF
    (`grade(expected, baseline, baseline, ...)`). Pass the result to `grade`
    as `trivial=` so those checkpoints are graded as preservation duties."""
    return {c["id"] for c in (report or {}).get("checkpoints") or []
            if c.get("score") is not None and c["score"] >= 1.0
            and _klass(c["id"]) == "C"}


def _reward_units(expected: dict, checkpoints: list) -> list[dict]:
    """One entry per expected unit: {unit, passed, checkpoints:[ids]}.
    A unit passes when it has at least one scored checkpoint and ALL of its
    scored checkpoints pass (a composite that was never created emits no skin
    checkpoints — its layers count as failed units)."""
    keys: list[str] = []
    for b in ("stories", "walls", "doors", "windows", "slabs", "rooms", "stairs"):
        keys += [f"{b}.{i}" for i in range(len(expected.get(b) or []))]
    for i, c in enumerate(expected.get("composites") or []):
        skins = c.get("skins") or []
        keys += ([f"composites.{i}.skin{k}" for k in range(len(skins))]
                 if skins else [f"composites.{i}"])
    keys += [f"composites_absent.{i}"
             for i in range(len(expected.get("composites_absent") or []))]
    by = {k: [] for k in keys}
    for c in checkpoints:
        m = _UNIT_RE.match(c["id"])
        if not m:
            continue
        b, i, sk = m.groups()
        key = f"{b}.{i}.{sk}" if sk else f"{b}.{i}"
        if key in by:                       # composite-level found/layers cps fall out
            by[key].append(c)
    units = []
    for k in keys:
        scored = [c for c in by[k] if c["score"] is not None]
        units.append({"unit": k,
                      "passed": bool(scored) and all(c["score"] >= 1.0 for c in scored),
                      "checkpoints": [c["id"] for c in by[k]]})
    return units


def grade(expected: dict, baseline: dict, final: dict, composites_created=None,
          anchor: bool = True, answer: str | None = None,
          composites_final=None, trivial=None) -> dict:
    """Run every checker. PASS = every checkpoint passes; score = passed/total
    checkpoints; reward = passed/total UNITS (elements / composite layers) —
    partial credit for what was built even when the case fails.

    `trivial` — ids of the C-class checkpoints a NO-OP run already satisfies
    (see `trivial_from_report`). They are re-classed into P, which is what
    makes `pcs` a score over the changes the task actually asks for and `cfr`
    a check on everything that had to survive. Omitting it leaves every
    restated checkpoint in C, i.e. the un-normalised behaviour.

    `any_of`: a list of ALTERNATIVE partial expected_results (e.g. two equally
    valid door-swing resolutions). Each alternative is merged over the base
    expected_result (its keys REPLACE the base's), graded fully, and the best
    one (passed first, then score) is returned with an `alternative` index —
    a model matching a MIX of two alternatives satisfies neither and fails."""
    alts = expected.get("any_of")
    if alts:
        base_er = {k: v for k, v in expected.items() if k != "any_of"}
        reports = []
        for i, alt in enumerate(alts):
            rep = grade({**base_er, **alt}, baseline, final, composites_created,
                        anchor=anchor, answer=answer, composites_final=composites_final,
                        trivial=trivial)
            rep["alternative"] = i
            reports.append(rep)
        return max(reports, key=lambda r: (bool(r["passed"]), r["score"] or 0,
                                           r["reward"] or 0))
    ctx = build_context(expected, baseline, final, composites_created, anchor=anchor,
                        answer=answer, composites_final=composites_final)
    checkpoints = []
    for check in ALL_CHECKS:
        checkpoints.extend(check(ctx))
    # Class every checkpoint before scoring: a C-class id listed in `trivial`
    # is a restated preservation duty, so it is graded under P.
    triv = set(trivial or ())
    for c in checkpoints:
        c["trivial"] = bool(c["id"] in triv and _klass(c["id"]) == "C")
        c["klass"] = "P" if (c["trivial"] or _klass(c["id"]) == "P") else "C"
    scored = [c for c in checkpoints if c["score"] is not None]
    unchecked = [c for c in checkpoints if c["score"] is None]
    passed_n = sum(1 for c in scored if c["score"] >= 1.0)
    goal = [c for c in scored if c["klass"] == "C"]
    keep = [c for c in scored if c["klass"] == "P"]
    goal_ok = sum(1 for c in goal if c["score"] >= 1.0)
    keep_ok = sum(1 for c in keep if c["score"] >= 1.0)
    units = _reward_units(expected, checkpoints)
    units_ok = sum(1 for u in units if u["passed"])
    return {
        "score": round(passed_n / len(scored), 4) if scored else None,
        "passed": bool(scored) and passed_n == len(scored),
        # PCS — the share of the asked-for changes that were made. None when a
        # case has no C checkpoint left (the start state already satisfies the
        # whole key); such a case is excluded from the PCS average.
        "pcs": round(goal_ok / len(goal), 4) if goal else None,
        "pcs_passed": goal_ok,
        "pcs_total": len(goal),
        # CFR — binary: everything that had to survive, survived. An empty P
        # (a build from an empty project, nothing to damage) scores 1.
        "cfr": 1.0 if keep_ok == len(keep) else 0.0,
        "cfr_passed": keep_ok,
        "cfr_total": len(keep),
        # of which were reclassified out of C
        "trivial_total": sum(1 for c in scored if c["trivial"]),
        "reward": round(units_ok / len(units), 4) if units else None,
        "units_passed": units_ok,
        "units_total": len(units),
        "checkpoints_passed": passed_n,
        "checkpoints_total": len(scored),
        "checkpoints_unchecked": len(unchecked),
        "alignment_shift_mm": ctx["shift"],
        "units": units,
        "checkpoints": checkpoints,
    }
