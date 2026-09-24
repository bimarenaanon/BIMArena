"""Re-run selected bench cases IN PLACE, in the `results/<tool>_bycase_<phase>` layout.

The by-case results tree was originally produced by ad-hoc commands; this is the reusable
tool for the same layout, so a partial re-run (e.g. only the cases a framework change can
affect) lands in exactly the same shape as the rest:

    <results>/<CASE_ID>/<tool>/
        source.txt                     one-line provenance of THIS run
        result_api.pln|.rvt            the project saved after the agent finished
        score_api.json                 live-graded report + a "run" block of agent stats
        api/command.txt                the exact agent command line
        api/stdout.log                 the agent's console output
        api/agent_run/                 the collected runs/<id>/ (memory.json, trace.jsonl)

Per case: open the case's START project -> run the agent as a subprocess -> save-as
result_<phase>.<ext> -> grade LIVE (reopen + snapshot) against task.json's expected_result
for THIS tool's variant.

WHICH APPLICATION is DETECTED, not chosen: there is deliberately no `--tool` flag. Whichever
BIM application is up decides which variant's env is opened, which expected_result grades it
and which results tree it lands in. The AGENT is never told — every application's tools are in
its pool and working out which one it is in is part of what the benchmark measures — so the
detection here stays strictly harness-side and never reaches the agent's command line.

Project OPEN is deterministic where the application allows it (Archicad: Tapir `OpenProject`;
Revit: Ctrl+O + paste, verified against the add-in's /health doc title), SAVE-AS goes through
the GUI on both. Both are VERIFIED: a case whose project did not actually open, or whose save
produced no file, is recorded as failed and NOT graded — grading a stale/wrong document would
silently corrupt the results.

Usage (repo root, ONE BIM application open, no modal dialogs):
    python bench_runner/rerun_cases.py --only B_element_creation9 B_element_creation10 --note "swing fix"
    python bench_runner/rerun_cases.py --from-file cases.txt --note "..." --dry-run
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))    # case_io / drivers / reports / verifier
sys.path.insert(0, str(ROOT))    # authoring_framework.*

import case_io  # noqa: E402
from case_io import discover_cases  # noqa: E402
from drivers import archicad_io, revit_io  # noqa: E402
from reports import case_eval_md  # noqa: E402
from verifier import baselines, sources  # noqa: E402
from verifier.grade import grade, normalize_composites, trivial_from_report  # noqa: E402
from verifier import trivial_probe  # noqa: E402

# Per-phase wiring. There is ONE agent module — the phase IS the agent's `--tools` mode
# (the six action spaces), which is what the comparison actually varies. A phase that drives
# the mouse/keyboard also refreshes the per-case materials skill doc, FOCUSES Archicad before
# launching, and gets a longer default timeout. The ONE run limiter is the agent's TURN cap
# (tool calls per turn are NOT limited), fixed PER SUBSET — see TURNS_BY_SUBSET — and handed
# to the agent as $AGENT_MAX_TURNS; the framework default (100) is the manual-run fallback.
AGENT_MODULE = "authoring_framework"
AGENT_EXIT_LLM_FAILURE = 13   # react.EXIT_LLM_FAILURE: the provider stayed down through every retry
# The agent's runs/ tree — the same $AGENT_RUNS_DIR the framework honours (config.RUNS_DIR).
# It must be PRIVATE to this machine: runs/.current is one pointer file, and the VM bench
# runs several guests from one shared checkout, so a shared runs/ made this harness collect
# another guest's run as this case's record (2026-09-03).
AGENT_RUNS = Path(os.environ["AGENT_RUNS_DIR"]) if os.environ.get("AGENT_RUNS_DIR") \
    else ROOT / "authoring_framework" / "runs"
# The turn cap, by SUBSET (the dir the case lives under: .../<subset>/<tool>/<case_id>): an
# atomic case is one operation; a reasoning / long-sequence case is a multi-element build.
# One flat number per track, so "ran out of turns" means the same thing in every row of it.
TURNS_BY_SUBSET = {"atomic_tasks": 100, "reasoning_tasks": 300, "long-seq_tasks": 300}
TURNS_DEFAULT = 300          # a dataset tree with another name
# The RUNNABLE phases are the paper's three support settings: gui-raw (w/o support — no
# retrieval tool), gui-docs (w/ doc) and gui-support (w/ doc+skill). gui-priors (the old name
# of gui-support) and the four API / hybrid phases are LEGACY — the agent can no longer run
# them — and
# survive here ONLY so `--regrade` can still re-grade the result trees they produced
# (result_<phase>.* / score_<phase>.json are named after the phase).
PHASES = {
    "gui-raw":       {"tools": "gui-raw",       "timeout": 3600.0, "drives_ui": True},
    "gui-docs":      {"tools": "gui-docs",      "timeout": 3600.0, "drives_ui": True},
    "gui-support":   {"tools": "gui-support",   "timeout": 3600.0, "drives_ui": True},
    "gui-priors":    {"legacy": True, "timeout": 3600.0},      # the old name of gui-support
    "api-priors":    {"legacy": True, "timeout": 1800.0},
    "api-raw":       {"legacy": True, "timeout": 1800.0},
    "hybrid-priors": {"legacy": True, "timeout": 3600.0},
    "hybrid-raw":    {"legacy": True, "timeout": 3600.0},
}
# Older spellings, still accepted on the CLI.
PHASE_ALIASES = {"api": "api-priors", "code": "api-raw",
                 "hybrid": "hybrid-priors",
                 "api-tools": "api-priors", "gui-skills": "gui-support",
                 "hybrid-tools": "hybrid-priors"}
PHASE = "gui-support"               # set by main() from --phase; used by the helpers below

# WHICH APPLICATION this batch runs against. There is NO flag for it and it is never passed to
# the agent: the harness DETECTS which BIM application is live (it has to — it opens the project
# file and grades the result), while the agent gets the whole tool pool and has to work the same
# thing out for itself from the model state. Those are two separate jobs and telling the agent
# would defeat the measurement.
TOOL = "archicad"                  # set by main() from the live-application detection

# WHICH DATASET TREE the case ids are resolved against (set by main() from --bench-root).
# The dataset is split into three subsets of the same `<subset>/<tool>/<case_id>` layout:
# `bench_cases/reasoning_tasks/` (the default), `bench_cases/long-seq_tasks/` (currently an identical
# copy) and `bench_cases/atomic_tasks/` (the atomic capability cases) — pointing this at
# another subset is all a batch over it needs, since case_io/baselines take the root as an
# argument everywhere else.
BENCH_ROOT = ROOT / "bench_cases" / "reasoning_tasks"

# Per-application adapter: the few things that genuinely differ between driving Archicad and
# driving Revit. Everything else in this file is application-agnostic.
TOOLS = {
    "archicad": {
        "io": None,                     # filled below (module import order)
        "ext": ".pln",
        "variant": "ArchiCAD",          # task.json's authoring_tool spelling
        "open_mode": "tapir",           # deterministic; Tapir registers OpenProject
        "save_mode": "tapir",           # in-place SaveProject on the RESULT COPY (below);
                                        # the keyboard Save As stays as the fallback
        # WORK ON A COPY (2026-09-02): Tapir has no Save As, only an in-place SaveProject.
        # So the start .pln is COPIED to result_<phase>.pln before the open, the agent
        # edits that file, and the save is a parameterless SaveProject — no Save-As
        # dialog, no keystrokes, and the case's start project is never even opened.
        "work_on_copy": True,
        "window": "archicad",           # substring the foreground window title must contain
    },
    "revit": {
        "io": None,
        "ext": ".rvt",
        "variant": "Revit",
        "open_mode": "api",             # the add-in's /open route (2026-09-02); Ctrl+O +
        "save_mode": "api",             # paste and Alt,F,A,P stay as the automatic fallback
        "window": "revit",
    },
}


def _cfg():
    return PHASES[PHASE]


TOOLS["archicad"].update(io=archicad_io, focus=archicad_io._focus_archicad,
                         open_name=lambda quiet=False: _archicad_open_name(quiet),
                         live=lambda p, reopen=True: sources.live(p, io_mode="tapir",
                                                                  reopen=reopen))
TOOLS["revit"].update(io=revit_io, focus=revit_io._focus_revit,
                      open_name=lambda quiet=False: _revit_open_name(quiet),
                      live=lambda p, reopen=True: sources.live_revit(p, io_mode="api",
                                                                     reopen=reopen))


def _tool():
    return TOOLS[TOOL]


RESULTS_OVERRIDE: Path | None = None   # set by main() from --results-dir
MAX_TURNS_OVERRIDE: int | None = None  # set by main() from --max-turns (overrides the subset's cap)
LLM_OVERRIDE: dict = {}                # set by main() from -p/--provider and -m/--model


def _results_dir() -> Path:
    """`results/<tool>_bycase_<phase>` — the archicad trees keep their existing names.
    `--results-dir` overrides it, so a fresh batch can land in its own tree (same shape)
    instead of overwriting the previous batch's per-case results."""
    return RESULTS_OVERRIDE or HERE / "results" / f"{TOOL}_bycase_{PHASE}"


def _case_dir(cid: str) -> Path:
    return _results_dir() / cid / TOOL


def _detect_tool() -> str:
    """Which BIM application is actually up. Harness-side only (see TOOL above)."""
    from authoring_framework.tools.target import bim_target
    return bim_target()


# ---------------------------------------------------------------- helpers

def _current_run_dir() -> Path | None:
    runs = AGENT_RUNS
    ptr = runs / ".current"
    if ptr.exists():
        d = runs / ptr.read_text(encoding="utf-8").strip()
        if d.is_dir():
            return d
    return None


def _project_info(quiet: bool = False) -> dict:
    """Tapir GetProjectInfo ({} when unavailable) — used to VERIFY an open actually landed."""
    try:
        from bench_runner.backend.archicad.client import ArchicadClient
        return ArchicadClient.connect().tap("GetProjectInfo", {}) or {}
    except BaseException as e:          # SystemExit when Archicad is not reachable at all
        if not quiet:
            print(f"    [warn] GetProjectInfo failed: {type(e).__name__}: {e}")
        return {}


def _archicad_open_name(quiet: bool = False) -> str | None:
    """The file name Archicad reports open, or None when it is not answering."""
    info = _project_info(quiet=quiet)
    return (info.get("projectName") or info.get("projectPath") or "") if info else None


def _revit_open_name(quiet: bool = False) -> str | None:
    """The doc title the BimAgent add-in reports, or None when it is not answering.

    `_doc_title()` returns the sentinel ABSENT when the routes port is dead and BUSY when the
    server answers but the API thread does not (Revit mid-load, or a modal). BUSY is given a
    grace window (`_await_free`) before it counts as "not answering" — reporting it straight
    away had the caller treat a still-loading document as a crashed application."""
    title = revit_io._await_free()
    if title in (revit_io.ABSENT, revit_io.BUSY):
        if not quiet:
            print(f"    [warn] the Revit add-in is not answering /health "
                  f"({'busy' if title == revit_io.BUSY else 'unreachable'})")
        return None
    return title or ""


def _app_up() -> bool:
    """Is the application reachable AND past any modal/splash state (its API answers)?"""
    return _tool()["open_name"](quiet=True) is not None


def _wait_for_app(minutes: float, settle: float) -> bool:
    """Block until the application answers again, up to `minutes`, then let it settle.

    The application CRASHING mid-batch is the expensive failure: without this every remaining case
    burns its open+agent+save on a dead application. With it the batch simply pauses until the
    application is back (a fresh launch also has to get past its recovery dialog, hence the
    settle delay), and resumes where it stopped."""
    if _app_up():
        return True
    deadline = time.time() + minutes * 60
    print(f"  [wait] {TOOL} is not answering — waiting up to {minutes:.0f} min for it "
          f"to come back ...", flush=True)
    while time.time() < deadline:
        time.sleep(15)
        if _app_up():
            print(f"  [wait] {TOOL} is back; settling {settle:.0f}s before continuing",
                  flush=True)
            time.sleep(settle)
            return _app_up()
    print(f"  [wait] gave up waiting for {TOOL}", flush=True)
    return False


def _opened_ok(project: Path) -> bool:
    """True when the application really has `project` open — checked against what IT reports,
    never assumed from the open command returning. Grading a stale document would silently
    score the wrong model.

    Archicad: the check must be by FULL PATH, not name — every case's start file is
    `archicad.pln`, so a name match would accept the PREVIOUS case's still-open project when
    this case's open silently failed. The path is compared field-by-field (json.dumps would
    double the backslashes and never match a Windows path)."""
    if TOOL == "archicad":
        info = _project_info()
        if not info or info.get("isUntitled"):
            return False
        want = str(project).lower().replace("/", "\\")
        for v in info.values():
            if isinstance(v, str) and v.lower().replace("/", "\\") == want:
                return True
        # fallback: no path field in the report at all — accept a name match rather than
        # failing every case on an older Tapir that reports only the project name
        if not any(isinstance(v, str) and ("\\" in v or "/" in v) for v in info.values()):
            return project.name.lower() in json.dumps(info).lower()
        return False
    title = _revit_open_name()
    if not title:
        return False
    return project.stem.lower() in title.lower()


def _wait_for_focus(minutes: float, poll: float = 45.0) -> bool:
    """Archicad is ALIVE but we cannot own the desktop — a human is using the machine (their
    typing steals the foreground; parking the mouse in a screen corner trips pyautogui's
    fail-safe). Periodically re-attempt activation until it verifies or the timeout runs out,
    so the batch PAUSES for the human instead of burning the remaining cases."""
    print(f"  [wait] {TOOL} is alive but the desktop is in use (focus lost / fail-safe) — "
          f"retrying activation every {poll:.0f}s, up to {minutes:.0f} min ...", flush=True)
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(poll)
        if _focus_verified(attempts=1, settle=1.5):
            print("  [wait] desktop is free again — resuming", flush=True)
            return True
    print("  [wait] desktop never freed up — giving up on this case", flush=True)
    return False


def _restart_revit(minutes: float, settle: float) -> bool:
    """Force-quit a dead/hung Revit and launch a fresh one, then wait for the add-in.

    Part of the CRASH POLICY (2026-08-08): a Revit that stopped answering mid-batch never
    comes back by itself — a crash dialog or a zombie process would park the batch for the
    whole wait window. Kill whatever is left, relaunch the exe, and let `_wait_for_app`
    confirm /health before the batch continues."""
    subprocess.run(["taskkill", "/IM", "Revit.exe", "/F"], capture_output=True)
    time.sleep(5)
    exe = next(iter(Path(r"C:\Program Files\Autodesk").glob("Revit 20*/Revit.exe")), None)
    if exe is None:
        print(r"  [restart] no Revit.exe under C:\Program Files\Autodesk — cannot relaunch",
              flush=True)
        return False
    print(f"  [restart] launching {exe}", flush=True)
    subprocess.Popen([str(exe)])
    return _wait_for_app(minutes, settle)


def _crash_fail(case) -> dict:
    """BENCH POLICY (2026-08-08): the application DIED mid-case (crash during the agent run
    or the save/reopen) — the case is a ZERO-CREDIT FAIL, not a retry. The score file carries
    the agent stats as of the crash (run block from the collected agent_run) plus one
    synthetic failing checkpoint naming the crash, so the EVAL row reads honestly. The
    checkpoint/unit DENOMINATORS come from grading the untouched baseline against itself —
    deterministic, no application needed."""
    cid = case.id
    out = _case_dir(cid)
    out.mkdir(parents=True, exist_ok=True)
    run_block = None
    mj = out / PHASE / "agent_run" / "memory.json"
    if mj.exists():
        try:
            run_block = _run_block_from_memory(json.loads(mj.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"    [warn] no run block from memory.json: {e}", flush=True)
    tot_cp = tot_units = tot_goal = tot_keep = None
    try:
        base = baselines.load(cid, TOOL)
        expected = case_io.read_spec(BENCH_ROOT, TOOL, cid).get("expected_result")
        if expected:
            probe = grade(expected, base.get("snapshot") or {}, base.get("snapshot") or {},
                          normalize_composites([]), anchor=(TOOL == "revit"),
                          composites_final=base.get("composites"),
                          trivial=_trivial_ids(cid, expected, base))
            tot_cp, tot_units = probe.get("checkpoints_total"), probe.get("units_total")
            tot_goal, tot_keep = probe.get("pcs_total"), probe.get("cfr_total")
    except Exception as e:
        print(f"    [warn] could not derive checkpoint totals: {e}", flush=True)
    report = {"case": cid, "phase": PHASE, "tool": TOOL,
              "status": "fail (Revit crashed — not gradable)", "source": "crash",
              "graded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
              "score": 0.0, "passed": False, "reward": 0.0,
              # a crash produces no model, so nothing asked for was built and
              # nothing that had to survive can be shown to have survived
              "pcs": 0.0, "pcs_passed": 0, "pcs_total": tot_goal or 0,
              "cfr": 0.0, "cfr_passed": 0, "cfr_total": tot_keep or 0,
              "units_passed": 0, "units_total": tot_units or 0,
              "checkpoints_passed": 0, "checkpoints_total": tot_cp or 0,
              "checkpoints": [{"id": "Revit crashed mid-case", "score": 0.0}]}
    if run_block:
        report["run"] = run_block
    (out / f"score_{PHASE}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
    try:
        case_eval_md.write(out, PHASE)
    except Exception:
        pass
    print(f"  [crash-fail] {cid}: scored 0 (Revit crashed) — moving on", flush=True)
    return report


# Settings dialogs an agent can leave open, blocking the next case's Tapir open with
# error 4001 ("ongoing user input"). STRICT ALLOWLIST, and it must stay one: Archicad's
# own internal top-level windows carry titles too, and closing one KILLS the application
# — 'DGTransparentWindow' (its dialog-manager overlay) and 'Learning Center' each took
# Archicad down with them on 2026-08-24, once via WM_CLOSE from a blanket "close every
# titled window that is not the main one" pass. Never widen this to a denylist; add a
# title here only after seeing it left open by a finished run.
_CLOSEABLE_MODALS = {
    "model view options", "wall default settings", "slab default settings",
    "door default settings", "window default settings", "object default settings",
    "zone default settings", "stair default settings", "column default settings",
    "beam default settings", "composites", "building materials", "surfaces",
    "layers (model views)", "story settings", "project preferences", "work environment",
    "find & select", "search & replace", "element information", "element id manager",
    # floating palettes/reports an agent can leave over the CANVAS, where they eat its
    # clicks (Tapir palette was the first one seen doing it; then Issue Organizer and
    # Model Check Report — the latter is what a clash_check case leaves behind)
    "issue organizer", "issue manager", "tapir palette", "model check report",
    "change manager",
}


def _clear_input_state(presses: int = 4) -> None:
    """Esc out of any half-finished TOOL INPUT the agent left behind.

    Distinct from `_dismiss_stray_modals`, which closes stray DIALOG windows: this is the
    case where no window is open at all and Archicad is simply mid-gesture — a Marquee
    waiting for its rotation vector, an unfinished polyline. Tapir refuses every command
    while the application is in "ongoing user input" (error 4001), so the runner reads the
    application as dead and burns its whole --wait-for-app hour. Observed three times on
    2026-08-27; each was cleared by Esc alone, with the app otherwise healthy (process
    responding, port listening, document open, no dialog on screen).

    Esc is safe here: with no tool active it is a no-op, and it never commits anything.
    Archicad-only, and only when its window is genuinely foreground — keystrokes sent at
    whatever happens to be focused are how the batch typed a project path into a crash
    reporter on 2026-08-24."""
    if TOOL != "archicad":
        return
    try:
        import pyautogui
        import pygetwindow as gw
        w = next((x for x in gw.getAllWindows()
                  if (x.title or "").endswith("Archicad 29")), None)
        if not w:
            return
        try:
            if w.isMinimized:
                w.restore()
            w.activate()
        except Exception:
            pass
        time.sleep(0.8)
        active = gw.getActiveWindow()
        if not active or "archicad" not in (active.title or "").lower():
            print("    [esc] Archicad is not foreground — skipping (no stray keystrokes)")
            return
        for _ in range(presses):
            pyautogui.press("esc")
            time.sleep(0.4)
    except Exception as e:
        print(f"    [esc] {type(e).__name__}: {e}")


def _dismiss_stray_modals() -> None:
    """Close settings dialogs the PREVIOUS case's agent left open (WM_CLOSE = Cancel).

    Only titles in `_CLOSEABLE_MODALS` are touched; every other stray window is REPORTED
    and left alone (see the allowlist's comment — closing an internal Archicad window
    kills the application). WM_CLOSE on a settings dialog is its Cancel, so nothing the
    agent did is committed. Archicad-only; a no-op elsewhere."""
    if TOOL != "archicad":
        return
    try:
        import ctypes
        import ctypes.wintypes as wt
        import psutil
        u = ctypes.windll.user32
        pids = {p.pid for p in psutil.process_iter(["name"])
                if (p.info["name"] or "").lower() == "archicad.exe"}
        if not pids:
            return
        seen = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _):
            if u.IsWindowVisible(h):
                n = u.GetWindowTextLengthW(h)
                if n:
                    b = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(h, b, n + 1)
                    pid = wt.DWORD()
                    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    if pid.value in pids and "archicad 29" not in b.value.lower():
                        seen.append((h, b.value))
            return True

        u.EnumWindows(cb, 0)
        for h, title in seen:
            if title.strip().lower() not in _CLOSEABLE_MODALS:
                print(f"  [modal] leaving unknown window {title!r} alone "
                      f"(not on the closeable allowlist)", flush=True)
                continue
            # CLICK the window's own X. WM_CLOSE is NOT used on an Archicad-owned window:
            # it killed the whole application twice on 2026-08-24 ('Learning Center' and
            # the internal 'DGTransparentWindow'). Clicking the X is the proven-safe path.
            # Safe to drive the mouse here: this runs at case start, before the agent.
            r = wt.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            import pyautogui
            pyautogui.moveTo(r.right - 15, r.top + 14, duration=0.2)
            pyautogui.click()
            # give it a few seconds: a dialog can take a moment to tear down, and a
            # premature check reports a false "still open" (seen on 'Find & Select').
            # Do NOT click twice - if the window did close, the second click lands on
            # whatever is underneath, which is the canvas.
            gone = False
            for _ in range(6):
                time.sleep(1)
                if not u.IsWindow(h) or not u.IsWindowVisible(h):
                    gone = True
                    break
            print(f"  [modal] clicked the X of {title!r} — closed={gone}", flush=True)
    except Exception as e:
        print(f"  [modal] cleanup skipped ({type(e).__name__})", flush=True)


def _close_tapir_palette() -> None:
    """Close Tapir's floating script palette if it is open (WM_CLOSE — no focus steal).

    The palette floats over the CANVAS and eats the GUI agent's clicks. Its visibility is
    Archicad's standard modeless-window persistence, but the loaded Tapir 1.5.3 has the
    known lifecycle bug (fixed upstream in 1.5.7) where the palette REAPPEARS after being
    closed — and the add-on is deliberately pinned (the api_doc corpus and every probed
    behaviour track this exact build), so the fix is not an upgrade: close it
    deterministically before every case. A PostMessage to an absent window is a no-op."""
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.FindWindowW(None, "Tapir Palette")
        if h:
            u.PostMessageW(h, 0x0010, 0, 0)             # WM_CLOSE
            print("  [tapir] closed the floating Tapir Palette", flush=True)
    except Exception:
        pass


def _focus_verified(attempts: int = 6, settle: float = 2.0) -> bool:
    """Bring the application to the FOREGROUND and VERIFY it actually is the active window.

    Each io module's `_focus_*` is best-effort (it prints a warning and returns); for the GUI
    phase that is not enough — every keystroke/click of the agent lands in the active window,
    whatever it is. Retry a few times (the window may still be busy right after a project open),
    and only report success when the ACTIVE window's title names the application."""
    import pygetwindow as gw
    # A cursor PARKED IN A SCREEN CORNER trips pyautogui's fail-safe on the case's first
    # mouse op (observed 2026-08-19: a corner-parked physical mouse burned 12 consecutive
    # cases in minutes — the focus gate verifies fine, then the agent dies instantly).
    # Recenter it OUTSIDE pyautogui (SetCursorPos knows no fail-safe) before the gate; the
    # fail-safe itself stays on — slamming the mouse into a corner DURING a case is still
    # the human's abort switch.
    try:
        import ctypes
        u = ctypes.windll.user32
        u.SetCursorPos(u.GetSystemMetrics(0) // 2, u.GetSystemMetrics(1) // 2)
    except Exception:
        pass
    cfg = _tool()
    for i in range(1, attempts + 1):
        try:
            cfg["focus"]()
            time.sleep(settle)
            active = gw.getActiveWindow()
            title = (active.title if active else "") or ""
            if cfg["window"] in title.lower():
                return True
            print(f"    [focus] attempt {i}/{attempts}: active window is "
                  f"{title!r}, not {TOOL}")
        except Exception as e:
            print(f"    [focus] attempt {i}/{attempts} failed: {type(e).__name__}: {e}")
    return False


def _open_verified(project: Path, attempts: int = 2, settle: float = 3.0) -> bool:
    cfg = _tool()
    for i in range(1, attempts + 1):
        cfg["io"].open_project(project, mode=cfg["open_mode"])
        time.sleep(settle)
        if _opened_ok(project):
            return True
        print(f"    [open] attempt {i}/{attempts}: {TOOL} does not report "
              f"{project.name} open")
    return False


def _agent_argv(case) -> list[str]:
    argv = [sys.executable, "-m", AGENT_MODULE]
    argv += [str(d) for d in case.drawings]      # every view of a multi-drawing case
    if case.instruction:
        argv += ["-i", case.instruction]
    # NO --target: every application's tools are in the agent's pool, and identifying which one
    # is actually running is part of what the benchmark measures. Narrowing here would hand that
    # answer over. The harness still opens an ARCHICAD project and grades the Archicad model —
    # the agent has to work out that that is where it is.
    argv += ["--tools", _cfg()["tools"]]
    # The model: -p/-m on this CLI win over the agent's own defaults ($LLM_PROVIDER /
    # $LLM_MODEL in .env), exactly as they would on a hand-run `python -m authoring_framework`.
    if LLM_OVERRIDE.get("provider"):
        argv += ["-p", LLM_OVERRIDE["provider"]]
    if LLM_OVERRIDE.get("model"):
        argv += ["-m", LLM_OVERRIDE["model"]]
    return argv


def _run_block(mem: dict, started: datetime, seconds: float, rc: int, timed_out: bool,
               early_stop: str | None = None) -> dict:
    """The score file's informational `run` block.

    Field definitions (from the ReAct agent's memory.stats — see react._record_stats):
      tools         = the run's --tools mode (gui-raw | gui-support; older trees also carry
                      the legacy api-* / hybrid-* modes)
      turns         = memory.stats.turns             (LLM round-trips)
      actions       = memory.stats.tool_calls        (tool calls actually executed)
      exec_failures = memory.stats.calls_failed
      by_family     = memory.stats.calls_by_family   (how much of the work went each route)
      `aborted` carries e.g. "turn_budget_exceeded".
    """
    st = mem.get("stats") or {}
    tot = ((st.get("llm") or {}).get("total") or {})
    out = {"started_at": started.strftime("%Y-%m-%dT%H:%M:%S"),
           "agent_seconds": round(seconds, 1),
           "agent_rc": rc,
           "timed_out": timed_out,
           "llm_calls": tot.get("calls"),
           "tokens_in": tot.get("input_tokens"),
           "tokens_out": tot.get("output_tokens"),
           "tokens_cached": tot.get("cache_read_tokens"),
           "tools": st.get("tools"),
           "turns": st.get("turns"),
           "actions": st.get("tool_calls"),
           "write_actions": st.get("write_calls"),
           "support_actions": _support_actions(st),
           "exec_failures": st.get("calls_failed"),
           "by_family": st.get("calls_by_family")}
    if st.get("aborted"):
        out["aborted"] = st.get("aborted")
    elif st.get("gave_up"):
        # the agent ended the run with "RESULT: abandoned" (prompt: WHEN TO GIVE UP) —
        # shown in the scoreboard's aborted column so a deliberate stop is distinguishable
        # from a build the agent believed complete
        out["aborted"] = "agent_gave_up"
        out["gave_up_reason"] = st.get("gave_up") if isinstance(st.get("gave_up"), str) else ""
    if early_stop:
        out["early_stop"] = early_stop     # loop-detector kill (see _LoopDetector)
    if st.get("gui"):   # coordinate frame, wording, screenshot caps + the size actually sent
        out["gui"] = st.get("gui")
    return out


# ---------------------------------------------------------------- grading

def _collected_answer(out: Path) -> str | None:
    """The agent's FINAL TEXT, out of the collected agent_run/memory.json.

    A READ atom's output is that text, not the model: the loop ends on a reply
    carrying no tool calls and stores it as `answer`. It is graded like any other
    checkpoint (`answer_pairs` in the expected_result) and copied into the score
    file, so nothing about a read case needs a human to open memory.json.

    NOT-COLLECTED and DID-NOT-ANSWER are different and must stay so: None means
    there is no run record to read (an older tree — the answer checkpoints go
    UNCHECKED), while "" means the run is there and ended without answering (a
    turn cap, a crash), which for a read atom is a failed deliverable."""
    mj = out / PHASE / "agent_run" / "memory.json"
    if not mj.exists():
        return None
    try:
        return json.loads(mj.read_text(encoding="utf-8")).get("answer") or ""
    except Exception as e:
        print(f"    [warn] could not read the agent's answer: {e}")
        return None


def _grade_saved(cid: str, out: Path, result_pln: Path, run_block: dict | None,
                 reopen: bool = True) -> dict:
    """Grade an ALREADY-SAVED result_<phase>.pln live and write score_<phase>.json.

    `run_block` is carried through verbatim — it describes the agent run that produced the
    project and must survive a pure re-grade (e.g. after a ground-truth correction).
    `reopen=False` (2026-09-02) grades the document that is ALREADY open — right after the
    harness's own Save As that IS the result file, and the caller has verified the
    application reports it open (the wrong-document incident of 2026-08-25 was two
    documents open after a restart; the verification, not the reopen, is what guards it)."""
    base = baselines.load(cid, TOOL)
    got = _tool()["live"](result_pln, reopen=reopen)
    comps = sources.created_composites(got["composites"], base.get("composites"))
    expected = case_io.read_spec(BENCH_ROOT, TOOL, cid).get("expected_result")
    if not expected:
        return {"case": cid, "status": "no-gt"}
    # anchor=revit-only: revit ERs are validated in the drawing frame (hand-drawn
    # envs anywhere); archicad ERs are written in RAW model coordinates.
    answer = _collected_answer(out)
    report = grade(expected, base.get("snapshot") or {}, got["snapshot"],
                   normalize_composites(comps), anchor=(TOOL == "revit"), answer=answer,
                   composites_final=got["composites"],
                   trivial=_trivial_ids(cid, expected, base))
    report.update({"case": cid, "phase": PHASE, "tool": TOOL, "status": "graded",
                   "source": "live",
                   "graded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
    if answer is not None:
        report["answer"] = answer
    if run_block:
        report["run"] = run_block
    (out / f"score_{PHASE}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
    case_eval_md.write(out, PHASE)     # the per-case EVAL.md, fresh with every grading
    print(f"  graded: score={report.get('score')} reward={report.get('reward')} "
          f"{'PASS' if report.get('passed') else 'fail'} "
          f"({report.get('checkpoints_passed')}/{report.get('checkpoints_total')} cps)")
    return report


_TRIVIAL_CACHE: dict[str, set] = {}


def _trivial_ids(cid: str, expected: dict, base: dict) -> set:
    """Which goal checkpoints the START state already satisfies — grade the
    case's own baseline against itself and read the passes off it. They are
    restated preservation duties, not goals, so `grade` moves them into P:
    PCS then scores only the changes the task asks for, and CFR notices when a
    run breaks something that was already right. Cached per case — the probe
    is deterministic and a batch re-grades the same case repeatedly."""
    if cid in _TRIVIAL_CACHE:
        return _TRIVIAL_CACHE[cid]
    # prefer the live probe: the stored baseline predates wall facing and
    # opening swing in the snapshot schema, so it leaves those undecided
    live = trivial_probe.load_trivial(BENCH_ROOT.name, TOOL, cid)
    if live is not None:
        _TRIVIAL_CACHE[cid] = live
        return live
    snap = base.get("snapshot") or {}
    try:
        probe = grade(expected, snap, snap, normalize_composites([]),
                      anchor=(TOOL == "revit"), composites_final=base.get("composites"))
        ids = trivial_from_report(probe)
    except Exception as e:                      # never let the probe fail a grading
        print(f"    [warn] no-op probe failed ({e}); PCS falls back to un-normalised",
              flush=True)
        ids = set()
    _TRIVIAL_CACHE[cid] = ids
    return ids


def _llm_calls(mem: dict) -> int:
    """How many LLM calls the run actually COMPLETED. 0 means the provider never answered —
    llm.py retries a 5xx four times and then lets the exception kill the agent process."""
    return (((mem.get("stats") or {}).get("llm") or {}).get("total") or {}).get("calls") or 0


def _support_actions(st: dict) -> int | None:
    """How many of the run's tool calls used the OPERATIONAL SUPPORT — the packaged API tools
    (family "api", pre-2026-09-21 result trees only) plus `operational_skill_retrieval` (the
    hand-written recipes; `open_software_skill` in older runs). Everything else is the
    raw/neutral channel: the GUI ops and `documentation_retrieval` (official help).
    None when the stats are absent."""
    if not st:
        return None
    fam = st.get("calls_by_family") or {}
    tools_n = st.get("tool_breakdown") or {}
    return (int(fam.get("api") or 0) + int(tools_n.get("operational_skill_retrieval") or 0)
            + int(tools_n.get("open_software_skill") or 0))


def _run_block_from_memory(mem: dict) -> dict:
    """Rebuild the informational run block from a collected agent_run/memory.json — the
    authoritative record of the run that produced result_<phase>.pln. --regrade prefers this
    over the previous score's block: after a rerun whose GRADING step failed, the old score
    (and its run block) describe an OLDER run than the saved project being graded."""
    st = mem.get("stats") or {}
    tot = ((st.get("llm") or {}).get("total") or {})
    out = {"started_at": str(st.get("started_at") or "").replace(" ", "T"),
           "agent_seconds": st.get("duration_s"),
           "agent_rc": None, "timed_out": None,
           "llm_calls": tot.get("calls"),
           "tokens_in": tot.get("input_tokens"),
           "tokens_out": tot.get("output_tokens"),
           "tokens_cached": tot.get("cache_read_tokens"),
           "tools": st.get("tools"),
           "turns": st.get("turns"),
           "actions": st.get("tool_calls"),
           "write_actions": st.get("write_calls"),
           "support_actions": _support_actions(st),
           "exec_failures": st.get("calls_failed"),
           "by_family": st.get("calls_by_family")}
    if st.get("aborted"):
        out["aborted"] = st.get("aborted")
    elif st.get("gave_up"):
        out["aborted"] = "agent_gave_up"
        out["gave_up_reason"] = st.get("gave_up") if isinstance(st.get("gave_up"), str) else ""
    if st.get("gui"):   # coordinate frame, wording, screenshot caps + the size actually sent
        out["gui"] = st.get("gui")
    return out


def regrade(case) -> dict:
    """Re-grade a case from its already-saved result_<phase>.pln — no agent run, no re-save.
    Used when the GROUND TRUTH changed (a task.json fix) or a rerun's grading step failed,
    and the model must be re-scored without spending another agent run."""
    cid = case.id
    out = _case_dir(cid)
    result_pln = out / f"result_{PHASE}{_tool()['ext']}"
    print(f"\n========== {cid} (re-grade only) ==========")
    if not result_pln.exists():
        return {"case": cid, "status": "no-data", "error": f"{result_pln.name} missing"}
    run_block = None
    mj = out / PHASE / "agent_run" / "memory.json"
    if mj.exists():
        try:
            run_block = _run_block_from_memory(json.loads(mj.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"    [warn] could not rebuild the run block from memory.json: {e}")
    if run_block is None:
        sp = out / f"score_{PHASE}.json"
        if sp.exists():
            run_block = json.loads(sp.read_text(encoding="utf-8")).get("run")
    return _grade_saved(cid, out, result_pln, run_block)


def rescue(case, save_wait: float, dialog_delay: float) -> dict:
    """SAVE THE DOCUMENT THE APPLICATION STILL HAS OPEN into result_<phase> and grade it —
    no agent run (2026-09-04). For a case whose agent finished but whose save or grade step
    failed: the VM runner's REPAIR HOLD leaves the guest untouched, the cause is fixed, and
    this turns the still-open model into a score instead of throwing the run away."""
    cid = case.id
    out = _case_dir(cid)
    result_pln = out / f"result_{PHASE}{_tool()['ext']}"
    print(f"\n========== {cid} (rescue: save the open document + grade) ==========")
    run_block = None
    mj = out / PHASE / "agent_run" / "memory.json"
    if mj.exists():
        try:
            run_block = _run_block_from_memory(json.loads(mj.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"    [warn] could not rebuild the run block from memory.json: {e}")
    _dismiss_stray_modals()
    _clear_input_state()
    before_save = result_pln.stat().st_mtime if result_pln.exists() else None
    _tool()["io"].save_as(result_pln, mode=_tool()["save_mode"], save_wait=save_wait,
                          dialog_delay=dialog_delay, confirm_enter=result_pln.exists())
    for _ in range(10):
        if result_pln.exists() and (before_save is None
                                    or result_pln.stat().st_mtime > before_save):
            break
        time.sleep(2.0)
    else:
        return {"case": cid, "status": "save-failed", "run": run_block}
    _clear_input_state()
    reopen = not _opened_ok(result_pln)
    if reopen:
        print("  [grade] the saved result is not the open document — reopening it", flush=True)
    r = _grade_saved(cid, out, result_pln, run_block, reopen=reopen)
    r["rescued"] = True
    return r


# ---------------------------------------------------------------- one case

# EARLY STOP (opt-in: $BENCH_EARLY_STOP=1, default OFF so other machines/batches keep their
# comparability). Kills an agent caught in a PROVEN dead loop instead of letting it grind to
# the turn cap / wall-clock timeout. Detection reads the agent's own `[tools]` batch lines
# (one per turn, full call arguments included) and compares them VERBATIM:
#   1. the identical batch 8 turns in a row      — the observed "mouse_click(x=17, y=470),
#      observation()" echo-chamber
#   2. 15 turns cycling among <=2 distinct batches — the "click A / Esc / click A" two-state
# Signatures carry the coordinates and text, so one changed pixel or character is a new
# batch and neither rule fires: healthy exploration (drifting coordinates) and progressive
# input (a different value each turn) never trigger. At temperature 0 a verbatim repeat is
# a loop the model does not exit. A tripped detector kills the agent down the SAME path as
# a harness timeout — the project is still saved and graded (partial checkpoints count) —
# and the score's run block carries `early_stop` with the reason, so it is auditable.
_EARLY_STOP_ON = os.getenv("BENCH_EARLY_STOP") == "1"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _batch_sig(line: str) -> str | None:
    """The verbatim tool-batch signature of one agent stdout line, or None.
    Matches react.py's per-turn batch line `[tools] call(args), ...` — exactly one space
    after the tag (the startup banner prints two) and not the 'dropped N unusable' notice."""
    t = _ANSI_RE.sub("", line).rstrip()
    if t.startswith("[tools] ") and not t.startswith("[tools]  ") \
            and not t.startswith("[tools] dropped "):
        return t[len("[tools] "):]
    return None


class _LoopDetector:
    IDENTICAL_RUN = 8       # rule 1: same batch this many consecutive turns
    WINDOW = 15             # rule 2: this many consecutive turns...
    MAX_DISTINCT = 2        # ...spent cycling among at most this many distinct batches

    def __init__(self):
        self._last = None
        self._run = 0
        self._recent: list[str] = []

    def feed(self, sig: str) -> str | None:
        """Feed one batch signature; a non-None return is the kill reason."""
        self._run = self._run + 1 if sig == self._last else 1
        self._last = sig
        self._recent.append(sig)
        if len(self._recent) > self.WINDOW:
            self._recent.pop(0)
        if self._run >= self.IDENTICAL_RUN:
            return (f"identical tool batch {self._run} turns in a row: "
                    f"{sig[:80]}")
        if len(self._recent) == self.WINDOW:
            counts = {b: self._recent.count(b) for b in set(self._recent)}
            # every batch in the window must recur (>=3x): a genuine A/B loop alternates
            # ~evenly, while one stray click inside a run of observations must NOT count
            # as a "cycle" (that near-miss is rule 1's territory once the stray ages out)
            if len(counts) <= self.MAX_DISTINCT and min(counts.values()) >= 3:
                return (f"{self.WINDOW} turns cycling among {len(counts)} batch(es): "
                        f"{sig[:80]}")
        return None


def rerun(case, note: str, timeout: float, save_wait: float, dialog_delay: float,
          echo: bool = True) -> dict:
    cid = case.id
    out = _case_dir(cid)
    phase_dir = out / PHASE
    phase_dir.mkdir(parents=True, exist_ok=True)
    result_pln = out / f"result_{PHASE}{_tool()['ext']}"
    print(f"\n========== {cid} ==========")
    print(f"  drawings={[d.name for d in case.drawings] or 'text-only'}  pln={case.pln.name}")

    # 1) open the case's START project (verified)
    # Both of the previous case's leftovers block the Tapir open, and they are different
    # things: a stray DIALOG (closed by title, allowlisted) and a half-finished TOOL GESTURE
    # (Esc'd out). Only the dialog was handled here, so a Marquee left waiting for its
    # rotation vector still failed the next case with `OpenProject timed out` — seen on the
    # gpt-5.6-terra atomic run, 2026-08-29.
    _dismiss_stray_modals()     # a modal left by the previous case blocks the Tapir open
    _clear_input_state()        # ...and so does a tool the previous case left mid-gesture
    to_open = case.pln
    if _tool().get("work_on_copy"):
        # the agent works on the RESULT file from the start (see TOOLS): copy the pristine
        # start project there and open the copy — the save is then an in-place one
        for stale in (result_pln, result_pln.with_suffix(".bpn"), result_pln.with_suffix(".pln.lck")):
            if stale.exists():
                stale.unlink()
        result_pln.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(case.pln, result_pln)
        to_open = result_pln
        print(f"  [copy] {case.pln.name} -> {result_pln.name} (the agent edits the result file)")
    if not _open_verified(to_open):
        return {"case": cid, "status": "open-failed"}
    _close_tapir_palette()      # the floating script palette eats canvas clicks (see helper)

    env = None
    # (The per-case materials re-dump was RETIRED 2026-08-11: the existing_walls skill doc it
    # refreshed has been read by nothing since the role pipeline died — on the GUI route the
    # agent reads the library off the application's own dialogs, which is the point of the
    # interface axis.)
    # The subset's flat turn cap (TURNS_BY_SUBSET); --max-turns overrides it for the batch.
    subset = Path(case.dir).parents[1].name
    turns = MAX_TURNS_OVERRIDE or TURNS_BY_SUBSET.get(subset, TURNS_DEFAULT)
    # PYTHONUNBUFFERED: the agent's stdout goes into a PIPE, which Python block-buffers by
    # default — a 15-minute case then shows NOTHING in the tee'd log until the process exits,
    # indistinguishable from a hang (observed 2026-08-24: a live sketch-mode run read as
    # "stuck" and was interfered with). Line-buffered output keeps the batch log live.
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if turns:
        env["AGENT_MAX_TURNS"] = str(turns)
        print(f"  AGENT_MAX_TURNS={turns}"
              + (" (--max-turns)" if MAX_TURNS_OVERRIDE else f" ({subset})"))
    if _cfg().get("drives_ui"):
        # the GUI agent drives the real mouse/keyboard — Archicad MUST be the foreground
        # window when it takes its first screenshot (a Tapir open does not raise the window).
        # HARD GATE: if Archicad cannot be verified as the ACTIVE window, the case is
        # aborted before the agent launches — an agent clicking into whatever else happens
        # to be focused is not just a lost case, it is keyboard/mouse input into arbitrary
        # applications.
        if not _focus_verified():
            return {"case": cid, "status": "focus-failed"}

    # 2) run the agent
    argv = _agent_argv(case)
    (phase_dir / "command.txt").write_text(" ".join(argv), encoding="utf-8")
    run_before = _current_run_dir()
    started, t0 = datetime.now(), time.time()
    timed_out, rc = False, None
    with open(phase_dir / "stdout.log", "w", encoding="utf-8") as fh:
        # STREAM the agent's stdout: tee every line into the log AND (echo) onto this
        # console, so a live batch shows each run as it happens instead of a silent wait.
        proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env)

        detector = _LoopDetector() if _EARLY_STOP_ON else None
        stop = {"reason": None}

        def _pump():
            for line in proc.stdout:
                fh.write(line)
                fh.flush()
                if echo:
                    print("    | " + line.rstrip(), flush=True)
                if detector is not None and stop["reason"] is None:
                    sig = _batch_sig(line)
                    if sig is not None:
                        reason = detector.feed(sig)
                        if reason:
                            stop["reason"] = reason
                            fh.write(f"\n[harness] EARLY STOP — {reason}\n")
                            fh.flush()
                            if echo:
                                print(f"    | [harness] EARLY STOP — {reason}", flush=True)
                            proc.kill()

        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            timed_out, rc = True, -1
        pump.join(timeout=10)
        early_stop = stop["reason"]
        if timed_out:
            fh.write("\n[harness] TIMEOUT — agent killed\n")
            if echo:
                print("    | [harness] TIMEOUT — agent killed", flush=True)
    secs = time.time() - t0
    tag = "(TIMEOUT) " if timed_out else f"(EARLY STOP) " if early_stop else ""
    print(f"  agent rc={rc} {tag}{secs:.0f}s")

    # 3) collect the agent's run dir. An agent that exits NON-ZERO with any code but the
    # provider-outage one before it made a single LLM call did not fail at the task — it
    # refused to start (a missing help corpus, an unknown provider, a missing key). That is a
    # CONFIGURATION error that hits every case identically: report the agent's last lines
    # and let the batch loop stop instead of grading or retrying.
    def _startup_error(mem_or_none):
        if rc in (0, AGENT_EXIT_LLM_FAILURE) or timed_out or early_stop:
            return None
        if mem_or_none is not None and _llm_calls(mem_or_none) > 0:
            return None
        lines = [ln.rstrip() for ln in (phase_dir / "stdout.log").read_text(
            encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        tail = lines[-6:]
        print("  !! the agent exited before its first LLM call — a configuration error, "
              "not a model result:")
        for ln in tail:
            print(f"     {ln}")
        stop = next((ln.strip() for ln in reversed(lines) if "[stop]" in ln), None)
        return {"case": cid, "status": "agent-startup-error", "agent_rc": rc,
                "error": stop or (tail[-1].strip() if tail else f"agent rc={rc}")}
    run_dir = _current_run_dir()
    if run_dir is None or run_dir == run_before:
        return _startup_error(None) or {"case": cid, "status": "no-run", "agent_rc": rc}
    dest = phase_dir / "agent_run"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run_dir, dest)
    if not (dest / "memory.json").exists():
        return _startup_error(None) or {"case": cid, "status": "no-run", "agent_rc": rc}
    mem = json.loads((dest / "memory.json").read_text(encoding="utf-8"))
    bad = _startup_error(mem)
    if bad:
        return bad

    # 3b) AN LLM OUTAGE IS NOT A MODEL RESULT. Two signals: the agent died without completing
    # a single LLM call (legacy detection — the provider 5xx'd through every retry in llm.py
    # before turn 1), or it died MID-RUN and marked mem["aborted"]="llm_failure" (react.py,
    # 2026-08-11 — this is the case that used to slip through and get graded half-done, which
    # poisoned the v2 tree on 2026-08-10). NOT on a harness TIMEOUT: a killed agent never
    # writes stats, so _llm_calls==0 there too, and without this guard every wall-clock
    # timeout (a legitimate model result) would masquerade as an outage — two consecutive
    # cx5 timeouts would then stop the whole batch. The half-run must not be saved or
    # graded: park stale artefacts as *.stale (a resume into an existing tree must not LOSE
    # the previous batch's good score to one provider blip) and let main() retry or stop.
    # (an EARLY-STOP kill is a legitimate model result too — same exemption as a timeout)
    if rc != 0 and not timed_out and not early_stop and (
            rc == AGENT_EXIT_LLM_FAILURE
            or mem.get("aborted") == "llm_failure"
            or (mem.get("stats") or {}).get("aborted") == "llm_failure"):
        print("  !! LLM provider died (outage, not a model result) — not saved, not graded")
        for stale in (result_pln, out / f"score_{PHASE}.json"):
            if stale.exists():
                parked = stale.with_suffix(stale.suffix + ".stale")
                if parked.exists():
                    parked.unlink()
                stale.rename(parked)
        return {"case": cid, "status": "llm-unreachable", "agent_rc": rc,
                "run": _run_block(mem, started, secs, rc, timed_out, early_stop)}

    # 4) save the finished project (delete the old file first: no overwrite dialog —
    #    unless the agent has been working ON the result file, which is then saved in place).
    #    A killed agent leaves whatever it had open — a Composites dialog, a half-drawn
    #    wall — and Tapir answers 4001 to everything while it does, so the in-place save
    #    (and the add-in's /saveas on Revit) would be refused. Clear the UI first; the same
    #    two calls already guard the grade below.
    _dismiss_stray_modals()
    _clear_input_state()
    if not _tool().get("work_on_copy"):
        for stale in (result_pln, out / f"result_{PHASE}.bpn"):
            if stale.exists():
                stale.unlink()
    before_save = result_pln.stat().st_mtime if result_pln.exists() else None
    _tool()["io"].save_as(result_pln, mode=_tool()["save_mode"], save_wait=save_wait,
                        dialog_delay=dialog_delay, confirm_enter=result_pln.exists())
    saved = False
    for _ in range(10):                                   # wait for the file to appear/change
        if result_pln.exists() and (before_save is None
                                    or result_pln.stat().st_mtime > before_save):
            saved = True
            break
        time.sleep(2.0)
    if not saved:
        return {"case": cid, "status": "save-failed", "agent_rc": rc,
                "run": _run_block(mem, started, secs, rc, timed_out, early_stop)}

    # Grading reads the project through the API, so the application has to be answering.
    # The agent frequently leaves a tool mid-gesture, which Tapir rejects as 4001 "ongoing
    # user input" — the save above still succeeds (it goes through the GUI), and the stall
    # then shows up here, at the grade, as "archicad is not answering".
    _clear_input_state()

    # 5) grade LIVE. After Save As the open document IS the result file; when the
    #    application confirms that (by path on Archicad, by title on Revit) it is read in
    #    place — the reopen round trip (~15 s, plus a keyboard dance on Revit before the
    #    /open route) only happens when the check fails.
    reopen = not _opened_ok(result_pln)
    if reopen:
        print("  [grade] the saved result is not the open document — reopening it", flush=True)
    report = _grade_saved(cid, out, result_pln,
                          _run_block(mem, started, secs, rc, timed_out, early_stop),
                          reopen=reopen)
    (out / "source.txt").write_text(note, encoding="utf-8")
    return report


def _discard_open_changes(case, r, a) -> None:
    """The dead half-run left UNSAVED changes in the open document; park them in a throwaway
    save-as so the retry's open of the start project cannot hit a save-changes prompt (and,
    on Revit, so the start file is no longer the open document). Skipped only when the run
    record POSITIVELY says nothing was written — unknown (stats missing after a kill) means
    the run may have written plenty, so discard defensively."""
    if (r.get("run") or {}).get("write_actions") == 0:
        return
    throwaway = _case_dir(case.id) / PHASE / f"discard_llmfail{_tool()['ext']}"
    try:
        throwaway.parent.mkdir(parents=True, exist_ok=True)
        if throwaway.exists():
            throwaway.unlink()
        _tool()["io"].save_as(throwaway, mode=_tool()["save_mode"], save_wait=a.save_wait,
                              dialog_delay=a.dialog_delay, confirm_enter=False)
        print(f"  [llm-retry] half-run changes parked in {throwaway.name} (throwaway)")
    except Exception as e:
        print(f"  [llm-retry] discard save failed ({e}) — the reopen may hit a save prompt")


# ---------------------------------------------------------------- keep-awake sidecar

def _start_keep_awake():
    """Spawn keep_awake.py BESIDE this batch (Windows only): it blocks display/system sleep
    and nudges the mouse so the machine's inactivity lock (900 s policy here) cannot kill the
    batch — a locked session has no activatable window, and every remaining case would die at
    its project open. Terminated via atexit on any normal/exception exit; the child's
    `--hours 24` self-limit is the backstop for a hard-killed runner, so an orphaned nudger
    cannot hold the machine awake forever."""
    if sys.platform != "win32":
        return None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(HERE / "keep_awake.py"), "--hours", "24"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:                       # a missing/broken sidecar must not stop a batch
        print(f"[keep_awake] could not start ({e}) — the idle lock is NOT held off", flush=True)
        return None
    print(f"[keep_awake] running alongside the batch (pid {proc.pid}; sleep blocked, "
          f"mouse nudged every 60s)", flush=True)
    atexit.register(_stop_keep_awake, proc)
    return proc


def _stop_keep_awake(proc):
    if proc is not None and proc.poll() is None:
        proc.terminate()


# ---------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--phase", choices=list(PHASES) + list(PHASE_ALIASES), required=True,
                   help="REQUIRED — which arm to run/grade: gui-raw (no retrieval tool — w/o support), "
                        "gui-docs (+ official documentation) or gui-support (+ documentation "
                        "and the hand-written operational skills). It "
                        "is passed straight to the agent's --tools and names the per-case "
                        "files (result_<phase>.* / score_<phase>.json). The api-* / hybrid-* "
                        "phases are LEGACY: the agent can no longer run them, they are "
                        "accepted only with --regrade to re-grade existing result trees")
    p.add_argument("--bench-root", type=Path, default=None, metavar="DIR",
                   help="dataset tree the case ids resolve against (default "
                        "bench_cases/reasoning_tasks). Pass bench_cases/atomic_tasks for the atomic "
                        "tree or bench_cases/long-seq_tasks — all three share the layout")
    p.add_argument("-p", "--provider", default=None,
                   help="LLM provider for the agent (openai | anthropic | gemini | qwen | meta | "
                        "evocua | opencua); default: $LLM_PROVIDER from .env")
    p.add_argument("-m", "--model", default=None,
                   help="model id for the agent (e.g. claude-opus-5); default: the provider's "
                        "default or $LLM_MODEL from .env")
    p.add_argument("--max-turns", type=int, default=None, metavar="N",
                   help="ONE turn cap for every case of this batch, replacing the subset's "
                        "default (atomic_tasks 100, reasoning_tasks / long-seq_tasks 300)")
    p.add_argument("--only", nargs="*", default=None, help="case ids to re-run")
    p.add_argument("--results-dir", type=Path, default=None, metavar="DIR",
                   help="results tree to write into (default: results/<tool>_bycase_<phase>). "
                        "Give a fresh dir to keep the previous batch intact and pass THAT as "
                        "--eval-baseline for the delta column")
    p.add_argument("--from-file", type=Path, default=None,
                   help="file with one case id per line (# comments allowed)")
    p.add_argument("--note", default="", help="source.txt provenance line for these runs")
    p.add_argument("--timeout", type=float, default=None,
                   help="agent timeout per case (s); default per phase (api 1800, gui 3600)")
    p.add_argument("--save-wait", type=float, default=8.0)
    p.add_argument("--dialog-delay", type=float, default=1.5)
    p.add_argument("--focus-countdown", type=float, default=5.0)
    p.add_argument("--progress", type=Path, default=None,
                   help="append one JSON line per finished case here (resumable batches)")
    p.add_argument("--regrade", action="store_true",
                   help="do NOT re-run the agent: re-grade each case's existing "
                        "result_<phase>.pln|.rvt (use after a task.json fix)")
    p.add_argument("--rescue", action="store_true",
                   help="do NOT run the agent: save the document the application still has "
                        "OPEN into result_<phase> and grade it (after a repair hold)")
    p.add_argument("--wait-for-app", type=float, default=0.0, metavar="MINUTES",
                   help="wait (up to N minutes) for Archicad to answer before starting, and "
                        "again whenever a case fails because the application went away — so "
                        "an application crash pauses the batch instead of failing every "
                        "remaining case")
    p.add_argument("--app-settle", type=float, default=45.0, metavar="SECONDS",
                   help="grace period after Archicad reappears (recovery dialog, project "
                        "load) before driving it again")
    p.add_argument("--llm-retries", type=int, default=1, metavar="N",
                   help="when a case dies on an LLM-provider outage (status llm-unreachable "
                        "— 5xx/timeout through every retry in the agent's llm layer), wait "
                        "--llm-retry-wait, DISCARD the half-modified project (throwaway "
                        "save-as, then a fresh open of the start project) and re-run the "
                        "case, up to N times (default 1; 0 disables)")
    p.add_argument("--llm-retry-wait", type=float, default=120.0, metavar="SECONDS",
                   help="pause before an LLM-outage retry, giving the provider time to "
                        "recover (default 120)")
    p.add_argument("--eval-md-header", type=Path, default=None, metavar="HEADER_MD",
                   help="header file for the EVAL_RESULTS.md regeneration (default: "
                        "<results>/header.md when it exists)")
    p.add_argument("--eval-baseline", type=Path, default=None, metavar="RESULTS_TREE",
                   help="baseline results tree for EVAL_RESULTS.md's delta column (default: "
                        "results/archi/archicad_bycase_api_baseline_e5b0410 when it exists)")
    p.add_argument("--no-eval-md", action="store_true",
                   help="do NOT regenerate <results>/EVAL_RESULTS.md after each case "
                        "(regeneration is the default)")
    p.add_argument("--quiet", action="store_true",
                   help="do not echo the agent's stdout to this console (it always goes to "
                        "the per-case stdout.log)")
    p.add_argument("--no-keep-awake", action="store_true",
                   help="do not auto-start the keep_awake.py sidecar (e.g. one is already "
                        "running by hand)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    # the agent prints arrows/checkmarks; a cp1252 console would crash the echo
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # An unattended batch must never block on a driver's manual-fallback input() — make the
    # drivers raise instead (the exception becomes an ordinary open/save failure the retry
    # machinery handles).
    os.environ["BENCH_NONINTERACTIVE"] = "1"

    global PHASE, TOOL, RESULTS_OVERRIDE, BENCH_ROOT, MAX_TURNS_OVERRIDE, LLM_OVERRIDE
    MAX_TURNS_OVERRIDE = a.max_turns
    LLM_OVERRIDE = {"provider": a.provider, "model": a.model}
    if a.bench_root:
        BENCH_ROOT = a.bench_root.resolve()
        # baselines.py resolves env dirs off its OWN root constant, so it has to follow —
        # otherwise a case would be graded against the main tree's baseline (or none).
        baselines.BENCH_CASES = BENCH_ROOT
        # the bench root may live OUTSIDE the repo (the VM bench copies each case into a
        # guest-local workspace), so never assume it is a subpath of ROOT
        shown = (BENCH_ROOT.relative_to(ROOT) if BENCH_ROOT.is_relative_to(ROOT)
                 else BENCH_ROOT)
        print(f"[dataset] {shown}")
    PHASE = PHASE_ALIASES.get(a.phase, a.phase)
    if PHASE != a.phase:
        print(f"[phase] legacy name {a.phase!r} -> {PHASE!r} (results tree/files use the "
              f"new name; pass --results-dir to target an old tree)")
    if PHASES[PHASE].get("legacy") and not (a.regrade or a.rescue or a.dry_run):
        sys.exit(f"--phase {PHASE} is LEGACY: the agent framework is GUI-only (gui-raw / "
                 f"gui-docs / gui-support). It is accepted only with --regrade, to re-grade an existing "
                 f"result tree.")
    if a.results_dir:
        RESULTS_OVERRIDE = a.results_dir.resolve()
    # WHICH APPLICATION: detected, never a flag. The harness must know (it opens the project and
    # grades the result); the AGENT must not be told (working it out from the model state is part
    # of what is being measured), so this never reaches the agent's command line.
    TOOL = _detect_tool()
    if not _app_up():
        # A dialog, a floating palette or a half-finished tool gesture left over by an EARLIER
        # batch makes Tapir answer 4001 to everything, which reads here as "not answering".
        # The cleanup that fixes exactly this used to run only at CASE open — i.e. after this
        # gate had already aborted the whole arm (2026-08-29: a leftover 'Composites' dialog
        # from an interrupted run killed the resumed chain in its first second). Clear first,
        # then believe the probe.
        print("  [preflight] the application is not answering — clearing leftover UI state")
        _dismiss_stray_modals()
        _close_tapir_palette()
        _clear_input_state()
        if not _app_up():
            print(f"[abort] detected {TOOL} as the live application, but it is not answering. "
                  f"Open it (and, for Revit, make sure the BimAgent add-in is serving) and retry.")
            return 2
        print("  [preflight] cleared — the application answers now")
    print(f"[tool] {TOOL} (detected — the agent is NOT told; it has the whole pool)")
    if a.timeout is None:
        a.timeout = _cfg()["timeout"]
    _results_dir().mkdir(parents=True, exist_ok=True)

    ids = list(a.only or [])
    if a.from_file:
        # utf-8-SIG, not utf-8: a case list written by Windows PowerShell's `Set-Content
        # -Encoding utf8` carries a BOM, which glued itself to the FIRST id and made the
        # whole arm abort with "unknown/not-runnable case(s)" (2026-08-29).
        ids += [ln.strip() for ln in a.from_file.read_text(encoding="utf-8-sig").splitlines()
                if ln.strip() and not ln.startswith("#")]
    if not ids:
        p.error("give --only and/or --from-file")
    seen, order = set(), []
    for c in ids:                                        # de-dup, keep the given order
        if c not in seen:
            seen.add(c)
            order.append(c)

    cases = {c.id: c for c in discover_cases(BENCH_ROOT, tool=TOOL)
             if c.runnable}
    missing = [c for c in order if c not in cases]
    if missing:
        p.error(f"unknown/not-runnable case(s): {', '.join(missing)}")
    todo = [cases[c] for c in order]

    print(f"re-running {len(todo)} case(s) [{TOOL} · phase={PHASE}] into {_results_dir()}")
    for c in todo:
        print(f"  {c.id:26s} {', '.join(d.name for d in c.drawings) or 'text-only'}")
    if a.dry_run:
        return 0
    if not a.note and not a.regrade and not a.rescue:
        p.error("--note is required (it becomes each case's source.txt provenance line)")

    if not a.no_keep_awake:
        _start_keep_awake()

    if a.wait_for_app and not _wait_for_app(a.wait_for_app, a.app_settle):
        print(f"{TOOL} never came back — nothing run.")
        return 1
    if a.focus_countdown > 0:
        print(f"\nLIVE run: {TOOL} must be OPEN with no modal dialog. "
              f"Starting in {a.focus_countdown:.0f}s ...")
        time.sleep(a.focus_countdown)

    # statuses that mean "the application, not the agent, is the problem"
    # ("llm-unreachable" is deliberately NOT here: the BIM app is fine — it gets its OWN
    #  retry loop below, with a recovery pause and a discard of the half-run's changes.)
    _APP_DEAD = {"open-failed", "save-failed", "no-run", "error", "focus-failed"}
    done = []
    llm_dead = 0
    for i, c in enumerate(todo, 1):
        print(f"\n### [{i}/{len(todo)}] {c.id}", flush=True)
        try:
            r = (rescue(c, a.save_wait, a.dialog_delay) if a.rescue
                 else regrade(c) if a.regrade
                 else rerun(c, a.note, a.timeout, a.save_wait, a.dialog_delay,
                            echo=not a.quiet))
        # SystemExit included: the Revit client's connect() upgrades "add-in unreachable" to
        # SystemExit (right for the AGENT process at startup, but here it is one case's
        # grading step) — without catching it, one Revit crash mid-batch kills the whole
        # batch instead of engaging the wait-for-app retry below.
        except (Exception, SystemExit) as e:             # one bad case must not kill the batch
            r = {"case": c.id, "status": "error", "error": f"{type(e).__name__}: {e}"}
            print(f"  !! {r['error']}", flush=True)
        if r.get("status") == "agent-startup-error":
            # the same configuration error would stop every remaining case the same way
            done.append(r)
            print(f"\nstopping the batch: the agent cannot start ({r.get('error')}). Fix the "
                  "configuration (see the lines above) and re-run.", flush=True)
            break
        # LLM-OUTAGE RETRY (2026-08-11): the provider (a 5xx, a gateway timeout) died
        # mid-case. The half-run was neither saved nor graded (rerun 3b); discard its unsaved
        # changes and give the case a fresh start once the provider has had time to recover.
        for att in range(1, (0 if a.regrade else max(0, a.llm_retries)) + 1):
            if r.get("status") != "llm-unreachable":
                break
            print(f"  [llm-retry {att}/{a.llm_retries}] provider outage mid-case — waiting "
                  f"{a.llm_retry_wait:.0f}s, then discarding the half-run and re-running "
                  f"{c.id}", flush=True)
            time.sleep(a.llm_retry_wait)
            _discard_open_changes(c, r, a)
            try:
                r = rerun(c, a.note, a.timeout, a.save_wait, a.dialog_delay,
                          echo=not a.quiet)
            except (Exception, SystemExit) as e:
                r = {"case": c.id, "status": "error", "error": f"{type(e).__name__}: {e}"}
                print(f"  !! {r['error']}", flush=True)
        # The application (or the desktop) went away mid-batch. Three distinct paths:
        #   * REVIT DEAD (crash policy 2026-08-08): a case whose agent already RAN is a
        #     zero-credit FAIL — its stats stand as of the crash, no retry (the crash is the
        #     environment's failure, and a GUI re-run costs 10+ minutes). Only a case that
        #     never started (open-failed) is retried. Revit is force-restarted either way.
        #   * app DEAD, other tool: wait for it to come back, then retry the case.
        #   * app ALIVE but focus lost / pyautogui fail-safe (a human at the machine):
        #     wait until activation verifies again, then retry.
        retry_ok = False
        if a.wait_for_app and r.get("status") in _APP_DEAD:
            if not _app_up() and TOOL == "revit":
                came_back = _restart_revit(a.wait_for_app, a.app_settle)
                if r.get("status") == "open-failed":
                    retry_ok = came_back
                else:
                    r = _crash_fail(c)
            elif not _app_up():
                retry_ok = _wait_for_app(a.wait_for_app, a.app_settle)
            else:
                retry_ok = _cfg().get("drives_ui") and _wait_for_focus(a.wait_for_app)
        if retry_ok:
            print(f"  [retry] {c.id} after the application/desktop came back", flush=True)
            try:
                r = (rescue(c, a.save_wait, a.dialog_delay) if a.rescue
                     else regrade(c) if a.regrade
                     else rerun(c, a.note, a.timeout, a.save_wait, a.dialog_delay,
                                echo=not a.quiet))
            except (Exception, SystemExit) as e:         # same contract as the first attempt
                r = {"case": c.id, "status": "error", "error": f"{type(e).__name__}: {e}"}
                print(f"  !! {r['error']}", flush=True)
        done.append(r)
        if a.progress:
            with open(a.progress, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: r.get(k) for k in
                                     ("case", "status", "score", "passed", "reward",
                                      "checkpoints_passed", "checkpoints_total", "error")}) + "\n")
        if not a.no_eval_md:
            # regenerate the results tree's EVAL_RESULTS.md IMMEDIATELY after each case, so
            # the summary document is live during the batch (a failure must not kill the run).
            # Header: --eval-md-header, else <results>/header.md when present (edit THAT file
            # to change the document's narrative block). Baseline for the delta column:
            # --eval-baseline, else the committed e5b0410 tree when present.
            try:
                from reports import gen_eval_results
                gargs = [str(_results_dir()), "--phase", PHASE, "--tool", TOOL,
                         "--bench-root", str(BENCH_ROOT)]
                hdr = a.eval_md_header or (_results_dir() / "header.md")
                if Path(hdr).exists():
                    gargs += ["--header-file", str(hdr)]
                base = a.eval_baseline or (HERE / "results" / "archi"
                                           / "archicad_bycase_api_baseline_e5b0410")
                if Path(base).is_dir():
                    gargs += ["--baseline", str(base)]
                gen_eval_results.main(gargs)
            except Exception as e:
                print(f"  [eval-md regen failed: {e}]", flush=True)

        # A dead LLM provider hits every remaining case identically, so churning through the
        # list costs a minute each and leaves nothing behind. One case is tolerated (a single
        # blip can outlast llm.py's ~15 s of retries); the SECOND in a row stops the batch, so
        # the rest of the list stays unrun and resumes cleanly once the provider is back.
        if r.get("status") == "llm-unreachable":
            llm_dead += 1
            if llm_dead >= 2:
                print(f"\n!! the LLM provider is not answering — batch STOPPED after {c.id}. "
                      f"{len(todo) - i} case(s) left unrun; relaunch with --from-file (the "
                      f"unrun cases + the {llm_dead} that hit the outage) once it is back.",
                      flush=True)
                break
        else:
            llm_dead = 0

    ok = [r for r in done if r.get("status") == "graded"]
    print(f"\n=== finished: {len(ok)}/{len(done)} graded, "
          f"{sum(1 for r in ok if r.get('passed'))} passed ===")
    for r in done:
        if r.get("status") != "graded":
            print(f"  !! {r.get('case')}: {r.get('status')} {r.get('error', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
