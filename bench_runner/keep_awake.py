"""Keep this Windows session awake and UNLOCKED for the length of a bench batch.

Why this exists (2026-08-12): a batch that runs the agent over the API drives the desktop
only briefly, at the open/save of each case — the agent's own turns can run for 15+ minutes
with no keyboard or mouse input at all. This box locks after `InactivityTimeoutSecs` (a
machine policy, 900 s here), and a locked session has no activatable window: the runner's
`_focus_revit` finds nothing, pyautogui reads the cursor at a fail-safe corner, and EVERY
remaining case dies at its project open. That is exactly how the 08-12 revit api-priors
continuation lost 23 cases.

Two different timers have to be held off, and they need different mechanisms:

- display / system sleep -> `SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED |
  ES_SYSTEM_REQUIRED)`, which is a flag on THIS thread and holds while the process lives.
- the inactivity LOCK -> the above does nothing for it; the policy reads the last-input time
  (`GetLastInputInfo`), which only synthesized INPUT resets. So we nudge the mouse every
  `--interval` seconds: a RELATIVE move of `--pixels` and straight back, so the cursor ends
  where it started. Relative moves cannot land the pointer in a screen corner, which matters
  because pyautogui's fail-safe aborts the runner if it ever finds it there.

Run it BESIDE a batch (its own process, killed when the batch ends):

    bench_env\\Scripts\\python.exe bench_runner\\keep_awake.py            # until Ctrl+C
    bench_env\\Scripts\\python.exe bench_runner\\keep_awake.py --hours 8  # self-limiting

It cannot unlock an ALREADY-locked session — start it before the batch, not after.
"""
from __future__ import annotations

import argparse
import ctypes
import time
from ctypes import wintypes

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _move(dx: int, dy: int = 0) -> None:
    """One RELATIVE mouse move through SendInput — this is what resets the idle timer."""
    ev = _INPUT(type=INPUT_MOUSE,
                mi=_MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE,
                               time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(_INPUT))


def _nudge(pixels: int) -> None:
    """Out and back, so the cursor ends exactly where the user (or the runner) left it."""
    _move(pixels)
    time.sleep(0.05)
    _move(-pixels)


def _no_sleep() -> None:
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)


def _release() -> None:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", type=float, default=60.0, metavar="SECONDS",
                   help="seconds between nudges (default 60; keep it well under the "
                        "machine's InactivityTimeoutSecs)")
    p.add_argument("--pixels", type=int, default=1, metavar="PX",
                   help="how far the nudge moves before moving back (default 1)")
    p.add_argument("--hours", type=float, default=0.0,
                   help="stop after N hours (default: run until killed)")
    a = p.parse_args()

    _no_sleep()
    deadline = time.time() + a.hours * 3600 if a.hours > 0 else None
    limit = f"for {a.hours}h" if deadline else "until killed"
    print(f"[keep_awake] display/system sleep blocked; nudging the mouse {a.pixels}px every "
          f"{a.interval:.0f}s {limit}", flush=True)
    try:
        while deadline is None or time.time() < deadline:
            _nudge(a.pixels)
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        _release()
        print("[keep_awake] released", flush=True)


if __name__ == "__main__":
    main()
