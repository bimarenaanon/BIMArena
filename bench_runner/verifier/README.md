# bench_runner/verifier — automated grading (checkpoint model)

Grades a run against each case's structured `expected_result`
(in `bench_cases/<subset>/<tool>/<id>/task.json` — one flat single-tool file). The consumer is
`bench_runner/rerun_cases.py`, which grades LIVE right after each case
(and re-grades with `--regrade` after a ground-truth fix).

**Checkpoint model**: every check is one binary point (pass/fail).
A case **PASSES only when every checkpoint passes**; the score
(= passed / total checkpoints) is reported alongside for gradation. Checkpoints
whose data the snapshot can't provide (door swing, …) score `null` =
"unchecked" — excluded from both the pass decision and the score.

**Goal vs preservation (PCS / CFR)**: every checkpoint carries a `klass` — **C** (goal: what
the task asks to add or change) or **P** (preservation: what must survive untouched). `pcs` =
goal checkpoints passed / total; `cfr` = 1.0 only when every preservation checkpoint holds; a
case succeeds only when both are fully satisfied. Goal checkpoints the START state already
satisfies are restated preservation duties — `trivial_probe.py` finds them and
`grade(trivial=…)` grades them under P.

**Reward** (partial credit): one UNIT per asked-for thing — an element (wall
segment / door / window / slab / zone / stair / storey) or a composite LAYER.
A unit succeeds when all of its checkpoints pass; reward = units passed /
units total ("create 5 walls, 3 correct" -> 0.6). Global constraints
(exact_counts, no_extra, preserve) stay out of the reward — they only gate
PASS. Per-unit results are in the report's `units` list.

Tolerances are deliberately buffered ("roughly right" passes); cases whose
instruction pins exact numbers tighten them per-case.

## Run

```bash
# run + grade cases live (the normal path — see bench_runner/README.md)
python bench_runner/rerun_cases.py --only <case ...> --note "..."

# re-grade an existing result_<phase>.pln after a ground-truth / task.json fix
python bench_runner/rerun_cases.py --only <case ...> --regrade

# baselines only (env pre-state)
python bench_runner/verifier/baselines.py live
```

Outputs: `<results>/<case>/<tool>/score_<phase>.json` (per-checkpoint report);
`gen_eval_results.py` renders them into `<results>/EVAL_RESULTS.md`.

## How grading works

- The env **baseline** (`<case dir>/env/start/baseline.json`) is the
  pre-state: elements CREATED by the agent = final snapshot minus baseline
  guids. `preserve` checks pre-existing elements survived untouched.
- All `expected_result` geometry is in **mm**, same origin/axes as the case
  instruction. Snapshots (metres) are converted once in `grade.py`.
- **Alignment**: when the task itself creates the walls (expected walls with
  coordinates, nothing pre-existing to anchor the origin), all CREATED
  geometry is translated as one rigid set so its wall bounding box matches the
  expected one — a GUI run drawn elsewhere on the canvas is graded on its
  RELATIVE layout, not the arbitrary global origin. The shift is reported as
  `alignment_shift_mm`.
- Composites aren't in the snapshot: live mode diffs `list_composites` against
  the baseline's composite list; when either list is unknown the composite
  checkpoints score `null` (unchecked).
- All name matching (`*_contains`) is case-insensitive substring: the built
  name just has to CONTAIN one of the words.

## expected_result schema (all optional, mm)

```jsonc
{
  // buffered defaults; override per-case for precisely-specified tasks
  "tolerance_mm": 150,              // levels, regions
  "wall_tolerance_mm": 300,         // wall segment matching
  "opening_pos_tolerance_mm": 500,  // door/window centre matching
  "size_tolerance_mm": 30,          // opening width/height
  "iou_min": 0.8,                   // slab outline match

  "stories": [{"name": "1 Floor", "elevation_mm": 0}],
  "stories_exact": true,            // count must match too (default true)
  "active_story": "3 Floor",        // which storey must be left active

  "composites": [{                  // NEW composites this run must create
    "skins": [                      // build-up order (reverse also accepted)
      {"material_contains": ["tile", "ceramic"],  // name has any of these
       "thickness_mm": 10}],                      // or [10, 12, 15] = any-of
    "layers_exact": true,           // false: extra built layers (air gap) OK
    "name_contains": ["cavity"]     // optional name keywords
  }],
  "no_extra_composites": true,      // exactly len(composites) new ones

  "walls": [
    {"beg": [0,0], "end": [5800,0], "composite": "100 Block Insulated Cavity"},
      // collinear split pieces accepted; composite: name | [keywords] | "$new"
    {"existing": true, "beg": ..., "end": ..., "composite": "..."},
      // a PRE-EXISTING wall must now carry this composite (convert task)
    {"match": "any", "beg": ..., "end": ...},
      // final layout regardless of guid (an ADJUST-walls task moves existing walls)
    {"beg": ..., "end": ..., "floor": 1},
      // multi-storey build: match only walls on that storey
    {"length_mm": 6000, "height_mm": 3000, "composite": "$new"}
      // position-free spec
  ],
  "no_extra_walls": true,           // every created wall consumed by a segment

  "doors": [ /* same shape for "windows" */
    {"center": [7350,7300], "width_mm": 900, "height_mm": 2100,
     "type_contains": ["sliding"], "sill_mm": 900, "swing": "in",
     "gt_type": "Door 18"},         // informational only (from gt.pln), not checked
    {"host_side": "top", "centered_on_host": true},   // relative spot
    {"near": [9559,5142], "type_contains": ["sliding"]}
      // replace case: matched over ALL final elements near the old position
  ],

  "slabs": [{"floor": "active",     // or a storey index
             "outline": "footprint",// polygon the final walls enclose, or [[x,y],...]
             "composite": "...",    // name | [keywords] | "$new"
             "level_mm": 0,
             "exclude_region": [x0,y0,x1,y1],  // stairwell keep-clear: satisfied by
                                               // a boundary notch OR a hole cut into
                                               // the slab (snapshot carries slab holes)
             "existing": true}],    // grade a pre-existing slab (convert case)

  "rooms": [{"name": "Kitchen", "name_contains": ["kitchen"], "inside": [x,y]}],
  "stairs": [{"floor": 2, "region": [x0,y0,x1,y1], "axis": "x", "height_mm": 3000}],

  "exact_counts": {"doors": 4, "windows": 0},   // on the FINAL model
  "preserve": ["walls",                          // pre-existing untouched (by guid)
               {"bucket": "doors", "except_near": [[x,y]]}],  // exempt replaced ones

  // READ cases: graded on the agent's FINAL TEXT, not the model. The loop ends
  // on a reply with no tool calls and stores that text as memory.json's
  // `answer`; the runner passes it to grade(answer=...). All three shapes below
  // parse "<label>: <value>" lines, which the INSTRUCTION must pin.
  "answer_values": {"walls": 6,                     // a labelled NUMBER per line
                    "area": {"value": 16.0, "tol": 1.0, "unit": "m2"}},
  "answer_items": [{"label": "material", "min": 5,  // a labelled LIST, one/line
                    "must_match": [["brick"], ["concrete"]],  // ANY item matches
                    "contains": ["garage"],         // EVERY item must match
                    "exact": false,                 // ...by equality, not substring
                    "distinct": true}],             // repeats collapse (default)
  "answer_pairs": {"relation": "conflicts with",    // an unordered SET of pairs
                   "pairs": [["wall","door"]]}
}
```

- **`answer_values`** — one checkpoint per label. The label matches on
  singularised words (`Exterior wall type` = `exterior_wall_types`), the value is
  the first number on that line (thousands separators and a trailing unit are
  fine), compared within `tol` (0 = exact).
- **`answer_items`** — one `.count` checkpoint per label (`min` items, deduped
  unless `distinct: false`) plus two keyword shapes, both matching on
  containment: one checkpoint per `must_match` group, satisfied by ANY item
  containing ANY of its keywords (the key pins what must be there, not
  everything there is — for a library the case cannot enumerate); and one
  `.contains` checkpoint over EVERY item, each of which must contain one of its
  keywords (the label names a CATEGORY the whole answer has to stay inside, so
  padding with off-category names cannot score) — with `"exact": true` that list
  is matched by EQUALITY instead (case and whitespace ignored), for a read whose
  ground truth is enumerable and whose instruction asks for EXACT names. An
  empty list fails `.contains` rather than passing vacuously.
- **`answer_pairs`** — one checkpoint per expected pair PLUS `answer.no_extra`,
  so an answer that simply lists every type combination scores 1/(n+1) instead of
  full marks. Order inside a pair, plurals and verb agreement do not matter.

No final text collected (an older results tree) = unchecked; a run that ENDED
WITHOUT ANSWERING = failed, since for a read case the text is the deliverable.
Answer checkpoints are constraints — they stay out of the reward. The instruction
must pin the line format for any of this to be gradeable — see
`bench_cases/atomic_tasks/README.md`.

## Files

- `geometry.py` — segment/coverage matching, polygon IoU, wall-loop footprint
  (shapely), rect-room side classification
- `checkers.py` — per-bucket checkers -> checkpoints
- `grade.py` — mm normalization, created/existing split, alignment shift,
  all-pass scoring
- `sources.py` — the live snapshot sources (result project reopened in Archicad / Revit)
- `baselines.py` — write per-case env baselines (live)
- `trivial_probe.py` — the goal checkpoints the start state already satisfies (graded under P)
- `gt_extract.py` — gt model -> expected_result draft (used by the Revit GT capture)
- `revit_capture_gui.py` / `revit_gt.py` — Revit GT capture (live add-in + GUI driver)
- `../rerun_cases.py` — the CLI that drives grading
