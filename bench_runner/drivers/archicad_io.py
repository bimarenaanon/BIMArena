"""Open / save the live Archicad project for a bench run.

Three modes:

- `gui`     (recommended) — drive Archicad's own Open / Save-As dialogs by keyboard,
            exactly as a human would: Ctrl+O -> paste path -> Enter -> wait; agent runs;
            Ctrl+Shift+S -> paste path -> Enter -> wait. Fully unattended once Archicad is
            open. Uses pyautogui + pygetwindow + pyperclip (all in the venv).
- `manual`  — the harness pauses and asks you to open / save by hand, then press Enter.
- `tapir`   — send Tapir `OpenProject` / `SaveProjectAsFile` to the running instance (if
            your Tapir build exposes them; falls back to a manual prompt otherwise).

The path is put on the CLIPBOARD and pasted (Ctrl+A, Ctrl+V) so the keyboard layout never
mangles the colons/backslashes.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

try:
    from bench_runner.backend.archicad.client import ArchicadClient
except Exception:  # import resolved at runtime via sys.path
    ArchicadClient = None


# ---------------------------------------------------------------- manual / tapir

def _prompt(msg: str) -> None:
    """Ask the human to do it by hand. UNDER A BATCH ($BENCH_NONINTERACTIVE=1) this RAISES
    instead: on an interactive console `input()` would block the unattended batch forever
    (the EOFError branch fires only when there is no console at all), whereas an exception
    becomes an ordinary open-failed/save-failed the runner's retry machinery handles."""
    if os.getenv("BENCH_NONINTERACTIVE", "0") == "1":
        raise RuntimeError(f"manual step required but the batch is unattended: {msg}")
    print(f"\n  >>> {msg}\n      press Enter when done ...", flush=True)
    try:
        input()
    except EOFError:
        print("      [non-interactive: continuing]", flush=True)


def _tap(cmd: str, params: dict):
    if ArchicadClient is None:
        raise RuntimeError("ArchicadClient import failed (run from the repo root).")
    return ArchicadClient.connect().tap(cmd, params)


# ---------------------------------------------------------------- gui automation

def _focus_archicad() -> bool:
    """Bring the Archicad APP window to the foreground so keystrokes land in it.

    Matching: the app's window title is "<project> - Archicad <version>", so require the
    title to END that way — a plain "archicad" substring also matched e.g. a browser tab or
    an editor with an *.archicad.md file open (observed live: a Chrome tab named
    "...walls.archicad.md ... - Google Chrome" out-sorted the real app window).

    Foreground: Windows refuses SetForegroundWindow from a background process while another
    app holds the foreground lock — press ALT first (releases the lock), and fall back to a
    minimize/restore cycle, which the OS always allows to end up in front."""
    import re as _re

    import pyautogui
    import pygetwindow as gw
    wins = [w for w in gw.getAllWindows()
            if w.title and _re.search(r"archicad\s*\d+\s*$", w.title.lower())]
    for w in wins:
        try:
            if getattr(w, "isMinimized", False):
                w.restore()
                time.sleep(0.4)
            pyautogui.press("alt")           # release the foreground lock
            w.activate()
            time.sleep(0.4)
            active = gw.getActiveWindow()
            if active and active.title == w.title:
                return True
            w.minimize()                     # the always-allowed fallback
            time.sleep(0.4)
            w.restore()
            time.sleep(0.6)
            active = gw.getActiveWindow()
            if active and active.title == w.title:
                return True
        except Exception:
            continue
    print("  [gui: could not find/activate an Archicad APP window — is it open?]")
    return False


def _paste_path(path: str) -> None:
    # The Save/Open dialog opens with the default filename already SELECTED, so pasting
    # replaces it. (Do NOT press Ctrl+A first — in Archicad's dialog it deselects and the
    # path gets appended to the old name, e.g. "archicad.plnC:\...\result_api.pln".)
    import pyautogui
    import pyperclip
    pyperclip.copy(path)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")   # paste the full path over the pre-selected name
    time.sleep(0.3)


def _gui_open(pln: Path, open_wait: float, dialog_delay: float) -> None:
    import pyautogui
    _focus_archicad()
    pyautogui.hotkey("ctrl", "o")            # File > Open
    time.sleep(dialog_delay)                 # let the Open dialog appear
    time.sleep(1.0)                          # extra settle: dialog ready to accept input
    _paste_path(str(pln))
    pyautogui.press("enter")                 # open it
    print(f"  [gui] Ctrl+O -> {pln.name} -> Enter; waiting {open_wait}s for load")
    time.sleep(open_wait)


def _window_type():
    """Tapir GetCurrentWindowType, or None when Tapir does not answer."""
    try:
        return (_tap("GetCurrentWindowType", {}) or {}).get("currentWindowType")
    except BaseException:
        return None


def _ensure_plan_window() -> None:
    """Bring the ACTIVE storey's FLOOR PLAN to the front before any save (2026-09-04).
    Four runs ended with the agent's final check in the 3D window ([3D / All] active):
    there Archicad's Save / Save As act on the 3D view, so Tapir's SaveProject answered OK
    without writing the .pln and the keyboard Save As wrote nothing either — the models
    were lost. A bare F2 (Window > Floor Plan) did not switch it on the guest, so the
    switch goes through Tapir: GetStories.actStory -> ChangeWindow to that storey's Project
    Map item (the backend's set_active_story, which also CONFIRMS the active storey did not
    change — the grader keys on it), verified with GetCurrentWindowType; F2 is the fallback
    when Tapir is not answering."""
    import pyautogui
    wt = _window_type()
    if wt == "FloorPlan":
        return
    # 2026-09-07: the window type is None when the agent leaves a SCHEDULE window in front
    # (GetCurrentWindowType has no name for it) — Save As from there wrote an .xlsx, not the
    # .pln (two Sonnet inspect_project4 runs). So the Tapir switch is attempted whatever the
    # reported type, and the keyboard fallback sends Esc first (a schedule's cell editor
    # swallows a bare F2) and retries once.
    switched = False
    if ArchicadClient is not None:
        try:
            from bench_runner.backend.archicad.actions import stories as _st
            client = ArchicadClient.connect()
            st = _st.get_stories(client)
            act = st.get("actStory") if st.get("ok") else None
            if act is not None:
                r = _st.set_active_story(client, act)
                switched = bool(r.get("ok"))
                if not switched:
                    print(f"  [window] ChangeWindow to storey {act} failed: {r.get('error')}")
        except BaseException as e:
            print(f"  [window] Tapir window switch failed ({e.__class__.__name__}: {e})")
    for attempt in range(2):
        if switched and _window_type() == "FloorPlan":
            break
        _focus_archicad()
        pyautogui.press("esc")                   # leave a schedule cell / pet palette
        time.sleep(0.5)
        pyautogui.press("f2")                    # Window > Floor Plan
        time.sleep(2.0)
        if _window_type() == "FloorPlan":
            break
    after = _window_type()
    print(f"  [window] {wt or '?'} -> {after or '?'} before the save"
          + ("" if after == "FloorPlan" else "  (NOT a floor plan — the save may not write)"),
          flush=True)


def _gui_save_as(dest: Path, save_wait: float, dialog_delay: float,
                 confirm_enter: bool) -> None:
    import pyautogui
    _focus_archicad()
    # clear any pending tool / input state before saving (3x Esc, 1s apart)
    for _ in range(3):
        pyautogui.press("esc")
        time.sleep(1.0)
    pyautogui.hotkey("ctrl", "shift", "s")   # File > Save as...
    time.sleep(dialog_delay)
    time.sleep(1.0)                          # extra settle: dialog ready to accept input
    _paste_path(str(dest))
    pyautogui.press("enter")
    if confirm_enter:
        # The destination already exists (the work-on-copy flow copies the start file to
        # the result path BEFORE the run, so this is the normal case): Archicad asks
        # "result.pln already exists. Do you want to replace it?" with NO as the highlighted
        # default — Enter would refuse the save. "Y" is the Yes accelerator. Seen live
        # 2026-09-04: the dialog sat unanswered and the case was declared save-failed.
        time.sleep(dialog_delay)
        pyautogui.press("y")
        time.sleep(1.0)
    print(f"  [gui] Ctrl+Shift+S -> {dest.name} -> Enter; waiting {save_wait}s")
    time.sleep(save_wait)


# ---------------------------------------------------------------- public API

def open_project(pln: Path, mode: str = "gui", *, open_wait: float = 15.0,
                 dialog_delay: float = 1.5) -> None:
    pln = Path(pln).resolve()
    if mode == "gui":
        _gui_open(pln, open_wait, dialog_delay)
        return
    if mode == "tapir":
        try:
            _tap("OpenProject", {"projectFilePath": str(pln)})
            return
        except Exception as e:
            print(f"  [tapir OpenProject failed: {e} — falling back to manual]")
    _prompt(f"OPEN this project in Archicad:\n      {pln}")


def save_as(dest: Path, mode: str = "gui", *, save_wait: float = 5.0,
            dialog_delay: float = 1.5, confirm_enter: bool = False) -> None:
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)   # the save dialog needs the folder to exist
    if mode in ("gui", "tapir"):
        _ensure_plan_window()                        # a 3D window would save the VIEW, not the .pln
    if mode == "gui":
        _gui_save_as(dest, save_wait, dialog_delay, confirm_enter)
        return
    if mode == "tapir":
        # Tapir's only save is the parameterless IN-PLACE `SaveProject` (no SaveProjectAs in
        # any release up to 1.5.8). It is used ONLY when the open project already IS `dest`
        # — the runner's work-on-copy flow (2026-09-02: the start .pln is copied to the
        # result path BEFORE the open, so the agent edits the result file itself). Any
        # other destination goes through the keyboard Save As, never through SaveProject:
        # an in-place save of a different document would write the agent's model OVER the
        # case's versioned start .pln.
        if _open_project_is(dest):
            before = dest.stat().st_mtime if dest.exists() else None
            try:
                _tap("SaveProject", {})
            except BaseException as e:               # SystemExit from connect() included
                print(f"  [tapir SaveProject failed: {e} — falling back to the GUI Save As]")
            else:
                # VERIFY THE WRITE (2026-09-04): SaveProject answered OK on a run whose
                # result file kept the start file's size and mtime to the byte — nothing
                # was written, the runner declared save-failed, and the model was lost
                # when the guest reverted. The file's mtime is the only truth: give the
                # write a few seconds, and if it never lands fall back to the keyboard
                # Save As while the model is still open.
                for _ in range(8):
                    if dest.exists() and (before is None or dest.stat().st_mtime > before):
                        print(f"  [tapir] SaveProject -> {dest.name} (in place)", flush=True)
                        return
                    time.sleep(2.0)
                print("  [tapir SaveProject returned OK but the file did not change — "
                      "falling back to the GUI Save As]", flush=True)
        else:
            print(f"  [tapir] the open project is not {dest.name} — GUI Save As instead",
                  flush=True)
        _gui_save_as(dest, save_wait, dialog_delay, confirm_enter)
        return
    _prompt(f"SAVE AS (File > Save a copy as...):\n      {dest}")


def _open_project_is(path: Path) -> bool:
    """True when Tapir reports `path` as the open project (compared by full path — every
    case's start file is archicad.pln, so a name match would be worthless)."""
    try:
        info = _tap("GetProjectInfo", {}) or {}
    except BaseException:
        # ArchicadClient.connect() raises SystemExit (not Exception) when Tapir refuses —
        # typically 4001 "ongoing user input" because the agent left a dialog open. That
        # must degrade to the keyboard Save As, not kill the case (2026-09-03: a 60-minute
        # run lost its score to exactly this).
        return False
    if not info or info.get("isUntitled"):
        return False
    want = str(Path(path).resolve()).lower().replace("/", "\\")
    return any(isinstance(v, str) and v.lower().replace("/", "\\") == want
               for v in info.values())
