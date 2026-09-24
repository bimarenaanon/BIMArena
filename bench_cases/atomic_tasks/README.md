# atomic_tasks — one minimal case per atomic task

A demonstration tree beside the main benchmark trees: at least one case per atom of each
application's atomic-task vocabulary (ArchiCAD 40, Revit 41 — mapped onto the canonical
capabilities in `bench_cases/CAPABILITIES.md`), plus further variants where a second scenario was worth demonstrating —
**62 ArchiCAD + 61 Revit case dirs.** Each case is
deliberately SIMPLE — a self-contained instruction that exercises exactly one atomic
operation end to end, so the whole workflow (read the task → drive the tool → verify) can be
shown and smoke-tested per atom.

`delete_element` carries the most cases (8 archicad / 7 revit) because deletion varies along
axes the other atoms do not have: what is deleted (one named element, one picked out of a set,
a whole bucket, everything — and on archicad an ATTRIBUTE: `delete_element8` deletes a
composite from the library, graded by the verifier's `composites_absent` checkpoint) and what
must SURVIVE it.

## Case ids

A case id is the paper's capability name plus a running number per application —
`create_door1`, `replace_element_type7`, `inspect_project4` (the 23 capabilities of
`bench_cases/CAPABILITIES.md`, snake-cased). The software-specific template a case
instantiates is its `atom` field (`place_door`, `modify_wall`, `get_selection`, …) and its
pre-rename id is kept as `legacy_id`, which is what older result trees are keyed by.

## Layout

Since 2026-08-13 the tree carries the SAME per-case layout as `bench_cases/reasoning_tasks/archicad/` and
`bench_cases/reasoning_tasks/revit/`, so `bench_runner/case_io.py` resolves an atomic case exactly like a
graded one and no tooling needs a special path:

    atomic_tasks/
      archicad/<capability>1/task.json     the case (e.g. create_door1)
      archicad/<capability>1/env/start/    archicad.pln + baseline.json  (SEEDED, gitignored)
      archicad/<capability>2/…             the next variant of the same capability
      archicad/_env_empty/start/           stock template — the start for creation atoms
      archicad/_env_base/start/            the built model every edit/read atom points at
      archicad/_env_clash/start/           _env_base + the seeded defects clash_check finds
      archicad/_env_rich/start/            a bigger flat — subjects that must be picked out of a SET
      revit/<capability>N/…                the same, as revit.rvt + baseline.json
      seed_envs.py                         (re)fills every case's env/start from the templates
      build_env_revit.py                   authors revit/_env_base|rich|clash over the add-in
      validate_env_archicad.py             proves every case is failable AND passable
      validate_env_revit.py                the Revit twin (shares the grading half)

Differences from the main trees, all deliberate:

- **One case per atom, more where the atom has more than one shape.** The ids keep the
  trailing digit (`create_wall1`), and a further variant runs the same operation with
  different numbers and a different way of naming the subject (endpoints instead of a compass
  direction, a typed-out polygon instead of "the western enclosure"), or at a different SCALE
  (one wall against a closed loop; two openings of differing parameters against one). Every
  variant differs from its siblings in at least one graded number, so none can be passed by
  replaying another's answer. Numbering is per tree and gaps are fine — Revit's single-wall
  case is `create_wall3` because `create_wall2` was already taken there.
- **PER-CASE env dirs, seeded from ONE template per tool.** Each case has its own
  `env/start/` like a graded case, but the start project is a byte-copy of the
  tool's template, so those copies are **gitignored** (`bench_cases/atomic_tasks/*/*/env/**/*.pln|rvt`
  — 123 × ~15 MB / ~5.7 MB of identical bytes has no business in history) and are recreated by
  `python bench_cases/atomic_tasks/seed_envs.py`. Only the `<tool>/_env_*/start/` templates
  are versioned.
  `baseline.json` IS tracked, so the skeleton itself is in git. Cases are all text-only; no drawings.
- **`env_template` names the start state a case's instruction assumes** — `"empty"`,
  `"base"`, `"clash"` or `"rich"`. **ArchiCAD: all four are authored** — drawn BY HAND in
  ArchiCAD (2026-08-13) and captured with `seed_envs.py --baselines-only`, which writes each
  template's `baseline.json` from the live model. There is no script that rebuilds them: the
  tables below RECORD what the saved `.pln`s hold, and every case's expected_result is fitted
  to that record, so changing a template means re-fitting its cases (and re-capturing the
  baselines). **Revit's four templates are AUTHORED BY SCRIPT** (2026-08-14):
  `build_env_revit.py --which base|rich|clash` drives the add-in's `/action` routes, so on that
  side the script IS the specification and the tables below are generated from it rather than
  recording a hand-drawn file. All 61 Revit cases are seeded, validated in both directions and
  graded like the ArchiCAD ones.
- **An atom's instruction is ONE operation — the setup lives in the env, not in the text.**
  An atomic case exists to exhibit a WORKFLOW end to end, not to pose a problem: it should
  read like a single sentence naming what to do to which element. The earlier shape had
  every edit atom build its own subject first ("place a wall …, place a 1200x1200 window
  with a 900 mm sill …, THEN modify that window"), which put more operations in the SETUP
  than in the atom under test and made a failed setup indistinguishable from a failed atom.
  Creation atoms start from `_env_empty` because creating from nothing IS their workflow;
  every atom that edits, moves, replaces, deletes, selects or reads an existing element
  starts from `_env_base` and simply names its subject.
- **Read atoms** (`observation`, `clash_check`, `list_*`, `get_selection`) end with
  "report X in your final answer". The model-state checks in `expected_result` grade
  only the setup; the reported text is the atom's real output. That text is not a
  side-channel: the ReAct loop ENDS on a reply carrying no tool calls and stores it as
  `memory.json`'s `answer`, the runner hands it to `grade(answer=...)` and copies it into
  `score_<phase>.json`. **Every read atom is machine-graded — no human in the loop.**
  Two rules make that possible.

  **Pin the output format in the instruction.** Each read atom ends with "give your answer
  as ONE LINE PER ITEM, in the form `"<label>: <value>"`", naming the labels it wants, so
  the text parses into labelled data. Three key shapes grade it (schema in
  `bench_runner/verifier/README.md`): `answer_values` for labelled numbers (counts, a
  width, an area), `answer_items` for a labelled list (material / type / library-part
  names — `min` distinct items plus keyword keys: `must_match` when ANY item must carry a
  keyword, `contains` when EVERY item must), `answer_pairs` for an unordered SET
  (clash_check's type pairs, with `answer.no_extra` so listing every combination fails).
  Pin what the case can actually assert and say in `reason` what it cannot: the count under
  a group label is checkable, "is this really a FAVORITE rather than a library part" is not.

  **Never key on a readable element ID** — `id` falls out of the API snapshot for free
  while a UI agent has to select each element and open its settings to read one, so an
  ID-keyed answer grades the interface instead of the atom; key on what every action space
  reaches equally (types, counts, names, positions).
- **One atom, its own case pair where the element type splits the work.** Revit's
  `list_families` is demonstrated by `query_library1` and `query_library2`,
  mirroring Archicad's `list_library_door` / `list_library_window`. The tool takes an
  `element_type` of "Door" or "Window" and the two halves browse different library content,
  so one case would leave half the capability untested. The atom vocabulary, the API
  tool (`revit_list_families`) and the `software_skills` recipe all stay ONE — only the
  demonstration cases split.
- **No-API atoms** (ArchiCAD `load_library_*`, `list_library_*`; `move_with_constrain`
  on both) are still authored — they are GUI-route demonstrations; `reason` notes the
  missing API route.
- `category` is `"atomic"`; ids are `<atom><variant>`, not `<letter>_<category><n>` — and
  each spec also carries the bare atom name in its `atom` field, so a case maps back to the
  vocabulary and to its `software_skills` recipe without string-stripping the trailing
  digit. This tree is NOT part of the graded benchmark case sets and is not listed in
  `bench_cases/README.md`.

## `_env_base` — what the shared built model must contain

**HAND-AUTHORED in ArchiCAD** (2026-08-13) and captured with `seed_envs.py --baselines-only`;
the Revit twin is authored by `build_env_revit.py` (see its own table below). `seed_envs.py` hands the template to every case whose
`env_template` is `"base"`. The table below is a RECORD of what the saved `.pln` holds, not a
specification something rebuilds it from.

Derived from what every editing atom needs a subject for; one room covers nearly all of them.
Each element must be UNAMBIGUOUSLY nameable in one phrase, since that phrase is how an
instruction points at it ("the window on the north wall") — that identification is part of the
workflow, but a guess between two candidates is not.

| # | element | geometry | attribute |
|---|---|---|---|
| 1-4 | four exterior walls, closed rectangle, drawn COUNTERCLOCKWISE so layers face out | (0,0) → (11129,0) → (11129,10205) → (0,10205) → (0,0) | composite `100 Block Insulated Cavity`, 275 mm |
| 5 | ONE interior partition — the only non-exterior wall, so "the partition wall" is unambiguous | (5784,0) → (5784,10205) | BASIC 100 mm wall, reference line Center (no composite — see below) |
| 6 | ONE door, on the SOUTH wall, opening INTO the room (+y), hinge on the WEST jamb | centre (4000, 0) | 900 x 2100 mm, a hinged single-leaf type (AC: favorite `Internal Door`, library part `Door`) |
| 7 | ONE window, on the NORTH wall, glazing facing OUT (+y) | centre (4000, 10205) | 1200 x 1200 mm, sill 900 mm, an openable casement type (AC: favorite `European Tilt-Turn Window`, library part `Window`) |
| 8 | ONE slab, Ground Floor, level 0, outline = the room footprint | (0,0) → (11129,0) → (11129,10205) → (0,10205) | composite `Concrete Floor with 10mm Tile` |
| 9 | ONE zone, filling the EAST enclosure | (5834,272) → (10854,275) → (10854,9930) → (5833,9930), **48.5 m²** | name `Office`, number `01` |

Storeys: three, named `Ground Floor` (0 mm), `First Floor` (3000 mm), `Second Floor` (6000 mm),
with **Ground Floor active** on open, and NO elements above the ground floor. (An isolated
First-Floor wall used to sit here so a "reach another storey" atom had a target; it was removed
2026-08-13 and `delete_element2`, which deleted it, was re-aimed at the zone.) The stock
composite / favorite inventory of `_env_empty` carries over unchanged.

The partition is a **BASIC** wall (single building material) on purpose, since 2026-08-14: a
COMPOSITE wall's thickness is the sum of its skins and cannot be set, so while it was the
`Stud Partition` composite `replace_element_type3` ("make it 400 mm thick") could not be satisfied
without first authoring a composite — a different atom. Being basic, its thickness is an
editable field. Two keys followed the change: `move_element4` and `move_with_constraints1` assert
`width_mm: 100` where they asserted the composite NAME, and `inspect_project5` reports the
wall's height instead of its composite name (a basic wall has none). `replace_element_type8`
is unaffected — switching a basic wall to a named composite is the same edit it always was.

**Types that must be AVAILABLE without a library load.** The `replace_*` atoms name their
target type, and each must already be in the project:

| | window target | door target |
|---|---|---|
| Archicad | favorite `Sliding Window` (library part `2-Sash Sliding Window`) | favorite `Double Entrance Door` (library part `Entrance Double Door`) |
| Revit | stock `0610 x 1220mm` fixed | a double-leaf type named **`2100 x 2100mm`** |

The ArchiCAD targets are what the stock template actually carries, and both are checkable:
the snapshot reports an opening's LIBRARY PART (not the favorite), so `type_contains` grades
the swap — `sliding` / `double` cannot be hit by the seeded `Window` / `Door` parts. The
earlier plan named `Double-Hung Window`, which no favorite in the template resolves to; since
Tapir cannot load a library part, an unavailable name makes the case unpassable on the API
route rather than hard.

Revit's door target is `M_Door-Passage-Double-Flush: 2100 x 2100mm`, which the metric library
already ships — `build_env_revit.py` LOADS it into `_env_base` (an earlier plan to duplicate a
type under that name fails: "the name is already in use", the family carrying it itself). On
Revit the size IS the type, so the case cannot assert a size no loaded type carries. Neither door target may be a SLIDING one: that keyword
belongs to the load atoms.

This boundary is not a convenience. Fetching a part from the Library Manager is
`load_library_*` / `load_family_type_*`, and an atom passable by doing another atom's work
grades neither cleanly. The mirror rule holds too — a `load_*` atom must name a part the
project does NOT already carry, or it grades nothing.

Nothing else. Every extra element is one more thing an instruction has to disambiguate against.

The interior partition is load-bearing on the DESIGN, not just the model: it splits the plan
into two closed enclosures (west 0..2000, east 2000..6000). The seeded zone/room sits in the
EAST one, which leaves the west enclosure free for the atoms that CREATE a room — so even those
need no wall-building setup.

**Revit's `_env_base` is the same model in Revit's vocabulary**, authored by
`build_env_revit.py --which base` — 11000 x 10000 mm to match this tree's scale, on round
numbers because it is scripted rather than drawn:

| # | element | geometry (mm) | attribute |
|---|---|---|---|
| 1-4 | four exterior walls, drawn on their EXTERIOR FACE, counterclockwise | (0,0) → (11000,0) → (11000,10000) → (0,10000) → (0,0) | `Exterior - Brick on Mtl. Stud`, 350 mm |
| 5 | ONE interior partition, full depth | (5500,0) → (5500,10000) | `Interior - Blockwork 100` — **124 mm**, the name states its blockwork, not its thickness |
| 6 | ONE wall on **Level 2** — `delete_element2`'s target | (0,0) → (5000,0) | `Exterior - Brick on Mtl. Stud` |
| 7 | ONE door, SOUTH wall, opening into the building | centre (4000, 0) | `M_Single-Flush: 0915 x 2134mm`; hinges EAST (see below) |
| 8 | ONE window, NORTH wall, glazing out, sill 900 | centre (4000, 10000) | `M_Fixed: 0915 x 1220mm` |
| 9 | ONE floor, Level 1, level 0, the full footprint | (0,0) → (11000,0) → (11000,10000) → (0,10000) | `Insitu Concrete 225mm` |
| 10 | ONE room in the EAST enclosure | 5562..10650 x 350..9650 — **47.3 m²** | name `Office`, number `1` |
| — | SEEDED DEFECT: the SOUTH and EAST walls are FLIPPED, their brick face pointing inward | — | `flip_element3` / `flip_element4`'s subjects |
| — | LOADED, unplaced: `M_Fixed: 0610 x 1220mm`, `M_Door-Passage-Double-Flush: 2100 x 2100mm` | — | the `replace_*` atoms' targets |

Levels: `Level 1` (0 mm) and `Level 2` (4000 mm), Level 1 active on open.

Two Revit facts every Revit key rests on. A wall's reported LOCATION CURVE is not the line it
was drawn on: seated on its exterior finish face, a 350 mm envelope wall reports its centreline
175 mm inside, so the snapshot shows 175..10825 for a shell authored at 0..11000 — the grader
canonicalizes envelope walls back to their outer face, which is why the keys state 0/11000. And
the seeded door HINGES EAST although the builder asks for the west jamb: the add-in applies a
hinge side on a modify but not at placement, so the env keeps Revit's default and
`flip_element2` is written against the measured state.

`_env_clash` is `_env_base` plus SEEDED DEFECTS for `clash_check` — kept separate because the
other atoms need a clean model to edit. What defects it carries is the answer to that case and
belongs in its `expected_result`, not here. One constraint on the Revit side: `clash.check`
runs 2D SNAPSHOT-ONLY there (no Tapir 3D `GetCollisions`), so seed defects the 2D checks can
actually see — stair-vs-wall body clashes are not detected on that backend in v1.

## `_env_rich` — a set to pick a subject out of

`_env_base` holds exactly one of everything, which is what makes its subjects nameable in one
phrase — and exactly why it cannot pose "delete EVERY door" or "the door in the SOUTH wall".
`_env_rich` is the same shell with a SET to select from: three doors and three windows, one
per elevation, and no slab, no partition and no zone.

**HAND-AUTHORED in ArchiCAD** (2026-08-13, as `_env_base_noslab` before it was renamed);
the table records what the saved `.pln` holds. **Revit's `_env_rich`** is scripted
(`build_env_revit.py --which rich`) and is NOT the same set: the same 11000 x 10000 shell, but
with TWO partitions (vertical at x=5500, horizontal at y=5000 from x=5500 east), three doors
(the entrance at (2000,0) in the south exterior wall, one in each partition at (5500,2500) and
(8250,5000)), three windows (north (8000,10000), east (11000,7500), west (0,7500)), the full
floor and one room `Office` west of partition A — its five cases ask for "every door", "both
partitions" and "the door hosted in an EXTERIOR wall", which need exactly that shape.

| # | element | geometry | attribute |
|---|---|---|---|
| 1-4 | four exterior walls, closed rectangle, COUNTERCLOCKWISE — the SAME shell as `_env_base` | (0,0) → (11129,0) → (11129,10205) → (0,10205) → (0,0) | `100 Block Insulated Cavity`, 275 mm |
| 5 | door, SOUTH wall | centre (4000, 0) | 900 x 2100 mm, sill 0 |
| 6 | door, WEST wall | centre (0, 7120) | 900 x 2100 mm, sill 100 |
| 7 | door, EAST wall | centre (11129, 5115) | 900 x 2100 mm, sill 100 |
| 8 | window, NORTH wall | centre (4000, 10205) | 1200 x 1200 mm, sill 900 |
| 9 | window, WEST wall | centre (0, 2296) | 900 x 1500 mm, sill 1000 |
| 10 | window, EAST wall | centre (11129, 7950) | 900 x 1500 mm, sill 1000 |

NO slab, NO partition, NO zone — that absence is what the template is for: `create_slab1` and
`create_room_zone2` author the missing element instead of adding a second one, and no partition
means "the walls" is the four-wall envelope with nothing to argue about.

Storeys as in `_env_base` (three, Ground Floor active), and no elements above the ground floor
— "delete every window" must not have to argue about whether one on another storey counts.

Two properties are load-bearing for the cases:

- **One door per elevation, all the same size.** `delete_element6` singles its subject out by
  ELEVATION ("the one in the SOUTH wall"), which is the only thing that separates them —
  and `inspect_project2` can report ONE width/height pair for the whole selection.
- **Every wall carries the same composite**, so `inspect_project1` has a single right answer to
  read off the selection and `flip_element3` can ask for all four at once.

Element IDs are set explicitly on the openings: both applications number an opening from its
family/library part, so same-type doors arrive carrying the SAME readable id, and a set the
cases talk about element by element has to be legible in the app.

### Named stock inventory

Beyond the model itself the cases name resources by hand, and each name has to hold in the
authored env:

| | must be present, NOT already in the project | must be present, already available |
|---|---|---|
| Archicad | library parts `Pivot Door`, `Triple Window` (the `load_library_*` targets) | composites `Concrete Floor Insulated with Parquet`, `Double 50 Block Cavity Plastered`, `215 Block Insulated Cavity Plastered` |
| Revit | families `M_Door-Single-Panel`, `M_Window-Sliding` (the `load_family_type_*` targets) | types `Concrete-Domestic 425mm`, `Beam and Block 200mm`, `Exterior - Block on Mtl. Stud`, `Exterior - Render on Brick on Block` |

The right-hand column is all stock in the template projects already (`baseline.json` lists
it, and `validate_env_archicad.py` reaches every ArchiCAD name in a live reference solution).
The left-hand column is the one to CHECK against the installed library for the version in
use, and to check is NOT in the project — the mirror of the rule above: a `load_*` atom whose
part is already carried grades nothing. ArchiCAD's door favorites already include a sliding
one, which is why the load targets are `Pivot Door` / `Triple Window` and not the sliding
parts the earlier plan named.

## Keeping the envs and the specs honest

```bash
python bench_cases/atomic_tasks/seed_envs.py --tool archicad --baselines-only --force
python bench_cases/atomic_tasks/seed_envs.py --tool archicad --force
python bench_cases/atomic_tasks/validate_env_archicad.py         # both directions, live
python bench_cases/atomic_tasks/validate_env_archicad.py --start-only   # offline half
```

`validate_env_archicad.py` checks the two properties a case/env pair has to have:

- **failable** — grading the untouched start against the case's own `expected_result` must
  NOT pass. (Read atoms are exempt: their model-state half IS a "nothing was touched" check;
  their real answer key is the `answer_values`/`answer_items`/`answer_pairs` block, graded off
  the agent's final text.)
- **passable** — a scripted reference solution applied through the API must grade PASS.
  Those solutions are an answer key and live in that script, never anywhere an agent reads.

Both halves caught real defects when the ArchiCAD envs were first authored (2026-08-13): a
composite wall cannot be re-thicknessed by `modify_wall`; a floor-less wall spec matched the
collinear First-Floor wall; slab-outline IoU of 0.8 was looser than the edit under test; and
opening entries anchored with `center` are matched only against CREATED elements, so every
in-place edit atom graded as "not placed". Each is recorded in the `reason` of the case it hit.

## Running one

```bash
python -m authoring_framework -i "$(jq -r .instruction bench_cases/atomic_tasks/archicad/create_wall1/task.json)"
```

(or point `bench_runner/rerun_cases.py`-style tooling at a case dir; `case_io.py`
resolves the shared env via the spec's `env.files[].filepath`.)
