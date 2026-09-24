"""RevitClient — HTTP transport to a Revit add-in's local server.

Stdlib-only (urllib) so the agent needs no extra dependency. A Revit-side add-in (e.g. a C#
native-API add-in) must serve these routes (default base `http://localhost:48884`, override via
`$REVIT_ROUTES_URL`) — this is the contract the add-in implements:

    GET  /health                 -> {ok, doc}
    GET  /snapshot               -> the model snapshot (same schema as ults/model_snapshot, metres)
    GET  /materials              -> [building-material names]
    GET  /composites             -> [{name, total_thickness_m, skins_outer_to_inner:[...]}]
    GET  /favorites/<type>       -> [type names]  (Door/Window -> loadable family symbol names)
    GET  /elements               -> [{guid, type, id}]   (for readable log labels)
    POST /action  {action,params}-> the action result {ok, guid?, ...}
    POST /open   {path, close_others=true}  -> {ok, doc, path, closed:[titles]}   HARNESS:
                                    open + activate a project, discard every other open doc
    POST /saveas {path, overwrite=true}     -> {ok, doc, path, exists}            HARNESS:
                                    save the active doc under a new name (its title follows)
"""
import json
import urllib.error
import urllib.request

from ..settings import REVIT_ROUTES_URL


class RevitClient:
    """Talks to the Revit add-in's HTTP server (the routes above)."""

    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    @classmethod
    def connect(cls):
        """Build a client and verify the add-in server is actually reachable. A dead server
        at CONNECT time is fatal (SystemExit — nothing can run); mid-run transport errors
        are RuntimeError so run_actions records them per action instead of dying."""
        c = cls(REVIT_ROUTES_URL)
        try:
            c.health()
        except RuntimeError as e:
            raise SystemExit(str(e))
        return c

    # ------------------------------------------------------------------ transport
    # Consecutive-timeout fail-fast: a Revit wedged behind a native dialog still ACCEPTS the
    # TCP connection and stalls, costing the full 180 s per call — with no memo, a big turn's
    # batch burns hours against a dead application. After this many timeouts in a row the
    # client fails immediately with an error naming the wedge; any successful request resets.
    _TIMEOUT_TRIP = 3

    def _request(self, method, path, payload=None):
        if getattr(self, "_timeouts", 0) >= self._TIMEOUT_TRIP:
            raise RuntimeError(
                f"the Revit add-in timed out {self._timeouts} times in a row — Revit is "
                f"likely wedged behind a native dialog; clear it (the harness's "
                f"--wait-for-app can restart Revit) before retrying")
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read().decode("utf-8")
            self._timeouts = 0
        except urllib.error.HTTPError as e:           # the route ran but returned an error
            self._timeouts = 0                        # it answered — not a wedge
            detail = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"Revit route {method} {path} -> HTTP {e.code}: {detail}")
        except urllib.error.URLError as e:            # could not reach the server at all.
            # RuntimeError, NOT SystemExit: SystemExit is a BaseException that run_actions'
            # `except Exception` cannot catch — one dropped connection mid-batch would kill
            # the whole process instead of recording a per-action failure. connect() upgrades
            # this to SystemExit at startup, where dying IS the right behaviour.
            if isinstance(getattr(e, "reason", None), TimeoutError):
                self._timeouts = getattr(self, "_timeouts", 0) + 1
            raise RuntimeError(
                f"cannot reach the Revit add-in server at {url} — open Revit with the BIM-agent "
                f"add-in loaded and its HTTP server running, or set $REVIT_ROUTES_URL. ({e.reason})")
        except (TimeoutError, OSError) as e:
            # a timeout/disconnect during the response READ (r.read()) is raised raw, not
            # wrapped in URLError — it must honor the same RuntimeError contract, or a hung
            # add-in surfaces as a bare TimeoutError traceback instead of a per-action failure
            # (and a clean SystemExit at connect time).
            self._timeouts = getattr(self, "_timeouts", 0) + 1
            raise RuntimeError(f"Revit route {method} {path} transport error: "
                               f"{type(e).__name__}: {e}")
        try:
            return json.loads(body) if body else None
        except ValueError:
            raise RuntimeError(f"Revit route {method} {path} returned unparseable JSON: "
                               f"{body[:200]!r}")

    def get(self, path):
        out = self._request("GET", path)
        # Belt-and-braces with the add-in's GET-error->HTTP-500 rule: an {ok:false} body that
        # still arrives with 200 (an older add-in build) must not be consumed as data — a
        # failed /snapshot dict is truthy, so `or {}` would silently hand the verifier an
        # "empty model" and /composites would crash the actor iterating the dict's keys.
        if isinstance(out, dict) and out.get("ok") is False:
            raise RuntimeError(f"Revit route GET {path} failed: {out.get('error')}")
        return out

    def post(self, path, payload):
        return self._request("POST", path, payload)

    # ------------------------------------------------------------------- endpoints
    def health(self):
        return self.get("health")

    def snapshot(self):
        return self.get("snapshot") or {}

    def composites(self):
        return self.get("composites") or []

    def elements(self):
        return self.get("elements") or []

    def run_action(self, action, params):
        return self.post("action", {"action": action, "params": params})
