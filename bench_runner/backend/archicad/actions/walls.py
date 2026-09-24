"""Wall actions (Tapir CreateWalls), basic + composite."""
from ...settings import WALL_HEIGHT
from ..client import exec_error

# Where the wall's reference line sits relative to its thickness. The DEFAULT authors from
# the OUTSIDE face: the begin/end coordinates are the wall's outermost edge. NOTE: the
# `referenceLineLocation` field on CreateWalls only exists in Tapir >= 1.5.3. Tapir 1.5.2
# REJECTS it (schema additionalProperties=false), so `_create_walls` strips it and retries
# on that error — walls then fall back to centre-referenced until the add-on is updated.
WALL_REFERENCE_LINE = "Outside"

# The reference lines the `reference` tool param exposes, agent vocabulary -> Tapir's enum.
# The three whole-wall ones are what the Revit backend can mirror (Finish Face: Exterior /
# Wall Centerline / Finish Face: Interior); the three CORE ones are Archicad-side only and
# are what a layered wall is dimensioned on in practice — the core is the structure, the
# finishes come and go. CREATE-TIME ONLY on either application: Tapir's ModifyWalls REJECTS
# `referenceLineLocation` (4002, schema additionalProperties — probed 2026-08-14 on add-on
# 1.5.3), so changing a BUILT wall's reference line means delete + recreate, or the GUI's
# Wall Settings.
REFERENCE_LINES = {"outside": "Outside", "center": "Center", "centre": "Center",
                   "inside": "Inside",
                   "core outside": "CoreOutside", "core_outside": "CoreOutside",
                   "core center": "CoreCenter", "core_center": "CoreCenter",
                   "core centre": "CoreCenter", "core_centre": "CoreCenter",
                   "core inside": "CoreInside", "core_inside": "CoreInside"}


def _create_walls(client, walls_data):
    """CreateWalls, stripping `referenceLineLocation` and retrying if this Tapir version
    rejects it (1.5.2 schema has additionalProperties=false; the field landed in 1.5.3)."""
    try:
        return client.tap("CreateWalls", {"wallsData": walls_data})
    except Exception as e:
        if "referenceLineLocation" in str(e) and "additionalProperties" in str(e):
            stripped = [{k: v for k, v in w.items() if k != "referenceLineLocation"}
                        for w in walls_data]
            return client.tap("CreateWalls", {"wallsData": stripped})
        raise


def bulk_create_walls(client, walls_data):
    """Create many walls from ready-made wallsData dicts.

    Normalizes PARTIAL failures: Tapir returns {"elements": [...]} where a failed segment is
    an {"error": ...} entry with NO top-level "ok" — without this, the pipeline's failure
    filter ('ok' is False) misses it, the log prints '✓ create_walls', and the verifier never
    hears that walls are missing.

    The failure result carries the per-segment split — `failed_segments` (0-based indices
    into the submitted list) and `created` (the segments that DID build, with their guids) —
    and the error text says so explicitly: the repair round would otherwise re-emit the
    WHOLE segment list and duplicate every wall that succeeded."""
    resp = _create_walls(client, walls_data)
    elements = resp.get("elements") if isinstance(resp, dict) else None
    errs = [(i, e) for i, e in enumerate(elements or [])
            if isinstance(e, dict) and e.get("error")]
    if errs:
        first = errs[0][1]["error"]
        msg = first.get("message") if isinstance(first, dict) else first
        failed_idx = [i for i, _ in errs]
        created = [{"segment": i, "guid": e["elementId"]["guid"]}
                   for i, e in enumerate(elements or [])
                   if isinstance(e, dict) and "elementId" in e]
        return {"ok": False,
                "error": (f"segment(s) {failed_idx} of {len(walls_data)} failed: {msg}. "
                          f"The other {len(created)} segment(s) WERE created — when fixing, "
                          f"re-emit ONLY the failed segment(s), never the whole list"),
                "failed_segments": failed_idx,
                "created": created,
                "elements": elements}
    return resp


def create_walls(client, segments, height=WALL_HEIGHT, thickness=0.2, z=0.0,
                 reference_line=WALL_REFERENCE_LINE, material=None):
    """Create straight single-material walls from (x1,y1,x2,y2) reference-line segments.

    `reference_line` (Tapir >= 1.5.3) sets which edge the begin/end coords describe;
    default "Outside" = the outer face. Ignored by Tapir 1.5.2.
    `material` names an EXISTING building material for the walls' basic structure
    (resolved via material_ref, never invented) — omit for the application default.
    """
    mat_guid = None
    if material:
        from ..attributes import material_ref
        mat_guid = material_ref(client, material, strict=True)   # named by the user: no
        if mat_guid is None:                                     # silent generic fallback
            return {"ok": False, "error": f"no existing building material matching "
                    f"{material!r} — use a name from the project's material list"}
    walls_data = [{
        "begCoordinate": {"x": float(x1), "y": float(y1)},
        "endCoordinate": {"x": float(x2), "y": float(y2)},
        "zCoordinate": float(z), "height": float(height), "thickness": float(thickness),
        "referenceLineLocation": reference_line,
        **({"buildingMaterialId": client.aid_plain(mat_guid)} if mat_guid else {}),
    } for (x1, y1, x2, y2) in segments]
    return bulk_create_walls(client, walls_data)


def create_wall(client, begin, end, height=WALL_HEIGHT, thickness=None, z=0.0,
                reference_line=WALL_REFERENCE_LINE, material=None,
                composite_name=None, composite_guid=None, total_thickness=None):
    """ONE straight wall, composite OR basic — the merged create behind the `create_wall`
    tool (2026-08-03: it replaced the create_walls/create_composite_wall pair; those stay
    as the underlying implementations and for older callers).

    Structure is picked by the params: composite_name/composite_guid -> composite wall;
    material and/or thickness -> basic single-material wall; none -> basic wall with the
    application defaults. Always returns {"ok", "guid"/"error"} — one wall, one guid, so an
    opening in the same batch can host on it via "$id.guid".
    """
    if composite_guid or composite_name:
        if material:
            return {"ok": False, "error": "give ONE structure: composite_name/composite_guid "
                                          "OR material — not both"}
        return create_composite_wall(client, begin, end, composite_guid=composite_guid,
                                     total_thickness=total_thickness, height=height,
                                     thickness=thickness, z=z, reference_line=reference_line,
                                     composite_name=composite_name)
    seg = (float(begin[0]), float(begin[1]), float(end[0]), float(end[1]))
    resp = create_walls(client, [seg], height=height, thickness=thickness or 0.2, z=z,
                        reference_line=reference_line, material=material)
    if isinstance(resp, dict) and resp.get("ok") is False:   # material miss / partial failure
        return resp
    el = (resp.get("elements") or [{}])[0] if isinstance(resp, dict) else {}
    return {"ok": True, "guid": el["elementId"]["guid"]} if "elementId" in el \
        else {"ok": False, "error": (el.get("error") or {}).get("message", "unknown")}


def create_composite_wall(client, begin, end, composite_guid=None, total_thickness=None,
                          height=WALL_HEIGHT, thickness=None, z=0.0,
                          reference_line=WALL_REFERENCE_LINE, composite_name=None):
    """Create one wall that uses a composite, by guid OR by the NAME of an existing composite.

    composite_guid  : guid of the composite (e.g. from a just-created one).
    composite_name  : REUSE an existing composite by name (resolved to its guid) — used so
                      upper-floor walls reuse the ground floor's composites, no duplicates.
    total_thickness : the composite's total thickness (used if `thickness` is None).
    reference_line  : which edge begin/end describe (Tapir >= 1.5.3; default outer face).
    Returns {"ok": ..., "guid"/"error": ...}.
    """
    if composite_guid is None and composite_name:    # REUSE an existing composite by name
        from ..attributes import composite_info
        info = composite_info(client, composite_name)   # ONE resolution: guid + thickness
        if info is None:
            return {"ok": False, "error": f"no existing composite named {composite_name!r}"}
        composite_guid = info["guid"]
        if not thickness and not total_thickness:    # take the wall width from that composite
            total_thickness = info["total_thickness_m"]
    if composite_guid is None:
        return {"ok": False, "error": "need composite_guid or composite_name"}
    if not thickness and not total_thickness:
        return {"ok": False, "error": "need total_thickness (or thickness)"}
    wall = {
        "begCoordinate": {"x": float(begin[0]), "y": float(begin[1])},
        "endCoordinate": {"x": float(end[0]), "y": float(end[1])},
        "zCoordinate": float(z), "height": float(height),
        "thickness": float(thickness) if thickness else float(total_thickness),
        "structureType": "Composite", "compositeId": client.aid_plain(composite_guid),
        "referenceLineLocation": reference_line,
    }
    try:
        resp = _create_walls(client, [wall])
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    el = resp["elements"][0]
    return {"ok": True, "guid": el["elementId"]["guid"]} if "elementId" in el \
        else {"ok": False, "error": el.get("error", {}).get("message", "unknown")}


def _xy(p):
    """Accept a point as [x, y] or {"x": .., "y": ..}."""
    return (p["x"], p["y"]) if isinstance(p, dict) else (p[0], p[1])


def modify_wall(client, guid, begin=None, end=None, height=None, thickness=None,
                composite_guid=None, composite_name=None, building_material=None):
    """Modify an existing wall (Tapir ModifyWalls). Only the given fields change.

    composite_name    : switch the wall to an EXISTING composite resolved by NAME (the
                        modify twin of create_composite_wall's composite_name — the LLM
                        holds composite NAMES, not guids, so a "change this wall to
                        composite X" modify needs this route; no new composite is created).
    building_material : switch the wall to a BASIC (single-material) structure using an
                        EXISTING building material, resolved by name via material_ref.
    composite_guid / composite_name / building_material are mutually exclusive.
    """
    if sum(x is not None for x in (composite_guid, composite_name, building_material)) > 1:
        return {"ok": False, "error": "give ONE of composite_guid / composite_name / "
                "building_material and OMIT the others entirely (an empty string counts "
                "as given)"}
    if composite_name is not None:
        from ..attributes import composite_ref
        composite_guid = composite_ref(client, composite_name)   # resolve, never create
        if composite_guid is None:
            return {"ok": False, "error": f"no existing composite named {composite_name!r}"}
    w = {"elementId": client.aid_plain(guid)}
    if begin is not None:
        x, y = _xy(begin); w["begCoordinate"] = {"x": float(x), "y": float(y)}
    if end is not None:
        x, y = _xy(end); w["endCoordinate"] = {"x": float(x), "y": float(y)}
    if height is not None:
        w["height"] = float(height)
    if thickness is not None:
        w["thickness"] = float(thickness)
    if composite_guid is not None:
        w["structureType"] = "Composite"
        w["compositeId"] = client.aid_plain(composite_guid)
    if building_material is not None:
        from ..attributes import material_ref
        # strict: the material was NAMED by the caller — the lenient keyword/generic fallback
        # would silently substitute an arbitrary material and report ok (create_walls already
        # resolves strictly for the same reason; materials never show in the geometry diff, so
        # a silent substitute is invisible to the verifier).
        mat = material_ref(client, building_material, strict=True)
        if mat is None:
            return {"ok": False, "error": f"no building material matching {building_material!r}"}
        w["structureType"] = "Basic"
        w["buildingMaterialId"] = client.aid_plain(mat)
    try:
        resp = client.tap("ModifyWalls", {"wallsWithDetails": [w]})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    # ModifyWalls reports per-element failures in executionResults with NO exception — a
    # failed modify must not return ok (the verifier would think the wall was fixed).
    err = exec_error(resp, "modify failed")
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "guid": str(guid)}
