"""Project inventory reads (composites + walls-with-composite) used by the snapshot.

- list_composites(client)            : every composite attribute (name + skin stack)
- list_walls_with_composite(client)  : every wall with its composite skin stack
"""


def list_composites(client):
    """Every composite attribute in the project: [{name, total_thickness_m, use_with,
    skins_outer_to_inner:[{material,thickness_m,type}]}]. Lets upper-floor walls REUSE the
    composites the ground floor already created instead of inventing new (slightly different) ones.

    `use_with` (["Wall"] | ["Slab"] | ["Roof", "Shell"] | ...) is what the attribute may be
    ASSIGNED to, and it is not cosmetic: a Slab-only composite does not appear in the wall
    tool's structure picker at all, so a reader told only the name hunts for a row that cannot
    exist. Half this template's composites are slab/roof-only."""
    acc = client.acc
    bm = {str(d.buildingMaterialAttribute.attributeId.guid): d.buildingMaterialAttribute.name
          for d in acc.GetBuildingMaterialAttributes(acc.GetAttributesByType("BuildingMaterial"))}
    out = []
    for d in acc.GetCompositeAttributes(acc.GetAttributesByType("Composite")):
        c = d.compositeAttribute
        skins = []
        for s in c.compositeSkins:
            sk = s.compositeSkin
            guid = getattr(getattr(sk.buildingMaterialId, "attributeId", None), "guid", None)
            stype = "Core" if sk.isCore else ("Finish" if sk.isFinish else "Other")
            skins.append({"material": bm.get(str(guid)) if guid else None,
                          "thickness_m": round(sk.thickness, 4), "type": stype})
        out.append({"name": c.name, "total_thickness_m": round(c.totalThickness, 4),
                    "use_with": list(getattr(c, "useWith", None) or []),
                    "skins_outer_to_inner": skins})
    return out


def list_walls_with_composite(client, pairs=None):
    """Retrieve every wall with its composite skin stack (material/thickness/type).

    Used by the snapshot (wall width = sum of skin thicknesses) and the verifier to compare
    what was built against the plan. Returns {"walls": [...], "count": n}.

    `pairs` — an already-fetched client.all_elements() result to reuse; the full-project
    inventory is 2 Tapir round-trips, so a caller that just did one (model_snapshot) passes
    it in instead of paying for a second.
    """
    acc = client.acc
    bm = {str(d.buildingMaterialAttribute.attributeId.guid): d.buildingMaterialAttribute.name
          for d in acc.GetBuildingMaterialAttributes(acc.GetAttributesByType("BuildingMaterial"))}
    comp = {}
    for d in acc.GetCompositeAttributes(acc.GetAttributesByType("Composite")):
        c = d.compositeAttribute
        skins = []
        for s in c.compositeSkins:
            sk = s.compositeSkin
            bmid = getattr(sk.buildingMaterialId, "attributeId", None)   # ErrorItem if material deleted
            guid = getattr(bmid, "guid", None)
            stype = "Core" if sk.isCore else ("Finish" if sk.isFinish else "Other")
            skins.append({"material": bm.get(str(guid)) if guid else None,
                          "thickness_m": round(sk.thickness, 4), "type": stype})
        comp[c.name] = {"total_thickness_m": round(c.totalThickness, 4),
                        "skins_outer_to_inner": skins}

    if pairs is None:
        pairs = client.all_elements()
    welems = [e for e, d in pairs if d.get("type") == "Wall"]
    wdet = [d for e, d in pairs if d.get("type") == "Wall"]
    uid = [u for u in acc.GetAllPropertyNames()
           if type(u).__name__ == "BuiltInPropertyUserId" and u.nonLocalizedName == "Construction_CompositeName"]
    walls = []
    if welems and uid:
        pid = acc.GetPropertyIds(uid)[0].propertyId
        pv = acc.GetPropertyValuesOfElements(welems, [pid])
        for e, d, row in zip(welems, wdet, pv):
            det = d["details"]
            try:
                cname = row.propertyValues[0].propertyValue.value
            except Exception:
                cname = None
            walls.append({"id": d.get("id"),
                          "guid": e["elementId"]["guid"],   # unique — readable ids can repeat
                          "begin": [round(det["begCoordinate"]["x"], 3), round(det["begCoordinate"]["y"], 3)],
                          "end": [round(det["endCoordinate"]["x"], 3), round(det["endCoordinate"]["y"], 3)],
                          "composite_name": cname,
                          "skins_outer_to_inner": comp.get(cname, {}).get("skins_outer_to_inner")})
    # BASIC walls: Construction_CompositeName is empty and every element-level material
    # property reports notAvailable (probed 2026-08-20) — the material lives on the wall's
    # ONE component, so it is read through the COMPONENT API and attached as "material".
    # Best-effort: a failed read leaves the field absent (material checkpoints then score
    # unchecked), never breaks the inventory.
    basic = [(w, e) for w, e in zip(walls, welems) if not w.get("composite_name")]
    if basic:
        try:
            muid = [u for u in acc.GetAllPropertyNames()
                    if type(u).__name__ == "BuiltInPropertyUserId"
                    and u.nonLocalizedName == "SurfaceAndMaterials_ComponentBuildingMaterialName"]
            if muid:
                mpid = acc.GetPropertyIds(muid)[0].propertyId
                comps = acc.GetComponentsOfElements([e for _, e in basic])
                for (w, _), row in zip(basic, comps):
                    cids = [ci.elementComponentId for ci in (row.elementComponents or [])]
                    if not cids:
                        continue
                    pv = acc.GetPropertyValuesOfElementComponents(cids, [mpid])
                    try:
                        w["material"] = pv[0].propertyValues[0].propertyValue.value
                    except Exception:
                        pass
        except Exception:
            pass
    return {"walls": walls, "count": len(walls)}
