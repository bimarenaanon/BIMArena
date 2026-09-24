# bench_runner — by-case runner + live grading

Runs selected bench cases against the live application (Archicad or Revit — detected, never
a flag) and grades each one immediately, in the **by-case results layout**:

    results/<tree>/<CASE_ID>/<app>/
        source.txt                 one-line provenance of the run
        result_<phase>.pln|.rvt    the project saved after the agent finished
        score_<phase>.json         live-graded checkpoint report + a "run" stats block
        EVAL.md                    the score json rendered per case (reports/case_eval_md.py)
        <phase>/command.txt        the exact agent command line
        <phase>/stdout.log         the agent's console output
        <phase>/agent_run/         the collected runs/<id>/ (memory.json, trace.jsonl, screenshots)
    results/<tree>/EVAL_RESULTS.md the summary document (see below)

Two ways to run it: **bare metal** (`rerun_cases.py` on the desktop the application is
open on) and **isolated** (`vm/vm_bench.py`, which restores a VMware snapshot around every
case and runs `rerun_cases.py` inside the guest — see `vm/README.md`).

## The loop, per case (`rerun_cases.py`)

1. **Open** the case's start project (`bench_cases/<subset>/<app>/<id>/env/start/*`). Revit:
   the BimAgent add-in's `/open` route — Ctrl+O + pasted path only as the fallback when the
   route refuses. Archicad: the start `.pln` is first COPIED to `result_<phase>.pln` and the
   COPY is Tapir-opened (Tapir has no Save As, so the run edits the result file in place and
   the pristine start project is never opened). Verified — a case whose project did not actually open is
   recorded as failed, never graded against the wrong document).
2. **Run** the agent as a subprocess:
   `python -m authoring_framework [<drawing>…] -i "<instruction>" --tools <phase>`
   with `$AGENT_MAX_TURNS` fixed per subset — atomic_tasks 100, reasoning_tasks and
   long-seq_tasks 300 (`--max-turns` overrides it for a batch).
3. **Collect** the agent's `runs/<id>/` into the case's results dir.
4. **Save** the finished project as `result_<phase>.*` (Revit: the add-in's `/saveas` route,
   Alt,F,A,P + the rescue ladder as the fallback; Archicad: an in-place Tapir `SaveProject` on
   the result copy, GUI Save-As as the fallback; existence-verified).
5. **Grade LIVE**: the open document is verified to BE the saved result (path on Archicad,
   title on Revit) and read in place — it is reopened only when that check fails; snapshot
   through the add-in, grade against `task.json`'s `expected_result` (baseline = the case's
   `env/start/baseline.json`) → `score_<phase>.json`.
6. Regenerate `EVAL_RESULTS.md` immediately — the summary stays live during a batch.

## Usage (repo root, the application open, no modal dialogs)

```powershell
$py = "bench_env\Scripts\python.exe"
& $py bench_runner\rerun_cases.py --phase gui-support --bench-root bench_cases\reasoning_tasks `
      --results-dir bench_runner\results\<tree> --from-file bench_runner\cases\full_archicad.txt `
      --note "<provenance>" --wait-for-app 30
& $py bench_runner\rerun_cases.py --phase gui-support --only A_setup_types1 --note "..." --dry-run
& $py bench_runner\rerun_cases.py --phase gui-raw --results-dir <tree> --only A_setup_types1 --regrade
```

- `--phase {gui-raw|gui-docs|gui-support}` (required) IS the agent's `--tools` mode (the
  api-* / hybrid-* phases are LEGACY — the framework is GUI-only — and are accepted only with
  `--regrade`); it also picks the timeout and the
  hard focus gate (the case is aborted if the application cannot be verified as the active
  window: an agent clicking into whatever else is focused is keyboard/mouse input into
  arbitrary applications).
- `--bench-root` selects the subset (`bench_cases/reasoning_tasks` default, `long-seq_tasks`, `atomic_tasks`).
- `--results-dir DIR` writes the batch into its own tree; `--eval-baseline` adds a Δ column.
- `--regrade` skips the agent and re-grades the existing result project (after a
  ground-truth / task.json fix, or when live grading is suspected to have read the wrong
  document — see below).
- `--wait-for-app N` pauses the batch while the application is down or a human holds the
  desktop, then retries the interrupted case. An LLM outage mid-case is neither saved nor
  graded; the case is retried once after `--llm-retry-wait`.
- `keep_awake.py` is started beside every batch (`--no-keep-awake` opts out): this box's
  policy locks the session after 900 s without input, and a locked desktop kills every
  remaining case at its project open.

## Per-machine setup (every bench box, once)

- **Revit: unassign the `CA` (Canvas Theme) shortcut.** The agent types material names like
  "Cast Concrete" on the real keyboard; one missed click lands the leading `C`,`A` on the
  canvas and flips the background dark mid-case. Remove it in Keyboard Shortcuts (search
  "canvas") or drop `Shortcuts="CA"` from `ID_CANVAS_THEME_SWITCH` in
  `%APPDATA%\Autodesk\Revit\Autodesk Revit 2027\KeyboardShortcuts.xml` (takes effect on the
  next start).
- **Revit: no typed shortcuts are needed** for the harness — edit modes are left by clicking
  the ribbon's red "Cancel Edit Mode" ✗ (located geometrically; `revit_io.py`), and a "Save
  File" prompt is answered with Enter (Esc = Cancel would wedge the batch).
- **Archicad: Tapir enabled**, the Toolbox wide (text labels beside the icons — set it once
  and bake it into the VM snapshot; the runner no longer drags the divider itself), no
  floating script palette (the runner closes Tapir's palette after every open).
- **Every start project saved with a plan view active** (rooms/levels are read off the active
  plan view; the snapshot flags NO active storey otherwise).

## Data-integrity checks

- **Wrong-document grading.** Live grading snapshots the ACTIVE document. If a restart left
  two documents open, the log carries `warning: doc title is 'revit', expected
  'result_<phase>'` — treat it as an alarm: the scores are PARTIAL, not zero (the count
  checkpoints still pass), so they look plausible. `--regrade` the affected cases; it reopens
  the saved result and is deterministic.
- **Partial snapshots.** Tapir does not always detail elements outside the ACTIVE window, so
  a model read while an Elevation/Section is open can miss walls that are present. The live
  snapshot source opens a floor-plan window first and the snapshot reports every skipped
  element; a grade that saw fewer pre-existing elements than the case started with, although
  nothing was deleted, is that symptom — `--regrade` it with a plan window active.
- Do not count passes with `grep -l '"passed": true'` — every unit inside a score carries its
  own `passed`; read the top-level key (what `gen_eval_results.py` does).

## Metrics — SR / PCS / CFR

Checkpoints fall into two disjoint classes: **C** (goal — what the task asks to add or change)
feeds **PCS** (fraction of goal checkpoints passed); **P** (preservation — what must survive
untouched) feeds **CFR** (1.0 only when every preservation checkpoint holds). A case SUCCEEDS
(SR) only when both are fully satisfied. Goal checkpoints the START state already satisfies are
restated preservation duties: `verifier/trivial_probe.py` finds that set and the runner passes
it to `grade(trivial=…)`, so they are graded under P. Every `score_<phase>.json` carries
`pcs` / `cfr` (+ `_passed` / `_total`) and a per-checkpoint `klass`.

## The summary document (`reports/gen_eval_results.py`)

```powershell
& $py bench_runner\reports\gen_eval_results.py bench_runner\results\<tree> --phase gui-support `
      --tool revit --bench-root bench_cases\reasoning_tasks [--baseline <other tree>] [--header-file header.md]
```

Per-case table (reward/checkpoints/score/Δ/time/tokens), totals and the by-category
breakdown. Cases without a score file get a counted-as-fail row (the
denominator never silently shrinks). `rerun_cases.py` and `vm_bench.py run` call this after
every finished case (header: `<tree>/header.md` when present).

## Layout

- `rerun_cases.py` — the by-case runner/grader. THE entry point.
- `case_io.py` — the ONE place the `bench_cases/` layout is resolved (`task.json` →
  `Case{id, tool, instruction, drawings, env_dir, pln}`).
- `cases/` — case-id lists for `--from-file` (one id per line, `#` comments).
- `vm/` — the isolated-VM bench: `vmrun.py` (the hypervisor wrapper) + `vm_bench.py`
  (revert → sync → run in guest → pull → revert). See `vm/README.md`.
- `drivers/` — `archicad_io.py` / `revit_io.py`: open / save the live project (Tapir open +
  `SaveProject`, the add-in's `/open` + `/saveas`, keyboard-driven Save-As as the fallback, the
  Revit pre-save rescue ladder).
- `reports/` — `gen_eval_results.py` (the tree's `EVAL_RESULTS.md`), `case_eval_md.py` (the
  per-case `EVAL.md`; `--watch` polls a running batch),
  `recompute_metrics.py` (back-fills PCS/CFR onto older reports, writes `results/METRICS.csv`)
  and `gen_main_table.py` (the SR/PCS/CFR LaTeX table from that CSV).
- `cases/` — the reusable case lists for `--from-file`: `full_*` = reasoning_tasks,
  `grounded_*` = long-seq_tasks, `atomic_all_*` = atomic_tasks.
- `dataset/` — `gen_cases_readme.py` regenerates `bench_cases/README.md` after changing a
  case; `projects.py` packs / unpacks the main tracks' start projects (release assets);
  `extract_figures.py` cuts the sourced figures; `anonymize_projects.py` scrubs a user name.
- `verifier/` — the grading core (`grade.py` + `checkers.py` + `geometry.py`, see its README
  for the `expected_result` schema), `baselines.py`, `sources.py` (the live
  snapshot sources), `trivial_probe.py` (which goal checkpoints the start state already
  satisfies), and the Revit GT capture tooling (`revit_capture_gui.py` / `revit_gt.py` /
  `gt_extract.py`).
- `keep_awake.py` — spawned by the runner so the desktop never locks (see above).
- `results/` — the output trees (git-ignored, created on demand; finished trees are archived
  outside the repo).
