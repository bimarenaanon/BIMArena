"""Computer controller — the single surface for low-level OS control.

Drives the BIM authoring application through the screen/mouse/keyboard, all via pyautogui.
`apply()` executes ONE op dict; the ops it accepts are exactly the GUI tool family declared in
`tools/gui/__init__.py` (which is where their LLM-facing documentation lives — this module is
the mechanism, that module is the spec). The ops are application-agnostic; the per-app GUI
gestures that combine them live in the software skills.
"""
import io
import sys
import time

import pyautogui
from PIL import Image

MOVE_DURATION = 0.6   # seconds the cursor takes to glide to a target (visible motion, no teleport)
CLICK_SETTLE_S = 0.3  # pause between arriving at (x, y) and pressing the button in the one-call
                      # click ops: the move must fully land (and the UI register the hover) before
                      # the click, or the press fires while the cursor is still in transit
_SELECT_ALL = ("command", "a") if sys.platform == "darwin" else ("ctrl", "a")   # select-all hotkey
_PASTE = ("command", "v") if sys.platform == "darwin" else ("ctrl", "v")        # paste hotkey


# CAPS on the screenshot that is sent to the model. A provider that resizes the image
# server-side makes the model read click targets in the RESIZED pixel space, so every click
# lands short in proportion to its distance from the origin. Downscaling CLIENT-side keeps the
# coordinate space the model sees identical to the image bytes we hold, and _SCALE maps it back
# to pyautogui logical points in one step. TWO caps, because the long edge alone cannot
# express the limit that bites: Anthropic resizes anything over ~1568 px on an edge OR over
# ~1.15 megapixels, and a 16:9 screen at a 1568 px edge is 1568x882 = 1.38 MP — legal by edge,
# over by area. WHICH caps apply is decided PER MODEL by `tools/gui/profile.py`, read at
# CAPTURE time (this module can be imported before config.py loads .env).
def _img_edge_cap():
    """The long-edge cap in px for this run's model; 0 means none."""
    from . import profile
    return profile.resolve()["img_edge"]


def _img_pixel_cap():
    """The pixel-count cap for this run's model; 0 means none."""
    from . import profile
    return profile.resolve()["img_pixels"]


_SCALE = None         # sent-screenshot px per logical pt (Retina x downscale) — process-wide
_SENT_SIZE = None     # (w, h) of the last screenshot SENT to the model — the frame its coords are in
_SHIFT_HELD = False   # Shift kept DOWN across rounds by shift_hover (door/window pre-highlight);
                      # released by commit_select / press_esc / any other op / abort — never stuck

# COORDINATE FRAME of the model's click targets (2026-09-12). The tool contract says "screen
# pixels read off the screenshot", and GPT / Claude answer in exactly that frame. Gemini, Qwen
# and Meta's vision models do NOT: their grounding is trained on a 0-1000 NORMALISED frame per
# axis (Gemini documents it for its computer-use output; their own agent SDKs denormalise), and
# no prompt wording moves them off it — probed 2026-09-12 with labelled-button images at
# 1568x882 and 1920x1080: gemini-3.7-flash, qwen3.7-plus and muse-spark-1.1 all returned
# x*1000/W, y*1000/H with a ~1 px residual, while gpt-5.6 was pixel-exact on the same probe.
# Read as pixels, every one of their clicks landed at (0.64x, 1.13y) of the target, which is
# what their 08-24..08-29 Atomic results measured. The decode below is the provider adapter
# their SDKs ship: it maps 0-1000 back onto the SENT screenshot before _SCALE maps that to
# logical points. WHICH frame applies is decided PER MODEL ID by `tools/gui/profile.py` (the
# provider is only the fallback); $GUI_COORD_FRAME (pixels | norm1000) forces one.
# evocua: its harness runs `--coordinate_type relative` (a 0..999 grid; providers/evocua.py
# rescales by 1000/999 so this decode reproduces the upstream `original / 999` exactly).


def _coord_frame():
    from . import profile
    return profile.resolve()["frame"]


def decode_frame(x, y, sent_size, frame=None):
    """Map a model-issued (x, y) into SENT-screenshot pixels. Pure, so it can be tested
    without a screen: in the norm1000 frame the point is x/1000 of the sent width and
    y/1000 of the sent height; in the pixels frame it is returned unchanged."""
    frame = frame or _coord_frame()
    if frame == "norm1000" and sent_size:
        w, h = sent_size
        return x * w / 1000.0, y * h / 1000.0
    return x, y


class ComputerController:
    """Screen + mouse + keyboard primitives, backed by pyautogui. This is the action space."""

    # ---- screen ----
    def screenshot(self):
        """Capture the whole main screen, downscaled to fit BOTH caps (long edge and pixel
        count), and return it as PNG bytes (feed to llm.complete). Staying under the providers'
        resize thresholds means the (x, y) the actor reads off the sent image IS that image's
        real pixel space — _scale_factor() maps it back to logical points."""
        global _SCALE, _SENT_SIZE
        img = pyautogui.screenshot()
        pixels, edge = _img_pixel_cap(), _img_edge_cap()
        k = min(1.0,
                edge / max(img.size) if edge else 1.0,
                (pixels / (img.width * img.height)) ** 0.5 if pixels else 1.0)
        if k < 1.0:
            img = img.resize((round(img.width * k), round(img.height * k)),
                             Image.Resampling.LANCZOS)
        _SCALE = img.width / pyautogui.size().width   # sent px -> logical pt, in one factor
        _SENT_SIZE = img.size                         # the frame a norm1000 model answers in
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _scale_factor(self):
        """How many SENT-screenshot pixels per pyautogui logical point — one factor covering
        BOTH the Retina capture (screenshot 2x the moveTo() space) AND the client-side LLM
        downscale. Set by every screenshot(); computed on demand if none was taken yet."""
        if _SCALE is None:
            self.screenshot()
        return _SCALE

    # ---- action space (low-level mouse + keyboard) ----
    def mouse_move_to(self, x, y):
        """Move the cursor to (x, y), given in SENT-SCREENSHOT pixels (scaled to logical
        points). The move is animated over MOVE_DURATION so the cursor glides instead of
        teleporting. Coords are clamped 1 pt inside the screen edges: pyautogui's fail-safe
        fires on the EXACT screen corners, and one corner-landing click target would crash
        the whole run on the next pyautogui call."""
        s = self._scale_factor()                  # also guarantees _SENT_SIZE is set
        x, y = decode_frame(x, y, _SENT_SIZE)     # norm1000 providers -> sent-screenshot px
        w, h = pyautogui.size()
        lx = min(max(x / s, 1), w - 2)
        ly = min(max(y / s, 1), h - 2)
        pyautogui.moveTo(lx, ly, duration=MOVE_DURATION)

    def mouse_click(self, x=None, y=None):
        """Left-click; with (x, y) given, move there first and SETTLE before pressing (one
        call = move + pause + click — clicking straight out of the glide fires mid-air)."""
        if x is not None and y is not None:
            self.mouse_move_to(x, y)
            time.sleep(CLICK_SETTLE_S)
        pyautogui.click()

    def mouse_double_click(self, x=None, y=None):
        """Double-click (e.g. to FINISH a stair baseline / polyline); with (x, y) given,
        move there first and SETTLE before pressing (see mouse_click)."""
        if x is not None and y is not None:
            self.mouse_move_to(x, y)
            time.sleep(CLICK_SETTLE_S)
        pyautogui.doubleClick()

    def mouse_press_hold(self, x=None, y=None, seconds=1.0):
        """Press the LEFT button and HOLD it for `seconds` before releasing — the flyout
        gesture (a control whose variants pop out on a ~1 s press-and-hold, e.g. an Info
        Box method icon). With (x, y) given, move there and SETTLE first (see mouse_click).
        The release always runs, even if the sleep is interrupted — a stuck-down button
        would corrupt every op after it."""
        if x is not None and y is not None:
            self.mouse_move_to(x, y)
            time.sleep(CLICK_SETTLE_S)
        pyautogui.mouseDown()
        try:
            time.sleep(min(max(float(seconds or 1.0), 0.2), 5.0))
        finally:
            pyautogui.mouseUp()

    def shift_hover(self, x, y):
        """HOLD Shift down (persisting ACROSS rounds) and glide the cursor to (x, y) WITHOUT clicking,
        so the element under the cursor PRE-HIGHLIGHTS. This is how a door/window is selected: hover
        here, let the NEXT round's screenshot confirm the OPENING (not the wall/slab) is highlighted,
        THEN `commit_select`. Shift stays held between rounds; any op other than shift_hover /
        commit_select auto-releases it (see apply), and press_esc / abort release it too — never stuck."""
        global _SHIFT_HELD
        if not _SHIFT_HELD:
            pyautogui.keyDown("shift")
            _SHIFT_HELD = True
        self.mouse_move_to(x, y)

    def commit_select(self):
        """Click at the CURRENT cursor position (where a prior shift_hover parked it, on the now-
        highlighted opening) to select it, then release Shift. Use ONLY after a screenshot has
        confirmed the intended door/window is highlighted."""
        pyautogui.click()
        self._release_shift()

    def _release_shift(self):
        """Release a Shift held by shift_hover, if any — the safety valve against a stuck modifier."""
        global _SHIFT_HELD
        if _SHIFT_HELD:
            pyautogui.keyUp("shift")
            _SHIFT_HELD = False

    def shift_click(self, x, y):
        """One-shot select (hold Shift, move to (x, y), click, release) — the atomic version of
        shift_hover+commit_select for when the target pixel is trusted without a highlight check."""
        pyautogui.keyDown("shift")
        try:
            self.mouse_move_to(x, y)
            time.sleep(CLICK_SETTLE_S)      # land + let the hover register before pressing
            pyautogui.click()
        finally:
            pyautogui.keyUp("shift")

    def type(self, text):
        """Type the given text on the keyboard. A small per-key interval — write() at the
        default 0 is known to DROP characters in heavyweight GUI apps, and a dropped digit in
        a typed wall length (4142 -> 442) is a silent geometry error.

        NON-ASCII goes through the clipboard: pyautogui.write() silently SKIPS any character
        it cannot map on the US layout, so an umlaut in a typed composite/material name
        ("Außenwand") would vanish and the attribute would be authored under a wrong name."""
        text = str(text)
        if any(ord(c) > 127 for c in text):
            try:
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey(*_PASTE)
                return
            except Exception as e:
                print(f"[gui] WARNING: non-ASCII text and no clipboard route "
                      f"({type(e).__name__}: {e}) — unmappable characters will be DROPPED")
        pyautogui.write(text, interval=0.03)

    def select_all(self):
        """Select all text in the focused field (Cmd+A on macOS, Ctrl+A elsewhere) — use before
        typing to replace a field that already has content."""
        pyautogui.hotkey(*_SELECT_ALL)

    def press_enter(self):
        """Press the Enter / Return key."""
        pyautogui.press("enter")

    def press_esc(self):
        """Press the Escape key (also releases a Shift held by shift_hover — Esc aborts a
        hover/selection, so no modifier should linger)."""
        self._release_shift()
        pyautogui.press("esc")

    def press_tab(self):
        """Press the Tab key — move focus / cycle the active input field, where the software skill
        calls for it."""
        pyautogui.press("tab")

    def delete_selected(self):
        """Delete the currently selected element(s) by pressing the Delete key. Select
        the element first (click it on the canvas) so only the intended element is removed; with
        nothing selected this is a no-op. macOS: pyautogui's "delete" is FORWARD-delete
        (fn+Delete); the key that deletes a selection is Backspace."""
        pyautogui.press("backspace" if sys.platform == "darwin" else "delete")

    def scroll(self, dy=0, dx=0):
        """Scroll the mouse wheel at the current cursor position. dy>0 = UP/away, dy<0 = DOWN/toward;
        dx scrolls horizontally (right>0). Over a list/dropdown it scrolls; over the drawing CANVAS
        the wheel ZOOMS. Move the cursor over the target panel first (it acts where the cursor is)."""
        if dy:
            pyautogui.scroll(int(dy))
        if dx:
            if sys.platform == "win32":
                # pyautogui's _hscroll on Windows is a plain VERTICAL wheel event — over the
                # canvas that would ZOOM instead of pan. Emulate horizontal via the standard
                # shift+wheel convention (honored by Windows list/canvas widgets).
                pyautogui.keyDown("shift")
                try:
                    pyautogui.scroll(int(dx))
                finally:
                    pyautogui.keyUp("shift")
            else:
                pyautogui.hscroll(int(dx))

    def hotkey(self, keys):
        """Press a key COMBINATION together (modifiers held while the final key is pressed), e.g.
        ["mod","up"] or ["mod","7"]. The special token "mod" maps to the platform's primary modifier
        — Command on macOS, Ctrl on Windows/Linux — so one shortcut works on both. Common aliases
        (cmd/command, opt/option→alt, control→ctrl) are normalized; other keys pass through."""
        darwin = sys.platform == "darwin"
        mod = "command" if darwin else "ctrl"
        opt = "option" if darwin else "alt"          # pyautogui knows no "option" on Windows —
        alias = {"mod": mod, "cmd": "command", "command": "command", "control": "ctrl",
                 "ctrl": "ctrl", "opt": opt, "option": opt, "alt": "alt", "shift": "shift"}
        mapped = [alias.get(str(k).strip().lower(), str(k).strip().lower()) for k in (keys or [])]
        if mapped:
            pyautogui.hotkey(*mapped)
        return mapped

    # ---- dispatch ----
    def apply(self, op):
        """Execute one action-space op (a dict with an "op" key); return a short text of what ran."""
        kind = op.get("op")
        # SAFETY: a Shift held by a prior shift_hover must be released before ANY op that is not
        # itself a hover/commit — otherwise it would turn the next click/type/hotkey into a
        # Shift+chord (e.g. Ctrl+T -> Ctrl+Shift+T). Only shift_hover (continue hovering) and
        # commit_select (releases it after its own click) keep it held.
        if kind not in ("shift_hover", "commit_select"):
            self._release_shift()
        if kind == "mouse_move_to":
            self.mouse_move_to(op["x"], op["y"]);  return f"mouse_move_to({op['x']}, {op['y']})"
        if kind in ("mouse_click", "mouse_double_click"):
            x, y = op.get("x"), op.get("y")
            if (x is None) != (y is None):
                # Half a coordinate: clicking at whatever pixel the cursor happens to be on
                # would act on the wrong control — refuse (without killing the run) and say so.
                return (f"{kind} NOT PERFORMED: x and y must be given together "
                        f"(or both omitted to click at the current cursor)")
            if kind == "mouse_click":
                self.mouse_click(x, y)
            else:
                self.mouse_double_click(x, y)
            return f"{kind}({x}, {y})" if x is not None else f"{kind}()"
        if kind == "mouse_press_hold":
            x, y = op.get("x"), op.get("y")
            if (x is None) != (y is None):
                return ("mouse_press_hold NOT PERFORMED: x and y must be given together "
                        "(or both omitted to hold at the current cursor)")
            secs = op.get("seconds", 1.0)
            self.mouse_press_hold(x, y, secs)
            at = f"{x}, {y}, " if x is not None else ""
            return f"mouse_press_hold({at}seconds={secs})"
        if kind == "shift_hover":
            self.shift_hover(op["x"], op["y"]);    return f"shift_hover({op['x']}, {op['y']})"
        if kind == "commit_select":
            self.commit_select();                  return "commit_select()"
        if kind == "shift_click":
            self.shift_click(op["x"], op["y"]);    return f"shift_click({op['x']}, {op['y']})"
        if kind == "type":
            self.type(op.get("text", ""));         return f"type({op.get('text', '')!r})"
        if kind == "select_all":
            self.select_all();                     return "select_all()"
        if kind == "press_enter":
            self.press_enter();                    return "press_enter()"
        if kind == "press_esc":
            self.press_esc();                      return "press_esc()"
        if kind == "press_tab":
            self.press_tab();                      return "press_tab()"
        if kind == "delete_selected":
            self.delete_selected();                return "delete_selected()"
        if kind == "scroll":
            self.scroll(op.get("dy", 0), op.get("dx", 0))
            return f"scroll(dy={op.get('dy', 0)}, dx={op.get('dx', 0)})"
        if kind == "hotkey":
            mapped = self.hotkey(op.get("keys") or [])
            return f"hotkey({'+'.join(mapped)})"
        raise ValueError(f"unknown op: {op!r}")
