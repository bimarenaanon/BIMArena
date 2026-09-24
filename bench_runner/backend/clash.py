"""Deterministic clash checks on the live Archicad model.

Two engines:
  - Tapir GetCollisions (via Toolbox.collisions) — Archicad's own 3D solid clash, used for
    wall-vs-wall and stair-vs-(wall/slab) body collisions. Exact, on the real BIM bodies.
  - Shapely (2D) — semantic checks the 3D body test can't express: duplicate (coincident)
    walls; duplicate / overlapping openings on a wall; an opening blocked by another wall
    crossing its span; a missing host wall. Openings can't use GetCollisions (their body
    lives inside the host wall, so it always "collides").

Opening extent comes from the 2D bounding box (the snapshot has no width). A door's box is
inflated along the wall by its swing arc, so opening spans over-estimate slightly — we
prefer over- to under-detection. `check` returns a flat list of issue dicts; empty = clean.
"""
import numpy as np
from shapely.geometry import LineString, Point

from .archicad.toolbox import Toolbox


def _seg(w):
    b, e = w.get("begCoordinate"), w.get("endCoordinate")
    return LineString([(b["x"], b["y"]), (e["x"], e["y"])]) if b and e else None


def _near_duplicate(s1, s2, band=0.3, min_overlap=0.3):
    """True if two wall centerlines are near-parallel, close, and overlap lengthwise —
    i.e. redundant near-coincident walls, even if their solid bodies don't actually touch."""
    (ax, ay), (bx, by) = s1.coords[0], s1.coords[1]
    (cx, cy), (dx, dy) = s2.coords[0], s2.coords[1]
    d1 = np.array([bx - ax, by - ay]); n1 = np.linalg.norm(d1)
    d2 = np.array([dx - cx, dy - cy]); n2 = np.linalg.norm(d2)
    if n1 == 0 or n2 == 0:
        return False
    u1 = d1 / n1
    if abs(u1[0] * d2[1] / n2 - u1[1] * d2[0] / n2) > 0.15:   # not parallel (~8.6 deg)
        return False
    perp = lambda px, py: abs((px - ax) * u1[1] - (py - ay) * u1[0])
    if perp(cx, cy) > band or perp(dx, dy) > band:            # too far apart perpendicularly
        return False
    along = lambda px, py: (px - ax) * u1[0] + (py - ay) * u1[1]
    t2 = sorted([along(cx, cy), along(dx, dy)])
    return min(n1, t2[1]) - max(0.0, t2[0]) > min_overlap     # lengthwise overlap


def _span(host, box):
    """The opening's [start, end] parameters along the host centerline, from its bbox."""
    corners = [(box["xMin"], box["yMin"]), (box["xMax"], box["yMin"]),
               (box["xMax"], box["yMax"]), (box["xMin"], box["yMax"])]
    ts = sorted(host.project(Point(c)) for c in corners)
    return ts[0], ts[-1]


def _check_2d(snapshot, active_floor=None):
    """Snapshot-only 2D clash for the Revit backend (no live body test available): duplicate /
    isolated walls, plus openings off their host wall or overlapping another opening on the same
    wall. Uses only the snapshot (wall begin/end; openings carry host + center_offset + width)."""
    issues = []
    on_floor = lambda el: active_floor is None or el.get("floor") == active_floor
    segs = [{"guid": w.get("guid"), "id": w.get("id"), "seg": _seg(w)}
            for w in (snapshot.get("walls") or []) if on_floor(w)]
    segs = [w for w in segs if w["seg"] is not None]

    # 1. duplicate walls — near-parallel + close + lengthwise-overlapping centrelines.
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if _near_duplicate(segs[i]["seg"], segs[j]["seg"]):
                issues.append({"kind": "duplicate_wall", "a": segs[i]["id"], "b": segs[j]["id"],
                               "a_guid": segs[i]["guid"], "b_guid": segs[j]["guid"]})
    # 2. isolated wall — touches no other wall on this storey. Only meaningful with >= 2
    # walls: `all()` over the empty "other walls" generator is vacuously True, so a storey
    # with exactly ONE wall (a legitimate single-wall case) would report isolated forever
    # and the run could only end in "no actionable fix".
    if len(segs) > 1:
        for i, w in enumerate(segs):
            if all(w["seg"].distance(o["seg"]) > 0.1 for j, o in enumerate(segs) if j != i):
                issues.append({"kind": "isolated_wall", "wall": w["id"], "guid": w["guid"]})

    # 3. openings: off their host wall, past the host's end, overlapping another opening
    # on the same wall, or overlapping ANOTHER wall's body (incl. a corner junction).
    wall_ids = {w["id"] for w in segs}
    seg_by_id = {w["id"]: w["seg"] for w in segs}
    wall_w = {w.get("id"): (w.get("width") or 0.2)
              for w in (snapshot.get("walls") or []) if on_floor(w)}
    by_host = {}
    for bucket in ("doors", "windows"):
        for o in (snapshot.get(bucket) or []):
            if not on_floor(o):
                continue
            if o.get("host") not in wall_ids:
                issues.append({"kind": "opening_off_wall", "opening": o.get("id"),
                               "opening_guid": o.get("guid"), "host": o.get("host")})
                continue
            by_host.setdefault(o["host"], []).append(o)
    for host, ops in by_host.items():
        hseg = seg_by_id[host]
        ops = sorted((o for o in ops if o.get("center_offset") is not None and o.get("width")),
                     key=lambda o: o["center_offset"])
        for k in range(1, len(ops)):
            prev, cur = ops[k - 1], ops[k]
            if (cur["center_offset"] - cur["width"] / 2) < (prev["center_offset"] + prev["width"] / 2) - 0.02:
                issues.append({"kind": "opening_clash", "a": prev.get("id"), "b": cur.get("id"),
                               "a_guid": prev.get("guid"), "b_guid": cur.get("guid")})
        for o in ops:
            t0 = o["center_offset"] - o["width"] / 2
            t1 = o["center_offset"] + o["width"] / 2
            if t0 < -0.01 or t1 > hseg.length + 0.01:
                issues.append({"kind": "opening_off_wall_end", "opening": o.get("id"),
                               "opening_guid": o.get("guid"), "host": host,
                               "out_m": round(max(-t0, t1 - hseg.length), 3)})
            for w in segs:
                if w["id"] == host:
                    continue
                body = w["seg"].buffer(wall_w.get(w["id"], 0.2) / 2, cap_style=2)
                inter = hseg.intersection(body)
                hit = False
                for seg_b in (g for g in getattr(inter, "geoms", [inter])
                              if g.geom_type == "LineString" and g.length > 0):
                    b0, b1 = sorted(hseg.project(Point(c))
                                    for c in (seg_b.coords[0], seg_b.coords[-1]))
                    if min(t1, b1) - max(t0, b0) > 0.02:
                        hit = True
                        break
                if hit:
                    issues.append({"kind": "opening_blocked", "opening": o.get("id"),
                                   "opening_guid": o.get("guid"), "by_wall": w["id"]})
                    break
    return issues


def check(snapshot, tb=None, active_floor=None):
    """Run all clash checks. `snapshot` supplies wall 2D geometry, `tb` runs the live tests.

    `active_floor` (storey index) scopes EVERY check to that storey: the same footprint
    repeated on another floor must NOT register as a duplicate/collision. None = all floors.
    """
    tb = tb or Toolbox.connect()
    # Revit backend has no Tapir GetCollisions / 2D-bbox reads — run the SNAPSHOT-ONLY 2D checks
    # (duplicate / isolated walls, openings off their host wall or overlapping). Body-clash checks
    # are skipped (note: stair-vs-wall 3D clash is not detected on Revit in v1).
    if hasattr(tb, "remote_snapshot"):
        return _check_2d(snapshot, active_floor)
    issues = []
    pairs = tb.all_elements()                        # ONE inventory, reused by every check below
    id_by_guid = {e["elementId"]["guid"].upper(): d.get("id") for e, d in pairs}
    floor_by_guid = {e["elementId"]["guid"].upper(): d.get("floorIndex") for e, d in pairs}
    lbl = lambda g: id_by_guid.get(g.upper())        # guid -> readable id
    # scope for NON-wall elements (stairs, openings): both sides on the active storey
    on_active = lambda g: active_floor is None or floor_by_guid.get(g.upper()) == active_floor

    # guids of the walls on the active storey (used to scope every wall/opening check)
    on_floor = lambda el: active_floor is None or el.get("floor") == active_floor
    active_wall_guids = {w["guid"].upper() for w in (snapshot.get("walls") or [])
                         if w.get("guid") and on_floor(w)}
    in_scope = lambda g: active_floor is None or g.upper() in active_wall_guids

    # 1. wall <-> wall and stair <-> wall/slab body collisions (Tapir 3D). Identity = guid
    # (ids like "DOO - 011" repeat); the readable id is carried alongside as a/b.
    wall_pairs = set()
    for c in tb.collisions("Wall", pairs=pairs):
        ga, gb = c["guid_a"], c["guid_b"]
        if not (in_scope(ga) and in_scope(gb)):      # ignore cross-storey body touches
            continue
        wall_pairs.add(frozenset((ga, gb)))
        issues.append({"kind": "wall_clash", "a": lbl(ga), "b": lbl(gb), "a_guid": ga, "b_guid": gb})
    # Stair vs WALL only. Stair-vs-slab is intentionally NOT checked: a stair always rests on
    # its own floor slab (expected) and a stairwell hole in an upper slab can't be verified
    # here anyway — Tapir's GetCollisions ignores slab openings, so it would keep reporting a
    # cleared penetration forever. The stairwell opening is handled at plan time (slabs task).
    # Storey-scoped like every other check: a ground-floor stair rising through the stairwell
    # legitimately touches the storey-above walls — that must not report forever.
    for c in tb.collisions("Stair", ["Wall"], pairs=pairs):
        if not (on_active(c["guid_a"]) and on_active(c["guid_b"])):
            continue
        issues.append({"kind": "stair_clash", "a": lbl(c["guid_a"]), "b": lbl(c["guid_b"]),
                       "a_guid": c["guid_a"], "b_guid": c["guid_b"]})

    # walls from the snapshot (carry guid + id + centerline), restricted to the active storey
    segs = [{"guid": w["guid"], "id": w.get("id"), "seg": _seg(w)}
            for w in (snapshot.get("walls") or []) if on_floor(w)]
    segs = [w for w in segs if w["seg"] is not None]
    by_host = {w["id"]: w["seg"] for w in segs}      # host lookup by wall id (walls' ids are unique)

    # 2. duplicate walls — near-parallel + close + overlapping centerlines (2D). Catches
    # redundant near-coincident walls whose bodies don't quite touch (Tapir's 3D test misses
    # them). Skip pairs Tapir already flagged as a body clash (compared by guid).
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            a, b = segs[i], segs[j]
            if frozenset((a["guid"].upper(), b["guid"].upper())) not in wall_pairs \
                    and _near_duplicate(a["seg"], b["seg"]):
                issues.append({"kind": "duplicate_wall", "a": a["id"], "b": b["id"],
                               "a_guid": a["guid"], "b_guid": b["guid"]})

    # 2b. every wall must touch at least one other wall — no free-floating wall. Only with
    # >= 2 walls (see _check_2d: a single-wall storey must not report isolated forever).
    if len(segs) > 1:
        for i, w in enumerate(segs):
            if all(w["seg"].distance(o["seg"]) > 0.1 for j, o in enumerate(segs) if j != i):
                issues.append({"kind": "isolated_wall", "wall": w["id"], "guid": w["guid"]})

    # 3. opening <-> opening BODY clashes (Tapir 3D): duplicate / overlapping doors and
    # windows, door-vs-window, even across different host walls. Exact (real bodies).
    # Storey-scoped: stacked openings on other floors are not this run's clashes.
    for ta, tb_types in (("Door", None), ("Window", None), ("Door", "Window")):
        for c in tb.collisions(ta, tb_types, pairs=pairs):
            if not (on_active(c["guid_a"]) and on_active(c["guid_b"])):
                continue
            issues.append({"kind": "opening_clash", "a": lbl(c["guid_a"]), "b": lbl(c["guid_b"]),
                           "a_guid": c["guid_a"], "b_guid": c["guid_b"]})

    # 4. opening host checks (2D): host wall missing, opening past the host wall's END,
    # or the opening span overlapping ANOTHER wall's body along the host — including a
    # perpendicular wall joining at a corner (whose centreline only touches the host's
    # endpoint, so a point-intersection test misses it; the body-interval test doesn't).
    # Span comes from Tapir's exact centerOffset/width when available — the 2D bbox is
    # inflated by a door's swing arc and would false-flag doors close to (but inside)
    # a wall end; the bbox stays as the fallback.
    wall_w = {w.get("id"): (w.get("width") or 0.2)
              for w in (snapshot.get("walls") or []) if on_floor(w)}
    op = []
    for e, d in pairs:
        if d.get("type") in ("Door", "Window") and (active_floor is None
                                                    or d.get("floorIndex") == active_floor):
            det = d.get("details") or {}
            owner = (det.get("ownerElementId") or {}).get("guid")
            op.append({"id": d.get("id"), "guid": e["elementId"]["guid"],
                       "host": id_by_guid.get((owner or "").upper()),
                       "offset": det.get("centerOffset"), "width": det.get("width")})
    boxes = tb.bboxes_2d([o["guid"] for o in op
                          if o.get("offset") is None or not o.get("width")]) if op else {}
    for o in op:
        host = by_host.get(o["host"])
        if host is None:
            issues.append({"kind": "opening_off_wall", "opening": o["id"],
                           "opening_guid": o["guid"], "host": o["host"]})
            continue
        exact = o.get("offset") is not None and o.get("width")
        if exact:
            t0, t1 = o["offset"] - o["width"] / 2, o["offset"] + o["width"] / 2
        elif boxes.get(o["guid"]):
            t0, t1 = _span(host, boxes[o["guid"]])
        else:
            continue
        # past the host wall's end (only trustworthy on the exact span — the bbox
        # over-estimates and would flag a door legitimately near the end)
        if exact and (t0 < -0.01 or t1 > host.length + 0.01):
            issues.append({"kind": "opening_off_wall_end", "opening": o["id"],
                           "opening_guid": o["guid"], "host": o["host"],
                           "out_m": round(max(-t0, t1 - host.length), 3)})
        for w in segs:
            if w["id"] == o["host"]:
                continue
            body = w["seg"].buffer(wall_w.get(w["id"], 0.2) / 2, cap_style=2)
            inter = host.intersection(body)
            blocked = [g for g in getattr(inter, "geoms", [inter])
                       if g.geom_type == "LineString" and g.length > 0]
            hit = False
            for seg_b in blocked:
                b0, b1 = sorted(host.project(Point(c))
                                for c in (seg_b.coords[0], seg_b.coords[-1]))
                if min(t1, b1) - max(t0, b0) > 0.02:
                    hit = True
                    break
            if hit:
                issues.append({"kind": "opening_blocked", "opening": o["id"],
                               "opening_guid": o["guid"], "by_wall": w["id"]})
                break
    return issues
