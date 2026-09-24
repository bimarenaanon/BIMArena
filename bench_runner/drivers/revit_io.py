"""Open / save the live Revit project for a bench run — the Revit twin of archicad_io.

Same public API (`open_project` / `save_as`) as archicad_io.py, so a caller can pick the
io module by tool (used by the Revit GT capture tooling and `verifier.sources.live_revit`).

Two modes:

- `gui`     (recommended) — drive Revit by keyboard, exactly as a human would:
              open:     Ctrl+O (a real Revit chord — proven over the bench GT captures)
              save-as:  Alt -> F -> A -> P   (ribbon KeyTips; Save As has no chord)
            each opens a file dialog; the path is pasted and Enter commits. Uses pyautogui +
            pygetwindow + pyperclip (all in the venv).
- `manual`  — the harness pauses and asks you to open / save by hand, then press Enter.

`tapir` (an archicad_io mode) has no Revit equivalent and falls back to a manual prompt.

Two Revit-specific rules (learned building the bench GT snapshots):

- Revit is MULTI-document and refuses two open docs with the same title. Every case env is
  `revit.rvt` and every result `result_<phase>.rvt`, so `open_project` first CLOSES all open
  docs (Ctrl+F4 loop) — otherwise case 2's open silently switches to case 1's still-open
  doc and its Save As collides.
- When the BimAgent add-in is serving (localhost:48884), open/close are VERIFIED against
  `/health`'s doc title instead of sleeping blind; without the add-in it falls back to the
  timed waits.
- A run that dies on the turn budget can leave Revit inside a SKETCH/EDIT MODE (floor
  boundary, stair, ...). Esc/Enter do NOT leave an edit mode and Save As is DISABLED
  inside one, so the blind Save-As chord lands on nothing. The only stable keyboard exit
  is the "Cancel Edit Mode" command, which has NO default shortcut — ONE-TIME SETUP on
  the bench box: in Revit, Options > User Interface > Keyboard Shortcuts: Customize...,
  search "Cancel Edit Mode", assign `XC` (takes effect immediately, no restart). The
  pre-save rescue ladder types it (twice, for nested edit modes) after closing dialogs;
  override the keys with $REVIT_CANCEL_EDIT_SHORTCUT, set it empty to disable. On a box
  without the assignment the typed letters match nothing and the trailing Esc flushes
  them — the old behaviour, unchanged.

The path is put on the CLIPBOARD and pasted so the keyboard layout never mangles the
colons/backslashes (and the Open dialog's autocomplete can't truncate a typed path).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HEALTH_URL = os.environ.get("REVIT_ROUTES_URL", "http://localhost:48884").rstrip("/") + "/health"

ABSENT = "?"      # nothing is listening on the routes port — no add-in, or Revit is gone
BUSY = "!"        # the server answered, but the API thread did not run the job (see below)

# Keyboard shortcut assigned IN REVIT to "Cancel Edit Mode". DEFAULT DISABLED (2026-08-24):
# typing letters into Revit is inherently unsafe — on a box without the assignment the
# letters linger in the type-ahead buffer and rolling-match into OTHER two-letter defaults
# (observed: leftover c + stray a fired CA = Canvas Theme, flipping the canvas dark). The
# edit-mode exit is now the LETTER-FREE ribbon click (_click_cancel_edit_button); set
# $REVIT_CANCEL_EDIT_SHORTCUT to opt back into the typed exit on a box where the click
# cannot work (e.g. exotic ribbon scaling).
CANCEL_EDIT_SHORTCUT = os.environ.get("REVIT_CANCEL_EDIT_SHORTCUT", "")


def _doc_title(timeout: float = 6.0) -> str | None:
    """The open doc's title per the BimAgent add-in, or a sentinel.

    The two failure modes must NOT be conflated (2026-08-17 — three gui-raw cases were scored
    as crashes because they were): `ABSENT` means the port is dead (add-in unloaded, Revit
    closed/crashed), while `BUSY` means the HTTP server answered but the dispatcher could not
    marshal the job onto the API thread in time — HTTP 500 `Revit job timed out`, which is the
    NORMAL state while Revit is loading a document (and also what a leftover modal looks like).
    Reading a BUSY as an ABSENT made the open loop fall through to a blind 15 s wait and the
    grading step then hit a still-loading document and died."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("doc")
    except urllib.error.HTTPError:                    # answered, job did not run
        return BUSY
    except urllib.error.URLError as e:
        return BUSY if isinstance(e.reason, TimeoutError) else ABSENT
    except TimeoutError:                              # timeout during the response read
        return BUSY
    except Exception:
        return ABSENT


def _await_free(timeout: float = 60.0, poll: float = 3.0) -> str | None:
    """Poll /health until it stops reporting BUSY (Revit's API thread is answering again)."""
    deadline = time.time() + timeout
    d = _doc_title()
    while d == BUSY and time.time() < deadline:
        time.sleep(poll)
        d = _doc_title()
    return d


def close_open_docs(save: bool = True, settle: float = 6.0) -> None:
    """Close whatever Revit has open, so the FILE ON DISK can be replaced.

    A builder overwrites its template's .rvt before opening it; Windows refuses while Revit
    holds the handle (WinError 32). Closing a MODIFIED document would pop a save prompt and
    hang the API thread, so `save` saves it in place first — for a BUILDER's own file that is
    safe, since the file is about to be overwritten anyway.

    But the same Ctrl+S lands on whatever is open, and during a bench batch that is the
    CASE'S ENV PROJECT: the agent's half-finished model gets written into
    bench_cases/.../env/start/revit.rvt, corrupting the start state of every later run of
    that case (observed once per finished case on 2026-08-26 until this guard). So the save
    is now gated on WHICH document is open — only a `result_*` doc (the harness's own
    save-as output) is ever saved in place; anything else is closed unsaved, exactly like
    the save-prompt guard in `_close_floating_dialogs`."""
    import pyautogui
    doc = _await_free()
    if doc in (None, ABSENT):
        return
    _focus_revit()
    if save and isinstance(doc, str) and doc.lower().startswith("result"):
        pyautogui.hotkey("ctrl", "s")
        time.sleep(settle)
    elif save:
        print(f"  [gui] not saving {doc!r} in place (only result_* docs are); closing unsaved",
              flush=True)
    _close_all()


def _decline_save_prompt() -> bool:
    """If Ctrl+F4 popped the "save changes?" prompt, answer NO — focused, never blind.

    A dirty doc (an agent-modified env, or a failed save-as) makes every close raise the
    "Do you want to save changes to <doc>?" box; unanswered it stalls `_close_all`, and
    the cascade that follows was measured live 2026-08-25: the stale doc's title equals
    the NEXT env's ('revit'), so the open's title check passes on the WRONG document and
    that case's agent runs against the previous case's model. The prompt's No accelerates
    on N in both UI languages on these boxes (No / Nein), and with the MODAL focused the
    keystroke reaches the dialog, not Revit's type-ahead buffer."""
    import ctypes
    import pyautogui
    try:
        dlgs = _revit_dialog_windows()
    except Exception:
        return False
    for hwnd, title in dlgs:
        print(f"  [gui] declining save prompt {title!r} (n)", flush=True)
        try:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        except Exception:
            pass
        pyautogui.press("n")
        time.sleep(1.0)
    return bool(dlgs)


def _close_all(max_tries: int = 8) -> None:
    """Close every open document (Ctrl+F4 until the add-in reports none). Bench envs are
    opened read-and-agent-modified but never saved in place, so Revit prompts to save —
    `_decline_save_prompt` answers No; a loop that stops making progress is reported."""
    import pyautogui
    d = _await_free()                     # a doc mid-load reports BUSY, not its title yet
    if d == ABSENT:                       # add-in absent: blind best-effort
        for _ in range(4):
            pyautogui.hotkey("ctrl", "f4")
            time.sleep(1.5)
            _decline_save_prompt()
        return
    for _ in range(max_tries):
        if d is None:
            return
        pyautogui.hotkey("ctrl", "f4")
        time.sleep(2.0)
        _decline_save_prompt()
        nxt = _await_free(timeout=30.0)   # closing a big doc keeps the API thread busy
        if nxt == d:                      # maybe several views of one doc / slow close
            time.sleep(2.5)
            _decline_save_prompt()
            nxt = _await_free(timeout=30.0)
        d = nxt
    print(f"  [gui] warning: docs may still be open (title {d!r})", flush=True)


# ---------------------------------------------------------------- manual

def _prompt(msg: str) -> None:
    print(f"\n  >>> {msg}\n      press Enter when done ...", flush=True)
    try:
        input()
    except EOFError:
        print("      [non-interactive: continuing]", flush=True)


# ---------------------------------------------------------------- gui automation

def _foreground_title() -> str:
    """Title of the window that actually holds the foreground, '' when it has none."""
    import ctypes
    user32 = ctypes.windll.user32
    h = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def _focus_revit() -> bool:
    """Bring the Revit window to the foreground so keystrokes land in it.

    Two layers, because `activate()` LIES. Windows denies SetForegroundWindow to a
    background process in real situations — measured 2026-08-25: an agent's stray click
    below the canvas left the TASKBAR (`Shell_TrayWnd`, empty title) holding the
    foreground, every activate() silently failed, and the old code still returned True.
    The save chord then typed its letters into whatever DID have focus (`Alt,F,A,P` ->
    a bare "fap" appearing in the operator's terminal) and the case was recorded
    save-failed. So the result is VERIFIED against the real foreground title, and when
    that fails a genuine input gesture takes over: Alt+Tab through the switcher, one
    window deeper each round, until Revit is in front. No letters are typed, so nothing
    can linger in Revit's type-ahead shortcut buffer."""
    import pygetwindow as gw
    import pyautogui
    wins = [w for w in gw.getAllWindows() if w.title and "revit" in w.title.lower()]
    # prefer the main app window (longest title, e.g. "Autodesk Revit 2027 - [<view>]")
    wins.sort(key=lambda w: len(w.title), reverse=True)
    for w in wins:
        try:
            if getattr(w, "isMinimized", False):
                w.restore()
            w.activate()
            time.sleep(0.4)
            if "revit" in _foreground_title().lower():
                return True
        except Exception:
            continue
    for k in range(1, 6):                    # Alt+Tab fallback, one window deeper per round
        pyautogui.keyDown("alt")
        for _ in range(k):
            pyautogui.press("tab")
            time.sleep(0.3)
        pyautogui.keyUp("alt")
        time.sleep(0.8)
        title = _foreground_title()
        if "revit" in title.lower() and "chrome" not in title.lower():
            print(f"  [gui] focus recovered via Alt+Tab x{k}", flush=True)
            return True
    print("  [gui: could not find/activate a Revit window — is it open?]", flush=True)
    return False


def _menu_keys(keys: list[str], key_delay: float = 0.5) -> None:
    """Ribbon KeyTip navigation: tap each key on its own, waiting for the menu to update.
    Revit reveals the KeyTips on the first Alt tap, then consumes one letter per level."""
    import pyautogui
    for k in keys:
        pyautogui.press(k)
        time.sleep(key_delay)


def _paste_path(path: str) -> None:
    # The Save/Open dialog opens with the default filename SELECTED, so pasting replaces it.
    # (Do NOT Ctrl+A first — as in Archicad's dialog it can deselect and append to the old name.)
    import pyautogui
    import pyperclip
    pyperclip.copy(path)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")   # paste the full path over the pre-selected name
    time.sleep(0.3)


def _gui_open(rvt: Path, open_wait: float, dialog_delay: float) -> None:
    import pyautogui
    _focus_revit()
    # Sweep leftover modals BEFORE closing docs (2026-08-25). The pre-save ladder only
    # runs before Save As; a modal raised DURING/AFTER the save — most often Revit's
    # "File Changed Since Last Save" box — survives into this step, blocks _close_all
    # (which then reports `docs may still be open (title '!')`), and leaves the old doc
    # open, so the following Ctrl+O of the same path raises that box again. Every case
    # then needed a hand-click. Sweeping here breaks the loop.
    # Revit raises these in SEQUENCE (closing a "Save File" prompt uncovers a "File
    # Changed Since Last Save" box, ...), so sweep-and-close until the API thread is
    # free again rather than a fixed number of times.
    for _ in range(4):
        _close_floating_dialogs()
        _close_all()                         # same-title docs cannot coexist
        if _doc_title() != BUSY:
            break
    pyautogui.press("esc")                   # clear any leftover ribbon/tool state
    time.sleep(0.8)
    pyautogui.hotkey("ctrl", "o")            # Open (real Revit chord)
    time.sleep(dialog_delay)                 # let the Open dialog appear
    time.sleep(1.0)                          # extra settle: dialog ready to accept input
    _paste_path(str(rvt))
    pyautogui.press("enter")                 # open it
    want = rvt.stem
    print(f"  [gui] Ctrl+O -> {rvt.name} -> Enter; waiting for load (title '{want}')", flush=True)
    # The floor is 180 s, not 60: a multi-megabyte bench result keeps Revit's API thread busy
    # well past a minute, and every /health during that window answers BUSY.
    deadline = time.time() + max(open_wait * 4, 180.0)
    while time.time() < deadline:
        d = _doc_title()
        if d == ABSENT:                      # add-in absent: fall back to the timed wait
            time.sleep(open_wait)
            return
        if d == want:
            time.sleep(2.0)                  # let the view settle
            return
        time.sleep(3.0)                      # BUSY (mid-load) or another doc still up
    print(f"  [gui] warning: doc title is {_doc_title()!r}, expected {want!r} — "
          f"the open may have failed", flush=True)


def _revit_dialog_windows():
    """Top-level VISIBLE windows of the Revit PROCESS that are not the main app window —
    i.e. agent-left dialogs, whatever their title ("Revit" message boxes, "Load Family"
    file dialogs, "Type Properties", ...). Enumerated by PID, not by title guessing:
    the 2026-08-23 title=="Revit" match missed a Load Family dialog and stalled a batch
    for 10 minutes. Returns [(hwnd, title), ...]; [] when Revit is not running."""
    import ctypes
    from ctypes import wintypes
    import psutil
    pids = {p.pid for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower() == "revit.exe"}
    if not pids:
        return []
    user32 = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(n, 1) + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.strip()
        # DIALOGS ONLY, by window CLASS (calibrated live 2026-08-23):
        #   #32770        = the standard Windows dialog class — Revit's message boxes
        #                   ("No Interference detected!") AND its file dialogs (Load
        #                   Family, Save As) all use it;
        #   HwndWrapper*  = WPF windows — a dialog when its title is NOT the product-
        #                   titled main window;
        # everything else (e.g. the add-in's GUID-titled WindowsForms helper window)
        # is internal plumbing that must not be focused or keyed.
        if cls.value == "#32770":
            out.append((hwnd, title or cls.value))
        elif (cls.value.startswith("HwndWrapper")
              and title and not title.lower().startswith("autodesk revit")):
            out.append((hwnd, title))
        return True

    user32.EnumWindows(_cb, 0)
    return out


def _dialog_text(hwnd) -> str:
    """The concatenated text of a dialog's CHILD controls — its message line and button
    labels. The window TITLE of Revit's save prompt is just "Save File"; which document
    it is about ("Do you want to save changes to revit.rvt?") only appears in the body,
    and that decides whether saving is wanted or destructive (see below)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    parts = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(child, _):
        n = user32.GetWindowTextLengthW(child)
        if n > 0:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(child, buf, n + 1)
            parts.append(buf.value)
        return True

    try:
        user32.EnumChildWindows(hwnd, _cb, 0)
    except Exception:
        return ""
    return " | ".join(parts)


def _active_doc_from_title() -> str:
    """The open document's name off Revit's MAIN WINDOW TITLE ("... - <doc>.rvt - <view>").

    Needed because `_dialog_text` cannot always read the save prompt's message line: Revit
    renders it in a WPF/DirectUI control that EnumChildWindows does not enumerate, so the
    body comes back as just the buttons ("&Ja | &Nein | Abbrechen") — live hit 2026-08-26,
    where the guard then read "no result in body" and would have answered NO to
    "save changes to result_gui-priors.rvt?", discarding a 29-minute run. The title is
    still readable while a modal is up (unlike /health, which reports BUSY)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                if "Autodesk Revit" in buf.value:
                    found.append(buf.value)
        return True

    try:
        user32.EnumWindows(_cb, 0)
    except Exception:
        return ""
    return max(found, key=len) if found else ""


def _close_floating_dialogs(max_rounds: int = 4) -> None:
    """Dismiss agent-left dialogs (an Interference report, a Load Family file dialog, a
    message box) before the blind save chord.

    These are top-level windows of the Revit process — not owner-modal children the main
    window forwards keys to — so `_focus_revit` (which activates the LONGEST-titled
    window, i.e. the main app) leaves them unfocused, the ladder's blind Enter/Esc never
    reaches them, and the open dialog holds the add-in's API thread BUSY while eating
    the whole Save-As chord. Bring each window to the FOREGROUND and press Esc first —
    on a FILE dialog Enter would be Open (a real model change: loading the family, ...),
    while Esc is always Cancel/Close — then Enter on a later round for message boxes
    whose only button is a default OK that Esc will not fire."""
    import ctypes
    import pyautogui
    for round_no in range(max_rounds):
        try:
            dlgs = _revit_dialog_windows()
        except Exception:
            return
        if not dlgs:
            return
        for hwnd, title in dlgs:
            try:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.6)
                # "Save File" ("Do you want to save changes to <doc>.rvt?") is a
                # THREE-button prompt (Yes / No / Cancel — Ja / Nein / Abbrechen).
                # Esc means Cancel: it does NOT complete the close the prompt belongs
                # to, so the ladder pressed Esc round after round while the API thread
                # stayed BUSY (live hit 2026-08-25: a reasoning_tasks case wedged 7+ minutes).
                # But the answer is NOT unconditionally Yes: the SAME prompt appears
                # when `_close_all` closes the case's ENV project, and Yes there writes
                # the agent's half-finished model into
                # bench_cases/.../env/start/revit.rvt — four long-seq_tasks templates were
                # corrupted that way on 2026-08-25 (restored from git). So decide by
                # WHICH document the prompt names:
                #   result_*.rvt -> Yes  (that doc IS the case result; saving is the point)
                #   anything else -> No  (never write into a benchmark environment;
                #                         "n" also dismisses the prompt, so no wedge)
                low = title.lower()
                if "save file" in low:
                    # Which document is it about? The body names it — WHEN it can be read.
                    # Revit sometimes renders that line in a control EnumChildWindows does
                    # not see, leaving only the button labels; then fall back to the main
                    # window title, which still shows the active doc under a modal.
                    body = _dialog_text(hwnd).lower()
                    named = ".rvt" in body
                    src = body if named else _active_doc_from_title().lower()
                    key = "enter" if "result" in src else "n"
                    print(f"  [gui] save prompt about {'body' if named else 'title'}="
                          f"{src[:60]!r} -> {'Yes' if key == 'enter' else 'No'}", flush=True)
                elif any(k in low for k in ("open", "load", "save as", "export",
                                            "import", "browse")):
                    key = "esc"               # file browser: Enter would ACT (load/save)
                else:
                    key = "esc" if round_no < 2 else "enter"
                print(f"  [gui] closing agent-left dialog {title!r} ({key})", flush=True)
                pyautogui.press(key)
                time.sleep(0.8)
            except Exception:
                continue


def _rescue_to_savable() -> None:
    """Blind-drive Revit from WHATEVER state the agent left it in back to a state where
    Save As works. Three layers, outermost first:

    1. MODAL dialogs (Edit Assembly / Type Properties / a warning): 3x Enter COMMITS and
       closes them innermost-out (Esc alone would only cancel the innermost level, and a
       modal freezes the add-in's API thread — 2026-08-08, several batch crashes were
       exactly this).
    2. Pending tool/input state (a placement preview, a half-typed dimension): 3x Esc.
       This also kills anything a stray Enter started — Enter on the bare canvas is
       Revit's repeat-last-command.
    3. SKETCH/EDIT MODES (floor boundary edit, stair, ...): Esc does NOT leave them and
       Save As is DISABLED inside them, so before 2026-08-20 the save chord died here.
       Type the "Cancel Edit Mode" shortcut (assigned in Revit — module doc), Enter for
       the "discard changes?" confirmation, Esc for the repeat-last-command an
       un-consumed Enter may have fired. Twice: edit modes NEST (a stair run sketch
       inside the stair editor). CANCEL, never Finish — finishing a half-drawn sketch
       pops the "lines must form closed loops" modal, and a budget-killed edit should
       not count anyway.

    If the add-in still reports BUSY afterwards (a modal survived — e.g. one whose
    default button spawned a child dialog), one more Enter/Esc round runs. ABSENT is
    fine here: without the add-in the ladder just stays blind.

    Layer 0 (2026-08-23): FLOATING dialogs titled just "Revit" get focused and closed
    DIRECTLY first — the blind volleys below land on the main window and never reach
    them (see _close_floating_dialogs)."""
    import pyautogui
    _close_floating_dialogs()
    for _ in range(3):
        pyautogui.press("enter")
        time.sleep(1.0)
    for _ in range(3):
        pyautogui.press("esc")
        time.sleep(1.0)
    # Edit-mode exit, LETTER-FREE (2026-08-24): when the API thread is still blocked the
    # doc is usually inside a sketch/edit mode — click the ribbon's red "Cancel Edit
    # Mode" ✗ directly instead of typing a shortcut (typed letters linger in Revit's
    # type-ahead buffer and rolling-match into unrelated two-letter defaults). Twice,
    # for nested edit modes. The optional typed exit survives as an env opt-in below.
    for _ in range(2):
        if _doc_title() != BUSY:
            break
        if not _click_cancel_edit_button():
            break                            # no Cancel ✗ on screen: a modal, not a sketch
        time.sleep(1.2)
        pyautogui.press("enter")             # confirm the discard prompt, if any
        time.sleep(1.2)
    if CANCEL_EDIT_SHORTCUT:
        for _ in range(2):
            for ch in CANCEL_EDIT_SHORTCUT.lower():
                pyautogui.press(ch)
                time.sleep(0.3)
            time.sleep(1.2)                  # the discard-confirmation dialog, if any
            pyautogui.press("enter")
            time.sleep(1.2)
            pyautogui.press("esc")           # repeat-last-command / leftover keystrokes
            time.sleep(0.8)
    if _doc_title() == BUSY:                 # a modal is STILL holding the API thread
        print("  [gui] still busy after the rescue ladder — one more Enter/Esc round",
              flush=True)
        for _ in range(2):
            pyautogui.press("enter")
            time.sleep(1.0)
            pyautogui.press("esc")
            time.sleep(1.0)


def _click_cancel_edit_button() -> bool:
    """Exit a sketch/edit mode by CLICKING the ribbon's red 'Cancel Edit Mode' ✗ —
    the letter-free replacement for the typed shortcut exit. The Cancel ✗ is found
    geometrically: it is the LARGE red glyph in the ribbon band whose green 'Finish
    Edit Mode' ✓ sits right next to it (the Modify panel's red Delete ✗ has no green
    neighbour, so the pair rule cannot hit it). Returns True when a pair was found
    and the ✗ was clicked; False leaves the caller to its Enter/Esc fallbacks."""
    import numpy as np
    import pyautogui
    BAND_TOP, BAND_BOTTOM = 40, 135              # the ribbon strip, in screen pixels
    img = np.asarray(pyautogui.screenshot())
    band = img[BAND_TOP:BAND_BOTTOM, :, :3].astype(int)
    r, g, b = band[..., 0], band[..., 1], band[..., 2]
    red = (r > 150) & (g < 90) & (b < 90)
    green = (g > 120) & (r < 110) & (b < 110)

    def _clusters(mask, min_px=40):
        ys, xs = np.nonzero(mask)
        out, used = [], np.zeros(len(xs), bool)
        for i in np.argsort(xs):
            if used[i]:
                continue
            sel = (np.abs(xs - xs[i]) < 30) & (np.abs(ys - ys[i]) < 30)
            used |= sel
            if sel.sum() >= min_px:              # a real glyph, not stray icon pixels
                out.append((float(xs[sel].mean()), float(ys[sel].mean())))
        return out

    for rx, ry in _clusters(red):
        for gx, gy in _clusters(green):
            if abs(rx - gx) < 90 and abs(ry - gy) < 90:
                # Deliberate slow click: a WPF ribbon button can swallow an instant
                # move+click as a mere hover (live hit 2026-08-24 — the tooltip showed,
                # the command did not fire). Hover first, then a spaced down/up.
                pyautogui.moveTo(int(rx), int(ry) + BAND_TOP)
                time.sleep(0.4)
                pyautogui.mouseDown()
                time.sleep(0.15)
                pyautogui.mouseUp()
                print("  [gui] clicked the Cancel Edit Mode ✗ "
                      f"({int(rx)},{int(ry) + BAND_TOP})", flush=True)
                return True
    return False


def _gui_save_as(dest: Path, save_wait: float, dialog_delay: float,
                 confirm_enter: bool) -> None:
    import pyautogui
    _focus_revit()
    # Clear whatever the agent left behind before the blind Save-As chord, then park the
    # mouse at the screen centre (away from ribbon flyouts and pyautogui's fail-safe
    # corners).
    _rescue_to_savable()
    w, h = pyautogui.size()
    # CLICK the canvas, don't just hover (2026-08-25). Alt only raises the ribbon KeyTips
    # when the MAIN VIEW has focus; with focus parked in the Project Browser or another
    # docked palette — where a list/observation agent naturally ends up — the whole
    # Alt,F,A,P chord is swallowed and Save As silently never happens (live hit:
    # list_types1 recorded save-failed twice in a row, the agent having browsed the
    # type tree). An empty-canvas click costs nothing and restores keytip routing.
    pyautogui.click(w // 2, h // 2)
    time.sleep(0.6)
    pyautogui.press("esc")                   # drop any selection the click may have made
    time.sleep(0.4)
    # Flush Revit's type-ahead shortcut buffer RIGHT before the menu chord. On a box where
    # CANCEL_EDIT_SHORTCUT is not assigned, its letters linger in the buffer; if the File
    # menu then misses a keytip, the stray "a" of Save As lands in the canvas and Revit's
    # rolling match can complete a two-letter shortcut off the leftover letter (live hit
    # 2026-08-24: leftover "c" + stray "a" fired CA = invert canvas background).
    pyautogui.press("esc")
    time.sleep(0.5)
    # LAST-MOMENT FOCUS GATE. Everything above (the rescue ladder, its dialog handling, the
    # canvas click) can hand the foreground to something else, and the chord is typed BLIND:
    # if Revit is not in front, `alt` does nothing and the bare letters land in whatever is —
    # observed repeatedly as a stray "fap" in the operator's terminal, one per silently
    # save-failed case. So the foreground is re-verified here, immediately before the keys,
    # and if it cannot be reclaimed NOTHING is typed: the save fails cleanly (the caller sees
    # no file and records save-failed) instead of scattering keystrokes into other apps.
    if "revit" not in _foreground_title().lower() and not _focus_revit():
        print("  [gui] ABORT save-as: Revit is not the foreground window; "
              "typing nothing (case will record save-failed)", flush=True)
        return
    _menu_keys(["alt", "f", "a", "p"])       # File > Save As > Project
    time.sleep(dialog_delay)
    time.sleep(1.0)                          # extra settle: dialog ready to accept input
    _paste_path(str(dest))
    pyautogui.press("enter")
    if confirm_enter:                        # dismiss an overwrite prompt on re-runs
        time.sleep(dialog_delay)
        pyautogui.press("enter")
    print(f"  [gui] Alt,F,A,P -> {dest.name} -> Enter; waiting {save_wait}s", flush=True)
    time.sleep(save_wait)


# ---------------------------------------------------------------- public API

def _route_post(path: str, payload: dict, timeout: float = 300.0) -> dict:
    """POST one harness route on the add-in (stdlib only, like _doc_title)."""
    url = HEALTH_URL[: -len("/health")] + "/" + path
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _api_open(rvt: Path) -> bool:
    """`POST /open` (added 2026-09-02): open + activate, discard every other document,
    verified against the title the add-in reports. False when the add-in refused or is
    not serving -- the caller falls back to the keyboard path."""
    try:
        out = _route_post("open", {"path": str(rvt), "close_others": True})
    except Exception as e:
        print(f"  [api] /open failed ({type(e).__name__}: {e}) — falling back to Ctrl+O",
              flush=True)
        return False
    if not out.get("ok"):
        where = f" (at {out['where']})" if out.get("where") else ""
        print(f"  [api] /open refused: {out.get('error')}{where} — falling back to Ctrl+O",
              flush=True)
        return False
    title = _await_free()
    ok = isinstance(title, str) and title not in (ABSENT, BUSY) and rvt.stem.lower() in title.lower()
    closed = out.get("closed") or []
    print(f"  [api] /open -> {out.get('doc')!r}" + (f" (closed {closed})" if closed else "")
          + ("" if ok else f" — title check FAILED (got {title!r})"), flush=True)
    return ok


def _api_save_as(dest: Path) -> bool:
    """`POST /saveas`: the active document saved under `dest`, verified by title + file."""
    try:
        out = _route_post("saveas", {"path": str(dest), "overwrite": True})
    except Exception as e:
        print(f"  [api] /saveas failed ({type(e).__name__}: {e}) — falling back to Alt,F,A,P",
              flush=True)
        return False
    if not out.get("ok"):
        print(f"  [api] /saveas refused: {out.get('error')} — falling back to Alt,F,A,P",
              flush=True)
        return False
    ok = bool(out.get("exists")) and dest.stem.lower() in str(out.get("doc") or "").lower()
    print(f"  [api] /saveas -> {out.get('doc')!r}" + ("" if ok else " — verification FAILED"),
          flush=True)
    return ok


def open_project(rvt: Path, mode: str = "gui", *, open_wait: float = 15.0,
                 dialog_delay: float = 1.5) -> None:
    rvt = Path(rvt).resolve()
    if mode == "api":
        if _api_open(rvt):
            return
        mode = "gui"                                  # the keyboard path is the fallback
    if mode == "gui":
        _gui_open(rvt, open_wait, dialog_delay)
        return
    # manual (and tapir, which Revit has no equivalent for) -> prompt
    _prompt(f"OPEN this project in Revit:\n      {rvt}")


def save_as(dest: Path, mode: str = "gui", *, save_wait: float = 5.0,
            dialog_delay: float = 1.5, confirm_enter: bool = False) -> None:
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)   # the save dialog needs the folder to exist
    if mode == "api":
        if _api_save_as(dest):
            return
        mode = "gui"                                  # rescue ladder + Alt,F,A,P as fallback
    if mode == "gui":
        _gui_save_as(dest, save_wait, dialog_delay, confirm_enter)
        return
    _prompt(f"SAVE AS (File > Save As > Project):\n      {dest}")
