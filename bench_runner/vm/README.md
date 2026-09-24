# bench_runner/vm — the isolated-VM bench

Every case runs inside a VMware Workstation guest that is **restored from a snapshot before
and after it**, so nothing a run does (a saved-over template, a leftover dialog, a stray
type-ahead buffer, a modified Revit shortcut file) can reach the next case.

**The code stays on the host.** This repo is shared into the guest as a VMware shared folder
(mapped to a drive, `Z:` by default); the guest executes the host's files in place, and the
agent's `runs/`, the batch logs and the results are written straight back to the host's disk
through the share. Nothing is cloned or synced.

```
host (this repo, shared as Z:)                     guest (VMware, snapshot S1-Revit-Exp-Start)
───────────────────────────────                    ──────────────────────────────────────
vm_bench.py run --only <case>
  │ revert <snapshot>  ─────────────────────────▶  Revit open, add-in serving, desktop idle
  │ push-case          ─────────────────────────▶  robocopy Z:\bench_cases\..\<case>  ->  C:\bench\workspace\bench_cases\..\<case>
  │ run .cmd           ─────────────────────────▶  C:\bench\venv\...\python.exe  Z:\bench_runner\rerun_cases.py --only <case>
  │                                                  open the WORKSPACE copy -> agent -> Save As -> grade LIVE
  │ tail vm_stdout.log ◀── (written onto Z:) ──    results -> Z:\bench_runner\results\<tree>\<case>\  (= the host)
  │ revert <snapshot>  ─────────────────────────▶  clean again
  └ EVAL_RESULTS.md regenerated on the host
```

Why the Python process still has to run in the guest: the GUI arms drive the **guest's**
screen, mouse and keyboard (pyautogui must run where the desktop is), the runner's own
open/Save-As are keyboard-driven too, and both add-ins bind to the guest's `localhost`. So
`rerun_cases.py` runs unchanged inside the guest — reading its code from the share.

What must live IN the guest (all baked into the snapshot):

- the BIM application + its add-in;
- a Python venv **outside the share** (`C:\bench\venv`) — a Windows venv carries absolute
  paths, so the host's `bench_env` cannot be reused;
- a local **workspace** (`C:\bench\workspace`) that receives a copy of each case's pristine
  dir before the run. The application writes lock/backup files beside the project it opens;
  opening it from the share would leave those in the host's `env/start/` — the very
  contamination the VM exists to prevent. The copy excludes application leftovers (grading needs only
  `task.json` + `env/start/baseline.json`; the GT models are not in the dataset at all).

## One-time guest setup (then take the snapshot)

1. Windows 11 guest, VMware Tools installed, **auto-login** to the bench account, screen
   lock / sleep / screensaver disabled, a fixed display resolution (the GUI arms read
   coordinates off screenshots — never change it after the snapshot).
2. VM settings → Options → Shared Folders: share this repo's root, **map as a network
   drive** (`Z:`). In the guest, `Z:\bench_runner\rerun_cases.py` must exist.
3. Install the BIM application(s). Revit 2027 (ships its own .NET 10 runtime — **no SDK
   needed in the guest**); Archicad 29 with the Tapir add-on
   (`bench_runner/backend/archicad/tapir_addon/TapirAddOn_AC29_Win.apx` via Options → Add-On Manager).
4. Build the guest venv (Python 3.14, same as the host):
   ```powershell
   py -3.14 -m venv C:\bench\venv
   C:\bench\venv\Scripts\pip install -r Z:\requirements.txt
   ```
5. **Deploy the Revit add-in** from the host (Revit CLOSED in the guest):
   ```powershell
   bench_env\Scripts\python.exe bench_runner\vm\vm_bench.py deploy-addin
   ```
   This zips the host's already-built `%APPDATA%\Autodesk\Revit\Addins\2027\` (BimAgent.dll +
   BimAgent.addin) onto the share and expands it into the same
   per-user folder in the guest. The add-in source stays in this repo and is built on the
   host (`dotnet build` in `bench_runner/backend/revit/addon/BimAgent`); the guest only ever
   receives the build output. Then start Revit in the guest and check
   `http://localhost:48884/health` answers.
6. Per-machine Revit setup (see `bench_runner/README.md`): remove the `CA` Canvas-Theme
   shortcut; make sure a plan view is the active view in every start project.
7. Take the snapshots: `bench_env\Scripts\python.exe bench_runner\vm\prep_vm.py <vmx>` boots
   the guest, brings Revit to its idle state (open, no document, 1920x1080) and snapshots
   it as `S1-Revit-Exp-Start`, swaps to Archicad for `S2-Archicad-Exp-Start`, then shuts
   the guest down cleanly for the powered-off `S0-Base-Off` (the linked-clone base). On an
   ENCRYPTED VM vmrun cannot snapshot ("Authentication for encrypted virtual machine
   failed"): take them in the Workstation UI instead, or better, remove the encryption.
   The running snapshots MUST be taken while the guest is running: a revert then restores memory
   too, so Revit is back in ~40 s instead of minutes, and the add-in's HTTP server is
   already listening (`revert` waits for `/health` and for the share before it reports
   the guest ready). A revert also restores the vmx's shared-folder flag as the snapshot
   saved it, so `restore()` re-enables sharing every time — nothing to do by hand.
   Reverting resets the guest resolution to whatever the snapshot had; set it before the
   snapshot and turn off View → Autosize → Autofit Guest in Workstation so a window
   resize cannot change it later.

The agent's `.env` is the host's (`Z:\.env`) — keys are configured once, on the host.

Host `.env` keys (see `.env.example`): `VM_VMX`, `VM_PASSWORD` (only for an ENCRYPTED VM —
Workstation encrypts a VM when it gets a virtual TPM, and `vmrun` then refuses even
`listSnapshots` without `-vp`; leave it empty once the encryption is removed),
`VM_GUEST_USER` / `VM_GUEST_PASSWORD` (the desktop account), `VM_SNAPSHOT`, `VM_TOOL`,
`VM_SHARE` (`Z:`), `VM_GUEST_PYTHON`, `VM_WORKSPACE`, `VM_WORKERS` (parallel guests).

## Running

```powershell
$py = "bench_env\Scripts\python.exe"
& $py bench_runner\vm\vm_bench.py status                  # power, tools, snapshots, share, /health
& $py bench_runner\vm\vm_bench.py run --phase gui-support --subset reasoning_tasks `
      --tree <model>/reasoning_tasks/3_support/revit `
      --from-file bench_runner\cases\full_revit.txt --note "<model> gui-support, VM"
& $py bench_runner\vm\vm_bench.py run ... --skip-done      # resume an interrupted arm
& $py bench_runner\vm\vm_bench.py revert                   # by hand: back to idle
& $py bench_runner\vm\vm_bench.py exec "Get-Process Revit | Select Id,MainWindowTitle"
```

- `--tree` is the results tree **relative to `bench_runner/results/`**; the guest writes into
  it through the share, so the host's tree IS the result — `EVAL_RESULTS.md` is regenerated
  after every case (header from `<tree>/header.md` if present).
- Per case: `<tree>/<case>/vm_stdout.log` (the guest runner's console, tailed live) and one
  line appended to `<tree>/vm_progress.jsonl`.
- The per-case timeout is the phase's agent timeout + 15 min for open/save/grade
  (`--timeout` overrides); on expiry the guest's python processes are killed and the guest
  is reverted; whatever the runner had already written is on the host.
- More `run` flags: `--env KEY=VALUE` (repeatable — how an arm's ablation switches, e.g.
  `LLM_EFFORT=low`, reach the guest), `--only`, `--tool`, `--snapshot`, `--max-turns`, `--regrade`,
  `--rescue`, `--workers`, `--keep-running`, `--no-revert`, `--poll`, `--quiet`, `--dry-run`.
  REPAIR HOLD: a failed case keeps the guest up for inspection for up to `--hold-max`
  (default 7200 s; `--no-hold` disables). Creating `<tree>/STOP` stops the batch gracefully
  after the case in hand.
- The application is NEVER passed to the agent; `rerun_cases.py` detects it in the guest
  exactly as on a bare-metal batch. `VM_TOOL` only tells the host which readiness probe to
  use (`/health` for Revit, the Tapir port for Archicad) and which result subdir to read.
- Shared-folder I/O (HGFS) is slower than a local disk; screenshots and `trace.jsonl`
  pay a small latency. If it ever matters, point `--results-dir` at the workspace instead
  and copy back — the code path is a two-line change in `run_case`.

## Parallel guests (linked clones)

One host can drive several guests at once; every guest takes the next case off one shared
queue and writes into the same host tree (case dirs never collide). Requirements: the
parent VM is **unencrypted** (Workstation refuses linked clones of an encrypted VM: remove
the vTPM and the encryption; Windows 11 runs fine without them once installed) and sized so
that N guests fit: at 4 vCPU / 12 GB three guests fit a 16-core / 64 GB laptop.

```powershell
$py = "bench_env\Scripts\python.exe"
& $py bench_runner\vm\prep_vm.py <parent.vmx>                 # S1-Revit / S2-Archicad (running) + S0-Base-Off
& $py bench_runner\vm\vm_bench.py clone BIMArena-A BIMArena-B  # linked clones of S0-Base-Off, beside the parent
& $py bench_runner\vm\vm_bench.py prep <A.vmx> <B.vmx>         # each clone gets its own S1/S2 (+ S0)
& $py bench_runner\vm\vm_bench.py run ... --workers "<parent.vmx>,<A.vmx>,<B.vmx>"
```

`VM_WORKERS` in `.env` (comma-separated vmx paths) makes `--workers` the default. All guests
must carry the same snapshot names, which `prep_vm.py` guarantees. Snapshot / clone /
delete through vmrun only work on an unencrypted VM; on an encrypted one they fail with
"Authentication for encrypted virtual machine failed" while the VM is open in the UI.
Licensing: every clone signs in with the same Autodesk / Graphisoft account. Test two
guests side by side before a batch, and switch accounts in the clones if a vendor kicks
concurrent sessions.
