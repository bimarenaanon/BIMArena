"""Opening actions: doors and windows hosted on walls.

Tapir CreateWindows / CreateDoors host an opening on a wall via:
    ownerWallId, centerOffset (m from wall begin), sillHeight, width, height.
"""
from ..client import exec_error


def _with_swing(data, reflected, refSide, oSide):
    """Return a copy of `data` plus the opening-direction booleans that are set."""
    out = dict(data)
    for k, v in (("reflected", reflected), ("refSide", refSide), ("oSide", oSide)):
        if v is not None:
            out[k] = bool(v)
    return out


def _tap_or_strip_swing(client, cmd, full, base):
    """Run cmd with `full`; if this Tapir version rejects the swing fields (schema error),
    retry with `base` (same payload minus the swing booleans)."""
    try:
        return client.tap(cmd, full)
    except Exception as e:
        if "additionalProperties" in str(e) and full != base:
            return client.tap(cmd, base)
        raise


def _create_opening(client, cmd, key, owner_wall_guid, center_offset, width, height, sill,
                    reflected=None, refSide=None, oSide=None, favorite_name=None):
    off = round(float(center_offset), 3)
    if off < 0:
        # Do NOT clamp to 0 (the old behaviour): a negative projection means the centre lies
        # BEFORE the host wall's begin (wrong wall picked / off-end estimate) — snapping it to
        # the wall start silently places the opening in the wrong spot and hides the mistake
        # from the verify loop. Fail loudly instead.
        return {"ok": False, "error": f"opening centre projects {abs(off)} m BEFORE the host "
                "wall's begin — wrong host wall or wrong centre point"}
    data = {"ownerWallId": {"guid": owner_wall_guid},
            "centerOffset": off,
            "sillHeight": float(sill), "width": float(width), "height": float(height)}
    if favorite_name:
        data["favoriteName"] = favorite_name          # applies a saved favorite (library part + settings)
    swung = _with_swing(data, reflected, refSide, oSide)
    try:
        resp = _tap_or_strip_swing(client, cmd, {key: [swung]}, {key: [data]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    el = resp["elements"][0]
    return {"ok": True, "guid": el["elementId"]["guid"], "center_offset_m": data["centerOffset"]} \
        if "elementId" in el else {"ok": False, "error": el.get("error", {}).get("message", "?")}


def create_window(client, owner_wall_guid, center_offset, width, height, sill=0.9,
                  reflected=None, refSide=None, oSide=None, favorite_name=None):
    return _create_opening(client, "CreateWindows", "windowsData", owner_wall_guid, center_offset,
                           width, height, sill, reflected, refSide, oSide, favorite_name)


def create_door(client, owner_wall_guid, center_offset, width, height, sill=0.0,
                reflected=None, refSide=None, oSide=None, favorite_name=None):
    return _create_opening(client, "CreateDoors", "doorsData", owner_wall_guid, center_offset,
                           width, height, sill, reflected, refSide, oSide, favorite_name)


def _modify_opening(client, cmd, key, guid, width=None, height=None, sill=None,
                    center_offset=None, reflected=None, refSide=None, oSide=None):
    """Modify a door/window (Tapir ModifyDoors/ModifyWindows). Only given fields change."""
    base = {"elementId": {"guid": str(guid)}}
    if width is not None:
        base["width"] = float(width)
    if height is not None:
        base["height"] = float(height)
    if sill is not None:
        base["sillHeight"] = float(sill)
    if center_offset is not None:
        off = round(float(center_offset), 3)
        if off < 0:
            # same rationale as the create path: clamping to the wall begin would silently
            # move the opening to the wrong spot and return ok — fail loudly instead.
            return {"ok": False, "error": f"opening centreOffset {off} m is before the host "
                    "wall's begin — wrong centre (nothing modified)"}
        base["centerOffset"] = off
    swung = _with_swing(base, reflected, refSide, oSide)
    if swung != base and len(base) == 1:
        # SWING-ONLY modify: the strip-and-retry fallback would send just {elementId} — an
        # empty modify that succeeds while changing NOTHING. Send the full payload and fail
        # loudly if this Tapir version rejects the swing fields.
        try:
            resp = client.tap(cmd, {key: [swung]})
        except Exception as e:
            if "additionalProperties" in str(e):
                return {"ok": False, "error": "this Tapir version cannot change an opening's "
                        "direction (reflected/refSide/oSide rejected) — nothing modified"}
            return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    else:
        try:
            resp = _tap_or_strip_swing(client, cmd, {key: [swung]}, {key: [base]})
        except Exception as e:
            return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    # ModifyDoors/ModifyWindows report per-element failures in executionResults with NO
    # exception — without this check a failed modify returns ok and the verifier never
    # hears the opening is still wrong.
    err = exec_error(resp, "modify failed")
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "guid": str(guid)}


def modify_door(client, guid, **kw):
    return _modify_opening(client, "ModifyDoors", "doorsWithDetails", guid, **kw)


def modify_window(client, guid, **kw):
    return _modify_opening(client, "ModifyWindows", "windowsWithDetails", guid, **kw)


def _replace_opening(client, guid, create_fn, kind, favorite_name=None, width=None,
                     height=None, sill=None, reflected=None, refSide=None, oSide=None):
    """Change an opening's TYPE. Tapir's ModifyDoors/ModifyWindows cannot swap the library
    part / favorite (the schema rejects favoriteName — probed on 1.5.3), so replace = read
    the current opening -> delete -> re-create at the SAME offset on the SAME wall with the
    new favorite. Everything is read and VALIDATED before the delete (same contract as
    modify_zone/modify_stair); omitted width/height/sill AND omitted swing booleans keep
    the current values (the swing is read from the old opening's details — recreating with
    library-default swing would silently flip a door the plan had oriented).
    NOTE: the opening gets a NEW guid (returned; "replaced" carries the old one)."""
    if not favorite_name:
        # the whole point of replace is the new TYPE; recreating with no favorite would
        # swap the opening to the DEFAULT library part — type data loss reported as ok.
        return {"ok": False, "error": f"replace_{kind.lower()} needs a `favorite` (the new "
                "type) — for size/position/swing changes use modify instead"}
    try:
        det = client.tap("GetDetailsOfElements",
                         {"elements": [{"elementId": {"guid": str(guid)}}]})["detailsOfElements"][0]
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    if det.get("type") != kind:
        return {"ok": False, "error": f"element {guid!r} is {det.get('type')!r}, not a {kind} "
                "— not replacing"}
    d = det.get("details") or {}
    owner = (d.get("ownerElementId") or {}).get("guid")
    offset = d.get("centerOffset")
    if not owner or offset is None:
        return {"ok": False, "error": f"{kind} {guid!r}: host wall / centerOffset unreadable "
                "— not replacing"}
    new_w = width if width is not None else d.get("width")
    new_h = height if height is not None else d.get("height")
    new_s = sill if sill is not None else (d.get("sillHeight") or 0.0)
    if new_w is None or new_h is None:
        return {"ok": False, "error": f"{kind} {guid!r}: current size unreadable — pass "
                "width and height explicitly"}
    # omitted swing booleans KEEP the old opening's direction (read from the same details
    # dict; absent keys stay None = library default, same as before).
    if reflected is None:
        reflected = d.get("reflected")
    if refSide is None:
        refSide = d.get("refSide")
    if oSide is None:
        oSide = d.get("oSide")
    try:
        dresp = client.tap("DeleteElements", {"elements": [{"elementId": {"guid": str(guid)}}]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error deleting the old {kind}: {e}"}
    # a silently-failed delete (executionResults, no exception) + recreate = TWO openings on
    # the same wall while reporting ok.
    err = exec_error(dresp, "delete failed")
    if err:
        return {"ok": False, "error": f"replace: deleting the old {kind} failed ({err}) — "
                "opening unchanged"}
    res = create_fn(client, owner, offset, new_w, new_h, sill=new_s, reflected=reflected,
                    refSide=refSide, oSide=oSide, favorite_name=favorite_name)
    if isinstance(res, dict) and res.get("ok"):
        res["replaced"] = str(guid)
    elif isinstance(res, dict):
        # the OLD opening is already GONE — without saying so, the next round re-targets its
        # guid and gets a baffling "not a Door" instead of re-creating the opening.
        res["error"] = (f"replace: the OLD {kind} {guid} was DELETED but the re-create "
                        f"FAILED — {res.get('error')}; re-CREATE it (host {owner}, "
                        f"centerOffset {offset}, w {new_w} x h {new_h}, sill {new_s})")
    return res


def replace_door(client, guid, **kw):
    return _replace_opening(client, guid, create_door, "Door", **kw)


def replace_window(client, guid, **kw):
    return _replace_opening(client, guid, create_window, "Window", **kw)
