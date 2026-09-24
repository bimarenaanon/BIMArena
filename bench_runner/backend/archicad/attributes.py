"""Attribute resolvers: building materials, solid line, composite creation.

Replaces the near-identical `resolve_building_materials`/`find_materials`,
`solid_line_ref`/`solid_line`, and the three CreateComposites payloads.
All functions take an `ArchicadClient`.
"""


def load_building_materials(client):
    """Return {name_lower: guid} for every building material in the project."""
    det = client.acc.GetBuildingMaterialAttributes(
        client.acc.GetAttributesByType("BuildingMaterial"))
    return {d.buildingMaterialAttribute.name.lower(): d.buildingMaterialAttribute.attributeId.guid
            for d in det}


# Map a planner material name (by keyword) onto an existing built-in material, which
# already carries a proper cut-fill pattern and colour. Order: most specific first.
_MATERIAL_KEYWORDS = [
    (("reinforced concrete", "concrete"), "concrete"),
    (("brick", "masonry", "clay"), "brick"),
    (("mineral wool", "mineral", "rock wool", "glass wool", "wool"), "mineral"),
    (("eps", "xps", "polystyrene", "plastic"), "plastic"),
    (("insulation", "dämm", "damm"), "insulation"),
    (("gypsum", "plasterboard", "drywall", "board"), "gypsum"),
    (("render", "stucco", "plaster"), "plaster"),
    (("timber", "wood"), "timber"),
    (("air",), "air"),
]


def material_ref(client, name, cache=None, strict=False):
    """Resolve a material name to an EXISTING material's guid. NEVER creates one.

    We only ever pick from materials already in the project (their cut-fill pattern,
    colour and surface are correct). Matching order:
      1. exact name;
      2. two-way substring (e.g. "Brick Masonry" -> built-in "Brick");
      3. keyword -> built-in (e.g. "Mineral Wool Insulation" -> "Insulation - Mineral");
      4. a generic existing material (last resort, with a warning) — SKIPPED with
         `strict=True`, which returns None instead: a caller applying a material the
         user NAMED must fail loudly rather than silently substitute an arbitrary one
         (composite-skin resolution keeps the lenient default: a build-up needs SOME
         material per layer to exist at all).
    """
    by_name = cache if cache is not None else load_building_materials(client)
    nl = name.lower()

    g = by_name.get(nl)                                                  # 1. exact
    if g is None:                                                        # 2. substring
        g = next((v for n, v in by_name.items() if nl in n or (len(n) >= 4 and n in nl)), None)
    if g is None:                                                        # 3. keyword -> built-in
        for kws, target in _MATERIAL_KEYWORDS:
            if any(k in nl for k in kws):
                g = next((v for n, v in by_name.items() if target in n), None)
                if g:
                    break
    if g is not None:
        return g
    if strict:
        return None

    # 4. never create — fall back to a generic existing material
    g = (next((v for n, v in by_name.items() if "generic" in n), None)
         or next((v for n, v in by_name.items() if "structural" in n), None)
         or next(iter(by_name.values()), None))
    print(f"[material] '{name}' not found in project; using a fallback EXISTING material")
    return g


def composite_info(client, name):
    """Resolve an EXISTING composite by name to {"guid", "name", "total_thickness_m"};
    None if not found. Matching: exact (case-insensitive) first, then two-way substring.

    The thickness comes from the SAME resolved attribute — the old callers re-looked it up
    by EXACT name, which broke whenever the substring match resolved a non-exact name
    (e.g. "Ext Wall" -> composite "Ext Wall 365": valid guid, thickness None, and the
    create failed with a misleading "composite has no thickness")."""
    if not name:
        return None
    acc = client.acc
    nl = str(name).strip().lower()
    det = acc.GetCompositeAttributes(acc.GetAttributesByType("Composite"))

    def _info(c):
        return {"guid": c.attributeId.guid, "name": c.name,
                "total_thickness_m": round(c.totalThickness, 4)}

    for d in det:                                          # exact (case-insensitive) first
        if d.compositeAttribute.name.strip().lower() == nl:
            return _info(d.compositeAttribute)
    for d in det:                                          # then two-way substring
        cn = d.compositeAttribute.name.strip().lower()
        if nl in cn or (len(cn) >= 4 and cn in nl):
            return _info(d.compositeAttribute)
    return None


def composite_ref(client, name):
    """Resolve an EXISTING composite's guid by name (case-insensitive). None if not found.
    Lets a wall REUSE a composite the ground floor already built, instead of recreating it."""
    info = composite_info(client, name)
    return info["guid"] if info else None


def solid_line_ref(client):
    """Return the raw guid of a 'solid' line attribute (fallback: first line)."""
    det = client.acc.GetLineAttributes(client.acc.GetAttributesByType("Line"))
    for d in det:
        if "solid" in d.lineAttribute.name.lower():
            return d.lineAttribute.attributeId.guid
    return det[0].lineAttribute.attributeId.guid


def create_composite(client, name, skins, use_with=("Wall",), mats_cache=None):
    """Create (or overwrite) a composite from skins (outer->inner).

    skins : [{"material": str, "type": "Core"|"Finish"|"Other", "thickness": meters}]
    Returns {"guid": ..., "total_thickness_m": ...}.
    """
    if not skins:
        return {"ok": False, "error": "skins required"}
    line = solid_line_ref(client)
    skin_objs = [{"type": s.get("type", "Other"),
                  "buildingMaterialId": client.aid(material_ref(client, s["material"], cache=mats_cache)),
                  "framePen": 1, "thickness": float(s["thickness"])}
                 for s in skins]
    separators = [{"lineTypeId": client.aid(line), "linePen": 1} for _ in range(len(skin_objs) + 1)]
    resp = client.tap("CreateComposites", {
        "compositeDataArray": [{"name": name, "useWith": list(use_with),
                                "skins": skin_objs, "separators": separators}],
        "overwriteExisting": True})
    guid = resp["attributeIds"][0]["attributeId"]["guid"]
    return {"guid": guid, "total_thickness_m": round(sum(float(s["thickness"]) for s in skins), 3)}
