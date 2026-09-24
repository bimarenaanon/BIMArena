"""Slab actions. A composite slab is two steps: CreateSlabs then ModifySlabs."""
from ..attributes import create_composite
from ..client import exec_error
from .points import pt as _pt


# CreateSlabs' reference-plane enum (which surface the slab's `level` pins). CREATE-time
# only: ModifySlabs rejects the field, so a wrong reference plane cannot be fixed in place.
_REF_PLANES = {"top": "Top", "bottom": "Bottom", "coretop": "CoreTop",
               "corebottom": "CoreBottom"}


def create_composite_slab(client, name=None, skins=None, polygon_xy=None, level=0.0,
                          composite_name=None, reference_plane=None):
    """Create a slab with a composite: a freshly-built one (name + skins) OR an EXISTING
    one reused by name (composite_name) — mirrors create_composite_wall's reuse route, so
    the BUILD `slabs` task can "select an EXISTING slab composite" without re-authoring it.

    skins          : [{"material", "type", "thickness"}] outer->inner (new composite).
    composite_name : reuse an existing composite by name (skins ignored).
    polygon_xy     : [(x, y), ...] meters.
    reference_plane: which slab surface `level` pins — "Top" | "Bottom" | "CoreTop" |
                     "CoreBottom" (tolerant to case/spaces). CREATE-time only (the modify
                     path cannot change it); omit for the application default.
    Returns {"ok", "slab_guid", "composite_guid", "total_thickness_m"} or error.
    """
    if reference_plane is not None:
        canon = _REF_PLANES.get(str(reference_plane).replace(" ", "").lower())
        if canon is None:
            return {"ok": False, "error": f"unknown reference_plane {reference_plane!r} — "
                    f"use one of {sorted(set(_REF_PLANES.values()))}"}
        reference_plane = canon
    if composite_name:                                # REUSE an existing composite by name
        from ..attributes import composite_info
        comp = composite_info(client, composite_name)   # ONE resolution: guid + thickness
        if comp is None:
            return {"ok": False, "error": f"no existing composite named {composite_name!r}"}
        total = comp["total_thickness_m"]
    else:                                             # author a NEW composite from the skins
        if not name or not skins:
            return {"ok": False, "error": "need composite_name (reuse) OR name + skins (new)"}
        comp = create_composite(client, name, skins, use_with=("Slab",))
        if "guid" not in comp:
            return {"ok": False, "error": comp.get("error", "composite creation failed")}
        total = comp["total_thickness_m"]

    try:                                              # points may be [x,y] OR {x,y} dicts
        coords = [{"x": x, "y": y} for x, y in (_pt(p) for p in (polygon_xy or []))]
    except Exception:
        return {"ok": False, "error": "polygon points must be [x, y] pairs or {x, y} dicts"}
    if len(coords) < 3:
        return {"ok": False, "error": "polygon needs >= 3 points"}
    slab = {"level": float(level), "thickness": total, "polygonCoordinates": coords}
    if reference_plane is not None:
        slab["referencePlaneLocation"] = reference_plane
    try:
        try:
            sresp = client.tap("CreateSlabs", {"slabsData": [slab]})
        except Exception as e:                        # older Tapir schema without the field
            if "referencePlaneLocation" in str(e) and "additionalProperties" in str(e):
                sresp = client.tap("CreateSlabs", {"slabsData": [
                    {k: v for k, v in slab.items() if k != "referencePlaneLocation"}]})
            else:
                raise
        el = sresp["elements"][0]
        if "elementId" not in el:                     # per-element create failure (no exception)
            return {"ok": False, "error": el.get("error", {}).get("message", "slab create failed")}
        slab_guid = el["elementId"]["guid"]
        mresp = client.tap("ModifySlabs", {"slabsWithDetails": [{
            "elementId": client.aid_plain(slab_guid),
            "structureType": "Composite",
            "compositeId": client.aid_plain(comp["guid"])}]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    # ModifySlabs reports failure via executionResults with NO exception. If this second step
    # fails, the slab exists but is left a BASIC slab — and since composites are attributes
    # (never in the geometry diff), the verify loop can NEVER see it. Fail loudly, with the
    # slab guid so a repair can re-assign instead of re-creating the slab.
    err = exec_error(mresp, "composite assignment failed")
    if err:
        return {"ok": False, "error": f"slab created but composite assignment failed: {err}",
                "slab_guid": slab_guid}
    return {"ok": True, "slab_guid": slab_guid, "composite_guid": comp["guid"],
            "total_thickness_m": total}


def modify_slab(client, guid, thickness=None, composite_guid=None, composite_name=None,
                polygon_xy=None):
    """Modify an existing slab (Tapir ModifySlabs). Only the given fields change.

    NOTE: there is NO level change here — ModifySlabs' zCoordinate does not actually move a
    slab (its elevation is tied to its home storey), so we don't expose it. A slab created on
    the right storey is already at the right height.
    thickness     -> slab thickness (m).
    composite_guid-> assign a composite (sets structureType=Composite).
    composite_name-> assign an EXISTING composite resolved by NAME (the modify twin of
                     create_composite_slab's composite_name; no new composite is created).
    polygon_xy    -> new outline [(x,y),...].
    Returns {"ok": True, "guid"} or {"ok": False, "error"}.
    """
    if composite_guid is not None and composite_name is not None:
        return {"ok": False, "error": "give composite_guid OR composite_name, not both"}
    if composite_name is not None:
        from ..attributes import composite_ref
        composite_guid = composite_ref(client, composite_name)   # resolve, never create
        if composite_guid is None:
            return {"ok": False, "error": f"no existing composite named {composite_name!r}"}
    s = {"elementId": {"guid": str(guid)}}
    if thickness is not None:
        s["thickness"] = float(thickness)
    if composite_guid is not None:
        s["structureType"] = "Composite"
        s["compositeId"] = client.aid_plain(composite_guid)
    if polygon_xy is not None:
        try:                                          # points may be [x,y] OR {x,y} dicts
            s["polygonOutline"] = [{"x": x, "y": y} for x, y in (_pt(p) for p in polygon_xy)]
        except Exception:
            return {"ok": False, "error": "polygon points must be [x, y] pairs or {x, y} "
                    "dicts (nothing modified)"}
    try:
        resp = client.tap("ModifySlabs", {"slabsWithDetails": [s]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    # same contract as modify_wall / modify_door: ModifySlabs reports per-element failure in
    # executionResults with NO exception — a failed modify must not return ok.
    err = exec_error(resp, "modify failed")
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "guid": str(guid)}


def create_slab_opening(client, slab_guid, base_xy, width, height, z=0.0):
    """Cut a rectangular opening (hole) through a slab — e.g. a stairwell void (Archicad
    won't auto-cut a slab for a stair). Tapir CreateOpenings.

    base_xy : [x, y] the hole's MIN corner (slab plane).
    width   : hole extent along X (m).   height : hole extent along Y (m).
    z       : the slab's level (m).
    Returns {"ok": True, "guid"} or {"ok": False, "error"}.

    NOTE (probed live on Tapir 1.5.3): CreateOpenings' basePoint is the hole's TOP-CENTRE
    anchor — x is the rect's centre, the rect hangs DOWNWARD (-y) from basePoint.y — so the
    min corner is converted here. The cut is an Opening ELEMENT: it never appears in the
    slab's own polygon `holes` (and Tapir can't read Opening details); model_snapshot merges
    Opening elements into the slab's holes from their 2D bboxes.
    """
    try:
        bx, by = _pt(base_xy)                         # [x,y] OR {x,y} dict
    except Exception:
        return {"ok": False, "error": "base_xy must be an [x, y] pair or {x, y} dict"}
    op = {"ownerElementId": {"guid": str(slab_guid)},
          # min corner -> Tapir's top-centre anchor
          "basePoint": {"x": bx + float(width) / 2, "y": by + float(height), "z": float(z)},
          "width": float(width), "height": float(height)}
    try:
        resp = client.tap("CreateOpenings", {"openingsData": [op]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    el = resp["elements"][0]
    return {"ok": True, "guid": el["elementId"]["guid"]} if "elementId" in el \
        else {"ok": False, "error": el.get("error", {}).get("message", "unknown")}
