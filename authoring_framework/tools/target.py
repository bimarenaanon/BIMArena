"""Which BIM applications exist — `archicad` (Tapir) and `revit` (HTTP add-in).

EVERY application's tools are in the pool: the harness does NOT pick one for the agent. The
agent works out which application it is actually in from the observed model state (each is
probed and reported separately) and uses that application's tool prefix. `bim_targets()` is
therefore the POOL, and `--target` / `$BIM_TARGET` only NARROW it — for ablations and for
reproducing single-application results.

`bim_target()` (singular) survives for the places that genuinely need one answer: the API
backend resolving which application a connection speaks to when nothing named it.

It lives in the TOOL layer because both consumers are here: the API backend
(`bench_runner/backend/settings.py`) and the framework's `config.py`.
"""
import os
import subprocess
import sys

BIM_TARGETS = ("archicad", "revit")

# Base URL of the Revit add-in's HTTP server (the C# add-in implements the route contract in
# bench_runner/backend/revit/client.py). Override the host/port via env to match the add-in.
REVIT_ROUTES_URL = os.getenv("REVIT_ROUTES_URL") or "http://localhost:48884"

_override = {}
_detected = {}


def set_target_override(target=None):
    """CLI hook: NARROW the tool pool to one application (or a comma-separated subset) for this
    process (beats $BIM_TARGET). Without it every application's tools are offered."""
    if target:
        _override["target"] = str(target).lower()


def _forced():
    """The narrowing the user asked for, as a tuple, or () when nothing was forced."""
    raw = _override.get("target") or os.getenv("BIM_TARGET")
    if not raw:
        return ()
    out = []
    for part in str(raw).lower().replace(";", ",").split(","):
        t = part.strip()
        if not t or t in ("all", "both", "any"):    # explicit "the whole pool"
            continue
        if t not in BIM_TARGETS:
            raise SystemExit(f"unknown BIM target {t!r} (use: {', '.join(BIM_TARGETS)}, "
                             f"or omit for all of them)")
        if t not in out:
            out.append(t)
    return tuple(out)


def bim_targets():
    """The applications whose tools are in the pool: ALL of them unless `--target` /
    `$BIM_TARGET` narrowed it. Nothing is auto-detected here — which application is actually
    running is something the agent reads off the observed model state, not something the
    harness decides for it."""
    return _forced() or BIM_TARGETS


def bim_target():
    """ONE application, for the callers that genuinely need a single answer (the API backend
    resolving a connection nothing else named). A narrowing wins; otherwise fall back to
    AUTO-DETECTING which application is up. Cached for the process."""
    forced = _forced()
    if forced:
        return forced[0]
    if "target" not in _detected:
        _detected["target"] = _detect_target()
    return _detected["target"]


def _running_bim_apps():
    """Which BIM apps have a RUNNING process: a subset of {'archicad', 'revit'}.
    Matched on the process image name (Archicad.exe / Revit.exe on Windows — 'revit.exe'
    EXACTLY, since Autodesk's RevitAccelerator background service runs even with Revit
    closed and must not count). Empty set = none found OR the process list was unreadable
    (the caller then falls back to the /health probe)."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, timeout=10).stdout
            names = [line.split('","')[0].strip('"').lower()
                     for line in out.splitlines() if line.startswith('"')]
        else:                                        # macOS/Linux: process command names
            out = subprocess.run(["ps", "-axo", "comm"], capture_output=True,
                                 text=True, timeout=10).stdout
            names = [line.rsplit("/", 1)[-1].strip().lower() for line in out.splitlines()]
    except Exception:
        return set()
    apps = set()
    if any(n.startswith("archicad") for n in names):
        apps.add("archicad")
    if any(n == "revit.exe" or n == "revit" for n in names):
        apps.add("revit")
    return apps


def _detect_target():
    """Pick the backend by which BIM app is actually RUNNING (process list) — the app the
    user has open beats a port probe (probing /health alone misfired whenever the add-in
    wasn't loaded, the port was stale, or Revit simply wasn't the app in use):
      - only Revit running            -> revit (connect() gives a clear error if the add-in is dead)
      - only Archicad running         -> archicad
      - BOTH running                  -> revit only if its add-in answers /health, else archicad
      - none found / list unreadable  -> the /health probe (keeps a REMOTE $REVIT_ROUTES_URL working)
    """
    apps = _running_bim_apps()
    if apps == {"revit"}:
        return "revit"
    if apps == {"archicad"}:
        return "archicad"
    return "revit" if _revit_bridge_up() else "archicad"


def _revit_bridge_up():
    """Is the Revit add-in's HTTP /health answering at REVIT_ROUTES_URL?"""
    import urllib.request
    try:
        with urllib.request.urlopen(REVIT_ROUTES_URL.rstrip("/") + "/health", timeout=1.5) as r:
            return 200 <= r.status < 300
    except Exception:
        return False
