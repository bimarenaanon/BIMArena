"""Toolbox — one object that gathers every Archicad API action in this package.

The package is layered (client / actions / inventory / attributes). That is good for
maintenance but means a caller has to import from half a dozen modules and thread an
`ArchicadClient` through every call. `Toolbox` is a thin FACADE over those layers: it
holds a single connected client and exposes every read / create / attribute / cleanup
operation as a method, so a caller gets the whole action space from one import.

It does NOT re-implement anything — each method delegates to the existing function in
`actions/`, `attributes.py` or `inventory.py`, so there is a single source of truth. Add a
capability once in `actions/*` and expose it here (and mirror it in the Revit add-in's
`Actions.cs` when both applications have it).

    from bench_runner.backend import Toolbox
    tb = Toolbox.connect()                      # Archicad must be open + Tapir enabled

The agent never calls these methods: this is the HARNESS side (open/save, the graded
snapshot, the atomic cases' scripted reference solutions). `run_actions([{action, params,
id?}])` resolves "$id.field" cross-references and remaps guids left stale by a
delete+recreate. UNITS HERE ARE METRES — the grader normalizes to millimetres.
"""
from .client import ArchicadClient, exec_error
from . import attributes as _attr
from . import inventory as _inv
from .actions import zones as _zones
from .actions import walls as _walls
from .actions import slabs as _slabs
from .actions import openings as _openings
from .actions import stairs as _stairs
from .actions import stories as _stories
from .. import swing


def _remap_stale_guids(params, remap):
    """Translate stale element guids in an action's params through the old->new registry
    (see run_actions): the "guid" param and any "guids" list. Case-insensitive; follows
    chains (an element replaced twice maps old -> mid -> new)."""
    if not remap:
        return params

    def follow(g):
        seen = set()
        cur = str(g)
        while cur.upper() in remap and cur.upper() not in seen:
            seen.add(cur.upper())
            cur = remap[cur.upper()]
        return cur if seen else g

    # "slab_guid" (create_slab_opening) and "host" (place_door/place_window) carry element
    # guids too — a slab is delete+recreated by modify_slab level=, so a follow-up hole cut
    # on the old guid must be translated the same way. A readable id in "host" is not a
    # remap key and passes through unchanged.
    for key in ("guid", "slab_guid", "host"):
        if isinstance(params.get(key), str):
            params = {**params, key: follow(params[key])}
    if isinstance(params.get("guids"), list):
        params = {**params, "guids": [follow(g) if isinstance(g, str) else g
                                      for g in params["guids"]]}
    return params


class Toolbox:
    """Single entry point to every Archicad authoring + reading action."""

    def __init__(self, client):
        self.client = client

    @classmethod
    def connect(cls, target=None):
        """Return a ready toolbox for the active BIM target.

        target (or `config.bim_target()` — set by `--target` / $BIM_TARGET) selects the backend:
        "archicad" (default) → this Tapir-backed Toolbox; "revit" → `RevitToolbox`, which forwards
        the SAME action surface (`run_actions`, reads, snapshot) over HTTP to the Revit add-in, so the
        planner/actor/verifier are unchanged. Local imports keep the Revit deps optional + avoid a
        circular import.
        """
        from ..settings import bim_target
        if (target or bim_target()) == "revit":
            from ..revit.toolbox import RevitToolbox
            return RevitToolbox.connect()
        return cls(ArchicadClient.connect())

    # ----------------------------------------------------------------- raw access
    def tap(self, cmd, params=None):
        """Call a raw Tapir add-on command (escape hatch for anything not wrapped).

        Args:
            cmd (str): Tapir command name, e.g. "CreateWalls", "GetStories".
            params (dict | None): the command's JSON payload; {} when omitted.
        Returns:
            dict: the raw Tapir response (shape depends on the command).
        """
        return self.client.tap(cmd, params)

    # ============================================================ READ / INVENTORY
    def all_elements(self):
        """Complete project inventory via Tapir (NOT view-filtered, unlike the official API).

        Args: none.
        Returns:
            list[tuple]: (element, detail) pairs for every element in the project.
                `element` carries elementId.guid; `detail` carries type + geometry.
        """
        return self.client.all_elements()

    def list_walls_with_composite(self, pairs=None):
        """List every wall with its full composite skin stack (material/thickness/type).

        Args:
            pairs: optional already-fetched all_elements() result to reuse (saves the
                2-round-trip full inventory when the caller just did one).
        Returns:
            dict: {"walls": [{"id","begin","end","composite_name",
                   "skins_outer_to_inner": [{"material","thickness_m","type"}]}], "count": n}.
        """
        return _inv.list_walls_with_composite(self.client, pairs=pairs)

    def collisions(self, types_a, types_b=None, pairs=None):
        """3D body collisions between two groups of element types (Tapir GetCollisions).

        Args:
            types_a (str | list[str]): element type(s) for the first group, e.g. "Wall"
                or ["Wall", "Slab"].
            types_b (str | list[str] | None): the second group; defaults to types_a
                (intra-group check, e.g. wall-vs-wall).
            pairs: optional already-fetched all_elements() result to build the groups from.
        Returns:
            list[dict]: [{"guid_a","guid_b"}] for every colliding pair (deduped, no self).

        The groups are built from the FULL Tapir inventory — NOT the official
        GetElementsByType, which is filtered by the current view/layer visibility and would
        silently check almost nothing (a false "no clashes") whenever a 3D window, a filtered
        view, or hidden layers are active.
        """
        if pairs is None:
            pairs = self.client.all_elements()

        def group(types):
            wanted = {types} if isinstance(types, str) else set(types)
            return [{"elementId": {"guid": e["elementId"]["guid"]}}
                    for e, d in pairs if d.get("type") in wanted]

        g1 = group(types_a)
        g2 = group(types_b) if types_b is not None else g1
        if not g1 or not g2:
            return []
        resp = self.client.tap("GetCollisions", {"elementsGroup1": g1, "elementsGroup2": g2})
        seen, out = set(), []
        for c in resp.get("collisions", []):
            a, b = c["elementId1"]["guid"].upper(), c["elementId2"]["guid"].upper()
            if a == b or not c.get("hasBodyCollision"):
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            out.append({"guid_a": a, "guid_b": b})
        return out

    def get_stories(self):
        """Read the project's story (floor) structure, including each story's elevation.

        Args: none.
        Returns:
            dict: {"ok", "firstStory", "lastStory", "actStory" (current 2D story index),
                   "skipNullFloor", "stories": [{"index","floorId","dispOnSections",
                   "level" (elevation in m), "name"}]}.
        """
        return _stories.get_stories(self.client)

    def bboxes_2d(self, guids):
        """2D bounding box per element guid: {guid: {"xMin","yMin","xMax","yMax"}} (meters)."""
        from uuid import UUID
        act = self.client.act
        items = [act.ElementIdArrayItem(act.ElementId(UUID(str(g)))) for g in guids]
        out = {}
        for g, b in zip(guids, self.client.acc.Get2DBoundingBoxes(items)):
            bb = getattr(b, "boundingBox2D", None)
            if bb is not None:
                out[g] = {"xMin": bb.xMin, "yMin": bb.yMin, "xMax": bb.xMax, "yMax": bb.yMax}
        return out

    def composite_names(self, element_type, pairs=None):
        """{element guid (upper): composite name} for all elements of a type.

        Reads the built-in Construction_CompositeName property (works for walls, slabs…).
        Elements come from the FULL Tapir inventory (`pairs` — pass an already-fetched
        all_elements() to reuse it), not the view-filtered official GetElementsByType.
        """
        acc = self.client.acc
        if pairs is None:
            pairs = self.client.all_elements()
        els = [e for e, d in pairs if d.get("type") == element_type]
        uid = [u for u in acc.GetAllPropertyNames()
               if type(u).__name__ == "BuiltInPropertyUserId"
               and u.nonLocalizedName == "Construction_CompositeName"]
        if not els or not uid:
            return {}
        pid = acc.GetPropertyIds(uid)[0].propertyId
        out = {}
        for el, row in zip(els, acc.GetPropertyValuesOfElements(els, [pid])):
            try:                                     # Tapir elements are dicts, not typed objects
                out[el["elementId"]["guid"].upper()] = row.propertyValues[0].propertyValue.value
            except Exception:
                pass
        return out

    # ==================================================================== CREATE
    # -- zones --
    def create_zone(self, name, number, polygon_xy, stamp_xy=None, floor_index=0):
        """Create a zone (room) from a closed-ish polygon.

        Args:
            name (str): zone name (shown in the zone stamp).
            number (str | int): zone number / id string.
            polygon_xy (list[tuple]): [(x, y), ...] in meters, >= 3 vertices. You do NOT
                need to repeat the first point — closing is handled.
            stamp_xy (tuple | None): (x, y) of the zone stamp. None = polygon centroid.
            floor_index (int): story index the zone sits on. Default 0 (ground).
        Returns:
            dict: {"ok": True, "guid", "name"} or {"ok": False, "error"}.
        """
        return _zones.create_zone(self.client, name, number, polygon_xy,
                                  stamp_xy=stamp_xy, floor_index=floor_index)

    def modify_zone(self, guid, polygon_xy=None, name=None, number=None, floor_index=None):
        """Modify an existing zone by guid (Tapir has no ModifyZones -> delete + recreate).

        Reads the current name/number/floor/outline; any field you pass overrides it.
        Args:
            guid (str): the zone's elementId.guid.
            polygon_xy (list | None): new boundary [(x, y), ...].
            name / number (str | None): new name / number.
            floor_index (int | None): new storey index.
        Returns:
            dict: the new zone's create result ("replaced": True) or {"ok": False, "error"}.
        """
        return _zones.modify_zone(self.client, guid, polygon_xy=polygon_xy, name=name,
                                  number=number, floor_index=floor_index)

    # -- walls --
    def create_wall(self, begin, end, height=None, thickness=None, z=0.0, material=None,
                    composite_name=None, composite_guid=None, total_thickness=None,
                    reference=None):
        """ONE straight wall, composite OR basic — the merged `create_wall` tool (2026-08-03,
        replacing the create_walls/create_composite_wall pair in the agent's action space;
        those methods stay for older callers and the bench tooling).

        Structure by params: composite_name/composite_guid -> composite; material/thickness ->
        basic single-material; none -> basic with application defaults. `reference` says WHICH
        line begin/end are (outside | center | inside — see `_walls.REFERENCE_LINES`). Always
        returns {"ok", "guid"/"error"} — one wall, one referenceable guid.
        """
        kw = {"thickness": thickness, "z": z, "material": material,
              "composite_name": composite_name, "composite_guid": composite_guid,
              "total_thickness": total_thickness}
        if height is not None:
            kw["height"] = height
        if reference is not None:
            ref = _walls.REFERENCE_LINES.get(str(reference).strip().lower())
            if ref is None:
                return {"ok": False, "error": f"unknown reference {reference!r} — use one of "
                                              f"{', '.join(sorted(_walls.REFERENCE_LINES))}"}
            kw["reference_line"] = ref
        res = _walls.create_wall(self.client, begin, end, **kw)
        if height is not None and res.get("ok") and res.get("guid"):
            # Tapir's CreateWalls ACCEPTS `height` and IGNORES it — the wall comes out at the
            # storey height (probed 2026-08-14 on add-on 1.5.3: height 2.4 in a 3.2 m storey
            # built a 3.2 m wall). ModifyWalls does honour it, so an explicitly requested
            # height is re-applied here. Only when the caller ASKED for one: a create with no
            # height keeps the application's storey-linked default, which is what it means.
            fix = _walls.modify_wall(self.client, res["guid"], height=height)
            if not fix.get("ok"):
                res["height_warning"] = fix.get("error", "could not set the wall height")
        return res

    def list_composites(self):
        """Every composite attribute in the project: [{name, total_thickness_m,
        skins_outer_to_inner}]. Use it to REUSE existing composites instead of duplicating."""
        return _inv.list_composites(self.client)

    # -- slabs --
    def create_composite_slab(self, name=None, skins=None, polygon_xy=None, level=0.0,
                              composite_name=None, reference_plane=None):
        """Create a slab with a composite: a freshly-built one (name + skins) OR an
        EXISTING one reused by name (composite_name) — two Tapir steps either way.

        Args:
            name (str): name for the NEW composite attribute (with `skins`).
            skins (list[dict]): layers outer->inner, each
                {"material": str, "type": "Core"|"Finish"|"Other", "thickness": m}.
                `material` is resolved to an EXISTING building material (never created).
            composite_name (str): REUSE an existing composite by name instead (the BUILD
                `slabs` task's route — no new composite is authored).
            polygon_xy (list[tuple]): [(x, y), ...] slab outline in meters.
            level (float): slab top/base level (m). Default 0.0.
            reference_plane (str | None): which slab surface `level` pins — "Top" |
                "Bottom" | "CoreTop" | "CoreBottom". CREATE-time only (the modify path
                cannot change it); None -> application default.
        Returns:
            dict: {"ok", "slab_guid", "composite_guid", "total_thickness_m"} or error.
        """
        return _slabs.create_composite_slab(self.client, name, skins, polygon_xy, level=level,
                                            composite_name=composite_name,
                                            reference_plane=reference_plane)

    def modify_slab(self, guid, thickness=None, composite_guid=None, composite_name=None,
                    polygon_xy=None, level=None):
        """Modify an existing slab by guid (Tapir ModifySlabs). Only given fields change.

        `level` (ABSOLUTE elevation, m) cannot be changed in place — ModifySlabs' zCoordinate
        does not move a slab — so a level change runs the established delete+recreate route
        (same contract as modify_zone/modify_stair): the old slab's outline and composite are
        read and VALIDATED first, then delete + create_composite_slab at the new level. The
        slab gets a NEW guid ("replaced" carries the old one); an omitted polygon/composite
        keeps the old value. Only a COMPOSITE slab can be re-levelled this way (a basic slab
        has no composite to re-create with — fails loudly, nothing deleted).
        Args:
            guid (str): the slab's elementId.guid.
            thickness (float | None): new thickness (m).
            composite_guid (str | None): assign a composite (sets structureType=Composite).
            composite_name (str | None): assign an EXISTING composite by NAME (resolved,
                never created) — mutually exclusive with composite_guid.
            polygon_xy (list | None): new outline [(x, y), ...].
            level (float | None): new ABSOLUTE elevation (m) — delete+recreate (see above).
        Returns:
            dict: {"ok": True, "guid"} or, for a level change,
            {"ok": True, "slab_guid", "replaced", ...} — or {"ok": False, "error"}.
        """
        if level is None:
            return _slabs.modify_slab(self.client, guid, thickness=thickness,
                                      composite_guid=composite_guid,
                                      composite_name=composite_name, polygon_xy=polygon_xy)
        # ---- level change = delete + recreate (everything validated BEFORE the delete) ----
        info = self._elem(guid)
        if not info or info[1].get("type") != "Slab":
            return {"ok": False, "error": f"modify_slab: no slab {guid!r} (nothing deleted)"}
        old_guid, d = info
        det = d.get("details") or {}
        # A `level` equal to the slab's CURRENT absolute elevation is a no-op: agents echo
        # observed values back as params ("same value = unchanged"), and rebuilding the slab
        # for that breaks the guid an "edit this existing slab" task must keep. Detail level
        # is RELATIVE to the home storey, so compare against storey elevation + offset.
        story = _stories.story_level(self.client, d.get("floorIndex"))
        if story is not None and abs(story + (det.get("level") or 0.0) - float(level)) < 5e-4:
            return _slabs.modify_slab(self.client, guid, thickness=thickness,
                                      composite_guid=composite_guid,
                                      composite_name=composite_name, polygon_xy=polygon_xy)
        outline = polygon_xy
        if outline is None:
            outline = [[p.get("x"), p.get("y")] for p in (det.get("polygonOutline") or [])
                       if isinstance(p, dict)]
        if len(outline or []) < 3:
            return {"ok": False, "error": "modify_slab: the slab's outline could not be read "
                    "and none was given (nothing deleted)"}
        comp_name = composite_name
        if comp_name is None and composite_guid is None:
            comp_name = self.composite_names("Slab").get(str(old_guid).upper())
        if not comp_name:
            return {"ok": False, "error": "modify_slab: a level change re-creates the slab and "
                    "needs its composite, but this slab reports none (a BASIC slab cannot be "
                    "re-levelled this way — nothing deleted)"}
        deleted = self.delete_element(old_guid)
        if not deleted.get("ok"):
            return {"ok": False, "error": f"modify_slab: delete failed — {deleted.get('error')}"}
        res = _slabs.create_composite_slab(self.client, polygon_xy=outline,
                                           level=float(level), composite_name=comp_name)
        if not res.get("ok"):
            res["error"] = (f"modify_slab: the OLD slab was deleted but the re-create at the "
                            f"new level FAILED — {res.get('error')} (outline {len(outline)} "
                            f"pts, composite {comp_name!r})")
            return res
        res["replaced"] = str(old_guid)
        if res.get("slab_guid"):
            # harmonize the replace contract ("replaced" + "guid"): run_actions records the
            # old->new remap only off a "guid" key — without it every later corrective call
            # still holding the OLD slab guid fails with a spurious "no slab".
            res["guid"] = res["slab_guid"]
        # The re-created slab homes on the storey whose band holds the requested ABSOLUTE
        # level (probed 2026-07-28: Archicad homes creations BY ELEVATION, not on the active
        # storey) — so the floor tag comes out right by itself. Never re-home it afterwards:
        # SetDetailsOfElements keeps the RELATIVE level, dragging the slab by the storey delta.
        return res

    def create_slab_opening(self, slab_guid, base_xy, width, height, z=0.0):
        """Cut a rectangular hole through a slab (e.g. a stairwell void — Archicad does NOT
        auto-cut a slab for a stair).

        Args:
            slab_guid (str): the host slab's guid (e.g. from create_composite_slab's slab_guid).
            base_xy (tuple): [x, y] the hole's MIN corner in the slab plane (m).
            width (float): hole extent along X (m).
            height (float): hole extent along Y (m).
            z (float): the slab's level (m).
        Returns:
            dict: {"ok": True, "guid"} or {"ok": False, "error"}.
        """
        return _slabs.create_slab_opening(self.client, slab_guid, base_xy, width, height, z=z)

    # -- stairs --
    def create_stair(self, baseline_xy, z=0.0, total_height=None, flight_width=1.0,
                     step_num=None, riser_height=None, tread_depth=None):
        """Create a stair from a baseline polyline (needs Tapir >= 1.5.0; else error 4010).

        Args:
            baseline_xy (list[tuple]): [(x, y), ...] in meters. 2 points ONLY (a straight
                run) — Tapir 1.5.2 FAILS on any multi-point baseline despite its schema
                claiming L/U support (probed); fake an L/U stair as straight runs + landings.
            z (float): absolute elevation of the stair base (m). Default 0.0.
            total_height (float | None): floor-to-floor rise (m). None -> config.WALL_HEIGHT.
            flight_width (float): width of the flight (m). Default 1.0.
            step_num (int | None): number of risers (steps). None -> Archicad derives it.
            riser_height (float | None): height of each riser (m). None -> derived.
            tread_depth (float | None): going/depth of each tread (m). None -> derived.
        Returns:
            dict: {"ok": True, "guid"} or {"ok": False, "error"}.
        """
        kw = {"z": z, "flight_width": flight_width, "step_num": step_num,
              "riser_height": riser_height, "tread_depth": tread_depth}
        if total_height is not None:
            kw["total_height"] = total_height
        return _stairs.create_stair(self.client, baseline_xy, **kw)

    # ============================================================ STORIES (FLOORS)
    def set_stories(self, stories):
        """Replace the WHOLE story (floor) stack — this defines how many floors exist.

        SetStories is whole-stack: the list you pass becomes the project's stories, in
        order, bottom -> top.

        Args:
            stories (list[dict]): ordered bottom->top, each
                {"name": str, "level": float (elevation in m),
                 "dispOnSections": bool (show level line on sections; default True)}.
        Returns:
            dict: {"ok": True, "stories": [...normalised...]} or {"ok": False, "error"}.
        """
        return _stories.set_stories(self.client, stories)

    def set_active_story(self, story):
        """Open a storey's floor plan, making it the ACTIVE storey.

        Args:
            story (str|int): the storey's NAME, or its bottom-up index.
        Returns:
            dict: {"ok": True, "story": {index, name, level}, "active": idx} or
                  {"ok": False, "error"}.
        """
        return _stories.set_active_story(self.client, story)

    # ================================================================ ATTRIBUTES
    def create_composite(self, name, skins, use_with=("Wall",), mats_cache=None):
        """Create (or overwrite) a composite (multi-layer assembly) attribute.

        Args:
            name (str): composite name (overwrites an existing one with the same name).
            skins (list[dict]): layers outer->inner, each
                {"material": str, "type": "Core"|"Finish"|"Other", "thickness": m}.
            use_with (tuple[str]): element types it may apply to, e.g. ("Wall",), ("Slab",).
            mats_cache (dict | None): optional material name->guid cache (see material_ref).
        Returns:
            dict: {"guid", "total_thickness_m"} or {"ok": False, "error"}.
        """
        return _attr.create_composite(self.client, name, skins,
                                     use_with=use_with, mats_cache=mats_cache)

    # ---- modify / delete by guid; place openings on a wall (by wall id OR guid) ----
    # ================================================= OPENINGS / ELEMENT EDITS
    def _elem(self, element_ref):
        """Resolve an element reference -> (guid, detail) (cached per toolbox instance).

        Used for opening HOSTS (walls). `element_ref` may be the readable id (e.g.
        "SW - 043") OR the raw guid — the planner/verifier use either, so we index both.
        """
        if not hasattr(self, "_emap"):
            self._emap = {}
            for e, d in self.all_elements():
                guid = e["elementId"]["guid"]
                entry = (guid, d)
                rid = d.get("id")
                if rid:
                    if rid not in self._emap:
                        self._emap[rid] = entry
                    elif self._emap[rid] is not None and self._emap[rid][0] != guid:
                        # readable ids REPEAT across storeys (e.g. after a storey copy) —
                        # an ambiguous id must fail LOUDLY ("no host wall"), not resolve to
                        # an arbitrary wall and silently host the opening on the wrong floor.
                        self._emap[rid] = None
                self._emap[guid] = entry
                self._emap[guid.upper()] = entry
        hit = (self._emap.get(element_ref)
               or self._emap.get(str(element_ref).upper()))
        if hit is None and not hasattr(self, "_elem_retrying"):
            # The cache is built on FIRST use and a batch may create elements after that
            # (e.g. [create wall A, place_door A, create wall B, place_door B]) — a miss on a
            # ref created later in the same batch would otherwise fail (or, worse, let a
            # modify_* return ok while silently dropping its center change). Rebuild once
            # from the live model and retry; a genuinely unknown ref still returns None
            # (and KEEPS the rebuilt cache — dropping it would force a full 2-round-trip
            # rebuild on every later lookup).
            del self._emap
            self._elem_retrying = True
            try:
                hit = self._elem(element_ref)
            finally:
                del self._elem_retrying
        return hit

    def favorites(self, element_type):
        """Names of saved favorites for an element type, e.g. favorites("Door").

        A door/window favorite bundles a library part (the 'type') + settings; pass its
        name as `favorite` to place_door/place_window to choose that door/window type.
        """
        try:
            return self.tap("GetFavoritesByType", {"elementType": element_type}).get("favorites") or []
        except Exception:
            return []

    def _resolve_favorite(self, element_type, name):
        """Resolve a favorite NAME tolerantly against the live favorites list: exact match
        (case-insensitive) first, then a UNIQUE containment match either way. Returns
        (canonical_name, None) or (None, error_dict) — the error LISTS the available
        favorites, so a repair/verify round can pick a real one instead of re-guessing
        blindly against an opaque backend failure."""
        if not name:
            return None, None
        try:
            favs = self.tap("GetFavoritesByType",
                            {"elementType": element_type}).get("favorites") or []
        except Exception as e:
            # NOT the favorites() shortcut: its swallowed-to-[] failure would misreport a
            # transient Tapir error (4001 busy) as "unknown favorite ...; available: []",
            # and the repair round would DROP the favorite instead of retrying.
            return None, {"ok": False,
                          "error": f"could not read the {element_type.lower()} favorites "
                                   f"list ({type(e).__name__}: {e}) — likely transient "
                                   f"(Archicad busy); RETRY with the same favorite"}
        low = str(name).strip().lower()
        exact = [f for f in favs if str(f).strip().lower() == low]
        if exact:
            return exact[0], None
        part = [f for f in favs if low in str(f).lower() or str(f).lower() in low]
        if len(part) == 1:
            return part[0], None
        detail = f" (ambiguous between {part})" if part else ""
        return None, {"ok": False,
                      "error": f"unknown {element_type.lower()} favorite {name!r}{detail}; "
                               f"available {element_type.lower()} favorites: {favs}"}

    def place_door(self, host, center, width, height, sill=0.0,
                   reflected=None, refSide=None, oSide=None, favorite=None,
                   opens_toward=None, hinge_toward=None):
        """Create a door on wall `host` (its id) at the [x,y] centre point.

        Opening direction — PREFER the geometric target points: `opens_toward` ([x,y] a point
        on the side the leaf swings toward) and `hinge_toward` ([x,y] a point at/near the
        doorway end the hinge is on) are converted DETERMINISTICALLY to Tapir's booleans and
        beat any raw reflected/oSide passed alongside. (reflected mirrors the hinge L<->R,
        oSide flips which way it opens, refSide is the wall reference side.)
        `favorite` picks a saved door type (see favorites()).
        """
        favorite, err = self._resolve_favorite("Door", favorite)
        if err:
            return err
        return self._place_opening(_openings.create_door, host, center, width, height, sill,
                                   opens_toward=opens_toward, hinge_toward=hinge_toward,
                                   reflected=reflected, refSide=refSide, oSide=oSide,
                                   favorite_name=favorite)

    def place_window(self, host, center, width, height, sill=0.9,
                     reflected=None, refSide=None, oSide=None, favorite=None,
                     faces_toward=None):
        """Create a window on wall `host` (its id) at the [x,y] centre point. `favorite` picks
        a type. `faces_toward` ([x,y] a point on the EXTERIOR side) sets the facing
        geometrically and beats a raw oSide."""
        favorite, err = self._resolve_favorite("Window", favorite)
        if err:
            return err
        return self._place_opening(_openings.create_window, host, center, width, height, sill,
                                   faces_toward=faces_toward,
                                   reflected=reflected, refSide=refSide, oSide=oSide,
                                   favorite_name=favorite)

    def _offset_from_center(self, opening_guid, center):
        """Convert an [x,y] (or {x,y}) centre point to the along-wall offset of an existing
        opening's HOST wall (so a modify can take a point like place_* does).

        Returns (offset_m, None) on success, or (None, reason) when the offset cannot be
        derived / the centre projects past the wall's end — the caller MUST fail loudly on
        (None, reason): passing a silent None into the modify would send an empty change
        that returns ok while the opening never moved."""
        import math
        info = self._elem(opening_guid)
        if not info:
            return None, f"opening {opening_guid!r} not found"
        _, d = info
        owner = ((d.get("details") or {}).get("ownerElementId") or {}).get("guid")
        wall = self._elem(owner) if owner else None
        if not wall:
            return None, "the opening's host wall cannot be resolved"
        wdet = (wall[1].get("details") or {})
        b, e = wdet.get("begCoordinate"), wdet.get("endCoordinate")
        if not b or not e:
            return None, "the host wall has no begin/end geometry"
        cx, cy = (center["x"], center["y"]) if isinstance(center, dict) else (center[0], center[1])
        dx, dy = e["x"] - b["x"], e["y"] - b["y"]
        length = math.hypot(dx, dy) or 1.0
        offset = round(((cx - b["x"]) * dx + (cy - b["y"]) * dy) / length, 3)
        if round(offset - length, 3) > 0:             # same guard as the place_* path — a
            # centre past the wall's end means a wrong wall / wrong point, not a valid move
            return None, (f"centre projects {round(offset - length, 3)} m PAST the host "
                          f"wall's end ({round(length, 3)} m long)")
        return offset, None

    # ---- swing geometry: TARGET POINTS -> Tapir booleans (deterministic; no LLM guessing).
    # The convention mirrors (is the exact inverse of) the grader's calibrated read
    # (bench_runner/verifier/geometry.py): `oSide` True = the leaf opens toward the LEFT side
    # of the wall's beg->end direction; `reflected` True = the hinge sits at the END-side end
    # of the doorway. `refSide` affects neither and is left untouched.
    # The conversion itself is CROSS-TARGET geometry and lives in `backend/swing.py` — the Revit
    # backend needs the identical mapping, and a second implementation there would drift from
    # this one (and from the grader it is calibrated against).
    _swing_bools = staticmethod(swing.swing_bools)

    def _opening_swing_geom(self, opening_guid, center=None):
        """(wall_beg, wall_end, cx, cy) for an EXISTING opening — the geometry _swing_bools
        needs. `center` (the intended [x,y]) is used when given; else the opening's CURRENT
        along-wall offset locates it. Returns (None, reason) when unresolvable."""
        info = self._elem(opening_guid)
        if not info:
            return None, f"opening {opening_guid!r} not found"
        det = (info[1].get("details") or {})
        owner = (det.get("ownerElementId") or {}).get("guid")
        wall = self._elem(owner) if owner else None
        if not wall:
            return None, "the opening's host wall cannot be resolved"
        wdet = wall[1].get("details") or {}
        b, e = wdet.get("begCoordinate"), wdet.get("endCoordinate")
        if not b or not e:
            return None, "the host wall has no begin/end geometry"
        if center is not None:
            cx, cy = (center["x"], center["y"]) if isinstance(center, dict) else (center[0], center[1])
        else:
            import math
            off = det.get("centerOffset")
            if off is None:
                return None, "the opening reports no centerOffset"
            dx, dy = e["x"] - b["x"], e["y"] - b["y"]
            L = math.hypot(dx, dy) or 1.0
            cx, cy = b["x"] + dx / L * float(off), b["y"] + dy / L * float(off)
        return (b, e, cx, cy), None

    def _swing_from_points(self, guid, center, opens_toward=None, hinge_toward=None,
                           faces_toward=None):
        """Resolve an existing opening's wall + centre and derive the swing booleans from the
        given target points. Returns (bools_dict, None) or (None, error_reason)."""
        if opens_toward is None and hinge_toward is None and faces_toward is None:
            return {}, None
        geom, err = self._opening_swing_geom(guid, center)
        if geom is None:
            return None, err
        b, e, cx, cy = geom
        return self._swing_bools(b, e, cx, cy, opens_toward=opens_toward,
                                 hinge_toward=hinge_toward, faces_toward=faces_toward), None

    def modify_door(self, guid, width=None, height=None, sill=None, center_offset=None,
                    center=None, reflected=None, refSide=None, oSide=None,
                    opens_toward=None, hinge_toward=None):
        """Modify an existing door by guid (Tapir ModifyDoors). Only given fields change.
        `center` ([x,y], like place_door) is converted to center_offset via the host wall.
        `opens_toward` / `hinge_toward` ([x,y] target points) set the swing GEOMETRICALLY —
        they beat any raw reflected/oSide booleans passed alongside."""
        sw, err = self._swing_from_points(guid, center, opens_toward=opens_toward,
                                          hinge_toward=hinge_toward)
        if sw is None:
            return {"ok": False, "error": f"modify_door: cannot derive the swing from the "
                    f"given points — {err} (nothing modified)"}
        oSide = sw.get("oSide", oSide)
        reflected = sw.get("reflected", reflected)
        if center is not None and center_offset is None:
            center_offset, err = self._offset_from_center(guid, center)
            if center_offset is None:
                return {"ok": False, "error": f"modify_door: cannot convert center to an "
                        f"along-wall offset — {err} (nothing modified)"}
        return _openings.modify_door(self.client, guid, width=width, height=height, sill=sill,
                                    center_offset=center_offset, reflected=reflected,
                                    refSide=refSide, oSide=oSide)

    def modify_window(self, guid, width=None, height=None, sill=None, center_offset=None,
                      center=None, reflected=None, refSide=None, oSide=None, faces_toward=None):
        """Modify an existing window by guid (Tapir ModifyWindows). Only given fields change.
        `center` ([x,y], like place_window) is converted to center_offset via the host wall.
        `faces_toward` ([x,y] a point on the EXTERIOR side) sets the facing geometrically."""
        sw, err = self._swing_from_points(guid, center, faces_toward=faces_toward)
        if sw is None:
            return {"ok": False, "error": f"modify_window: cannot derive the facing from the "
                    f"given point — {err} (nothing modified)"}
        oSide = sw.get("oSide", oSide)
        if center is not None and center_offset is None:
            center_offset, err = self._offset_from_center(guid, center)
            if center_offset is None:
                return {"ok": False, "error": f"modify_window: cannot convert center to an "
                        f"along-wall offset — {err} (nothing modified)"}
        return _openings.modify_window(self.client, guid, width=width, height=height, sill=sill,
                                      center_offset=center_offset, reflected=reflected,
                                      refSide=refSide, oSide=oSide)

    def _place_opening(self, fn, host, center, width, height, sill,
                       opens_toward=None, hinge_toward=None, faces_toward=None, **extra):
        import math
        info = self._elem(host)
        if not info:
            return {"ok": False, "error": f"no host wall {host!r}"}
        guid, d = info
        det = d.get("details") or {}
        b, e = det.get("begCoordinate"), det.get("endCoordinate")
        if not b or not e:
            return {"ok": False, "error": f"host wall {host!r} has no geometry"}
        cx, cy = (center["x"], center["y"]) if isinstance(center, dict) else (center[0], center[1])
        dx, dy = e["x"] - b["x"], e["y"] - b["y"]
        length = math.hypot(dx, dy) or 1.0
        offset = ((cx - b["x"]) * dx + (cy - b["y"]) * dy) / length   # along-wall, from begin
        if round(offset - length, 3) > 0:            # past the wall's END — wrong wall / centre.
            # 3-dp rounding mirrors the begin-side check in actions/openings.py: a centre
            # intended exactly AT the wall end may overshoot by fractions of a mm after the
            # actor's mm->m rounding — that must not hard-fail a legit end placement.
            return {"ok": False, "error": f"opening centre projects {round(offset - length, 3)} m "
                    f"PAST the host wall's end ({round(length, 3)} m long) — wrong host wall or "
                    "wrong centre point"}            # (< 0 is rejected in actions/openings.py)
        # geometric swing: opens_toward/hinge_toward/faces_toward target points beat any raw
        # reflected/oSide booleans riding in `extra` (the points are unambiguous; the booleans
        # are the LLM's guess at the same thing).
        extra.update(self._swing_bools(b, e, cx, cy, opens_toward=opens_toward,
                                       hinge_toward=hinge_toward, faces_toward=faces_toward))
        return fn(self.client, guid, offset, width, height, sill=sill, **extra)

    def modify_wall(self, guid, begin=None, end=None, height=None, thickness=None,
                    composite_guid=None, composite_name=None, building_material=None):
        """Modify an existing wall by its guid (Tapir ModifyWalls). Only given fields change.

        `composite_name` switches the wall to an EXISTING composite resolved by NAME (the
        modify twin of create_wall's composite_name); `building_material` (a name,
        resolved to an EXISTING material) switches it to a BASIC single-material structure.
        composite_guid / composite_name / building_material are mutually exclusive.
        """
        return _walls.modify_wall(self.client, guid, begin=begin, end=end, height=height,
                                 thickness=thickness, composite_guid=composite_guid,
                                 composite_name=composite_name,
                                 building_material=building_material)

    def flip_wall(self, guid):
        """Flip which side of the reference line a wall's body/layers occupy, by SWAPPING its
        begin and end coordinates (Tapir ModifyWalls). The reference line stays put; the
        element keeps its guid. This is the documented flip route — Tapir exposes no
        flip/mirror property on walls (probed), so a flip IS the endpoint swap.
        """
        info = self._elem(guid)
        if not info:
            return {"ok": False, "error": f"no wall {guid!r} in the live model"}
        det = (info[1].get("details") or {})
        b, e = det.get("begCoordinate"), det.get("endCoordinate")
        if not b or not e:
            return {"ok": False, "error": f"element {guid!r} has no begin/end geometry — "
                                          "not a straight wall"}
        return _walls.modify_wall(self.client, info[0],
                                  begin=(e["x"], e["y"]), end=(b["x"], b["y"]))

    def replace_door(self, guid, favorite=None, width=None, height=None, sill=None,
                     reflected=None, refSide=None, oSide=None,
                     opens_toward=None, hinge_toward=None):
        """Change an existing door's TYPE (library part). Tapir cannot swap a placed
        opening's favorite, so this REPLACES it: delete + re-create at the SAME offset on
        the SAME host wall (validated before the delete). Omitted width/height/sill keep
        the current values; the door gets a NEW guid ("replaced" carries the old one).
        `opens_toward` / `hinge_toward` ([x,y] target points) set the new door's swing
        geometrically (computed BEFORE the delete, from the current host wall + offset).
        """
        favorite, err = self._resolve_favorite("Door", favorite)
        if err:
            return err
        sw, gerr = self._swing_from_points(guid, None, opens_toward=opens_toward,
                                           hinge_toward=hinge_toward)
        if sw is None:
            return {"ok": False, "error": f"replace_door: cannot derive the swing from the "
                    f"given points — {gerr} (nothing replaced)"}
        return _openings.replace_door(self.client, guid, favorite_name=favorite, width=width,
                                      height=height, sill=sill,
                                      reflected=sw.get("reflected", reflected),
                                      refSide=refSide, oSide=sw.get("oSide", oSide))

    def replace_window(self, guid, favorite=None, width=None, height=None, sill=None,
                       reflected=None, refSide=None, oSide=None, faces_toward=None):
        """Change an existing window's TYPE (library part) — see replace_door. `faces_toward`
        ([x,y] a point on the EXTERIOR side) sets the new window's facing geometrically."""
        favorite, err = self._resolve_favorite("Window", favorite)
        if err:
            return err
        sw, gerr = self._swing_from_points(guid, None, faces_toward=faces_toward)
        if sw is None:
            return {"ok": False, "error": f"replace_window: cannot derive the facing from the "
                    f"given point — {gerr} (nothing replaced)"}
        return _openings.replace_window(self.client, guid, favorite_name=favorite, width=width,
                                        height=height, sill=sill, reflected=reflected,
                                        refSide=refSide, oSide=sw.get("oSide", oSide))

    def delete_element(self, guid):
        """Delete one element by its guid (Tapir DeleteElements)."""
        try:
            resp = self.client.tap("DeleteElements",
                                   {"elements": [{"elementId": {"guid": str(guid)}}]})
        except Exception as e:
            return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
        # DeleteElements reports failure via executionResults with NO exception — a false
        # "deleted" here makes the verifier believe an element is gone that is still built.
        err = exec_error(resp, "delete failed")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "deleted": str(guid)}

    # =============================================================== EXECUTION
    def run_actions(self, actions, results=None):
        """Execute a list of {action, params, id?} against this toolbox, in order.

        A param value of the form "$<id>.<field>" is replaced by the result that the
        earlier action with that id returned (e.g. "$comp1.guid"). Each action's result
        is recorded under its id. Returns [{action, id, result}] for every action.

        `results` (optional) is an EXTERNAL id -> result map to record into and resolve
        from, so cross-references survive ACROSS batches: the agent executes a few calls
        per round, and an action created in an earlier round must stay referenceable.
        """
        results = {} if results is None else results
        out = []
        # delete+recreate modifies (modify_zone, modify_slab level, replace_door/
        # replace_window) leave the element under a NEW guid; a later corrective round
        # routinely still holds the OLD one (its plan was reasoned over an earlier
        # snapshot) and would fail with a spurious "no element". Keep an old->new registry
        # for the LIFE of this Toolbox (one per run) and translate incoming guids.
        remap = getattr(self, "_guid_remap", None)
        if remap is None:
            remap = self._guid_remap = {}
        for a in actions:
            name = a.get("action")
            fn = getattr(self, name, None)
            resolved = a.get("params") or {}
            if not callable(fn):
                res = {"ok": False, "error": f"unknown action {name!r}"}
            else:
                try:
                    # $ref resolution INSIDE the try: a bad "$id.field" must fail THIS action,
                    # not abort the whole batch.
                    resolved = self._resolve_refs(a.get("params") or {}, results)
                    resolved = _remap_stale_guids(resolved, remap)
                    res = fn(**resolved)
                except Exception as e:
                    res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            # register the remap from the RESOLVED params: a "$step.guid" reference (or an
            # already-remapped guid) in the raw call would otherwise register a useless key
            # and lose the real old->new mapping.
            old = resolved.get("guid") if isinstance(resolved, dict) else None
            if isinstance(res, dict) and res.get("replaced") is not None and res.get("guid") \
                    and old and str(old).upper() != str(res["guid"]).upper():
                remap[str(old).upper()] = str(res["guid"])
            if a.get("id"):
                results[a["id"]] = res
            out.append({"action": name, "id": a.get("id"), "result": res})
            # the _elem cache (host-wall geometry for opening placement) must not survive an
            # action that MOVED/CHANGED/DELETED elements: a later opening in the same batch
            # would compute its along-wall offset from the PRE-change endpoints (silently
            # wrong position). Creates are safe (the cache rebuilds on a miss anyway).
            if name and not name.startswith(("create_", "place_")) and hasattr(self, "_emap"):
                del self._emap
        return out

    @staticmethod
    def _resolve_refs(value, results, key=None):
        """Recursively replace cross-references to an earlier action's result.

        Two forms are accepted:
          - "$<id>.<field>"  -> results[id][field]  (explicit field, e.g. "$comp1.guid").
            <id> may contain spaces/hyphens (action ids like "step 2" or "SW - 012"); the
            field is whatever follows the LAST dot. A reference that cannot be resolved
            (the earlier action FAILED, or the field doesn't exist) raises — silently
            passing None would let an optional param (e.g. `favorite`) swallow the miss
            and the action would "succeed" while dropping the plan's intent.
          - "<id>" in the "host" param -> results[id]["guid"] (a BARE id that exactly names
            an earlier action which produced a guid — an opening hosted on a wall CREATED in
            the same batch arrives as host="step 2"). ONLY the host param: substituting any
            matching string anywhere would corrupt a param that legitimately equals an
            action id (e.g. composite_name="Exterior Wall" vs an action id "Exterior Wall").
        """
        import re
        ref = re.compile(r"^\$(.+)\.(\w+)$")
        if isinstance(value, str):
            m = ref.match(value)
            if m:
                rid, field = m.groups()
                hit = results.get(rid)
                if not isinstance(hit, dict) or field not in hit:
                    why = (hit or {}).get("error") if isinstance(hit, dict) else "no such action id"
                    raise ValueError(f"unresolved reference {value!r} ({why or 'field missing'})")
                return hit[field]
            if key == "host":
                hit = results.get(value)
                if isinstance(hit, dict) and hit.get("guid"):
                    return hit["guid"]
            return value
        if isinstance(value, list):
            return [Toolbox._resolve_refs(v, results) for v in value]
        if isinstance(value, dict):
            return {k: Toolbox._resolve_refs(v, results, key=k) for k, v in value.items()}
        return value
