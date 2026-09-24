"""Isolated-VM bench orchestrator: one case per snapshot restore, code stays on the host.

The host repo is SHARED into the guest (a VMware shared folder mapped to a drive, `VM_SHARE`,
e.g. `Z:`). Nothing is cloned or synced: the guest executes the host's files in place, the
agent's `runs/`, the batch logs and the results are written straight back onto the host's
disk through the share. What must live in the guest is only what cannot be shared:

* the BIM application and its add-in (baked into the snapshot),
* a Python venv OUTSIDE the share (`VM_GUEST_PYTHON` -- a Windows venv carries absolute
  paths, so the host's `bench_env` cannot be reused), and
* a LOCAL WORKSPACE (`VM_WORKSPACE`) that receives a copy of each case's pristine dir before
  the run. The application writes lock/backup files beside the project it opens; opening it
  from the share would leave those in the host's `env/start/` -- the very contamination the
  VM exists to prevent.

Per case the host does exactly this:

    revert <snapshot>          the guest comes back RUNNING with the BIM app open and idle
      -> push-case             robocopy <share>\\bench_cases\\... -> <workspace>\\bench_cases\\...
      -> rerun_cases.py        in the guest's desktop session, --only <case>:
                               open the workspace copy -> agent -> Save As -> grade LIVE,
                               results into <share>\\bench_runner\\results\\<tree> (= the host)
      -> tail the log          written by the guest onto the share; exit code in a marker file
    revert <snapshot>          nothing a run did survives into the next case

`rerun_cases.py` runs INSIDE the guest, unchanged: the GUI arms drive the guest's screen and
both add-ins bind to the guest's localhost. The host never runs the agent, the application
or the grader -- it only drives the hypervisor.

Configuration comes from `.env` (VM_* keys, see `.env.example`) or the environment:

    VM_VMX, VM_PASSWORD, VM_GUEST_USER, VM_GUEST_PASSWORD, VM_SNAPSHOT, VM_TOOL,
    VM_SHARE (guest path of this repo, default Z:), VM_GUEST_PYTHON, VM_WORKSPACE

Usage (repo root, host venv):

    python bench_runner/vm/vm_bench.py status
    python bench_runner/vm/vm_bench.py deploy-addin            # Revit closed in the guest
    python bench_runner/vm/vm_bench.py snapshot S1-Revit-Exp-Start   # after the guest is set up
    python bench_runner/vm/vm_bench.py run --phase gui-support --subset reasoning_tasks \\
        --tree <model>/reasoning_tasks/3_support/revit --only A_setup_types1 --note "..."
    python bench_runner/vm/vm_bench.py exec "Get-Process Revit | Select Id, MainWindowTitle"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
ROOT = BENCH.parent
sys.path.insert(0, str(BENCH))

from dotenv import dotenv_values  # noqa: E402

from case_io import discover_cases  # noqa: E402
from vm.vmrun import VM, VmrunError  # noqa: E402

XFER = HERE / ".xfer"                            # git-ignored; on the share, so both sides see it
# gui-raw / gui-docs / gui-support are the runnable arms; gui-priors (the old name of gui-support) and the
# api-* / hybrid-* names are LEGACY and only
# make sense with --regrade (the agent framework is GUI-only since 2026-09-21).
PHASES = ("gui-raw", "gui-docs", "gui-support", "gui-priors", "api-priors", "api-raw", "hybrid-priors", "hybrid-raw")
# rerun_cases.py's per-phase agent timeout (api arms 30 min, UI-driving arms 60 min again since
# 2026-09-03 — opus-5 at ~40 s/turn hit the old 60 min on 45% of GUI cases while every
# GPT-family case finished in under 60) + a margin for open / save / live grading.
CASE_TIMEOUT = {p: (1800.0 if p.startswith("api") else 3600.0) + 900.0 for p in PHASES}


# ---------------------------------------------------------------------- configuration
def _cfg() -> dict:
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    env.update(os.environ)                          # a shell override wins over .env
    env.setdefault("VM_SHARE", "Z:")
    env.setdefault("VM_GUEST_PYTHON", r"C:\bench\venv\Scripts\python.exe")
    env.setdefault("VM_WORKSPACE", r"C:\bench\workspace")
    env.setdefault("VM_TOOL", "revit")
    env.setdefault("VM_SNAPSHOT", "S1-Revit-Exp-Start")
    return env


def _vm(a) -> VM:
    c = _cfg()
    vmx = a.vmx or c.get("VM_VMX")
    if not vmx:
        sys.exit("VM_VMX is not set (.env) and --vmx not given")
    return VM(vmx, vm_password=c.get("VM_PASSWORD"), guest_user=c.get("VM_GUEST_USER"),
              guest_password=c.get("VM_GUEST_PASSWORD"), verbose=a.verbose)


class Guest:
    """Guest-side paths. `share` is where the guest sees THIS repo; a host path under ROOT
    maps onto the guest with `g.on_share(path)`."""

    def __init__(self, c: dict):
        self.share = c["VM_SHARE"].rstrip("\\")
        self.python = c["VM_GUEST_PYTHON"]
        # One workspace subdir PER HOST PROCESS: with --no-revert the previous run's copy
        # is still open in the application (its .rvt locked), so overwriting in place
        # fails; a fresh stamped dir never collides. A revert wipes them all anyway.
        self.ws = c["VM_WORKSPACE"].rstrip("\\") + "\\" + datetime.now().strftime("%Y%m%d-%H%M%S")

    def on_share(self, host_path: Path) -> str:
        rel = Path(host_path).resolve().relative_to(ROOT)
        return self.share + "\\" + str(rel).replace("/", "\\") if str(rel) != "." else self.share

    def case_src(self, subset: str, tool: str, cid: str) -> str:
        return self.on_share(ROOT / "bench_cases" / subset / tool / cid)

    def case_dst(self, subset: str, tool: str, cid: str) -> str:
        return rf"{self.ws}\bench_cases\{subset}\{tool}\{cid}"

    def bench_root(self, subset: str) -> str:
        return rf"{self.ws}\bench_cases\{subset}"


def _log(msg: str) -> None:
    who = threading.current_thread().name
    tag = "" if who == "MainThread" else f" {who}:"
    print(f"[{datetime.now():%H:%M:%S}]{tag} {msg}", flush=True)


def _unlink_retry(path: Path, tries: int = 10, wait: float = 1.0) -> None:
    """Delete a host file the HGFS server may still hold open for the guest (a launcher
    cmd.exe is still exiting, a zip just expanded). Never fatal: plumbing files only."""
    for _ in range(tries):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(wait)
    _log(f"could not delete {path.name} (still held by the share) — left in place")


# ---------------------------------------------------------------------- guest readiness
def wait_for_app(vm: VM, tool: str, timeout: float = 300, poll: float = 3.0) -> bool:
    """True once the guest's BIM application answers (Revit add-in /health, Tapir port)."""
    if tool == "revit":
        probe = ("try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "
                 "http://localhost:48884/health; if ($r.StatusCode -eq 200) { exit 0 } } "
                 "catch {}; exit 1")
    else:
        # a bare TCP connect (Test-NetConnection also does ICMP/route work and can hang
        # for a minute while the guest is busy right after a snapshot)
        probe = ("try { $c = New-Object Net.Sockets.TcpClient; "
                 "if ($c.ConnectAsync('127.0.0.1', 19723).Wait(3000) -and $c.Connected) "
                 "{ $c.Close(); exit 0 } } catch {}; exit 1")
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if vm.powershell(probe, timeout=60) == 0:
                return True
        except VmrunError:
            pass
        time.sleep(poll)
    return False


def share_ok(vm: VM, g: Guest) -> bool:
    """The guest sees this repo through the share (and its own venv exists)."""
    probe = (f"if ((Test-Path -LiteralPath '{g.on_share(BENCH / 'rerun_cases.py')}') -and "
             f"(Test-Path -LiteralPath '{g.python}')) {{ exit 0 }}; exit 1")
    try:                                 # interactive: the Z: mapping lives in that session
        return vm.powershell(probe, interactive=True, timeout=60) == 0
    except VmrunError:
        return False


def sync_guest_clock(vm: VM) -> None:
    """Set the guest's clock to the host's, right after a revert (2026-09-12).

    A revert restores the guest's clock to the moment the snapshot was taken. The Revit
    snapshots came back ten days behind, and every TLS handshake with api.openai.com then
    failed with "certificate is not yet valid" — twenty retries, zero tokens, a no-score per
    case — while other endpoints' older certificates still validated, so only the OpenAI
    route showed it. Nothing inside the guest fixes it on its own: the guest
    user's INTERACTIVE token is UAC-filtered (Set-Date is refused), w32time has no peer, and
    VMware Tools' host->guest sync (tools.syncTime) did not step a ten-day gap. What does
    work is a NON-interactive guest program: the Tools service runs it with the account's
    full token, and Set-Date succeeds. The script is copied into the guest (the service
    session has no drive mapping to the share), carries the host's time as a literal, and
    is fire-and-forget — a failure here only means the run behaves as before this fix."""
    stem = Path(vm.vmx).stem
    local = XFER / f"set_clock_{stem}.ps1"
    reader = XFER / "clock_read.ps1"             # interactive read-back, via the share (Z:)
    report = XFER / f"clock_{stem}.txt"
    reader.write_text("(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | Out-File -Encoding utf8 "
                      "(Join-Path $PSScriptRoot $args[0])\n", encoding="utf-8")
    for attempt in range(3):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        local.write_text(f"Set-Date -Date '{stamp}' | Out-Null\n", encoding="utf-8")
        try:
            vm.copy_to_guest(local, r"C:\bench\set_clock.ps1")
            vm.run_program(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                           "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", r"C:\bench\set_clock.ps1",
                           interactive=False, timeout=120)
            # VERIFY: the very first attempt after a revert has silently done nothing (the
            # Tools service was not ready to run guest programs yet), so read the clock back
            # through the interactive session and retry until the guest's DATE is today's.
            time.sleep(2.0)
            report.unlink(missing_ok=True)
            vm.powershell(rf"powershell -NoProfile -ExecutionPolicy Bypass -File "
                          rf"Z:\bench_runner\vm\.xfer\clock_read.ps1 {report.name}; exit 0",
                          interactive=True, timeout=120)
            seen = report.read_text(encoding="utf-8-sig").strip() if report.exists() else "?"
            if seen[:10] == stamp[:10]:
                _log(f"guest clock set to {stamp} (guest reads {seen})")
                return
            _log(f"guest clock still {seen} after attempt {attempt + 1} — retrying")
        except Exception as e:                   # noqa: BLE001 — never let the clock stop a case
            _log(f"guest clock sync attempt {attempt + 1} failed ({e.__class__.__name__}: {str(e)[:100]})")
        time.sleep(8.0)
    _log("guest clock NOT synced after 3 attempts — a direct-OpenAI run on this guest will fail TLS")


def restore(vm: VM, g: Guest, snapshot: str, tool: str, app_timeout: float = 300) -> None:
    _log(f"revert -> {snapshot}")
    vm.revert(snapshot)
    vm.wait_for_tools()
    vm.enable_shared_folders()           # a revert restores the vmx's hgfs.disable flag
    if not wait_for_app(vm, tool, timeout=app_timeout):
        raise VmrunError(f"{tool} is not answering in the guest after the revert -- the "
                         f"snapshot must be a RUNNING state with the application open")
    for attempt in range(15):            # the guest's persistent mapping reconnects lazily
        if share_ok(vm, g):
            break
        time.sleep(2.0)
    else:
        raise VmrunError(f"the guest does not see the repo at {g.share} or has no venv at "
                         f"{g.python} -- map the shared folder / build the venv, re-snapshot")
    sync_guest_clock(vm)                 # last: the guest is settled and Z: is visible for the read-back
    _log("guest ready")


# ---------------------------------------------------------------------- case copy
def push_case(vm: VM, g: Guest, subset: str, tool: str, cid: str) -> None:
    """Copy the case's PRISTINE dir from the share into the guest workspace. Application
    leftovers are excluded (so is any stray `gt` dir -- the GT models live outside the
    dataset and grading needs only task.json + env/start/baseline.json). robocopy exit codes below 8 are success."""
    src, dst = g.case_src(subset, tool, cid), g.case_dst(subset, tool, cid)
    if not (ROOT / "bench_cases" / subset / tool / cid / "task.json").is_file():
        sys.exit(f"no such case: bench_cases/{subset}/{tool}/{cid}")
    rc = vm.powershell(
        f"if (Test-Path -LiteralPath '{dst}') {{ Remove-Item -LiteralPath '{dst}' -Recurse -Force }}; "
        f"robocopy '{src}' '{dst}' /E /XD gt /XF *.lck *.bpn *.0???.rvt /R:2 /W:2 "
        f"/NFL /NDL /NJH /NJS | Out-Null; if ($LASTEXITCODE -ge 8) {{ exit 1 }}; "
        f"if (-not (Test-Path -LiteralPath '{dst}\\task.json')) {{ exit 2 }}; exit 0",
        interactive=True, timeout=900)
    if rc != 0:
        raise VmrunError(f"copying {src} -> {dst} failed (rc={rc})")


# ---------------------------------------------------------------------- one case
def run_case(vm: VM, g: Guest, *, cid: str, subset: str, tool: str, phase: str, tree: str,
             note: str, timeout: float, max_turns: int | None, poll: float,
             echo: bool, env: dict[str, str] | None = None, regrade: bool = False,
             rescue: bool = False) -> dict:
    host_tree = BENCH / "results" / tree
    host_case = host_tree / cid
    host_case.mkdir(parents=True, exist_ok=True)
    # the launcher lives in the git-ignored staging dir: cmd.exe holds it through the share
    # until it exits, so it cannot always be deleted right away and must not sit in results
    # ...and it is named per GUEST: several batches share this host dir, and two guests
    # starting on the same case id overwrote each other's launcher (2026-09-02: the parent
    # ran clone B's script and crashed on B's workspace)
    log_h, done_h, cmd_h = (host_case / "vm_stdout.log", host_case / ".vm_done",
                            XFER / f"run_{Path(vm.vmx).stem}_{cid}.cmd")
    for f in (log_h, done_h):
        f.unlink(missing_ok=True)

    # 1) the pristine case dir into the guest workspace
    push_case(vm, g, subset, tool, cid)

    # 2) launch rerun_cases.py in the guest's desktop session. The launcher, its log and its
    #    exit-code marker all live on the SHARE, so the host reads them as plain files.
    argv = [f'"{g.python}"', f'"{g.on_share(BENCH / "rerun_cases.py")}"', "--phase", phase,
            "--bench-root", f'"{g.bench_root(subset)}"',
            "--results-dir", f'"{g.on_share(host_tree)}"', "--only", cid,
            "--note", f'"{note}"', "--focus-countdown", "0",
            "--no-keep-awake",           # the guest has no lock policy; no mouse nudging
            # an LLM failure mid-case must NOT make the guest runner replay the whole case
            # inside the same launch: that doubled the wall clock past the host's case
            # timeout (2026-09-03, a 75-min case killed without a score). The case simply
            # ends without a score and a later run --skip-done picks it up again.
            "--llm-retries", "0"]
    if max_turns:
        argv += ["--max-turns", str(max_turns)]
    if regrade:                      # no agent: reopen the saved result and grade it
        argv.append("--regrade")
    if rescue:                       # no agent: save the OPEN document and grade it
        argv.append("--rescue")
    cmd_h.write_text("\r\n".join([
        "@echo off", f"pushd {g.share}\\", "set PYTHONUNBUFFERED=1", "set PYTHONUTF8=1",
        # the agent's runs/ tree goes to the GUEST-LOCAL workspace: runs/.current is one
        # pointer file, and with several guests running from the shared checkout each
        # harness collected another guest's run as its own record (2026-09-03). The
        # runner copies the run into the results dir before the revert wipes it.
        f"set AGENT_RUNS_DIR={g.ws}\\runs",
        # per-arm environment for the runner + agent (ablation switches);
        # set inside the launcher so it can never leak into another arm's process
        *[f"set {k}={v}" for k, v in (env or {}).items()],
        " ".join(argv) + f' > "{g.on_share(log_h)}" 2>&1',
        f'echo %ERRORLEVEL% > "{g.on_share(done_h)}"', "popd", ""]), encoding="utf-8")
    _log(f"{cid}: agent launched in the guest ({phase}, timeout {timeout:.0f}s)")
    vm.run_cmd_file(g.on_share(cmd_h), no_wait=True)

    t0, shown = time.time(), 0
    status = "running"
    while True:
        time.sleep(poll)
        text = log_h.read_text(encoding="utf-8", errors="replace") if log_h.exists() else ""
        if echo and len(text) > shown:
            for ln in text[shown:].splitlines():
                print("    | " + ln.rstrip(), flush=True)
        shown = len(text)
        if done_h.exists():
            rc_text = done_h.read_text(encoding="utf-8", errors="replace").strip()
            status = "finished" if rc_text == "0" else f"runner-rc={rc_text or '?'}"
            break
        if time.time() - t0 > timeout:
            _log(f"{cid}: TIMEOUT after {timeout:.0f}s -- killing python in the guest")
            vm.powershell("Get-Process python -ErrorAction SilentlyContinue | "
                          "Stop-Process -Force", timeout=60)
            status = "timeout"
            break
    secs = time.time() - t0
    for f in (cmd_h, done_h):            # launcher + marker are plumbing, not results
        _unlink_retry(f)

    # 3) the score is already on the host (results dir on the share)
    score_f = host_case / tool / f"score_{phase}.json"
    rec = {"case": cid, "status": status, "seconds": round(secs)}
    if score_f.is_file():
        try:
            s = json.loads(score_f.read_text(encoding="utf-8"))
            rec.update(passed=bool(s.get("passed")), score=s.get("score"),
                       reward=s.get("reward"))
        except Exception as e:                       # a half-written score is still a result
            rec["score_error"] = f"{type(e).__name__}: {e}"
    elif status == "finished":
        rec["status"] = "no-score"
    _log(f"{cid}: {rec['status']} in {secs:.0f}s"
         + (f" passed={rec['passed']} score={rec.get('score')}" if "passed" in rec else ""))
    return rec


# ---------------------------------------------------------------------- subcommands
def cmd_status(a) -> int:
    vm = _vm(a)
    c = _cfg()
    g = Guest(c)
    print(f"vmx:       {vm.vmx}")
    print(f"running:   {vm.is_running()}")
    print(f"snapshots: {vm.list_snapshots()}  (VM_SNAPSHOT={c['VM_SNAPSHOT']})")
    if vm.is_running():
        print(f"tools:     {vm.tools_state()}")
        if vm.tools_state() == "running" and vm.guest_user:
            print(f"guest ip:  {vm.guest_ip(wait=False)}")
            print(f"share:     {g.share} -> repo visible + venv at {g.python}: {share_ok(vm, g)}")
            print(f"{c['VM_TOOL']}:     "
                  f"{'answering' if wait_for_app(vm, c['VM_TOOL'], timeout=1) else 'NOT answering'}")
    return 0


def cmd_revert(a) -> int:
    c = _cfg()
    restore(_vm(a), Guest(c), a.snapshot or c["VM_SNAPSHOT"], a.tool or c["VM_TOOL"])
    return 0


def cmd_snapshot(a) -> int:
    vm = _vm(a)
    _log(f"taking snapshot {a.name!r} (guest state: {'running' if vm.is_running() else 'off'})")
    vm.snapshot(a.name)
    print(vm.list_snapshots())
    return 0


def cmd_push_case(a) -> int:
    vm = _vm(a)
    c = _cfg()
    g = Guest(c)
    tool = a.tool or c["VM_TOOL"]
    vm.wait_for_tools()
    for cid in a.cases:
        push_case(vm, g, a.subset, tool, cid)
        _log(f"pushed {a.subset}/{tool}/{cid} -> {g.case_dst(a.subset, tool, cid)}")
    return 0


def cmd_deploy_addin(a) -> int:
    """Zip the HOST's built+deployed Revit add-in folder onto the share and expand it into
    the guest's per-user Addins folder. Revit must be CLOSED in the guest (it holds the dll)."""
    vm = _vm(a)
    g = Guest(_cfg())
    src = Path(a.source) if a.source else (
        Path(os.environ["APPDATA"]) / "Autodesk" / "Revit" / "Addins" / a.revit_version)
    if not (src / "BimAgent.dll").is_file() or not (src / "BimAgent.addin").is_file():
        sys.exit(f"{src} holds no built BimAgent add-in -- build it first "
                 f"(dotnet build in bench_runner/backend/revit/addon/BimAgent)")
    files = [p for p in src.rglob("*") if p.is_file()]
    z = XFER / "revit_addin.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(src).as_posix())
    vm.wait_for_tools()
    if vm.powershell("if (Get-Process Revit -ErrorAction SilentlyContinue) { exit 2 }; exit 0",
                     interactive=True, timeout=60) == 2:
        sys.exit("Revit is running in the guest -- close it, then deploy (the dll is locked)")
    dest = rf"$env:APPDATA\Autodesk\Revit\Addins\{a.revit_version}"
    rc = vm.powershell(f"New-Item -ItemType Directory -Force -Path \"{dest}\" | Out-Null; "
                       f"Expand-Archive -LiteralPath '{g.on_share(z)}' -DestinationPath "
                       f"\"{dest}\" -Force; if (-not (Test-Path \"{dest}\\BimAgent.dll\")) "
                       f"{{ exit 3 }}; exit 0", interactive=True, timeout=300)
    _unlink_retry(z)                     # the HGFS server may still hold the zip briefly
    if rc != 0:
        sys.exit(f"deploy failed in the guest (rc={rc})")
    _log(f"deployed {len(files)} files to {dest} in the guest -- start Revit there and "
         f"check http://localhost:48884/health")
    return 0


def cmd_exec(a) -> int:
    """Runs BEFORE the share exists too (it is the tool for setting the guest up): the
    output goes to a guest-local temp file and comes back through vmrun's file copy."""
    vm = _vm(a)
    out_g = r"C:\Users\Public\vm_bench_exec.out"     # writable from any session / account
    out_h = XFER / "exec.out"
    out_h.unlink(missing_ok=True)
    vm.delete_file(out_g)                            # never show a previous call's output
    script = Path(a.script[1:]).read_text(encoding="utf-8") if a.script.startswith("@") \
        else a.script
    rc = vm.powershell(f"& {{ {script} }} *> '{out_g}'; exit $LASTEXITCODE",
                       interactive=a.interactive, timeout=a.timeout)
    try:
        vm.copy_from_guest(out_g, out_h)
        raw = out_h.read_bytes()                     # PowerShell 5.1's *> writes UTF-16LE
        enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
        print(raw.decode(enc, errors="replace").replace("\r\n", "\n"), end="")
    except VmrunError as e:
        print(f"[no output captured: {e}]")
    print(f"[exit {rc}]")
    return rc


def _workers(a) -> dict[str, VM]:
    """name -> VM for every guest this batch drives: `--workers` (comma-separated vmx
    paths), else $VM_WORKERS, else the one VM_VMX. All must hold the SAME snapshot names
    (prep_vm.py gives every guest the same set)."""
    c = _cfg()
    spec = a.workers or c.get("VM_WORKERS") or ""
    paths = [p.strip() for p in spec.split(",") if p.strip()] or [a.vmx or c.get("VM_VMX")]
    if not paths[0]:
        sys.exit("no VM: set VM_VMX / VM_WORKERS in .env or pass --vmx / --workers")
    out = {}
    for p in paths:
        name = Path(p).stem
        out[name] = VM(p, vm_password=c.get("VM_PASSWORD"), guest_user=c.get("VM_GUEST_USER"),
                       guest_password=c.get("VM_GUEST_PASSWORD"), verbose=a.verbose)
    return out


def cmd_run(a) -> int:
    c = _cfg()
    workers = _workers(a)
    g = Guest(c)
    tool = a.tool or c["VM_TOOL"]
    snapshot = a.snapshot or c["VM_SNAPSHOT"]
    bench_root = ROOT / "bench_cases" / a.subset
    tree = a.tree.strip("/\\").replace("\\", "/")
    host_tree = BENCH / "results" / tree
    timeout = a.timeout or CASE_TIMEOUT[a.phase]

    ids = list(a.only or [])
    if a.from_file:
        ids += [ln.strip() for ln in a.from_file.read_text(encoding="utf-8-sig").splitlines()
                if ln.strip() and not ln.startswith("#")]
    if not ids:
        sys.exit("give --only and/or --from-file")
    order = list(dict.fromkeys(ids))
    known = {cs.id: cs for cs in discover_cases(bench_root, tool=tool) if cs.runnable}
    missing = [x for x in order if x not in known]
    if missing:
        sys.exit(f"unknown/not-runnable case(s) in {a.subset}/{tool}: {', '.join(missing)}")
    if a.skip_done:
        order = [x for x in order
                 if not (host_tree / x / tool / f"score_{a.phase}.json").is_file()]

    print(f"VM bench: {len(order)} case(s) [{a.subset}/{tool} · phase={a.phase}] -> {host_tree}")
    print(f"  snapshot={snapshot}  share={g.share}  workspace={g.ws}  "
          f"per-case timeout={timeout:.0f}s")
    print(f"  workers ({len(workers)}): " + ", ".join(workers))
    for x in order:
        print(f"  {x}")
    if a.dry_run:
        return 0

    # The host-side LLM probes must test the SAME route the guest agents get: --env
    # overrides (e.g. ANTHROPIC_ROUTE=direct) apply to this process too.
    for kv in (a.env or []):
        k, v = kv.split("=", 1)
        os.environ.setdefault(k, v)
    host_tree.mkdir(parents=True, exist_ok=True)
    progress = host_tree / "vm_progress.jsonl"
    done: list[dict] = []
    queue = list(order)
    lock = threading.Lock()
    total = len(order)

    def worker(name: str, wvm: VM):
        """One guest: pull the next case off the shared queue until it is empty. Every
        guest has its own disk, so workspaces never collide; results land in distinct
        case dirs of the one host tree, and only the progress file / scoreboard regen
        are serialised."""
        while True:
            with lock:
                if not queue:
                    return
                if (host_tree / "STOP").exists():   # graceful stop: finish the case in hand,
                    _log(f"{name}: STOP file present — not taking another case")   # take no more
                    return
                cid = queue.pop(0)
                i = total - len(queue)
            print(f"\n### [{i}/{total}] {cid}  ({name})", flush=True)
            try:
                if a.no_revert:          # debugging aid: run on the guest AS IT IS
                    wvm.wait_for_tools()
                    wvm.enable_shared_folders()
                else:
                    _ensure_llm(name)          # never launch a case into a dead route
                    restore(wvm, g, snapshot, tool)
                rec = run_case(wvm, g, cid=cid, subset=a.subset, tool=tool, phase=a.phase,
                               tree=tree, note=a.note, timeout=timeout,
                               max_turns=a.max_turns, poll=a.poll,
                               echo=not a.quiet and len(workers) == 1,
                               env=dict(kv.split("=", 1) for kv in (a.env or [])),
                               regrade=a.regrade, rescue=a.rescue)
            except (VmrunError, subprocess.TimeoutExpired) as e:
                rec = {"case": cid, "status": "vm-error", "error": f"{type(e).__name__}: {e}"}
                _log(f"{cid}: !! {rec['error']}")
            rec["worker"] = name
            with lock:
                done.append(rec)
                with open(progress, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
                _regen_eval_md(host_tree, a.phase, tool, bench_root)
            if _llm_outage(host_tree / cid):
                # The guest runner gave the case up as "llm-unreachable" (with
                # --llm-retries 0 it does not replay). Churning through the queue while
                # the provider is down burns a revert + 10 minutes of retries per case for
                # nothing — wait here until a one-token probe answers again.
                rec["status"] = "llm-unreachable"
                _wait_for_llm(name)
            elif _needs_repair(rec) and not a.no_hold:
                # REPAIR HOLD (2026-09-04, user decision): the case ended WITHOUT a score for
                # a harness reason (save failed, runner crashed, wall-clock kill) — the model
                # is still open in the guest. Do not revert: leave the guest as it is, say so,
                # and wait for the operator to fix the cause and `run --rescue --no-revert
                # --only <case>` (save the open document + grade), then drop RESOLVED.
                fixed = _repair_hold(name, host_tree / cid, tool, a.phase, a.hold_max)
                if fixed:
                    rec.update(fixed)
                    with lock:
                        with open(progress, "a", encoding="utf-8") as fh:
                            fh.write(json.dumps({**rec, "status": "repaired"}) + "\n")
                        _regen_eval_md(host_tree, a.phase, tool, bench_root)
        # unreachable

    threads = [threading.Thread(target=worker, args=(name, wvm), name=name, daemon=True)
               for name, wvm in workers.items()]
    for t in threads:
        t.start()
        time.sleep(2.0)                  # stagger the first reverts a little
    for t in threads:
        t.join()

    if not a.keep_running:
        for name, wvm in workers.items():
            try:
                _log(f"{name}: final revert -> {snapshot} (leave the guest clean)")
                wvm.revert(snapshot)
            except VmrunError as e:
                _log(f"{name}: final revert failed: {e}")
    graded = [r for r in done if "passed" in r]
    print(f"\n=== finished: {len(graded)}/{len(done)} graded, "
          f"{sum(1 for r in graded if r['passed'])} passed ===")
    for r in done:
        if "passed" not in r:
            print(f"  !! {r['case']}: {r['status']} {r.get('error', '')}")
    return 0


def cmd_clone(a) -> int:
    """A LINKED clone of the parent from its powered-off base snapshot, beside the parent
    (`<parent dir>\\..\\<name>\\<name>.vmx`). Needs an unencrypted parent (Workstation refuses
    linked clones of encrypted VMs) that is not running. The clone inherits the disk state
    only -- give it its own running snapshots with `prep`."""
    vm = _vm(a)
    if vm.is_running():
        sys.exit("the parent is running -- stop it first (vmrun clone needs it powered off)")
    if a.from_snapshot not in vm.list_snapshots():
        sys.exit(f"snapshot {a.from_snapshot!r} not found; have {vm.list_snapshots()}")
    for name in a.names:
        dest = Path(vm.vmx).parent.parent / name / f"{name}.vmx"
        if dest.exists():
            _log(f"{name}: exists at {dest} -- skipped")
            continue
        t = time.time()
        vm._run("clone", str(dest), "linked", f"-snapshot={a.from_snapshot}",
                f"-cloneName={name}", timeout=1800)
        _log(f"{name}: linked clone created in {time.time() - t:.0f}s -> {dest}")
    return 0


def cmd_prep(a) -> int:
    """Give one or more guests their snapshots (see prep_vm.py), one after the other."""
    from vm import prep_vm
    for vmx in a.vmx_paths:
        _log(f"=== prep {vmx}")
        argv = [vmx]
        if a.skip_off:
            argv.append("--skip-off")
        if a.skip_archicad:
            argv.append("--skip-archicad")
        prep_vm.main(argv)
    return 0


def _llm_outage(host_case: Path) -> bool:
    """Did the guest runner end this case as an LLM outage (not saved, not graded)?"""
    log = host_case / "vm_stdout.log"
    try:
        return "llm-unreachable" in log.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        return False


def _needs_repair(rec: dict) -> bool:
    """A case that ended without a score for a HARNESS reason worth an operator's attention:
    the guest runner finished but produced no score (save/grade failed) or crashed. NOT an
    LLM outage (handled by _wait_for_llm) and not a scored result of any kind.

    A host wall-clock TIMEOUT is deliberately excluded (2026-09-12): a run that used its full
    time budget is a model result, not an environment fault, and holding the guest for an
    operator stalls a batch of a slow model on every over-budget case. Timeouts count as a
    failure and the batch moves on; set $VM_HOLD_TIMEOUT=1 to restore the hold for debugging."""
    st = str(rec.get("status") or "")
    if st == "timeout":
        return os.getenv("VM_HOLD_TIMEOUT", "0") == "1"
    return "passed" not in rec and (st == "no-score" or st.startswith("runner-rc"))


def _repair_hold(name: str, host_case: Path, tool: str, phase: str, hold_max: float) -> dict | None:
    """Park this worker with the guest UNTOUCHED until <case>/RESOLVED (repaired: re-read the
    score) or <case>/SKIP (give the case up) appears, the tree's STOP file appears, or
    `hold_max` seconds pass. Returns the score fields when a score exists afterwards."""
    marker = host_case / "REPAIR_HOLD.txt"
    resolved, skip = host_case / "RESOLVED", host_case / "SKIP"
    for f in (resolved, skip):
        if f.exists():
            f.unlink()
    marker.write_text(
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} {name}: {host_case.name} ended without a score "
        f"(harness failure). The guest is LEFT AS IS — the model is still open.\n"
        f"Fix the cause, then save + grade the open document with\n"
        f"  vm_bench.py --vmx <this guest> run --phase {phase} --tool {tool} ... --only "
        f"{host_case.name} --rescue --no-revert\n"
        f"and create {resolved.name} here to continue (or {skip.name} to give the case up). "
        f"Auto-continues after {hold_max:.0f}s.\n", encoding="utf-8")
    _log(f"{name}: !! REPAIR HOLD on {host_case.name} — guest left as is; fix, run --rescue "
         f"--no-revert, then drop {resolved} (auto-continue in {hold_max/60:.0f} min)")
    t0 = time.time()
    while time.time() - t0 < hold_max:
        if resolved.exists() or skip.exists() or (host_case.parent / "STOP").exists():
            break
        time.sleep(30)
    why = ("RESOLVED" if resolved.exists() else "SKIP" if skip.exists()
           else "STOP" if (host_case.parent / "STOP").exists() else "hold expired")
    for f in (resolved, skip, marker):
        if f.exists():
            f.unlink()
    score_f = host_case / tool / f"score_{phase}.json"
    out = None
    if score_f.is_file():
        try:
            sc = json.loads(score_f.read_text(encoding="utf-8"))
            out = {"passed": bool(sc.get("passed")), "score": sc.get("score"),
                   "reward": sc.get("reward")}
        except Exception:
            out = None
    _log(f"{name}: repair hold on {host_case.name} ended ({why}) — "
         + (f"score {out['score']} passed={out['passed']}" if out else "still no score"))
    return out


def _probe_llm():
    """The host-side one-token probe of the configured LLM provider (the same .env the guest
    agents read). No in-process retries: the caller polls."""
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("LLM_TIMEOUT", "40")
    os.environ.setdefault("LLM_RETRIES", "0")
    from authoring_framework.providers import llm      # noqa: E402  (lazy: host venv)
    llm.complete("Reply with exactly: ok", system="terse", role="probe")


def _ensure_llm(name: str) -> None:
    """One probe before a case launches; a provider that is down parks the worker in
    _wait_for_llm instead of launching a case that would die on its first call."""
    try:
        _probe_llm()
    except Exception as e:
        _log(f"{name}: LLM route down before launch ({type(e).__name__}) — waiting for it")
        _wait_for_llm(name)


def _wait_for_llm(name: str, timeout: float = 3600.0, poll: float = 60.0) -> None:
    """Block until the configured LLM route answers a one-token probe, up to `timeout`.
    Runs on the HOST — one probe per minute, not the guest's ten retries per case."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            _probe_llm()
            _log(f"{name}: LLM route answers again after {time.time() - t0:.0f}s")
            return
        except Exception as e:
            _log(f"{name}: LLM route still down ({type(e).__name__}); next probe in {poll:.0f}s")
            time.sleep(poll)
    _log(f"{name}: LLM route did not recover within {timeout:.0f}s — carrying on anyway")


def _regen_eval_md(host_tree: Path, phase: str, tool: str, bench_root: Path) -> None:
    try:
        from reports import gen_eval_results
        gargs = [str(host_tree), "--phase", phase, "--tool", tool, "--bench-root", str(bench_root)]
        hdr = host_tree / "header.md"
        if hdr.exists():
            gargs += ["--header-file", str(hdr)]
        gen_eval_results.main(gargs)
    except Exception as e:                           # the summary must never kill a batch
        _log(f"eval-md regen failed: {e}")


# ---------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vmx", default=None, help="override VM_VMX")
    p.add_argument("-v", "--verbose", action="store_true", help="print every vmrun command")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="power / tools / snapshots / share / guest app health")

    s = sub.add_parser("revert", help="revert to the idle snapshot and wait for the app")
    s.add_argument("--snapshot", default=None)
    s.add_argument("--tool", choices=("revit", "archicad"), default=None)

    s = sub.add_parser("snapshot", help="take a snapshot of the CURRENT guest state")
    s.add_argument("name")

    s = sub.add_parser("push-case", help="copy pristine case dirs into the guest workspace")
    s.add_argument("cases", nargs="+")
    s.add_argument("--subset", default="reasoning_tasks")
    s.add_argument("--tool", choices=("revit", "archicad"), default=None)

    s = sub.add_parser("deploy-addin", help="copy the host's built BimAgent add-in into the guest")
    s.add_argument("--source", default=None, help="host folder (default %%APPDATA%%\\Autodesk\\Revit\\Addins\\<ver>)")
    s.add_argument("--revit-version", default="2027")

    s = sub.add_parser("exec", help="run a PowerShell snippet in the guest and print its output")
    s.add_argument("script", help="the snippet, or @<host file> to read it from a .ps1 "
                                  "(shell quoting eats backslashes; UNC paths need a file)")
    s.add_argument("--service-session", dest="interactive", action="store_false",
                   help="run outside the desktop logon session (default: on the desktop, "
                        "where the Z: mapping and the screen are)")
    s.add_argument("--timeout", type=float, default=600)

    s = sub.add_parser("clone", help="linked clone(s) of the parent from its powered-off base snapshot")
    s.add_argument("names", nargs="+", help="clone names, e.g. BIMArena-A BIMArena-B")
    s.add_argument("--from-snapshot", default="S0-Base-Off")

    s = sub.add_parser("prep", help="boot guest(s) and take the Revit / Archicad / powered-off snapshots")
    s.add_argument("vmx_paths", nargs="+")
    s.add_argument("--skip-off", action="store_true")
    s.add_argument("--skip-archicad", action="store_true")

    s = sub.add_parser("run", help="the per-case revert -> run -> revert loop (one or more guests)")
    s.add_argument("--workers", default=None,
                   help="comma-separated vmx paths to drive IN PARALLEL (default $VM_WORKERS, "
                        "else the single VM_VMX); each guest takes the next case off one queue")
    s.add_argument("--phase", choices=PHASES, required=True)
    s.add_argument("--subset", default="reasoning_tasks", help="reasoning_tasks | long-seq_tasks | atomic_tasks")
    s.add_argument("--tree", required=True, help="results tree, relative to bench_runner/results")
    s.add_argument("--only", nargs="*", default=None)
    s.add_argument("--from-file", type=Path, default=None)
    s.add_argument("--note", default="", help="source.txt provenance line")
    s.add_argument("--tool", choices=("revit", "archicad"), default=None)
    s.add_argument("--snapshot", default=None)
    s.add_argument("--max-turns", type=int, default=None, help="turn cap for this batch (else the subset's default: "
                        "atomic 100, reasoning / long-seq 300)")
    s.add_argument("--env", action="append", metavar="KEY=VALUE",
                   help="environment for the guest runner + agent, e.g. --env LLM_EFFORT=medium "
                        "(the raw arm); repeatable")
    s.add_argument("--timeout", type=float, default=None, help="per case, seconds")
    s.add_argument("--poll", type=float, default=15.0, help="log/marker poll interval")
    s.add_argument("--skip-done", action="store_true", help="skip cases with a score on the host")
    s.add_argument("--regrade", action="store_true",
                   help="no agent run: reopen each case's saved result_<phase> file in the "
                        "guest and grade it (rerun_cases --regrade)")
    s.add_argument("--rescue", action="store_true",
                   help="no agent run: save the document the guest's application still has "
                        "OPEN into result_<phase> and grade it (use with --no-revert --only "
                        "<case> during a repair hold)")
    s.add_argument("--hold-max", type=float, default=7200.0,
                   help="repair hold: seconds to keep the guest untouched after a case "
                        "ended without a score for a harness reason (default 7200)")
    s.add_argument("--no-hold", action="store_true", help="no repair hold: revert as before")
    s.add_argument("--keep-running", action="store_true", help="no final revert")
    s.add_argument("--no-revert", action="store_true",
                   help="skip the per-case revert: run on the guest as it is (debugging, "
                        "e.g. testing a freshly deployed add-in before re-snapshotting)")
    s.add_argument("--quiet", action="store_true", help="do not echo the guest log")
    s.add_argument("--dry-run", action="store_true")

    a = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    XFER.mkdir(parents=True, exist_ok=True)
    if a.cmd == "run" and not a.note and not a.dry_run:
        p.error("--note is required (it becomes each case's source.txt provenance line)")
    return {"status": cmd_status, "revert": cmd_revert, "snapshot": cmd_snapshot,
            "push-case": cmd_push_case, "deploy-addin": cmd_deploy_addin,
            "exec": cmd_exec, "run": cmd_run, "clone": cmd_clone, "prep": cmd_prep}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
