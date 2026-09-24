"""Stair actions (Tapir CreateStairs).

CreateStairs was added in Tapir 1.5.0; check the add-on version with
`GetAddOnVersion` if you hit error 4010 ("command not registered"). The vendored
bundle under tapir_addon/ may predate 1.5.0 — update it if so.
"""
from ...settings import WALL_HEIGHT
from .points import pt as _pt


def create_stair(client, baseline_xy, z=0.0, total_height=WALL_HEIGHT,
                 flight_width=1.0, step_num=None, riser_height=None, tread_depth=None):
    """Create one stair from a baseline polyline.

    baseline_xy  : [(x, y), ...] meters. 2 points ONLY (straight run) — Tapir 1.5.2 fails on
                   any multi-point baseline despite its schema claiming L/U support (probed).
    z            : absolute elevation of the stair base (m).
    total_height : floor-to-floor rise (m); defaults to the standard wall height.
    flight_width : width of the flight (m).
    step_num / riser_height / tread_depth : optional; Archicad derives sensible
                   defaults from total_height when omitted.
    Returns {"ok", "guid"} or {"ok": False, "error"}.
    """
    if not baseline_xy or len(baseline_xy) < 2:
        return {"ok": False, "error": "baseline needs >= 2 points"}
    try:
        points = [_pt(p) for p in baseline_xy]
    except Exception:
        return {"ok": False, "error": "baseline points must be [x, y] pairs or {x, y} dicts"}
    stair = {
        "baseLinePoints": [{"x": x, "y": y} for x, y in points],
        "zCoordinate": float(z),
        "totalHeight": float(total_height),
        "flightWidth": float(flight_width),
    }
    if step_num is not None:
        stair["stepNum"] = int(step_num)
    if riser_height is not None:
        stair["riserHeight"] = float(riser_height)
    elif step_num:
        # Tapir ACCEPTS stepNum and IGNORES it (probed 2026-08-14 on add-on 1.5.3:
        # stepNum=15 over a 3 m rise still built 20 risers of 150 mm — Archicad's own
        # default riser height wins). The riser HEIGHT is honoured, and it is the same
        # statement: N risers over the total rise. Sent only when the caller did not
        # pin a height itself; stepNum stays in the payload for a Tapir that fixes this.
        stair["riserHeight"] = float(total_height) / int(step_num)
    if tread_depth is not None:
        stair["treadDepth"] = float(tread_depth)
    try:
        resp = client.tap("CreateStairs", {"stairsData": [stair]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    el = resp["elements"][0]
    return {"ok": True, "guid": el["elementId"]["guid"]} if "elementId" in el \
        else {"ok": False, "error": el.get("error", {}).get("message", "unknown")}


