"""Zone actions (Tapir CreateZones)."""
from ..client import exec_error
from .points import pt as _pt


def create_zone(client, name, number, polygon_xy, stamp_xy=None, floor_index=0):
    """Create a Zone in the open project.

    polygon_xy : [(x, y), ...] meters, >= 3 vertices.
    stamp_xy   : stamp position; defaults to the polygon centroid.
    Returns a small dict the caller/model can read.
    """
    if not polygon_xy or len(polygon_xy) < 3:
        return {"ok": False, "error": "polygon needs >= 3 points"}
    try:
        coords = [{"x": x, "y": y} for x, y in (_pt(p) for p in polygon_xy)]
    except Exception:
        return {"ok": False, "error": "polygon points must be [x, y] pairs or {x, y} dicts"}
    if stamp_xy is None:
        stamp_xy = (sum(c["x"] for c in coords) / len(coords),
                    sum(c["y"] for c in coords) / len(coords))
    zone = {
        "name": name,
        "numberStr": str(number),
        "floorIndex": floor_index,
        "geometry": {"polygonCoordinates": coords},
        "stampPosition": {"x": float(stamp_xy[0]), "y": float(stamp_xy[1])},
    }
    try:
        resp = client.tap("CreateZones", {"zonesData": [zone]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    el = resp["elements"][0]
    if "elementId" in el:
        return {"ok": True, "guid": el["elementId"]["guid"], "name": name}
    return {"ok": False, "error": el.get("error", {}).get("message", "unknown")}


def modify_zone(client, guid, polygon_xy=None, name=None, number=None, floor_index=None):
    """Modify an existing zone. Tapir has NO ModifyZones, so this is delete + recreate:
    the current name/number/floor/outline are read and any of them you pass overrides.
    Returns the new zone's create result (with "replaced": True) or an error.
    """
    cur = None
    for e, d in client.all_elements():
        # guid case is UNRELIABLE (Tapir mixes cases; clash reports upper-case) — compare
        # case-insensitively, like Toolbox._elem does, or an upper-cased guid echoed back by
        # the LLM fails with a spurious "no zone".
        if str(e["elementId"]["guid"]).upper() == str(guid).upper() and d.get("type") == "Zone":
            det = d.get("details") or {}
            cur = {"name": det.get("name"), "number": det.get("numberStr"),
                   "floor_index": d.get("floorIndex") or 0,
                   "polygon": [(p["x"], p["y"]) for p in (det.get("polygonOutline") or [])]}
            break
    if cur is None:
        return {"ok": False, "error": f"no zone {guid}"}
    poly = polygon_xy if polygon_xy is not None else cur["polygon"]
    # validate BEFORE deleting — a bad polygon (too few points, or a point shape create_zone
    # would choke on, e.g. string coords) discovered after the delete loses the zone.
    try:
        if not poly or len(poly) < 3:
            raise ValueError
        for p in poly:
            _pt(p)
    except Exception:
        return {"ok": False, "error": "modify_zone: polygon needs >= 3 [x, y] pairs "
                "or {x,y} dicts (nothing was deleted)"}
    try:
        dresp = client.tap("DeleteElements", {"elements": [{"elementId": {"guid": str(guid)}}]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error (delete): {e}"}
    # DeleteElements reports failure via executionResults with NO exception — recreating
    # after a silently-failed delete would leave BOTH the old and the new zone in the model.
    err = exec_error(dresp, "delete failed")
    if err:
        return {"ok": False, "error": f"modify_zone: delete failed ({err}) — zone unchanged"}
    res = create_zone(client, name if name is not None else cur["name"],
                      number if number is not None else cur["number"], poly,
                      floor_index=floor_index if floor_index is not None else cur["floor_index"])
    if res.get("ok"):
        res["replaced"] = str(guid)       # the OLD guid — the documented replace contract
    else:
        # the OLD zone is already GONE — the error must say so, or the next round re-targets
        # its guid instead of re-creating the zone.
        res["error"] = (f"modify_zone: the OLD zone {guid} was DELETED but the re-create "
                        f"FAILED — {res.get('error')}; re-CREATE it "
                        f"({len(poly)}-pt polygon, name {cur['name']!r})")
    return res
