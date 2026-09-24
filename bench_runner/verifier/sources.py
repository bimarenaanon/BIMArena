"""Where the FINAL model state comes from.

live(pln, ...)     — reopen the collected result .pln in the running Archicad
                     (archicad_io) and take a fresh Tapir snapshot + composite
                     list. The official grading mode: independent of anything
                     the agent recorded.

Returns: {"snapshot": <model_snapshot schema, metres>,
          "composites": <list_composites schema, metres> | None}
"""
from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------- live

def live(pln: Path, io_mode: str = "gui", open_wait: float = 15.0,
         dialog_delay: float = 1.5, reopen: bool = True) -> dict:
    """Open the result project and read it back through the API tool backend.

    `reopen=False` reads the document that is ALREADY open -- the caller has verified that
    it is `pln` (right after the harness's own Save As it always is), so the reopen round
    trip is pure cost."""
    from drivers import archicad_io  # bench_runner subpackage (sys.path set by the CLI)
    from bench_runner.backend import Toolbox
    from bench_runner.backend.archicad.inventory import list_composites
    from bench_runner.backend.snapshot import model_snapshot

    if reopen:
        archicad_io.open_project(Path(pln), mode=io_mode, open_wait=open_wait,
                                 dialog_delay=dialog_delay)
    tb = Toolbox.connect()
    _force_floor_plan(tb)
    snap = model_snapshot(tb)
    if snap.get("untyped_elements"):
        print(f"  [grade] WARNING: {snap['untyped_elements']} element(s) came back with no "
              f"type — the read may be incomplete, so counts/preserve checkpoints on this "
              f"case are suspect")
    comps = list_composites(tb.client)
    _enrich_swing(tb, snap)
    enrich_wall_orientation(tb, snap)
    return {"snapshot": snap, "composites": comps}


def _force_floor_plan(tb) -> None:
    """Open the ACTIVE storey's floor plan before reading the model.

    A saved project reopens on whatever window was open when it was saved, and an agent
    that finished in an Elevation/Section window leaves it there. Tapir's
    GetDetailsOfElements does not reliably answer for elements outside the active window,
    and `model_snapshot` skips an element whose detail carries no type — so the same file
    grades differently depending on a view that has nothing to do with the model. Measured
    2026-08-29: create_door2 read 2 of its 5 walls and 0 of its 1 window, and two gpt-5.6
    flip cases scored 0.0 because the flipped opening "was not there".

    Switching to the storey's floor plan is `ChangeWindow` on its Project Map item, which is
    what `set_active_story` does. Best effort: a failure here must not stop grading, it just
    leaves the old risk in place (and `untyped_elements` will flag it)."""
    try:
        from bench_runner.backend.archicad.actions.stories import (
            get_stories, set_active_story)
        st = get_stories(tb.client)
        if not st.get("ok"):
            return
        act = st.get("actStory")
        stories = st.get("stories") or []
        # re-opening the ACTIVE storey is a no-op for the model and forces a plan window;
        # if the active index is unreadable, any storey's plan is still better than a section
        target = act if act is not None else (stories[0].get("index") if stories else None)
        if target is None:
            return
        r = set_active_story(tb.client, target)
        if not r.get("ok"):
            print(f"  [grade] could not open a floor plan before reading "
                  f"({r.get('error')}) — the snapshot may be view-filtered")
    except Exception as e:                      # never let this break grading
        print(f"  [grade] floor-plan switch skipped ({type(e).__name__}: {e})")


def _enrich_swing(tb, snap: dict) -> None:
    """Best-effort: attach swing info to doors/windows if Tapir details expose
    it (reflected/oSide are settable on create; some builds also report them).
    Leaves elements untouched when unavailable -> the swing criterion stays
    'unchecked'."""
    try:
        pairs = tb.all_elements()
    except Exception:
        return
    details = {e["elementId"]["guid"]: (d.get("details") or {}) for e, d in pairs}
    for kind in ("doors", "windows"):
        for o in snap.get(kind) or []:
            d = details.get(o.get("guid")) or {}
            if "oSide" in d or "reflected" in d:
                o["swing_raw"] = {k: d.get(k) for k in ("reflected", "refSide", "oSide")
                                  if k in d}


def enrich_wall_orientation(tb, snap: dict) -> None:
    """Best-effort wall enrichment off the official property API + 2D bboxes:

    - `orient` = {"ref": <Wall_ReferenceLineLocation>, "left_mm", "right_mm"}:
      the body's perpendicular extents each side of the reference line (left =
      left of beg->end) — consumed by the orientation ("faces") checkpoint;
    - `width` (metres, filled only when the snapshot has none) from
      General_Thickness — Tapir details carry no wall thickness;
    - `material` from SurfaceAndMaterials_ComponentBuildingMaterialName (a
      basic wall's building material; composite walls list every component).

    Walls it can't read stay as they were -> those checkpoints unchecked."""
    walls = snap.get("walls") or []
    if not walls:
        return
    _WANT = ("Wall_ReferenceLineLocation", "General_Thickness")
    try:
        acc, act = tb.client.acc, tb.client.act
        names = acc.GetAllPropertyNames()
        by_name = {getattr(n, "nonLocalizedName", ""): n for n in names}
        props = [by_name[k] for k in _WANT if k in by_name]
        pids = [p.propertyId for p in acc.GetPropertyIds(props)]
        idx = {k: i for i, k in enumerate(k for k in _WANT if k in by_name)}
        if "Wall_ReferenceLineLocation" not in idx:
            return
        eids = [act.ElementIdArrayItem(act.ElementId(w["guid"])) for w in walls]
        vals = acc.GetPropertyValuesOfElements(eids, pids)
        boxes = acc.Get2DBoundingBoxes(eids)
    except Exception:
        return

    # building materials live on the element COMPONENTS (the element-level
    # property is notAvailable): one name per skin, joined outer-to-inner
    try:
        mat_prop = by_name["SurfaceAndMaterials_ComponentBuildingMaterialName"]
        mat_pid = acc.GetPropertyIds([mat_prop])[0].propertyId
        comp_ids, owners = [], []
        for wi, cw in enumerate(acc.GetComponentsOfElements(eids)):
            for c in cw.elementComponents or []:
                comp_ids.append(act.ElementComponentIdArrayItem(c.elementComponentId))
                owners.append(wi)
        if comp_ids:
            per: dict[int, list] = {}
            for wi, v in zip(owners,
                             acc.GetPropertyValuesOfElementComponents(comp_ids, [mat_pid])):
                val = getattr(v.propertyValues[0].propertyValue, "value", None)
                if isinstance(val, str) and val:
                    per.setdefault(wi, []).append(val)
            for wi, mats in per.items():
                walls[wi]["material"] = "; ".join(mats)
    except Exception:
        pass

    def _pv(v, key):
        i = idx.get(key)
        if i is None:
            return None
        pv = v.propertyValues[i].propertyValue
        return getattr(pv, "value", None)

    for w, v, bb in zip(walls, vals, boxes):
        try:
            if w.get("width") is None:
                thick = _pv(v, "General_Thickness")
                if isinstance(thick, (int, float)):
                    w["width"] = thick
            val = _pv(v, "Wall_ReferenceLineLocation")
            loc = getattr(val, "nonLocalizedValue", None) or (
                val if isinstance(val, str) else None)
            beg, end = w.get("begCoordinate"), w.get("endCoordinate")
            box = bb.boundingBox2D
            dx, dy = end["x"] - beg["x"], end["y"] - beg["y"]
            if abs(dy) < 1e-6 and abs(dx) > 1e-6:        # horizontal wall
                up, down = box.yMax - beg["y"], beg["y"] - box.yMin
                left, right = (up, down) if dx > 0 else (down, up)
            elif abs(dx) < 1e-6 and abs(dy) > 1e-6:      # vertical wall
                xplus, xminus = box.xMax - beg["x"], beg["x"] - box.xMin
                left, right = (xminus, xplus) if dy > 0 else (xplus, xminus)
            else:                                        # slanted: bbox unusable
                if loc:
                    w["orient"] = {"ref": loc}
                continue
            w["orient"] = {"ref": loc,
                           "left_mm": round(max(left, 0.0) * 1000, 1),
                           "right_mm": round(max(right, 0.0) * 1000, 1)}
        except Exception:
            continue


def live_revit(rvt: Path, io_mode: str = "gui", open_wait: float = 15.0,
               dialog_delay: float = 1.5, reopen: bool = True) -> dict:
    """Revit twin of live(): reopen the result .rvt in the running Revit (revit_io: the
    add-in's /open route, or GUI-driven) and read it back through the BimAgent add-in's
    HTTP routes. `reopen=False` reads the already-open (verified) document."""
    from drivers import revit_io  # bench_runner subpackage (sys.path set by the CLI)
    from bench_runner.backend.revit.client import RevitClient

    if reopen:
        revit_io.open_project(Path(rvt), mode=io_mode, open_wait=open_wait,
                              dialog_delay=dialog_delay)
    revit_io._await_free()        # a still-loading doc answers /health with 500 "job timed
                                  # out", and connect() turns that into a fatal SystemExit
    c = RevitClient.connect()
    return {"snapshot": c.snapshot(), "composites": c.composites()}


def created_composites(final_composites, base_composites):
    """Composites NEW in the final model (by name, against the env's baseline composite
    list); None when either side is unknown."""
    if final_composites is None or base_composites is None:
        return None
    base_names = {c.get("name") for c in base_composites}
    return [c for c in final_composites if c.get("name") not in base_names]
