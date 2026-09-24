# authoring_framework

One computer-use agent, one loop, three support modes.

```
authoring_framework/
  react.py       THE AGENT: see the screen -> reason -> act -> ... -> answer
  config.py      providers, the turn cap, the two --tools modes, the --target selector
  prompt/        react.prompt — the one system prompt (a computer-use prompt; no procedures)
  providers/     llm.py (the LLM primitive, with native tool calling) + skills.py (skill retrieval)
  software_skills/  per-application GUI recipes, served by the operational_skill_retrieval tool
  memory/        MemoryStore: the per-run JSON record
  ults/          per-run directories (runs.py) and drawing -> PNG input (images.py)
  tools/         what the agent can DO — the action space
    gui/         THE ACTION SPACE: mouse + keyboard (computer use) + the two retrieval lookups
    api/backend/ NOT an action space — the application backends the bench harness grades
                 through: Archicad (Tapir) and Revit (HTTP add-in)
    target.py    which applications exist (the backend and config both read it)
  knowledge/     the official application help behind documentation_retrieval. The vendors'
                 help corpora are NOT shipped: build them once with
                 `python -m authoring_framework.knowledge.fetch_archicad_help` and
                 `python -m authoring_framework.knowledge.fetch_revit_help`
```

Run it (from the repo root, with the BIM application open):

```bash
python -m authoring_framework [<drawing> ...] -i "<instruction>" \
       [--tools gui-raw|gui-docs|gui-support] \
       [--target archicad|revit] [-p <provider>] [-m <model>]
```

## The loop

`react.py` hands the model the task, the drawing, and the action space as **native tool
declarations** — then loops: at the start of every turn it captures the screen and shows the
model the current and the previous capture (there is no screenshot tool); the model issues a
batch of mouse / keyboard actions and lookups, and the loop goes again until the model replies
without actions. There is no planner, no supervisor, no verify pass. A turn may carry several
tool calls (unlimited); `MAX_TURNS` (default 100, `$AGENT_MAX_TURNS` — the bench harness sets
it per subset: atomic 100, reasoning / long-seq 300) is the one run limiter. When the history grows past
`$AGENT_COMPACT_CHARS` (300k chars) it is folded into a written briefing (the opening task +
drawings always survive).

The framework keeps only what a language model cannot be trusted with, and all of it sits in
the tool layer rather than in the loop:

| | |
|---|---|
| `tools.plan_batch` | validates every call against the tool's declared params; a GUI batch is TRUNCATED at the first unusable call (the rest would act at a stale cursor position) |
| `tools.run_batch` | executes them in order, paced |
| `config.MAX_TURNS` | stops a run that is going nowhere |

Every call the model makes gets an answer, whatever happened to it — including "rejected
because X". A provider refuses the next turn if a tool call goes unanswered, and the reason is
better feedback than silence anyway.

## The action space — one interface, three support modes

Each mode is a strict superset of the one before it (no retrieval → the vendors' official
documentation → the benchmark authors' OPERATIONAL SUPPORT on top):

| mode | what the model is handed |
|---|---|
| `gui-raw` | mouse/keyboard ops only; the screen is captured and shown every turn (no tool) |
| `gui-docs` | gui-raw + `documentation_retrieval` (the official application help) |
| `gui-support` (default) | gui-docs + `operational_skill_retrieval` (the hand-written per-capability procedures) |

The GUI tools are application-agnostic, and nothing tells the agent which application it is
in: it reads the screen. `--target` only narrows which application's operational skills the
lookup serves.

## Direct vendor APIs only

Every LLM call goes to the vendor's own endpoint with the vendor's own key. The endpoints are pinned in `providers/llm.py`, so a stray `OPENAI_BASE_URL` /
`ANTHROPIC_BASE_URL` in the environment cannot re-route a run.

## Switching models — coordinates are handled for you

Models do not agree on what a click coordinate means: GPT and Claude answer in the PIXELS of
the screenshot they were sent; Gemini, Qwen, Meta, EvoCUA and OpenCUA answer on a 0-1000 GRID per axis;
and Claude's provider resizes large images server-side, which shifts every pixel answer.
`tools/gui/profile.py` resolves all of it from the MODEL ID: the decode frame, the matching wording in
the tool declarations, and the screenshot caps (Claude's are locked — the environment can only
tighten them). Just pass `-p/-m`; do not set `GUI_COORD_*` / `GUI_MAX_IMG_EDGE` /
`MAX_IMG_PIXELS` outside a deliberate ablation.

Every run prints the resolved profile (`[gui] frame=… wording=… img_edge<=…`) and records it
in `memory.json` (`gui_profile`, `stats.gui` with the sent-image size) and in the score's
`run.gui`. A model id no rule knows runs on its provider's default and prints a warning —
verify it once, then add a rule to `profile._MODEL_RULES`:

```bash
python -m authoring_framework.tools.gui.calibrate -p <provider> -m <model>   # PASS / FAIL
```

The probe hands the model the real `mouse_click` declaration and synthetic screenshots of the
size a run would send, and measures whether it answers in pixels, on the grid, or in the pixels
of a server-side RESIZED image; the evidence lands in `tools/gui/calibration/`.

`tools/TOOLS.md` is the generated reference of the action space; `bench_runner/README.md` and
`bench_runner/verifier/README.md` cover the harness, the backends and the grading schema.
