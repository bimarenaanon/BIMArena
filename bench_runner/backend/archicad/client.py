"""ArchicadClient — the single connection + Tapir wrapper used everywhere.

Replaces the `ACConnection.connect()` boilerplate, the `aid()`/`aid_plain()`
helpers, the three `tap`/`_tap` variants, the `clean()` delete methods, and the
`GetAllElements`+`GetDetailsOfElements` full-inventory pattern that were
duplicated across the old scripts.
"""
from archicad import ACConnection


def exec_error(resp, default="operation failed"):
    """First executionResults FAILURE message in a Tapir response, or None on success.

    Tapir's write commands (Modify*, DeleteElements, SetStories, ...) report per-element
    failure via `executionResults` WITHOUT raising — a caller that skips this check returns
    ok for an operation Archicad never applied (the verifier then believes the fix landed).
    Every Tapir write that isn't already normalized (create-style "elements" entries) must
    run its response through this. Scans EVERY entry — a multi-element write whose FIRST
    element succeeded must still report the failure of element 2+."""
    results = resp.get("executionResults") if isinstance(resp, dict) else None
    res = next((r for r in (results or []) if isinstance(r, dict)
                and r.get("success") is False), None)
    if res is not None:
        return (res.get("error") or {}).get("message", default)
    return None


class ArchicadClient:
    def __init__(self, acc, act):
        self.acc = acc
        self.act = act

    @classmethod
    def connect(cls):
        """Connect to the running Archicad instance (raises if unavailable).

        Sets a process-wide socket timeout FIRST: the vendored `archicad` package's transport
        is a bare `urlopen` with NO timeout, so a wedged Archicad (modal dialog, mid file
        open) would otherwise hang every call — and an unattended bench batch — forever.
        `urlopen` without an explicit timeout honours this global default, and 180 s matches
        the Revit client's per-request bound."""
        import socket
        if socket.getdefaulttimeout() is None:
            socket.setdefaulttimeout(180.0)
        conn = ACConnection.connect()
        if conn is None:
            raise SystemExit("Cannot connect to Archicad (open it + the project; port 19723).")
        return cls(conn.commands, conn.types)

    # ---- Tapir add-on command wrapper ----
    def tap(self, cmd, params=None):
        return self.acc.ExecuteAddOnCommand(
            self.act.AddOnCommandId("TapirCommand", cmd), params or {})

    # ---- attribute-id reference forms ----
    @staticmethod
    def aid(guid):
        """AttributeIdArrayItem form (inside arrays, e.g. a skin's material)."""
        return {"attributeId": {"guid": str(guid)}}

    @staticmethod
    def aid_plain(guid):
        """AttributeId / ElementId form (e.g. compositeId on a wall/slab)."""
        return {"guid": str(guid)}

    # ---- reads ----
    def all_elements(self):
        """Complete project inventory via Tapir. Returns list of (elem, detail) pairs."""
        elems = self.tap("GetAllElements")["elements"]
        det = self.tap("GetDetailsOfElements", {"elements": elems})["detailsOfElements"]
        return list(zip(elems, det))

