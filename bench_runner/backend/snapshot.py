"""Snapshot the currently-open Archicad model as JSON-able data.

A pre-step ("hook") that reads what already exists in the live project, grouped into
stories / walls / doors / windows / slabs / rooms / stairs. Goes through the Toolbox —
the framework's single Archicad API surface.

Slimmed for a planner:
  walls         : id, endpoints, height, width (composite thickness), composite name
  doors/windows : id, host wall id, centre point (from the 2D bounding box)
"""
import json

from .archicad.toolbox import Toolbox

# Archicad element type -> our snapshot bucket
_TYPE_BUCKET = {
    "Wall": "walls",
    "Door": "doors",
    "Window": "windows",
    "Slab": "slabs",
    "Zone": "rooms",
    "Stair": "stairs",
    "Object": "objects",
}

# detail fields to keep per bucket (Tapir returns no usable details for Stair -> id only)
_KEEP = {
    "rooms": ("name", "numberStr", "polygonOutline"),
    # (no "stairs" entry — stairs never reach the generic branch; they're handled explicitly)
}


def _center_on_wall(geom, offset):
    """Point [x,y] on a wall centreline at `offset` m from its begin. geom = (beg, end)
    coordinate dicts. None if either is missing."""
    import math
    if not geom or offset is None:
        return None
    b, e = geom
    if not b or not e:
        return None
    dx, dy = e["x"] - b["x"], e["y"] - b["y"]
    L = math.hypot(dx, dy) or 1.0
    return [round(b["x"] + dx / L * offset, 3), round(b["y"] + dy / L * offset, 3)]


def _swing_geometry(geom, center, width, swing, kind):
    """Computed swing GEOMETRY of a placed opening, from Tapir's raw booleans + the host
    wall — the numeric view the verifier can compare against the plan's target points
    (the raw booleans alone force the LLM back into geometric guessing).

    Convention (identical to the grader's calibrated read and the Toolbox's inverse,
    Toolbox._swing_bools): `oSide` True = the leaf/exterior side is the LEFT of the wall's
    beg->end direction; `reflected` True = the hinge sits at the doorway's END-side end.

    Returns {} or, per available flag: doors -> "opens_toward" ([x,y] a point 1 m out on
    the swing side) + "hinge_end" ([x,y] the hinged doorway end); windows -> "faces_toward"
    (1 m out on the exterior side)."""
    import math
    if not geom or not center or not swing:
        return {}
    b, e = geom
    if not b or not e:
        return {}
    dx, dy = e["x"] - b["x"], e["y"] - b["y"]
    L = math.hypot(dx, dy)
    if L == 0:
        return {}
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux                                  # left-hand normal of beg->end
    cx, cy = center
    out = {}
    if "oSide" in swing:
        sx, sy = (nx, ny) if swing["oSide"] else (-nx, -ny)
        key = "opens_toward" if kind == "doors" else "faces_toward"
        out[key] = [round(cx + sx, 3), round(cy + sy, 3)]
    if kind == "doors" and "reflected" in swing and width:
        sign = 1.0 if swing["reflected"] else -1.0    # +: toward wall end, -: toward begin
        half = float(width) / 2.0
        out["hinge_end"] = [round(cx + ux * half * sign, 3), round(cy + uy * half * sign, 3)]
    return out


# Which jamb a Revit leaf pivots on relative to `hand` (FamilyInstance.HandOrientation).
# MUST stay identical to the grader's calibration — bench_runner/verifier/geometry.py
# REVIT_HAND_TO_HINGE (calibrated 2026-08-06 against C_model_editing7's gt.rvt: the leaf
# pivots on the jamb the hand vector POINTS AT). Duplicated rather than imported: the
# backend is agent-side and must never depend on the grading package.
_REVIT_HAND_TO_HINGE = 1


def _fill_remote_swing(snapshot):
    """Add the computed swing POINTS to a Revit snapshot's openings, from the absolute
    `facing` / `hand` vectors the add-in reports.

    Doors get `opens_toward` (1 m out on the leaf side) + `hinge_end` (the hinged doorway
    end); windows get `faces_toward`. Identical in meaning to `_swing_geometry`'s output
    on the Tapir path and to how the grader reads a Revit opening
    (`verifier/geometry.py:opening_normal` / `hinge_point`), so what the agent writes as a
    target point is what it reads back.

    Openings the add-in could not orient keep no swing keys at all — an absent key means
    "unknown", which is what the verifier treats as unchecked; a guessed one would be a
    silent wrong answer."""
    import math
    for kind in ("doors", "windows"):
        for o in snapshot.get(kind) or []:
            center = o.get("center")
            if not center or len(center) < 2:
                continue
            try:
                cx, cy = float(center[0]), float(center[1])
            except (TypeError, ValueError):
                continue
            facing = o.get("facing")
            if facing and len(facing) >= 2:
                try:
                    fx, fy = float(facing[0]), float(facing[1])
                except (TypeError, ValueError):
                    fx = fy = 0.0
                L = math.hypot(fx, fy)
                if L > 1e-9:
                    key = "opens_toward" if kind == "doors" else "faces_toward"
                    o[key] = [round(cx + fx / L, 3), round(cy + fy / L, 3)]
            hand, width = o.get("hand"), o.get("width")
            if kind == "doors" and hand and len(hand) >= 2 and width:
                try:
                    hx, hy, w = float(hand[0]), float(hand[1]), float(width)
                except (TypeError, ValueError):
                    continue
                L = math.hypot(hx, hy)
                if L > 1e-9:
                    half = w / 2.0 * _REVIT_HAND_TO_HINGE
                    o["hinge_end"] = [round(cx + hx / L * half, 3),
                                      round(cy + hy / L * half, 3)]


def model_snapshot(tb=None):
    """Return a dict of the current model: {stories, walls, doors, windows, slabs, rooms,
    stairs, objects}."""
    tb = tb or Toolbox.connect()

    # Revit backend: the snapshot is computed Revit-side (HTTP add-in) in the SAME schema
    # (geometry in metres, stories with elevation_mm + active) — just return it.
    if hasattr(tb, "remote_snapshot"):
        remote = tb.remote_snapshot()
        # ...except the outward flag: the add-in reports each wall's EXTERIOR-face normal
        # (Wall.Orientation) but not whether that normal points away from the building —
        # that needs the storey's closed footprint, which is exactly what the second pass
        # below computes. Without this a flipped Revit wall was invisible to the verifier.
        try:
            _fill_wall_outward(remote.get("walls") or [])
        except Exception:
            pass
        # ...and the swing GEOMETRY. The add-in reports `facing`/`hand` (absolute plan
        # vectors) but not the POINTS, so the agent wrote a swing in one vocabulary
        # (`opens_toward`) and read it back in another — it could not verify its own
        # openings at all. Same computed view the Tapir path gets below.
        try:
            _fill_remote_swing(remote)
        except Exception:
            pass
        return remote

    snap = {b: [] for b in _TYPE_BUCKET.values()}
    st = tb.get_stories()
    raw_stories = st.get("stories", []) if st.get("ok") else []
    # the storey whose floor plan is CURRENTLY open in Archicad (actStory) — what "the active
    # story" in every task instruction refers to. Drives which floor plan the planner reads and
    # the base level new elements are placed on. We FLAG it inside `stories` ("active": true)
    # rather than repeating the whole storey in a separate "active_story" key (no duplication).
    act_idx = st.get("actStory") if st.get("ok") else None
    # storey elevation is reported in mm (architectural convention); level stays in m internally.
    snap["stories"] = [{"index": s.get("index"), "name": s.get("name"),
                        "elevation_mm": round((s.get("level") or 0.0) * 1000),
                        "active": s.get("index") == act_idx}
                       for s in raw_stories]
    story_level = {s.get("index"): s.get("level", 0.0) for s in raw_stories}  # m, for absolute levels
    # NB: existing composites are NOT stored in the snapshot (they bloat it and aren't diffed) —
    # the planner fetches them on demand as a transient input (see planner.py).

    pairs = tb.all_elements()                 # ONE full inventory, reused below (2 Tapir calls)

    # composite name + total thickness (width) per wall GUID (readable ids like "SW - 043"
    # can REPEAT across storeys — e.g. after copying a storey — and would mis-attribute)
    comp = {}
    for w in tb.list_walls_with_composite(pairs=pairs).get("walls", []):
        skins = w.get("skins_outer_to_inner") or []
        width = round(sum(s.get("thickness_m", 0) for s in skins), 3) if skins else None
        comp[w.get("guid")] = {"composite": w.get("composite_name"), "width": width,
                               "material": w.get("material")}   # basic walls only (inventory)

    # keyed UPPER-cased: the owner→wall join must not depend on Tapir returning
    # `ownerElementId` guids in the same case as the inventory guids (clash.py upper-cases
    # this exact join on both sides for the same reason).
    wall_id_by_guid = {e["elementId"]["guid"].upper(): d.get("id")
                       for e, d in pairs if d.get("type") == "Wall"}
    wall_geom_by_guid = {e["elementId"]["guid"].upper(): (d["details"].get("begCoordinate"),
                                                          d["details"].get("endCoordinate"))
                         for e, d in pairs if d.get("type") == "Wall" and d.get("details")}
    slab_comp = tb.composite_names("Slab", pairs=pairs)  # {guid(upper): composite name}

    # An element whose detail carries NO type is skipped below. That is normally harmless
    # (Tapir reports "Not yet supported element type" for markers and the like), but it is
    # also how a REAL element disappears: GetDetailsOfElements does not always answer for
    # elements outside the ACTIVE WINDOW, so a model read while an Elevation/Section window
    # is open can come back missing walls or rooms that are perfectly present. Grading such
    # a snapshot fails `preserve.*`/`counts.*` for elements nobody deleted (measured
    # 2026-08-29 on create_door2: 5 walls read as 2). Count the skips and report them, so the
    # loss is VISIBLE to whoever reads the snapshot instead of silently becoming a bad score.
    # Callers that need a complete read must open a floor-plan window first —
    # `bench_runner/verifier/sources.live()` does.
    untyped = 0
    for elem, detail in pairs:
        bucket = _TYPE_BUCKET.get(detail.get("type"))
        if not bucket:
            if not detail.get("type"):
                untyped += 1
            continue
        guid = elem["elementId"]["guid"]
        d = detail.get("details") or {}
        floor = detail.get("floorIndex")          # which storey the element sits on
        if bucket == "walls":
            c = comp.get(guid, {})
            snap["walls"].append({
                "guid": guid,
                "id": detail.get("id"),
                "floor": floor,
                "begCoordinate": d.get("begCoordinate"),
                "endCoordinate": d.get("endCoordinate"),
                "height": d.get("height"),
                "width": c.get("width"),
                "composite": c.get("composite"),
                "material": c.get("material"),   # a BASIC wall's building material by name
            })
        elif bucket in ("doors", "windows"):
            owner_guid = ((d.get("ownerElementId") or {}).get("guid") or "").upper() or None
            off = d.get("centerOffset")
            entry = {"guid": guid,
                     "id": detail.get("id"),
                     "floor": floor,
                     "type": (d.get("libPart") or {}).get("name"),
                     "host": wall_id_by_guid.get(owner_guid),
                     # built dimensions + position, so the verifier can compare to the drawing
                     # instead of re-emitting its (noisy) reading as a modify every round.
                     "width": d.get("width"),
                     "height": d.get("height"),
                     "sill": d.get("sillHeight"),
                     "center_offset": off,
                     # reliable centre ON the host wall centreline (computed from the offset,
                     # NOT the 2D bbox, whose box is inflated by a door's swing arc).
                     "center": _center_on_wall(wall_geom_by_guid.get(owner_guid), off)}
            # swing/orientation params, when the backend reports them — without these an
            # opening's facing is invisible, so a wrongly-swung door could never be
            # detected or corrected from the model state.
            swing = {k: d[k] for k in ("reflected", "refSide", "oSide") if k in d}
            if swing:
                entry["swing_raw"] = swing
                # ...and the COMPUTED geometry view of those booleans (doors: opens_toward +
                # hinge_end; windows: faces_toward) — numbers the verifier compares directly
                # against the plan's target points instead of re-deriving sides from flags.
                entry.update(_swing_geometry(wall_geom_by_guid.get(owner_guid),
                                             entry.get("center"), d.get("width"),
                                             swing, bucket))
            snap[bucket].append(entry)
        elif bucket == "slabs":
            # detail "level" is RELATIVE to the slab's home storey; report ABSOLUTE elevation
            # (storey level + offset) so the verifier compares against the drawing's FFL correctly
            # and doesn't keep "fixing" a slab that's already at the right height.
            rel = d.get("level") or 0.0
            snap["slabs"].append({
                "guid": guid,
                "id": detail.get("id"),
                "floor": floor,                       # every bucket is floor-tagged (contract)
                "thickness": d.get("thickness"),
                "level": round(story_level.get(floor, 0.0) + rel, 3),
                # reference-plane offset below the slab's TOP surface (m): 0 = Top
                # reference — lets the grader check a required reference plane
                "offset_from_top": d.get("offsetFromTop"),
                "composite": slab_comp.get(guid.upper()),
                "polygonOutline": d.get("polygonOutline"),
                # openings cut into the slab (e.g. a stairwell) — without them a
                # verifier keeps "re-cutting" a hole that is already there
                "holes": [h.get("polygonOutline") for h in (d.get("holes") or [])
                          if h.get("polygonOutline")],
            })
        elif bucket == "stairs":
            # Tapir GetDetails can't read a Stair; we fill footprint + a few dims below.
            snap["stairs"].append({"guid": guid, "id": detail.get("id"), "floor": floor})
        elif bucket == "objects":
            # furniture: keep the library-part name (the TYPE) + floor; centre filled below.
            # SKIP built-in markers (Story/Elevation markers): they are Objects OWNED by another
            # element (an ownerElementId/Type) and/or named "...Marker" — not furniture, so they
            # must not pollute the snapshot.
            libpart = (d.get("libPart") or {}).get("name")
            owned = d.get("ownerElementId") or d.get("ownerElementType")
            if not libpart or owned or "marker" in libpart.lower():
                continue
            snap["objects"].append({
                "guid": guid, "id": detail.get("id"), "floor": floor, "type": libpart})
        else:  # rooms
            keep = _KEEP.get(bucket)
            slim = {k: d.get(k) for k in keep} if keep is not None else d
            snap[bucket].append({"guid": guid, "id": detail.get("id"), "floor": floor, **slim})

    # Opening elements (the Opening tool — e.g. create_slab_opening's stairwell voids) CUT
    # their owner in 3D but never touch the slab's own polygon, and Tapir cannot read their
    # details ("Not yet supported element type") — so without this merge the snapshot reports
    # a hole-less slab and a verifier keeps re-cutting a void that is already there. Each
    # Opening becomes its 2D-bbox rectangle (openings are rectangular) appended to the slab
    # it sits in, attributed by floor + bbox-centre containment (the owner is unreadable).
    opening_guids = [(e["elementId"]["guid"], d.get("floorIndex"))
                     for e, d in pairs if d.get("type") == "Opening"]
    if opening_guids and snap["slabs"]:
        boxes = tb.bboxes_2d([g for g, _ in opening_guids])
        for g, fl in opening_guids:
            b = boxes.get(g)
            if not b:
                continue
            cx, cy = (b["xMin"] + b["xMax"]) / 2, (b["yMin"] + b["yMax"]) / 2
            for s in snap["slabs"]:
                if s.get("floor") == fl and _point_in_poly(cx, cy, s.get("polygonOutline") or []):
                    s["holes"].append([
                        {"x": b["xMin"], "y": b["yMin"]}, {"x": b["xMax"], "y": b["yMin"]},
                        {"x": b["xMax"], "y": b["yMax"]}, {"x": b["xMin"], "y": b["yMax"]},
                        {"x": b["xMin"], "y": b["yMin"]}])
                    break

    # Stairs: GetDetails returns nothing, so read what the SLAB task needs another way —
    # the 2D FOOTPRINT (for cutting a stairwell opening) plus flight width + total height.
    if snap["stairs"]:
        _fill_stair_dims(tb, snap["stairs"], pairs)

    # Objects: give each a centre point (from its 2D bbox) so the verifier can compare
    # furniture positions against the drawing.
    if snap["objects"]:
        boxes = tb.bboxes_2d([o["guid"] for o in snap["objects"]])
        for o in snap["objects"]:
            b = boxes.get(o["guid"])
            if b:
                o["center"] = [round((b["xMin"] + b["xMax"]) / 2, 3),
                               round((b["yMin"] + b["yMax"]) / 2, 3)]

    # Walls: which side of the reference line the body (and so each skin) faces is
    # otherwise INVISIBLE — a wall built with its layers the wrong way round could never
    # be detected or corrected from the model state. Best-effort enrichment.
    if snap["walls"]:
        _fill_wall_orientation(tb, snap["walls"])

    if untyped:
        # not an exception: some untyped entries are legitimate. Reported so a caller (and
        # any score built on this snapshot) can see that the read was not complete.
        snap["untyped_elements"] = untyped

    return snap


def _fill_wall_orientation(tb, walls):
    """Attach `orient` = {"ref": <reference-line location>, "left_mm", "right_mm"} to each
    wall (in place): the body's perpendicular extents each side of the reference line,
    where "left" is left of the begin->end direction. Read via the OFFICIAL property API
    (Wall_ReferenceLineLocation + General_Thickness) plus the 2D bounding boxes — Tapir's
    details carry no orientation. This tells a reader which way the wall's build-up faces
    (e.g. an outside-face reference line with the body on the wrong side = a flipped
    wall, fixable by swapping begin and end). Axis-aligned walls only (a slanted wall's
    bbox is unusable); walls that can't be read stay unchanged. Also fills a missing
    `width` from General_Thickness (basic walls carry no composite to sum)."""
    _WANT = ("Wall_ReferenceLineLocation", "General_Thickness")
    try:
        acc, act = tb.client.acc, tb.client.act
        by_name = {getattr(n, "nonLocalizedName", ""): n for n in acc.GetAllPropertyNames()}
        props = [by_name[k] for k in _WANT if k in by_name]
        idx = {k: i for i, k in enumerate(k for k in _WANT if k in by_name)}
        if "Wall_ReferenceLineLocation" not in idx:
            return
        pids = [p.propertyId for p in acc.GetPropertyIds(props)]
        eids = [act.ElementIdArrayItem(act.ElementId(w["guid"])) for w in walls]
        vals = acc.GetPropertyValuesOfElements(eids, pids)
        boxes = acc.Get2DBoundingBoxes(eids)
    except Exception:
        return

    def _pv(v, key):
        i = idx.get(key)
        if i is None:
            return None
        pv = v.propertyValues[i].propertyValue
        return getattr(pv, "value", None)

    for w, v, bb in zip(walls, vals, boxes):
        try:
            if w.get("width") is None:
                thick = _pv(v, "General_Thickness")
                if isinstance(thick, (int, float)):
                    w["width"] = round(thick, 3)
            val = _pv(v, "Wall_ReferenceLineLocation")
            loc = getattr(val, "nonLocalizedValue", None) or (
                val if isinstance(val, str) else None)
            beg, end = w.get("begCoordinate"), w.get("endCoordinate")
            if not beg or not end:
                continue
            box = bb.boundingBox2D
            dx, dy = end["x"] - beg["x"], end["y"] - beg["y"]
            if abs(dy) < 1e-6 and abs(dx) > 1e-6:        # horizontal wall
                up, down = box.yMax - beg["y"], beg["y"] - box.yMin
                left, right = (up, down) if dx > 0 else (down, up)
            elif abs(dx) < 1e-6 and abs(dy) > 1e-6:      # vertical wall
                xplus, xminus = box.xMax - beg["x"], beg["x"] - box.xMin
                left, right = (xminus, xplus) if dy > 0 else (xplus, xminus)
            else:                                        # slanted: bbox unusable
                if loc:
                    w["orient"] = {"ref": loc}
                continue
            w["orient"] = {"ref": loc,
                           "left_mm": round(max(left, 0.0) * 1000, 1),
                           "right_mm": round(max(right, 0.0) * 1000, 1)}
        except Exception:
            continue
    _fill_wall_outward(walls)


def _fill_wall_outward(walls):
    """Second pass: orient["outward"] = True when the wall's OUTER/finish face points
    AWAY from the building interior (False = built inside-out; absent = unreadable).

    Computed GEOMETRICALLY, exactly like the bench grader's faces check — the
    left/right body extents alone are NOT a facing judgment: swapping begin/end flips
    the body to the reference line's other side but it stays on the SAME handedness
    side of the new direction, so any left-vs-right rule misreads orientation and
    (worse) survives its own fix. Instead: reference-line semantics give the body's
    INNER side (an outside-face ref puts the body toward the interior), and a probe
    just beyond the body's inner face must land INSIDE the walls' closed footprint."""
    try:
        from shapely.geometry import LineString, Point
        from shapely.ops import polygonize, unary_union
    except Exception:
        return
    import math

    by_floor = {}
    for w in walls:
        by_floor.setdefault(w.get("floor"), []).append(w)

    for floor_walls in by_floor.values():
        lines = []
        for w in floor_walls:
            b, e = w.get("begCoordinate"), w.get("endCoordinate")
            if not b or not e:
                continue
            p1 = (round(b["x"], 2), round(b["y"], 2))
            p2 = (round(e["x"], 2), round(e["y"], 2))
            if p1 != p2:
                lines.append(LineString([p1, p2]))
        footprint = None
        if lines:
            polys = list(polygonize(unary_union(lines)))
            if polys:
                footprint = unary_union(polys)
        for w in floor_walls:
            # BASIC (single-material) walls have no finish/outer skin — "outward" is
            # meaningless for them, and hand-built walls can carry a MIRROR flag no
            # API exposes (the reference-line location alone then misreads the body
            # side): computing a flag here would invite the verifier to "fix"
            # correct walls. Composite walls only.
            if not w.get("composite"):
                continue
            o = w.get("orient") or {}
            ref = (o.get("ref") or "").lower()
            left, right = o.get("left_mm"), o.get("right_mm")
            b, e = w.get("begCoordinate"), w.get("endCoordinate")
            if left is None or right is None or not b or not e or footprint is None:
                continue
            # Revit reports the exterior-face NORMAL itself (and only for compound types),
            # which settles the facing exactly — no reference-line semantics needed. The KEY
            # being present identifies that backend, so a null value means "single-layer type,
            # no finish side" and must NOT fall through to the ArchiCAD thicker-side rule,
            # which would invent a flag from a Revit location-line name it cannot read.
            ext = o.get("exterior")
            if ext is None and "exterior" in o:
                continue
            if ext and len(ext) >= 2:
                ex, ey = float(ext[0]), float(ext[1])
                ln = math.hypot(ex, ey)
                dx, dy = e["x"] - b["x"], e["y"] - b["y"]
                n = math.hypot(dx, dy)
                if ln > 1e-9 and n > 0:
                    ex, ey = ex / ln, ey / ln
                    lx, ly = -dy / n, dx / n
                    reach = ((left if (ex * lx + ey * ly) > 0 else right) or 0) / 1000.0
                    mid = ((b["x"] + e["x"]) / 2, (b["y"] + e["y"]) / 2)
                    probe = Point(mid[0] + ex * (reach + 0.1), mid[1] + ey * (reach + 0.1))
                    try:
                        o["outward"] = not bool(footprint.contains(probe))
                        w["orient"] = o
                    except Exception:
                        pass
                    continue
            if "outside" in ref:
                inner_side = 1 if left >= right else -1        # body side = inner
            elif "inside" in ref:
                inner_side = -1 if left >= right else 1        # body side = outer
            elif abs(left - right) >= 2:
                inner_side = 1 if left > right else -1         # thicker = finish side
            else:
                continue                                       # symmetric: unreadable
            dx, dy = e["x"] - b["x"], e["y"] - b["y"]
            n = math.hypot(dx, dy)
            if n == 0:
                continue
            ux, uy = (-dy / n) * inner_side, (dx / n) * inner_side
            inner_extent = ((left if inner_side == 1 else right) or 0) / 1000.0
            mid = ((b["x"] + e["x"]) / 2, (b["y"] + e["y"]) / 2)
            probe = Point(mid[0] + ux * (inner_extent + 0.1),
                          mid[1] + uy * (inner_extent + 0.1))
            try:
                o["outward"] = bool(footprint.contains(probe))
                w["orient"] = o
            except Exception:
                continue


def _point_in_poly(x, y, outline):
    """Ray-cast point-in-polygon over a Tapir polygonOutline ({x,y} dicts)."""
    pts = [(p["x"], p["y"]) for p in outline if p]
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _fill_stair_dims(tb, stairs, pairs=None):
    """Add flight_width + height + a TRUE footprint [x0,y0,x1,y1] to each stair (in place).

    The stair's raw 2D bounding box is inflated by its 2D symbol (up-arrow / break line), so
    it's NOT the real void. We instead build the footprint as a flight_width x run rectangle
    centred on the bbox, oriented along the bbox's longer axis — the actual stairwell void.

    Stair elements come from the Tapir inventory (`pairs`), NOT the view-filtered official
    GetElementsByType (which returns nothing when a 3D window / filtered view is active —
    the stair would silently lose its dims and fall back to the inflated bbox).
    """
    # properties: flight width, total height, walking-line length (the run), and the
    # step geometry — riser height + going. There is NO built-in property holding the
    # NUMBER of risers (probed 2026-08-14: the only riser-count entry in the stock
    # property set is the STAIR DESCRIPTION expression group's "Abbrevation for Number
    # of Risers", whose value is the LABEL "No. R"), so the count is DERIVED below as
    # height / riser_height — exact for a straight single flight, which is all Tapir
    # CreateStairs can build anyway.
    acc = tb.client.acc
    want = {"Stair_FlightWidth": "flight_width", "General_Height": "height",
            "Stair_WalkingLineLength": "run",
            "Stair_DefaultRiserHeight": "riser_height", "Stair_DefaultGoing": "going"}
    names = [u for u in acc.GetAllPropertyNames()
             if type(u).__name__ == "BuiltInPropertyUserId" and u.nonLocalizedName in want]
    by_guid = {s["guid"].upper(): s for s in stairs}
    if pairs is None:
        pairs = tb.all_elements()
    if names:
        objs = [e for e, d in pairs if d.get("type") == "Stair"]
        pids = [p.propertyId for p in acc.GetPropertyIds(names)]
        for el, row in zip(objs, acc.GetPropertyValuesOfElements(objs, pids)):
            s = by_guid.get(el["elementId"]["guid"].upper())
            if not s:
                continue
            for nm, pv in zip(names, row.propertyValues):
                try:
                    s[want[nm.nonLocalizedName]] = round(pv.propertyValue.value, 3)
                except Exception:
                    pass
    for s in stairs:
        h, rh = s.get("height"), s.get("riser_height")
        if h and rh:
            s["risers"] = int(round(h / rh))

    boxes = tb.bboxes_2d([s["guid"] for s in stairs])
    for s in stairs:
        b = boxes.get(s["guid"])
        if not b:
            continue
        cx, cy = (b["xMin"] + b["xMax"]) / 2, (b["yMin"] + b["yMax"]) / 2
        fw, run = s.get("flight_width"), s.get("run")
        if fw and run:                               # clean rectangle from real width x run
            along_y = (b["yMax"] - b["yMin"]) >= (b["xMax"] - b["xMin"])
            half_w, half_l = fw / 2, run / 2
            if along_y:
                fp = [cx - half_w, cy - half_l, cx + half_w, cy + half_l]
            else:
                fp = [cx - half_l, cy - half_w, cx + half_l, cy + half_w]
        else:                                        # fallback: the raw bbox
            fp = [b["xMin"], b["yMin"], b["xMax"], b["yMax"]]
        s["footprint"] = [round(v, 3) for v in fp]


