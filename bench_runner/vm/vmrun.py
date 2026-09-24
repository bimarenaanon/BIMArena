"""A thin, typed wrapper over VMware Workstation's `vmrun` for ONE guest.

Everything the isolated bench needs from the hypervisor is here and nothing else: power
and snapshot control, VMware Tools readiness, file transfer, and running a program in the
guest's INTERACTIVE desktop session (a GUI agent has to click on a real desktop).

Facts this wrapper encodes, each one paid for once:

* An ENCRYPTED VM (Workstation encrypts any VM with a virtual TPM, which Windows 11
  requires) refuses every vmrun operation without `-vp <password>` -- even `listSnapshots`
  ("A password is required for this operation").
* Guest operations (`runProgramInGuest`, `copyFile*`, `fileExistsInGuest` ...) need `-gu`/`-gp`
  and a guest with VMware Tools RUNNING; `checkToolsState` is the readiness probe.
* `runProgramInGuest -interactive` runs the program in the CONSOLE session of the logged-in
  user (the one whose desktop is visible) -- required for anything that drives the screen.
  Without it the program runs in a service session with no desktop and pyautogui fails.
* vmrun copies FILES, not directories: a directory travels as a zip.
* `revertToSnapshot` restores the snapshot's power state. A snapshot taken while the guest
  was RUNNING (the shape the bench wants -- the BIM application already open) comes back
  running, but is not guaranteed to; `ensure_running()` starts it if `list` does not show it.
"""
from __future__ import annotations

import base64
import os
import subprocess
import time
from pathlib import Path

DEFAULT_VMRUN = Path(r"C:\Program Files\VMware\VMware Workstation\vmrun.exe")
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
CMD = r"C:\Windows\System32\cmd.exe"


class VmrunError(RuntimeError):
    pass


class VM:
    def __init__(self, vmx: str | Path, *, vm_password: str | None = None,
                 guest_user: str | None = None, guest_password: str | None = None,
                 vmrun: str | Path | None = None, verbose: bool = False):
        self.vmx = str(vmx)
        self.vm_password = vm_password or None
        self.guest_user = guest_user or None
        self.guest_password = guest_password or None
        self.vmrun = str(vmrun or os.getenv("VMRUN") or DEFAULT_VMRUN)
        self.verbose = verbose
        if not Path(self.vmrun).exists():
            raise VmrunError(f"vmrun not found at {self.vmrun} (set $VMRUN)")
        if not Path(self.vmx).exists():
            raise VmrunError(f"vmx not found: {self.vmx}")

    # ------------------------------------------------------------------ plumbing
    def _argv(self, op: str, *args: str, guest: bool = False, with_vmx: bool = True) -> list[str]:
        argv = [self.vmrun, "-T", "ws"]
        if self.vm_password:
            argv += ["-vp", self.vm_password]
        if guest:
            if not (self.guest_user and self.guest_password):
                raise VmrunError("guest credentials required (VM_GUEST_USER / VM_GUEST_PASSWORD)")
            argv += ["-gu", self.guest_user, "-gp", self.guest_password]
        argv.append(op)
        if with_vmx:
            argv.append(self.vmx)
        argv += list(args)
        return argv

    def _run(self, op: str, *args: str, guest: bool = False, with_vmx: bool = True,
             timeout: float = 600, check: bool = True) -> subprocess.CompletedProcess:
        argv = self._argv(op, *args, guest=guest, with_vmx=with_vmx)
        if self.verbose:
            secret = {self.vm_password, self.guest_password} - {None}
            print("  $ vmrun " + " ".join("***" if a in secret else a for a in argv[1:]),
                  flush=True)
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            # a guest op can stall while VMware is still busy (a snapshot consolidating,
            # a revert settling) -- surface it as an ordinary VmrunError so callers' retry
            # loops see it instead of dying on a foreign exception type
            raise VmrunError(f"vmrun {op} timed out after {timeout:.0f}s")
        if check and r.returncode != 0:
            raise VmrunError(f"vmrun {op} failed ({r.returncode}): "
                             f"{(r.stdout or '').strip()} {(r.stderr or '').strip()}")
        return r

    # ------------------------------------------------------------------ power / snapshots
    def is_running(self) -> bool:
        r = self._run("list", with_vmx=False)
        want = os.path.normcase(os.path.abspath(self.vmx))
        return any(os.path.normcase(os.path.abspath(ln.strip())) == want
                   for ln in r.stdout.splitlines() if ln.strip().lower().endswith(".vmx"))

    def start(self, gui: bool = True) -> None:
        self._run("start", "gui" if gui else "nogui", timeout=300)

    def stop(self, hard: bool = False) -> None:
        self._run("stop", "hard" if hard else "soft", timeout=300)

    def ensure_running(self) -> None:
        if not self.is_running():
            self.start()

    def list_snapshots(self) -> list[str]:
        r = self._run("listSnapshots")
        return [ln.strip() for ln in r.stdout.splitlines()[1:] if ln.strip()]

    def revert(self, snapshot: str) -> None:
        have = self.list_snapshots()
        if snapshot not in have:
            raise VmrunError(f"snapshot {snapshot!r} not found; have {have}")
        self._run("revertToSnapshot", snapshot, timeout=900)
        self.ensure_running()

    def snapshot(self, name: str) -> None:
        """NOTE: on an ENCRYPTED VM that is open in the Workstation UI this fails with
        "Authentication for encrypted virtual machine failed" (revert works) -- take the
        snapshot in the UI instead."""
        self._run("snapshot", name, timeout=1800)

    def enable_shared_folders(self) -> None:
        """Idempotent. Needed after EVERY revert: the snapshot carries the vmx's
        `isolation.tools.hgfs.disable` as it was, and a revert restores it -- the guest's
        HGFS client then lists nothing and a mapped drive shows 'Unavailable' until the
        host re-enables sharing (the persistent mapping reconnects by itself on access)."""
        self._run("enableSharedFolders", timeout=120)

    def delete_snapshot(self, name: str) -> None:
        self._run("deleteSnapshot", name, timeout=1800)

    # ------------------------------------------------------------------ tools / guest readiness
    def tools_state(self) -> str:
        r = self._run("checkToolsState", check=False)
        return (r.stdout or r.stderr or "").strip()

    def wait_for_tools(self, timeout: float = 300, poll: float = 2.0) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.tools_state() == "running":
                return
            time.sleep(poll)
        raise VmrunError(f"VMware Tools not running after {timeout:.0f}s "
                         f"(state={self.tools_state()!r})")

    def guest_ip(self, wait: bool = True) -> str:
        r = self._run("getGuestIPAddress", *(["-wait"] if wait else []), timeout=180)
        return r.stdout.strip()

    # ------------------------------------------------------------------ files
    @staticmethod
    def _exists_answer(r: subprocess.CompletedProcess) -> bool:
        text = ((r.stdout or "") + (r.stderr or "")).lower()
        return "exists" in text and "does not exist" not in text and "not exist" not in text

    def file_exists(self, guest_path: str) -> bool:
        return self._exists_answer(self._run("fileExistsInGuest", guest_path, guest=True,
                                             check=False))

    def dir_exists(self, guest_path: str) -> bool:
        return self._exists_answer(self._run("directoryExistsInGuest", guest_path, guest=True,
                                             check=False))

    def mkdir(self, guest_path: str) -> None:
        """Create a guest directory and its parents (vmrun creates one level only)."""
        parts = Path(guest_path).parts
        for i in range(2, len(parts) + 1):
            p = str(Path(*parts[:i]))
            if not self.dir_exists(p):
                self._run("createDirectoryInGuest", p, guest=True)

    def delete_file(self, guest_path: str) -> None:
        if self.file_exists(guest_path):
            self._run("deleteFileInGuest", guest_path, guest=True)

    def copy_to_guest(self, host_path: str | Path, guest_path: str) -> None:
        self.mkdir(str(Path(guest_path).parent))
        self._run("copyFileFromHostToGuest", str(host_path), guest_path, guest=True,
                  timeout=1800)

    def copy_from_guest(self, guest_path: str, host_path: str | Path) -> None:
        Path(host_path).parent.mkdir(parents=True, exist_ok=True)
        self._run("copyFileFromGuestToHost", guest_path, str(host_path), guest=True,
                  timeout=1800)

    # ------------------------------------------------------------------ programs
    def run_program(self, program: str, *args: str, interactive: bool = True,
                    active_window: bool = True, no_wait: bool = False,
                    timeout: float = 3600) -> int:
        """Run `program args...` in the guest. Returns the guest exit code (0 when `no_wait`).

        Each arg is passed to vmrun as ITS OWN argument -- vmrun re-quotes every one, so a
        single string holding the whole command line reaches the program as one quoted
        argument (PowerShell then tries to parse "-NoProfile -Command ..." as a command and
        exits 1). vmrun reports a non-zero guest exit code as its own failure with the text
        "Guest program exited with non-zero exit code: N" -- parsed back into an int here.
        """
        flags = []
        if no_wait:
            flags.append("-noWait")
        if active_window:
            flags.append("-activeWindow")
        if interactive:
            flags.append("-interactive")
        r = self._run("runProgramInGuest", *flags, program, *args,
                      guest=True, timeout=timeout, check=False)
        if r.returncode == 0:
            return 0
        text = (r.stdout or "") + (r.stderr or "")
        marker = "non-zero exit code:"
        if marker in text:
            try:
                return int(text.split(marker, 1)[1].strip().split()[0])
            except ValueError:
                pass
        raise VmrunError(f"runProgramInGuest failed: {text.strip()}")

    def powershell(self, script: str, *, interactive: bool = False, no_wait: bool = False,
                   timeout: float = 600) -> int:
        """Run a PowerShell snippet in the guest and return its exit code. Nothing is
        captured -- a snippet that must report text writes a file that is copied back.
        The script travels as `-EncodedCommand` (base64 UTF-16LE), so no quoting rule of
        vmrun's, cmd's or PowerShell's can mangle it. A cmdlet failure (Expand-Archive on a
        drive this session does not have, say) becomes exit code 1 -- cmdlets never set
        $LASTEXITCODE, so without the wrapper `exit $LASTEXITCODE` reported success.

        `interactive` runs it in the logged-in user's DESKTOP session. That matters beyond
        the screen: a mapped drive (the Z: share) belongs to the logon session that mapped
        it, so a service-session PowerShell does not see it."""
        wrapped = ("$ErrorActionPreference = 'Stop'; try { " + script +
                   " } catch { Write-Error $_; exit 1 }")
        encoded = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
        return self.run_program(POWERSHELL, "-NoProfile", "-NonInteractive",
                                "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded,
                                interactive=interactive, active_window=interactive,
                                no_wait=no_wait, timeout=timeout)

    def run_cmd_file(self, guest_cmd_path: str, *, no_wait: bool = True,
                     timeout: float = 600) -> int:
        """Run a .cmd batch file in the interactive desktop session."""
        return self.run_program(CMD, "/c", guest_cmd_path, interactive=True,
                                active_window=True, no_wait=no_wait, timeout=timeout)
