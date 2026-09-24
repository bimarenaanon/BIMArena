"""Prepare ONE guest's snapshots from a powered-off state, fully automated.

    python bench_runner/vm/prep_vm.py <vmx> [--revit-snapshot NAME] [--archicad-snapshot NAME]
                                            [--off-snapshot NAME] [--skip-off]

Sequence: start -> wait for the desktop session, the share and the venv -> launch Revit,
pin 1920x1080, wait for /health -> snapshot (running) -> close Revit, launch Archicad,
wait for the Tapir port, park the mouse -> snapshot (running) -> clean guest shutdown ->
snapshot (powered off; the linked-clone base). Snapshots with the same names are deleted
first, so the script is re-runnable. Needs an UNENCRYPTED VM (vmrun snapshot refuses an
encrypted one that is open in the UI).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from vm import vm_bench as vb  # noqa: E402
from vm.vmrun import VM  # noqa: E402

REVIT_EXE = r"C:\Program Files\Autodesk\Revit 2027\Revit.exe"
ARCHICAD_EXE = r"C:\Program Files\GRAPHISOFT\Archicad 29\Archicad.exe"
RES_SET = (r"cmd /c '\"C:\Program Files\VMware\VMware Tools\VMwareResolutionSet.exe\" "
           r"0 1 , 0 0 1920 1080' 2>&1 | Out-Null")


def log(msg):
    vb._log(msg)


def wait_desktop(vm: VM, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if vm.powershell("exit 0", interactive=True, timeout=60) == 0:
                return
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError("the guest desktop session never came up")


def wait_share(vm: VM, g, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if vb.share_ok(vm, g):
            return
        time.sleep(3)
    raise RuntimeError("the share / venv never became visible in the guest")


def fresh_snapshot(vm: VM, name: str):
    if name in vm.list_snapshots():
        log(f"deleting old snapshot {name!r}")
        vm.delete_snapshot(name)
    t = time.time()
    vm.snapshot(name)
    log(f"snapshot {name!r} taken in {time.time() - t:.0f}s")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("vmx")
    p.add_argument("--revit-snapshot", default="S1-Revit-Exp-Start")
    p.add_argument("--archicad-snapshot", default="S2-Archicad-Exp-Start")
    p.add_argument("--off-snapshot", default="S0-Base-Off")
    p.add_argument("--skip-off", action="store_true", help="no powered-off base snapshot")
    p.add_argument("--skip-archicad", action="store_true")
    p.add_argument("--skip-revit", action="store_true", help="resume after the Revit snapshot")
    a = p.parse_args(argv)

    c = vb._cfg()
    vm = VM(a.vmx, vm_password=c.get("VM_PASSWORD"), guest_user=c.get("VM_GUEST_USER"),
            guest_password=c.get("VM_GUEST_PASSWORD"))
    g = vb.Guest(c)
    t0 = time.time()

    if not vm.is_running():
        log("starting the guest")
        vm.start()
    vm.wait_for_tools(timeout=600)
    vm.enable_shared_folders()
    wait_desktop(vm)
    wait_share(vm, g)
    log(f"guest up: desktop + share + venv after {time.time() - t0:.0f}s")

    # ---- Revit idle
    if not a.skip_revit:
        vm.powershell("Get-Process Archicad,Revit -ErrorAction SilentlyContinue | Stop-Process -Force; "
                      f"Start-Process '{REVIT_EXE}'; {RES_SET}; exit 0", interactive=True, timeout=120)
        if not vb.wait_for_app(vm, "revit", timeout=600):
            raise RuntimeError("Revit's add-in never answered /health")
        time.sleep(10)
        vm.powershell(f"{RES_SET}; exit 0", interactive=True, timeout=60)
        fresh_snapshot(vm, a.revit_snapshot)

    # ---- Archicad idle
    if not a.skip_archicad:
        vm.powershell("Get-Process Revit -ErrorAction SilentlyContinue | Stop-Process -Force; "
                      f"Start-Sleep 3; Start-Process '{ARCHICAD_EXE}'; exit 0",
                      interactive=True, timeout=120)
        if not vb.wait_for_app(vm, "archicad", timeout=600):
            raise RuntimeError("Archicad's API port never answered")
        time.sleep(15)
        # park the mouse on the canvas (a hover over the toolbox leaves a tooltip in the shot)
        vm.powershell(f"& '{g.python}' -c 'import pyautogui; pyautogui.moveTo(1000, 600)'; "
                      f"{RES_SET}; exit 0", interactive=True, timeout=60)
        time.sleep(3)
        fresh_snapshot(vm, a.archicad_snapshot)

    # ---- powered-off base (the linked-clone source)
    if not a.skip_off:
        vm.powershell("Get-Process Archicad,Revit -ErrorAction SilentlyContinue | Stop-Process -Force; exit 0",
                      interactive=True, timeout=60)
        vm.stop(hard=False)
        for _ in range(100):
            if not vm.is_running():
                break
            time.sleep(3)
        if vm.is_running():
            raise RuntimeError("the guest did not shut down")
        fresh_snapshot(vm, a.off_snapshot)

    log(f"done in {time.time() - t0:.0f}s; snapshots: {vm.list_snapshots()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
