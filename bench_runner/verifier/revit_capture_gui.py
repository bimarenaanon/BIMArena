"""Batch-capture Revit baselines + GT snapshots for the bench cases (GUI driver).

The GUI companion to revit_gt.py: OPENS each case's .rvt in the running Revit
(Ctrl+O + a clipboard-PASTED absolute path — a typed path gets truncated by the
Open dialog's autocomplete dropdown) and calls revit_gt.capture once the add-in
reports the document active BY TITLE (env file must be revit.rvt, GT revitgt.rvt).
Closing all docs between opens is mandatory: Revit cannot hold two same-named
documents, and a same-name open silently switches to the already-open one.

Per case:
  1. close every open doc (Ctrl+F4 until /health doc == None)
  2. Ctrl+O, paste the FULL path to env/revit/start/revit.rvt, Enter
  3. poll /health until doc == 'revit'  -> capture baseline.json
  4. close; if revitgt.rvt exists: open it, poll doc == 'revitgt' -> gt_snapshot.json

Run with the venv python (needs pyautogui), Revit open with the BimAgent add-in,
and DO NOT touch mouse/keyboard while it runs. From the repo root:
  bench_env\\Scripts\\python.exe bench_runner/verifier/revit_capture_gui.py one <case_id>
  bench_env\\Scripts\\python.exe bench_runner/verifier/revit_capture_gui.py all [start_from]
  bench_env\\Scripts\\python.exe bench_runner/verifier/revit_capture_gui.py close   # recovery
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCR = ROOT / "bench_runner" / "results" / "_capture_shots"   # stuck-state screenshots
sys.path.insert(0, str(ROOT / "bench_runner"))
sys.path.insert(0, str(ROOT))

from verifier import revit_gt  # noqa: E402  (capture/_fetch_live/_counts)

HEALTH = "http://localhost:48884/health"
BENCH = ROOT / "bench_cases" / "reasoning_tasks"

import pyautogui  # noqa: E402
pyautogui.FAILSAFE = False


def health(timeout=8):
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_err": type(e).__name__}


def doc_title():
    return health().get("doc")


def activate_revit():
    ps = ("$p=Get-Process revit -ErrorAction SilentlyContinue | "
          "Sort-Object StartTime | Select-Object -First 1; "
          "if($p){(New-Object -ComObject WScript.Shell).AppActivate($p.Id)|Out-Null}")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                   capture_output=True, timeout=20)
    time.sleep(1.0)


def shot(tag):
    SCR.mkdir(parents=True, exist_ok=True)
    p = SCR / f"shot_{tag}.png"
    pyautogui.screenshot().save(p)
    print(f"    [screenshot] {p}")
    return p


def close_all(max_tries=10):
    """Ctrl+F4 until no document is active. We never modify docs, so no save
    prompt is expected; if the title stops changing, screenshot and bail."""
    activate_revit()
    for i in range(max_tries):
        d = doc_title()
        if d is None:
            print("  closed: no active doc")
            return True
        pyautogui.hotkey("ctrl", "f4")
        time.sleep(2.0)
        if doc_title() == d:            # one more settle chance (big models)
            time.sleep(3.0)
            if doc_title() == d:
                pyautogui.hotkey("ctrl", "f4")   # maybe multiple views
                time.sleep(2.5)
    if doc_title() is None:
        print("  closed: no active doc")
        return True
    print("  STUCK closing (doc still", repr(doc_title()), ")")
    shot("close_stuck")
    return False


def set_clipboard(text: str):
    subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                   input=text, text=True, capture_output=True, timeout=20)


def _issue_open(path: Path):
    activate_revit()
    pyautogui.press("esc")               # dismiss any leftover dialog/tool
    time.sleep(0.8)
    pyautogui.hotkey("ctrl", "o")
    time.sleep(4.0)                      # Open dialog
    # PASTE the full path — typing gets truncated by the autocomplete dropdown
    set_clipboard(str(path))
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.8)
    pyautogui.press("enter")


def open_file(path: Path, want_title: str, attempts=3, wait_per_attempt=60):
    for attempt in range(1, attempts + 1):
        _issue_open(path)
        print(f"  opening {path.name} (try {attempt}) -> waiting for title {want_title!r}")
        deadline = time.time() + wait_per_attempt
        while time.time() < deadline:
            d = doc_title()
            if d == want_title:
                time.sleep(2.0)          # let the view finish settling
                print(f"  ACTIVE: {d!r}")
                return True
            time.sleep(3)
        # not loaded — clear whatever half-state is up and retry fresh
        print(f"  retry: doc={doc_title()!r} after {wait_per_attempt}s")
        pyautogui.press("esc")
        time.sleep(1.0)
    print(f"  TIMEOUT opening {path} (doc={doc_title()!r})")
    shot(f"open_stuck_{want_title}")
    return False


def do_case(cid: str) -> list[str]:
    import case_io
    case = case_io.case_path(BENCH, 'revit', cid)
    results = []
    env_rvt = case_io.env_of(case, "revit") / "start" / "revit.rvt"
    # the hand-modelled GT lives OUTSIDE the dataset, beside its snapshot (case_io.gt_dir)
    gt_rvt = case_io.gt_dir(case) / "revitgt.rvt"

    if env_rvt.exists():
        if not close_all():
            return [f"{cid}: ABORT (cannot close current doc)"]
        if open_file(env_rvt.resolve(), "revit"):
            msg = revit_gt.capture(cid, "baseline")
            print("  ", msg)
            results.append(f"{cid} baseline: {msg}")
        else:
            results.append(f"{cid} baseline: OPEN FAILED")
            return results
    else:
        results.append(f"{cid}: no env/revit/start/revit.rvt")
        return results

    if gt_rvt.exists():
        if not close_all():
            results.append(f"{cid} gt: ABORT (cannot close)")
            return results
        if open_file(gt_rvt.resolve(), "revitgt"):
            msg = revit_gt.capture(cid, "gt")
            print("  ", msg)
            results.append(f"{cid} gt: {msg}")
        else:
            results.append(f"{cid} gt: OPEN FAILED")
    return results


def main():
    cmd = sys.argv[1]
    if cmd == "close":
        ok = close_all()
        return 0 if ok else 1
    if cmd == "one":
        for line in do_case(sys.argv[2]):
            print("=>", line)
        return 0
    if cmd == "all":
        start = sys.argv[2] if len(sys.argv) > 2 else None
        summary = []
        for d in sorted(BENCH.iterdir()):
            if not d.is_dir():
                continue
            if start and d.name < start:
                continue
            summary += do_case(d.name)
        print("\n===== SUMMARY =====")
        for line in summary:
            print(line)
        return 0
    print("unknown cmd")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
