# BimAgent — the Revit add-in behind the bench harness (native C# API)

The HARNESS-side backend for Revit. The agent never talks to it — it drives Revit through the
GUI only; this add-in is what `bench_runner` and the dataset tooling use to open and save
projects, read the model SNAPSHOT the grader compares, and apply the atomic cases' scripted
reference solutions. It serves the same action names and snapshot schema as the Archicad
(Tapir) backend, so the harness code is identical for both applications:

```bash
python bench_runner/rerun_cases.py --phase gui-support --only <case> --note "..."
```

**Deploying to a bench VM:** build here, then `bench_runner/vm/vm_bench.py deploy-addin`
copies the deployed `%APPDATA%\Autodesk\Revit\Addins\2027\` folder into the guest (Revit
closed there). The guest needs no .NET SDK — Revit 2027 ships the runtime.

## How it works

```
API tool backend (Python)                  Revit (this C# add-in, in-process)
  RevitToolbox.run_actions  ──HTTP POST──▶  /action   → Actions.Run  ─┐
  model_snapshot(tb)        ──HTTP GET ──▶  /snapshot → Reads.Snapshot ├─ marshalled onto the
  list_composites / ...     ──HTTP GET ──▶  /composites /elements ...  │   Revit API thread by
  bench harness (revit_io)  ──HTTP POST──▶  /open /saveas → Project    ┘   RevitDispatcher
```

`/open {path}` (open + activate, discard every other document) and `/saveas {path}` (save
the active document under a new name) are HARNESS routes, so
`bench_runner` does not have to open and Save-As by keystrokes; `revit_io.py` falls back to
the keyboard path when a route refuses (Revit inside a sketch/edit mode refuses both, just
as it greys the menu out). Both run under dialog/warning guards (`Project.UiGuards`).

`App` (IExternalApplication) starts a local `HttpServer` (`http://localhost:48884`) on a background
thread. Because the Revit API can only be used on the API thread, every request is handed to
`RevitDispatcher` — an `IExternalEventHandler` that runs the work on Revit's thread and returns the
result. `Reads` builds the snapshot in the SAME schema as `backend/snapshot.py` (metres; Revit
**UniqueId** = the agent's "guid"); `Actions` maps each action name to the Revit API in a
`Transaction`. The route contract is mirrored in
`bench_runner/backend/revit/client.py`.

## Prerequisites

- **Revit 2027** (the `.csproj` references its API DLLs at `C:\Program Files\Autodesk\Revit 2027\`).
- **.NET 10 SDK** (`winget install Microsoft.DotNet.SDK.10`) — or Visual Studio 2022 (17.12+) with the
  .NET desktop workload. **Revit 2027 runs on .NET 10**, so the add-in targets `net10.0-windows`
  (2025/2026 were .NET 8 — use `net8.0-windows` for those). Verified: builds clean against the
  Revit 2027 API.

## Build & install

```powershell
cd bench_runner\backend\revit\addon\BimAgent
dotnet build -c Debug
```

The post-build target copies the build output (`BimAgent.dll`) plus `BimAgent.addin` into
`%APPDATA%\Autodesk\Revit\Addins\2027\` (per-user, **no admin**). There are no NuGet dependencies.
Then **start Revit 2027**, open a project, and activate a **plan view** (rooms + level detection
use the active plan view). The HTTP server starts automatically with Revit.

**Rebuilding while Revit is running FAILS at the deploy step** — Revit holds `BimAgent.dll`
loaded, so the post-build copy hits a locked file. Close Revit, build, restart Revit.

Verify:
```powershell
curl http://localhost:48884/health      # -> {"ok":true,"doc":"<project>"}
```
Then run the agent with `--target revit`.

## Project layout

| File | Role |
|---|---|
| `BimAgent.csproj` / `BimAgent.addin` | project (net10.0-windows, Revit refs, auto-deploy) + add-in manifest |
| `App.cs` | `IExternalApplication`: starts the dispatcher + HTTP server |
| `Server/RevitDispatcher.cs` | `ExternalEvent` job queue — marshals work onto the Revit API thread |
| `Server/HttpServer.cs` | `HttpListener` server + route table |
| `Server/Params.cs` | typed reader over an action's `params` JSON |
| `Revit/Units.cs` | metre/mm ↔ Revit feet |
| `Revit/Lookups.cs` | element lookups (UniqueId = "guid"), levels, types, materials, symbols |
| `Revit/Reads.cs` | `snapshot` (schema-matched) + materials/composites/favorites/elements |
| `Revit/Actions.cs` | every toolbox action → Revit API, in a `Transaction` |

## v1 status / tuning points

**Compiles clean against the Revit 2027 API**, but **not yet run/tested live in Revit** — expect to
iterate. The Revit semantics that differ from Archicad are handled here but most likely to need tuning:

- **Units**: agent sends metres → Revit feet (`UnitUtils`).
- **Fail-loud contract**: a named type/favorite that doesn't resolve is an ERROR, never an
  arbitrary-type fallback (`composite_name` on walls AND slabs reuses the existing type by
  name — exact then substring match, case-insensitive, mirroring the Archicad backend);
  `create_composite` OVERWRITES a same-named type (Archicad `overwriteExisting` parity — no
  more " (2)" suffixes the name-graded verifier can't converge on). Failed GET reads return
  **HTTP 500** (a truthy `{ok:false}` body at 200 would be consumed as data); every
  transaction runs a warnings-deleting `IFailuresPreprocessor` (a modal warning dialog would
  freeze the API thread and time out every request); an HTTP-timeout job is CANCELLED so it
  can't still execute later behind the agent's back.
- **Walls**: created with Location Line = **Finish Face: Exterior** re-pinned to the given
  curve — the planner's coordinates are the OUTSIDE face (Archicad parity); the old default
  centerline placement shifted every wall by width/2, invisibly to the verifier.
- **Type vs instance**: wall thickness and door/window width/height are *type*-driven in Revit;
  openings set them on the instance best-effort — a size that could NOT be set is reported in
  the result's `note` (you may need pre-made sized types).
- **Rooms** (`create_zone`): Room Separation Lines along the polygon + a seed point; needs a plan
  view active. The snapshot flags NO active storey when the active view isn't a plan view
  (no silent storey-0 fallback) — activate the right plan view before a run.
- **Stairs** (`create_stair`): runs via `StairsEditScope` (multi-point baseline = L/U with auto
  landings); needs a level ABOVE the base (fails loudly otherwise — Revit stairs span level to
  level).
- **Boundary edits** (`modify_zone`/`modify_slab` polygon): delete + recreate keeping the
  name/number/type/level (the Archicad backend's contract; NEW guid, `replaced` = old). A
  replaced room's ORIGINAL separation lines are not tracked and stay in place.
- **Opening type swap** (`replace_door`/`replace_window`): IN-PLACE `ChangeTypeId` (guid KEPT —
  unlike Archicad's delete+recreate); the favorite resolves STRICTLY (loaded match or library
  load; no arbitrary fallback). `modify_wall building_material`
  duplicates the wall's current type into a single-layer structure carrying that material.
- **Slab/room outline in the snapshot**: floors use a bounding-box stand-in (real sketch profile is
  a follow-up); rooms use the real boundary loop.
- **Orientation & swing in the snapshot** (added 2026-07-29, compiles clean, **not yet read back
  from a live model**): every wall carries `orient = {ref, left_mm, right_mm, exterior}` —
  `ref` is the Location Line setting, `left_mm`/`right_mm` are how far the wall BODY reaches each
  side of the location curve (left = left of begin→end, the ArchiCAD `orient` shape and units),
  and `exterior` is `Wall.Orientation` as a plan unit vector, i.e. the normal pointing out of the
  EXTERIOR face. `exterior` is emitted **only for compound types** — a single-layer wall has no
  finish side, and a null there tells the reader to leave facing UNCHECKED instead of guessing.
  Doors/windows carry `facing` (`FacingOrientation`) and `hand` (`HandOrientation`) as plan unit
  vectors alongside the older `facing_flipped`/`hand_flipped` booleans: the vectors are absolute
  (Revit recomputes them after every flip) whereas the booleans only mean something relative to
  the family's default insertion. The grader consumes the vectors —
  **`facing` → swing direction works; the HINGE side still needs a one-time calibration** of
  `bench_runner/verifier/geometry.py:REVIT_HAND_TO_HINGE` (which jamb the leaf pivots on relative
  to the hand axis depends on how the family was authored), and stays unchecked until then.
- **Clash**: the verifier runs **2D-only** snapshot checks for Revit (no native 3D body test in v1).

## Notes

- `HttpListener` on `localhost` needs no URL ACL / admin. To change the port, edit `App.cs` **and**
  set `REVIT_ROUTES_URL` for the agent.
- JSON uses `System.Text.Json` from the runtime (no NuGet). If Revit's loaded version
  conflicts, switch to the Newtonsoft.Json that ships with Revit.