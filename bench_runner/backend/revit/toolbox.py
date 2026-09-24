"""RevitToolbox — the Revit backend behind `Toolbox.connect()` when `--target revit`.

It mirrors the subset of the Archicad `Toolbox` surface the pipeline actually uses
(`run_actions`, `list_composites`, `all_elements`, plus
`remote_snapshot` for the verifier) and forwards everything to the Revit add-in's HTTP server via
`RevitClient`. The actor's action list is identical to the Archicad path; `run_actions` resolves
`$id.field` cross-references in Python (same semantics as `Toolbox.run_actions`) and POSTs each
resolved action, threading earlier results forward.
"""
import re

from .client import RevitClient
from .. import swing

_REF = re.compile(r"^\$(.+)\.(\w+)$")


def _remap_guids(value, remap):
    """Translate stale guids (left behind by a delete+recreate) to their live successors, in
    any string param, chain-following with a cycle guard. Revit UniqueIds are case-sensitive,
    so the keys are exact strings (unlike the Archicad twin's upper-cased Tapir guids)."""
    if isinstance(value, str):
        seen, cur = set(), value
        while cur in remap and cur not in seen:
            seen.add(cur)
            cur = remap[cur]
        return cur
    if isinstance(value, list):
        return [_remap_guids(v, remap) for v in value]
    if isinstance(value, dict):
        return {k: _remap_guids(v, remap) for k, v in value.items()}
    return value


class RevitToolbox:
    """Same action surface as the Archicad Toolbox, served by a Revit add-in over HTTP."""

    def __init__(self, client):
        self.client = client
        self._snap = None          # per-batch snapshot cache (swing resolution)

    @classmethod
    def connect(cls):
        """Connect to the Revit add-in's HTTP server (Revit must be open with the BIM-agent add-in)."""
        return cls(RevitClient.connect())

    # ============================================================ READS
    def list_composites(self):
        """Existing layered types (Wall/Floor CompoundStructures) as
        [{name, total_thickness_m, skins_outer_to_inner:[{material, thickness_m, type}]}]."""
        return self.client.composites()

    def all_elements(self):
        """(element, detail) pairs shaped like the Archicad toolbox — for readable log labels and
        the agent's scope map. Revit serves a flat [{guid, type, id}] which we re-wrap."""
        return [({"elementId": {"guid": e.get("guid")}},
                 {"type": e.get("type"), "id": e.get("id")})
                for e in self.client.elements()]

    def remote_snapshot(self):
        """The full model snapshot (same schema as ults/model_snapshot, geometry in metres),
        computed Revit-side. `model_snapshot(tb)` dispatches here for the Revit backend."""
        return self.client.snapshot()

    # =============================================================== EXECUTION
    def run_actions(self, actions, results=None):
        """Execute a list of {action, params, id?} by POSTing each to Revit, in order.

        A param of the form "$<id>.<field>" is replaced by the result the earlier action with that
        id returned (e.g. a composite's "$comp1.guid"). Returns [{action, id, result}] per action —
        the SAME shape as Toolbox.run_actions, so agent.py consumes it unchanged.

        `results` (optional) is an EXTERNAL id -> result map (see Toolbox.run_actions), so
        "$id.field" references resolve across separate batches.
        """
        results = {} if results is None else results
        out = []
        self._snap = None                    # per-batch snapshot cache (see _swing_resolved)
        # Old->new guid registry for the delete+recreate actions (zone boundary edits, stair
        # reshapes, the slab-reshape fallback — the add-in returns `replaced` for them, same
        # contract as Archicad): a later corrective call routinely still holds the OLD
        # UniqueId. Same machinery as Toolbox.run_actions; lives for this toolbox's life.
        remap = getattr(self, "_guid_remap", None)
        if remap is None:
            remap = self._guid_remap = {}
        for a in actions:
            name = a.get("action")
            resolved = a.get("params") or {}
            try:
                # $ref resolution INSIDE the try: a bad "$id.field" must fail THIS action,
                # not abort the whole batch (same structure as Toolbox.run_actions).
                resolved = self._resolve_refs(a.get("params") or {}, results)
                resolved = _remap_guids(resolved, remap)
                params = self._swing_resolved(name, resolved)
                res = self.client.run_action(name, params)
                self._snap = None            # the model moved — drop the cached read
            except Exception as e:                    # transport / route / $ref error -> recorded failure
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            old = resolved.get("guid") if isinstance(resolved, dict) else None
            if isinstance(res, dict) and res.get("replaced") is not None and res.get("guid") \
                    and old and str(old) != str(res["guid"]):
                remap[str(old)] = str(res["guid"])
            if a.get("id"):
                results[a["id"]] = res
            out.append({"action": name, "id": a.get("id"), "result": res})
        return out

    # ------------------------------------------------- opening swing (points -> flip flags)
    #
    # The plan states a door's swing as target POINTS and the tool docs promise "the system
    # converts them geometrically". The Archicad toolbox did that conversion in its own
    # `place_door`/`modify_door` wrappers; this backend forwards raw params, so without this
    # step the points reached the add-in, which reads only `oSide`/`reflected`, and were
    # SILENTLY DROPPED — every opening kept Revit's default swing while the call reported ok.
    # The conversion itself is the shared `backend/swing.py`, so both backends agree with each
    # other and with the grader.

    _OPENING_ACTIONS = {"place_door", "place_window", "modify_door", "modify_window",
                        "replace_door", "replace_window"}

    def _snapshot(self):
        """The model snapshot for THIS batch (one read, dropped after any action runs)."""
        if self._snap is None:
            self._snap = self.client.snapshot() or {}
        return self._snap

    @staticmethod
    def _match(items, ref):
        """The element whose guid or id equals `ref` (the `host` param accepts either)."""
        key = str(ref or "").strip().lower()
        if not key:
            return None
        return next((el for el in items
                     if str(el.get("guid") or "").lower() == key
                     or str(el.get("id") or "").lower() == key), None)

    def _swing_geometry(self, action, params):
        """(wall_begin, wall_end, cx, cy) for the opening this action addresses, or None.

        A PLACE names its host wall and its centre directly. A MODIFY/REPLACE names the opening,
        so its host and centre come from the snapshot (an explicit `center` in the call wins —
        it is where the opening is being moved TO)."""
        snap = self._snapshot()
        walls = snap.get("walls") or []
        if action.startswith("place_"):
            wall = self._match(walls, params.get("host"))
            center = params.get("center")
        else:
            opening = self._match((snap.get("doors") or []) + (snap.get("windows") or []),
                                  params.get("guid"))
            if not opening:
                return None
            wall = self._match(walls, opening.get("host"))
            center = params.get("center") or opening.get("center")
        if not wall or center is None:
            return None
        b, e = wall.get("begCoordinate"), wall.get("endCoordinate")
        if not b or not e:
            return None
        cx, cy = swing._xy(center)
        return b, e, cx, cy

    def _swing_resolved(self, action, params):
        """`params` with any swing target points converted to this backend's flip flags."""
        if action not in self._OPENING_ACTIONS:
            return params
        if not any(params.get(k) is not None for k in swing.POINT_PARAMS):
            return params
        geom = self._swing_geometry(action, params)
        if geom is None:
            # Nothing to compute against — FAIL the action rather than silently placing with
            # the default swing: a print is not a tool result, so the agent would never learn
            # the swing was dropped and the checkpoint would fail with no breadcrumb. The
            # error names the fix (a real host/guid, or omit the points).
            raise ValueError(
                f"{action}: cannot resolve the host wall / opening centre from the model, so "
                f"the swing target points (opens_toward/hinge_toward/faces_toward) cannot be "
                f"applied — check the host/guid, or re-issue without the swing points and "
                f"set the swing afterwards")
        return swing.apply(params, *geom)

    @classmethod
    def _resolve_refs(cls, value, results, key=None):
        """Recursively replace cross-references to an earlier action's result (same semantics as
        the Archicad Toolbox._resolve_refs): "$<id>.<field>" -> results[id][field] (id may contain
        spaces; field follows the last dot; an unresolvable ref RAISES so the miss fails this
        action loudly instead of a silent None), and — in the "host" param ONLY — a BARE "<id>"
        that exactly names an earlier action which produced a guid -> that guid (an opening
        hosted on a same-batch wall arrives as host="step 2"; restricting to `host` keeps a
        param that legitimately equals an action id, e.g. a composite_name, intact)."""
        if isinstance(value, str):
            m = _REF.match(value)
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
            return [cls._resolve_refs(v, results) for v in value]
        if isinstance(value, dict):
            return {k: cls._resolve_refs(v, results, key=k) for k, v in value.items()}
        return value
