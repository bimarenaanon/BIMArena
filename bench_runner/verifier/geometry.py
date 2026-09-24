"""Pure-geometry helpers for the checkers. Everything is in MILLIMETRES."""
from __future__ import annotations

import math


def dist(p, q) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def seg_len(a, b) -> float:
    return dist(a, b)


def _project_t(p, a, b) -> float:
    """Parameter (mm along the segment) of p's projection onto line a->b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L


def point_line_dist(p, a, b) -> float:
    """Perpendicular distance of p from the INFINITE line through a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / L


def match_segment(a, b, walls, tol: float):
    """Match an expected undirected segment a->b against candidate wall segments.

    A wall counts toward the segment when it is COLLINEAR with it (both
    endpoints within `tol` of the infinite line) — its projected overlap with
    [0, L] is what it covers, so split pieces AND overshooting walls both get
    their on-segment part credited. Returns (coverage_fraction, used_indices).
    """
    L = seg_len(a, b)
    if L <= 0:
        return 0.0, []
    intervals, used = [], []
    for i, w in enumerate(walls):
        wb, we = w.get("beg"), w.get("end")
        if not wb or not we:
            continue
        if point_line_dist(wb, a, b) > tol or point_line_dist(we, a, b) > tol:
            continue
        t0, t1 = sorted((_project_t(wb, a, b), _project_t(we, a, b)))
        t0, t1 = max(t0, 0.0), min(t1, L)
        # "barely touching" filter, capped at half the segment: an expected
        # segment SHORTER than tol (a 300 mm jog at tol 300) must still accept
        # the wall that fully covers it
        if t1 - t0 <= min(tol, 0.5 * L):
            continue
        intervals.append((t0, t1))
        used.append(i)
    if not intervals:
        return 0.0, []
    intervals.sort()
    covered, cur0, cur1 = 0.0, *intervals[0]
    for t0, t1 in intervals[1:]:
        if t0 > cur1:
            covered += cur1 - cur0
            cur0, cur1 = t0, t1
        else:
            cur1 = max(cur1, t1)
    covered += cur1 - cur0
    return min(covered / L, 1.0), used


# ---------------------------------------------------------------- polygons

def to_polygon(outline, holes=None):
    """[[x,y], ...] (closed or open) -> shapely Polygon (minus any holes),
    or None if degenerate."""
    from shapely.geometry import Polygon

    def ring(pts):
        pts = [tuple(p) for p in pts]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        return pts if len(pts) >= 3 else None

    outer = ring(outline)
    if outer is None:
        return None
    poly = Polygon(outer, [h for h in map(ring, holes or []) if h])
    return poly if poly.is_valid and poly.area > 0 else poly.buffer(0)


def iou(outline_a, outline_b, holes_a=None, holes_b=None) -> float:
    pa, pb = to_polygon(outline_a, holes_a), to_polygon(outline_b, holes_b)
    if pa is None or pb is None or pa.is_empty or pb.is_empty:
        return 0.0
    inter = pa.intersection(pb).area
    union = pa.union(pb).area
    return inter / union if union > 0 else 0.0


def point_in_outline(p, outline) -> bool:
    from shapely.geometry import Point
    poly = to_polygon(outline)
    return bool(poly and poly.contains(Point(p[0], p[1])))


def outline_area_m2(outline, holes=None) -> float | None:
    """Polygon area of a mm-space outline in m² (None if degenerate)."""
    poly = to_polygon(outline, holes)
    if poly is None or poly.is_empty:
        return None
    return poly.area / 1e6


def overlap_fraction(outline, region, holes=None) -> float:
    """Fraction of rectangular region [x0,y0,x1,y1] covered by the outline
    (minus any holes — a slab with a stairwell CUT does not cover it)."""
    from shapely.geometry import box
    poly = to_polygon(outline, holes)
    if poly is None:
        return 0.0
    r = box(min(region[0], region[2]), min(region[1], region[3]),
            max(region[0], region[2]), max(region[1], region[3]))
    return poly.intersection(r).area / r.area if r.area > 0 else 0.0


def outside_fraction(outline, rects) -> float | None:
    """Fraction of the outline's area that lies OUTSIDE the union of the
    [x0,y0,x1,y1] rectangles (None if the outline is degenerate)."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    poly = to_polygon(outline)
    if poly is None or poly.is_empty or poly.area <= 0:
        return None
    if not rects:
        return 1.0
    region = unary_union([box(min(r[0], r[2]), min(r[1], r[3]),
                              max(r[0], r[2]), max(r[1], r[3])) for r in rects])
    return 1.0 - poly.intersection(region).area / poly.area


def rect_hits_wall(hole_pts, beg, end, half_width) -> bool:
    """Does a slab opening overlap a wall's plan BODY?

    The wall body is its centre line grown by half its thickness (plus any extra
    clearance the case asks for); the hole is its own polygon. Touching edges do
    not count - only a real overlap, so an opening drawn flush against a wall
    face still passes.
    """
    from shapely.geometry import LineString, Polygon
    try:
        poly = Polygon([(p[0], p[1]) for p in hole_pts])
        body = LineString([(beg[0], beg[1]), (end[0], end[1])]).buffer(half_width,
                                                                      cap_style=2)
    except Exception:
        return False
    if poly.is_empty or not poly.is_valid:
        poly = poly.buffer(0)
    return poly.intersection(body).area > 1.0        # > 1 mm2 = a real overlap


def rect_inside(rect, region, tol: float) -> bool:
    """Is rect [x0,y0,x1,y1] inside region [x0,y0,x1,y1] (grown by tol)?"""
    return (rect[0] >= region[0] - tol and rect[1] >= region[1] - tol
            and rect[2] <= region[2] + tol and rect[3] <= region[3] + tol)


def walls_footprint(walls, snap_mm: float = 10.0):
    """Outline [[x,y],...] of the closed region the wall centrelines enclose.

    Snaps endpoints to `snap_mm`, polygonizes the line network (shapely) and
    returns the LARGEST polygon's exterior — the building footprint. None when
    the walls don't close a region.
    """
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    lines = []
    for w in walls:
        b, e = w.get("beg"), w.get("end")
        if not b or not e:
            continue
        b = (round(b[0] / snap_mm) * snap_mm, round(b[1] / snap_mm) * snap_mm)
        e = (round(e[0] / snap_mm) * snap_mm, round(e[1] / snap_mm) * snap_mm)
        if b == e:
            continue
        # bridge mitred-corner gaps: a wall segment read at its FACE (or a
        # location curve trimmed by a corner join) can stop up to one wall
        # thickness short of the true corner, leaving a network that never
        # closes. Extend each segment by its own thickness — the extensions
        # cross the neighbour's line so polygonize gets its corner node, and
        # the dangling overshoot spurs are dropped by polygonize anyway.
        dx, dy = e[0] - b[0], e[1] - b[1]
        length = math.hypot(dx, dy)
        o = w.get("orient") or {}
        t = w.get("width") or ((o.get("left_mm") or 0) + (o.get("right_mm") or 0)) or 0
        t = min(t, length / 2)
        ux, uy = dx / length, dy / length
        lines.append(LineString([(b[0] - ux * t, b[1] - uy * t),
                                 (e[0] + ux * t, e[1] + uy * t)]))
    if not lines:
        return None
    polys = list(polygonize(unary_union(lines)))
    if not polys:
        return None
    # interior walls partition the footprint into room faces — the envelope is
    # their UNION, not the largest single face
    merged = unary_union(polys)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda p: p.area)
    return [[x, y] for x, y in merged.exterior.coords]


def walls_outer_footprint(walls):
    """Outline [[x,y],...] of the walls' EXTERIOR-FACE envelope.

    `walls_footprint` polygonizes the stored segments, which sit on whatever
    line each backend reports (outside face for ArchiCAD / face-shifted Revit
    compound walls, but the CENTERLINE for a Revit basic wall) — so its ring can
    run one half-thickness inside the true outer surface. Union the enclosed
    region with every wall's BODY rectangle (segment offset to the body centre,
    buffered by the half-width, square caps so corners close): the merged
    exterior ring lies on the outer faces whatever the segment convention.
    Bodies are built about the raw location curve (`loc_beg`/`loc_end` kept by
    grade.normalize) because the orient extents are measured about it.
    """
    fp = walls_footprint(walls)
    if not fp or len(fp) < 4:
        return fp
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    bodies = [Polygon(fp)]
    for w in walls:
        b = w.get("loc_beg") or w.get("beg")
        e = w.get("loc_end") or w.get("end")
        o = w.get("orient") or {}
        left, right = o.get("left_mm"), o.get("right_mm")
        if not b or not e or left is None or right is None:
            continue
        dx, dy = e[0] - b[0], e[1] - b[1]
        length = math.hypot(dx, dy)
        halfw = (left + right) / 2.0
        if length < 1e-9 or halfw <= 0:
            continue
        lx, ly = -dy / length, dx / length          # left of beg->end
        off = (left - right) / 2.0                  # centreline of the BODY
        seg = LineString([(b[0] + lx * off, b[1] + ly * off),
                          (e[0] + lx * off, e[1] + ly * off)])
        bodies.append(seg.buffer(halfw, cap_style=3))
    merged = unary_union(bodies)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda p: p.area)
    return [[x, y] for x, y in merged.exterior.coords]


# The plan compass and the bbox words name the same four sides. A case says "the WEST
# exterior wall" because that is how a building is described; wall_side() answers in bbox
# terms. Neither spelling is wrong, so both are accepted (added 2026-08-14, after a
# correctly-placed Revit door failed host_side: "west").
SIDE_ALIASES = {"north": "top", "south": "bottom", "east": "right", "west": "left",
                "top": "top", "bottom": "bottom", "right": "right", "left": "left"}


def side_key(word) -> str | None:
    """Canonical bbox word for a side named either way (compass or bbox)."""
    return SIDE_ALIASES.get((word or "").strip().lower())


def wall_side(wall, walls) -> str | None:
    """Classify a wall as the top/bottom/left/right side of the group's bbox.

    Meant for the simple rectangular-room cases ("place a window on the north
    wall"): horizontal wall nearest the bbox top -> "top", etc.
    """
    pts = [p for w in walls for p in (w.get("beg"), w.get("end")) if p]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    b, e = wall.get("beg"), wall.get("end")
    if not b or not e:
        return None
    horizontal = abs(e[1] - b[1]) <= abs(e[0] - b[0])
    cx, cy = (b[0] + e[0]) / 2, (b[1] + e[1]) / 2
    if horizontal:
        return "top" if abs(cy - y1) <= abs(cy - y0) else "bottom"
    return "right" if abs(cx - x1) <= abs(cx - x0) else "left"


def wall_midpoint(wall):
    b, e = wall.get("beg"), wall.get("end")
    if not b or not e:
        return None
    return [(b[0] + e[0]) / 2, (b[1] + e[1]) / 2]


# Revit hinge side. `HandOrientation` gives the family's +X axis in world coordinates (already
# corrected for flips), which runs ALONG the wall — but which jamb the leaf actually pivots on
# relative to that axis is a property of how the family was authored, so the sign has to be
# calibrated ONCE against a live model (place a door, read `hand`, compare with the plan arc).
#
# CALIBRATED 2026-08-06 against C_model_editing7's gt.rvt, whose drawing is unmirrored and
# whose arcs are unambiguous — two independent doors, both M_Single-Flush:
#   west DINING door   hand [0,1]  (north), leaf drawn at the NORTH jamb -> +1
#   north BALCONY door hand [-1,0] (west),  leaf drawn at the WEST jamb  -> +1
# So the leaf pivots on the jamb the hand vector POINTS AT: hinge = centre + hand*(width/2).
REVIT_HAND_TO_HINGE = 1


def hinge_point(swing_raw, wall, center, width):
    """[x,y] of the doorway end the leaf HINGES on, or None.

    REVIT: from `swing_raw["hand"]` (HandOrientation), gated on the
    REVIT_HAND_TO_HINGE calibration above.

    ARCHICAD: per the toolbox convention `reflected` mirrors the hinge
    left<->right along the wall: hinge at the wall-BEG-side end of the doorway
    when False, at the end-side end when True. Deterministic in (flags, host
    wall, centre, width), so expected values derived from a correct GT compare
    1:1 against a build on the same pre-existing wall.
    """
    sw = swing_raw or {}
    hand = sw.get("hand")
    if hand and len(hand) >= 2 and center and width:
        if REVIT_HAND_TO_HINGE is None:
            return None
        hx, hy = float(hand[0]), float(hand[1])
        L = math.hypot(hx, hy)
        if L == 0:
            return None
        half = width / 2.0 * REVIT_HAND_TO_HINGE
        return [center[0] + hx / L * half, center[1] + hy / L * half]
    if "reflected" not in sw or not wall or not center or not width:
        return None
    b, e = wall.get("beg"), wall.get("end")
    if not b or not e:
        return None
    dx, dy = e[0] - b[0], e[1] - b[1]
    L = math.hypot(dx, dy)
    if L == 0:
        return None
    dx, dy = dx / L, dy / L
    half = width / 2.0
    sign = 1.0 if sw["reflected"] else -1.0     # -: toward wall beg, +: toward end
    return [center[0] + dx * half * sign, center[1] + dy * half * sign]


def opening_normal(swing_raw, wall):
    """Unit normal of the SIDE an opening's leaf swings toward (in/out).

    TWO backends, two sources:

    * REVIT — `swing_raw["facing"]` is FamilyInstance.FacingOrientation as a plan
      unit vector, i.e. the side the instance faces, which for a swing family is
      the side the leaf opens toward. Revit RECOMPUTES it after every flip, so it
      is absolute: no host wall and no knowledge of the family's default
      insertion is needed, and it is used as-is when present.
    * ARCHICAD — derived from the host wall direction + Tapir's `oSide` flag:

    Per the toolbox convention (prompt/toolbox.md): `oSide` is what flips which
    way the opening opens (in<->out) — the LEFT side of beg->end when True, the
    RIGHT side when False (calibrated against a live GT: single doors with
    oSide=True open into the room, double doors with oSide=False open out).
    `reflected`/`refSide` mirror the hinge / reference side ALONG the wall and
    do not enter the in/out normal. Returns None when the flag or the wall
    geometry is unavailable (-> swing unchecked).
    """
    sw = swing_raw or {}
    facing = sw.get("facing")
    if facing and len(facing) >= 2:
        fx, fy = float(facing[0]), float(facing[1])
        L = math.hypot(fx, fy)
        if L > 1e-9:
            return (fx / L, fy / L)
    if "oSide" not in sw or not wall:
        return None
    b, e = wall.get("beg"), wall.get("end")
    if not b or not e:
        return None
    dx, dy = e[0] - b[0], e[1] - b[1]
    L = math.hypot(dx, dy)
    if L == 0:
        return None
    dx, dy = dx / L, dy / L
    nx, ny = -dy, dx                      # left-hand normal of beg->end
    if not sw["oSide"]:
        nx, ny = -nx, -ny
    return (nx, ny)
