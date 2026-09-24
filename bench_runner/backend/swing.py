"""Opening swing/facing geometry — the ONE conversion from target POINTS to backend flip flags.

The plan says where a door opens with a POINT (`opens_toward`, `hinge_toward`) and where a
window faces with a POINT (`faces_toward`), never with a boolean: a point is readable off a
drawing and is checkable against the built model, while "reflected=true" means nothing without
knowing the wall's direction. Turning those points into the flags a backend actually takes is
pure geometry, so it lives here rather than in either backend.

It is CROSS-TARGET on purpose. It was previously a private static method on the Archicad
toolbox, which left the Revit path with no conversion at all: the tool documentation promised
"the system converts them geometrically", the agent duly passed the points through, and nothing
consumed them — every door came out with Revit's default swing and the failure was invisible
(the built model looked fine, only the swing checkpoint disagreed).

The convention is calibrated 1:1 against the grader's read (`bench_runner/verifier/geometry.py`):
  `oSide`     True = the leaf opens toward the LEFT of the wall's begin->end direction
  `reflected` True = the hinge sits at the END-side end of the doorway
  `refSide`   affects neither and is left untouched.
"""
import math


def _xy(p):
    """One point — [x, y] sequence or {x, y} dict — as (x, y) floats."""
    if isinstance(p, dict):
        return float(p["x"]), float(p["y"])
    return float(p[0]), float(p[1])


def swing_bools(b, e, cx, cy, opens_toward=None, hinge_toward=None, faces_toward=None):
    """The flip flags derivable from the given target points; {} when none was given.

    `b`/`e` are the host wall's begin/end, `cx`/`cy` the opening's centre — all in the SAME
    units (metres at the backend boundary). Only the SIDE of the wall and the END of the
    doorway matter, never the distance, so a point anywhere on the correct side works.
    """
    bx, by = _xy(b)
    ex, ey = _xy(e)
    dx, dy = ex - bx, ey - by
    L = math.hypot(dx, dy)
    if L == 0:
        return {}
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux                     # left-hand normal of beg->end
    out = {}
    side_pt = opens_toward if opens_toward is not None else faces_toward
    if side_pt is not None:
        tx, ty = _xy(side_pt)
        out["oSide"] = ((tx - cx) * nx + (ty - cy) * ny) > 0
    if hinge_toward is not None:
        hx, hy = _xy(hinge_toward)
        out["reflected"] = ((hx - cx) * ux + (hy - cy) * uy) > 0
    return out


# The point params the conversion consumes. A backend that takes flags instead must strip these
# before the call — passing an unknown param on is a schema rejection on some backends.
POINT_PARAMS = ("opens_toward", "hinge_toward", "faces_toward")


def apply(params, b, e, cx, cy):
    """`params` with its swing POINTS replaced by the flags they imply.

    The points win over any raw `oSide`/`reflected` passed alongside — they are the documented
    input and the raw flags are the legacy escape hatch. Returns a NEW dict; the points are
    removed whether or not they produced a flag, so nothing unknown reaches the backend.
    """
    pts = {k: params.get(k) for k in POINT_PARAMS if params.get(k) is not None}
    if not pts:
        return params
    out = {k: v for k, v in params.items() if k not in POINT_PARAMS}
    out.update(swing_bools(b, e, cx, cy, **pts))
    return out
