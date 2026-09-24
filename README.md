# BIMArena — BIM authoring by computer use

An LLM agent operates **Autodesk Revit 2027** or **Graphisoft Archicad 29** through the
graphical user interface — screenshots in, mouse and keyboard out — and must bring the model
to the state a task requires (a text specification and/or 2D architectural drawings). The
saved project is graded programmatically through the applications' own APIs.

409 tasks in three tracks, each in both applications:

| track | what | cases (Archicad / Revit) |
|---|---|---|
| `atomic_tasks` | one fundamental capability per task (23 capabilities, `bench_cases/CAPABILITIES.md`) | 62 / 61 |
| `long-seq_tasks` | realistic multi-capability tasks, the requirement spelled out in text | 71 / 72 |
| `reasoning_tasks` | the same tasks driven by drawings / handbook figures / regulations | 71 / 72 |

```
bench_cases/           the dataset: <track>/<archicad|revit>/<case>/{task.json, drawing(s), env/start/}
authoring_framework/   the agent: one ReAct loop over a GUI action space, the 46 operational skills
bench_runner/          the harness: open case -> run agent -> save -> grade -> reports
bench_runner/backend/  the harness-side application backends (Tapir toolbox, Revit add-in)
bench_runner/vm/       the isolated-VM bench used for the paper's runs
```

---

## Quick start: reproduce a few cases

The shortest path is **bare metal**: one Windows machine with one of the two applications
open on its desktop. About half a day including the software installs; each case then takes
5–15 minutes.

### What you need

| | |
|---|---|
| Windows 10/11 | the applications only run on Windows; set the display to **1920×1080** |
| Revit 2027 **or** Archicad 29 | either one; an educational or 30-day trial licence is enough. Revit additionally needs the .NET 10 SDK to build the add-in |
| Python 3.14 | |
| one LLM API key | e.g. `Anthropic_KEY` or `OA_OPENAI_KEY` (the OpenAI key is also used for the skill retriever's embeddings; without it retrieval falls back to keyword scoring) |
| ~5 GB disk | the repository (140 MB) plus, for the main tracks only, the start projects (2 GB download, 2.9 GB unpacked) |

### Step 1 — install (15 min)

```powershell
git clone https://github.com/bimarenaanon/BIMArena.git ; cd BIMArena
py -3.14 -m venv bench_env
bench_env\Scripts\Activate.ps1           # every new terminal; cmd.exe: bench_env\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env                # fill in ONE LLM key; ignore the VM_* block
```

If PowerShell refuses to run the activation script, allow it once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Every command below assumes the
activated venv (`python` = `bench_env\Scripts\python.exe`). Two offline checks (no
application needed):

```powershell
python -m authoring_framework --help
python bench_cases\atomic_tasks\validate_env_archicad.py --start-only
#   -> "0 case(s) satisfied by their own start state": no atomic case passes without work
```

### Step 2 — the application and its add-in (30 min + download time)

**Getting the software.** Both vendors offer a 30-day trial and a free one-year educational
licence (student or teacher status, verified with an institutional e-mail or an enrolment
document); either is enough for the bench.

| | trial | educational licence |
|---|---|---|
| Revit 2027 | [autodesk.com/products/revit/free-trial](https://www.autodesk.com/products/revit/free-trial) | [autodesk.com/education/edu-software/revit](https://www.autodesk.com/education/edu-software/revit) |
| Archicad 29 | [graphisoft.com/en-us/trial](https://www.graphisoft.com/en-us/trial/) | [myarchicad.graphisoft.com](https://myarchicad.graphisoft.com/) ([how to apply](https://www.graphisoft.com/en-us/plans-and-products/education/)) |

The add-ins below are the **harness's** way into the application (open/save projects, read
the model for grading). The agent never uses them — it only sees the screen.

**Archicad 29** (simplest — nothing to compile): install Archicad (its installer includes the
library the cases use), then Options → Add-On Manager → Add →
`bench_runner\backend\archicad\tapir_addon\TapirAddOn_AC29_Win.apx` → tick it → restart
Archicad. Set the Toolbox to show text labels beside the icons (right-click the Toolbox).

**Revit 2027**: install Revit, then install the **content library** — the cases' door,
window and other families come from Autodesk's stock content, which the Revit installer does
NOT include. Sign in to your Autodesk Account → All Products and Services → Revit → View
Details → Available Downloads → **Libraries** → download and run **"US English Content for
Revit 2027"** (it installs to `C:\ProgramData\Autodesk\RVT 2027\Libraries`; see
[Download and Install Revit Content](https://help.autodesk.com/view/RVT/2027/ENU/?guid=GUID-A69690A6-62F3-48C6-9F34-043051F815CE)).
Then build the add-in:

```powershell
winget install Microsoft.DotNet.SDK.10
cd bench_runner\backend\revit\addon\BimAgent
dotnet build                          # deploys BimAgent.dll + .addin to %APPDATA%\Autodesk\Revit\Addins\2027\
cd ..\..\..\..\..
```

Start Revit; `http://localhost:48884/health` in a browser must answer `{"ok":true,...}`.
Then unassign the `CA` (Canvas Theme) keyboard shortcut (Keyboard Shortcuts → search
"canvas") — the agent types material names on the real keyboard and a stray `C`,`A` would
flip the canvas theme.

### Step 3 — put the start projects in place (5 min)

```powershell
# atomic track: every case's start project is a copy of one of the 8 versioned templates
python bench_cases\atomic_tasks\seed_envs.py

# main tracks (long-seq_tasks / reasoning_tasks): 286 projects, downloaded as two release archives
python bench_runner\dataset\projects.py unpack --release https://github.com/bimarenaanon/BIMArena/releases/download/v1.0
python bench_runner\dataset\projects.py check       # -> 286 present, 0 missing
```

Only the first command is needed to run atomic cases.

The default arm (`gui-support`, and `gui-docs`) gives the agent the vendors' official help
through `documentation_retrieval`. Those pages are copyrighted and not versioned; build the
two corpora once (network, ~10 min) or the agent refuses to start in those arms — run
`--phase gui-raw` to skip them entirely:

```powershell
python -m authoring_framework.knowledge.fetch_archicad_help     # 237 pages
python -m authoring_framework.knowledge.fetch_revit_help        # 478 pages
```

Six reasoning cases use a figure from
Neufert, *Architects' Data* (4th ed.) that is not distributed; with your own PDF of the book,
`bench_runner\dataset\extract_figures.py --pdf <Neufert.pdf>` cuts them out (`--check`
lists them). A case whose figure or start project is missing is skipped as not runnable.

**Drawing sources.** Several reasoning-track floor plans are adapted from publicly available
apartment plans; the faint watermarks of their producers (e.g. CubiCasa, virtualdesign.fi) are
left in place as attribution. The drawings are included for non-commercial research use; the
rights remain with their owners.

### Step 4 — run a case (5–15 min each)

A case is a directory `bench_cases\<track>\<application>\<case_id>\`; the case id is what
you pass to the runner. Atomic case ids are the paper's capability names plus a number
(`create_wall1`, `create_door2`, `replace_element_type5`, …); main-track ids are
`<letter>_<category><n>` (`B_element_creation3`). `bench_cases\README.md` lists every main-track case with its instruction, or
just look at the directory names, e.g. `dir bench_cases\atomic_tasks\revit`.

Have the application open with any project loaded, no dialog open, and leave the desktop
alone while it runs — the agent drives **this** screen, mouse and keyboard.

```powershell
# one case
python bench_runner\rerun_cases.py --phase gui-support --bench-root bench_cases\atomic_tasks --only create_wall1 `
    -p openai -m gpt-5.6-sol --results-dir bench_runner\results\review --note "review"

# several cases: list their ids after --only
python bench_runner\rerun_cases.py --phase gui-support --bench-root bench_cases\atomic_tasks --only create_wall1 create_wall2 create_door1 `
    -p openai -m gpt-5.6-sol --results-dir bench_runner\results\review --note "review"

# a whole track for one application, from a case list (bench_runner\cases\*.txt)
python bench_runner\rerun_cases.py --phase gui-raw --bench-root bench_cases\reasoning_tasks --from-file bench_runner\cases\full_revit.txt `
    -p openai -m gpt-5.6-sol --results-dir bench_runner\results\review --note "review"
```

| flag | meaning |
|---|---|
| `--bench-root` | the track (default `bench_cases\reasoning_tasks`): `bench_cases\atomic_tasks`, `bench_cases\long-seq_tasks`, `bench_cases\reasoning_tasks` |
| `--only <id> …` | the case(s) to run, by directory name; `--from-file <list.txt>` takes a list (`atomic_all_*`, `grounded_*` = long-seq, `full_*` = reasoning, per application) |
| `-p`, `-m` | the LLM provider (`openai`, `anthropic`, `gemini`, `qwen`, `meta`, or the self-hosted `evocua` / `opencua`) and model id; without them the agent uses `LLM_PROVIDER` / `LLM_MODEL` from `.env` |
| `--phase` | **required** — the support arm: `gui-raw` (no retrieval), `gui-docs` (official documentation), `gui-support` (documentation + the 46 operational skills — the paper's "w/ support") |
| `--results-dir` | where the results go (any new directory) |
| `--note` | free text recorded with the run |

The application is **detected**, never passed: the runner finds the one that is open and
runs the case from that application's tree. Per case it opens the start project, launches
the agent as a subprocess, waits for its final `RESULT:` reply, saves the project, reads it
back through the add-in and grades it against `task.json`'s `expected_result`; the console
prints PASS/FAIL with PCS and CFR.

The model's key must be in `.env`; the self-hosted `evocua` / `opencua` take their vLLM
endpoint from `EVOCUA_BASE_URL` / `OPENCUA_BASE_URL` there. Coordinate frames and prompt
formats are resolved per model automatically. Turn budget (atomic 100, main tracks 300), the 60-minute wall
clock, 1920×1080 screenshots (downscaled client-side for Claude, whose clicks are mapped back) and the LLM settings (T = 1.0, 8 192 output tokens,
reasoning `high`) are the paper's defaults — no flags needed.

### Step 5 — read the results

```
bench_runner\results\review\create_wall1\archicad\
    score_gui-support.json        every checkpoint (goal / preservation), pcs, cfr, the run stats
    EVAL.md                       the same, rendered
    result_gui-support.pln        the project the agent left — open it in the application
    gui-support\agent_run\        memory.json (per-turn reasoning, final answer, settings),
                                  trace.jsonl, screenshot\ (one per turn)
bench_runner\results\review\EVAL_RESULTS.md      the summary table, regenerated after every case
```

**Metrics** (`bench_runner/verifier/grade.py`): every check is a binary checkpoint. Goal
checkpoints feed **PCS** (fraction satisfied); preservation checkpoints feed **CFR** (1 only
when all hold); a task counts as **SR** success only when both are complete. Runs are
stochastic (T = 1.0, one run per task in the paper), so individual cases may come out
differently — compare rates, not single cases.

---

## The full benchmark: the isolated-VM bench

The paper's numbers were produced with every case inside a **VMware Workstation** guest
restored from a running-state snapshot before and after it, so no case can contaminate the
next, and several guests can run in parallel. The runner is the same `rerun_cases.py`; the
host script `bench_runner\vm\vm_bench.py` reverts the guest, copies the case in, runs the
runner inside the guest's desktop session through a shared folder and collects the results.
The setup — guest image, shared folder, guest venv, add-in deployment, snapshots, `.env`
`VM_*` keys — and the batch commands are documented in
[`bench_runner/vm/README.md`](bench_runner/vm/README.md). A whole arm of one track on one
application is a few hours on one guest.

Result trees follow `bench_runner\results\<model>\<track>\{1_raw,2_docs,3_support}\<application>`;
`bench_runner\reports\gen_eval_results.py`, `recompute_metrics.py` and `gen_main_table.py`
turn them into the summary documents and the SR/PCS/CFR table. `rerun_cases.py --regrade`
re-grades saved results without an agent run.

## Where things are

- [`bench_cases/README.md`](bench_cases/README.md) — the generated per-case index (instruction,
  required capabilities, input). A case is `task.json` (`instruction`, `required_capabilities`,
  `expected_result` — never shown to the agent), its drawings and `env/start/` (the start
  project plus `baseline.json`, its pre-state snapshot). Geometry is in millimetres.
- [`bench_cases/CAPABILITIES.md`](bench_cases/CAPABILITIES.md) — the 23 fundamental capabilities
  and their mapping onto both applications.
- [`authoring_framework/README.md`](authoring_framework/README.md) — the agent: the loop, the
  action space (`tools/TOOLS.md`), the system prompt (`prompt/react.prompt`), the operational
  skills (`software_skills/`), the providers.
- [`bench_runner/README.md`](bench_runner/README.md) — the runner, per-machine setup, metrics,
  reports; [`bench_runner/verifier/README.md`](bench_runner/verifier/README.md) — the
  `expected_result` schema.
- [`bench_runner/backend/revit/addon/README.md`](bench_runner/backend/revit/addon/README.md) — the
  Revit add-in.
