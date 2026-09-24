# Canonical BIM-authoring capability taxonomy

The **23 fundamental building modeling capabilities** of the paper (Table
`tab:capability_taxonomy` — names, grouping and descriptions here are aligned with it 1:1):
software-neutral names for what a BIM author does, each mapped onto the software-specific
atomic task templates (ArchiCAD + Revit).

Why the extra layer: the two vocabularies name the same operation differently
(`create_composite_wall` vs `create_type_wall`, `create_zone` vs `create_room`), split it
differently (Revit's door sizes are TYPE-level, ArchiCAD's ride the place call), or have it
on one side only (ArchiCAD cannot load a library part through its API at all). The canonical
layer is where cross-application claims live — "the agent can create walls" — while the
template layer stays what is actually executed and graded.

Granularity rule (deliberately mixed): **creation** capabilities are per element kind
(Create Wall ≠ Create Slab — different tools, different dialogs, different failure modes);
**editing** capabilities are cross-element (Move Element covers walls, doors and windows —
one gesture family, one API pattern per application); **queries** are per information kind.

Each capability has a DISPLAY NAME (the paper's) and a canonical snake_case `id` — the id is
what the code uses: the atomic cases' capability and the file base of the GUI operational
skills (served by `operational_skill_retrieval`) in `authoring_framework/software_skills/<id>.<application>.md`.

## How to read the per-capability tables

An atomic CASE is named after its capability — `<capability>N`, e.g. `create_door1`,
`replace_element_type7` — while the tables below list the TEMPLATES (the `atom` field of each
`task.json`) that the cases instantiate.

The agent drives both applications through the GUI ONLY — there is no API tool in its action
space. The **backend action** column names the HARNESS-side operation behind each atomic task
template (`bench_runner/backend/`: a `Toolbox` method on ArchiCAD/Tapir, the
same action name on the Revit add-in): it is what the atomic cases' scripted reference
solutions (`validate_env_*.py`, `build_env_revit.py`) call, and it tells you whether a template
is scriptable at all. Several templates share ONE action (a move and a parameter edit are both
`modify_wall`). `none (GUI only)` = no backend counterpart; `none (composite)` = a composite
of other actions.

## The five capability families

| family | capabilities — display name (`id`) |
|---|---|
| 1. Config. & Types | Create Stories (`set_stories`), Switch Active Story (`set_active_story`), Create Wall Type (`create_wall_type`), Create Slab Type (`create_slab_type`), Create Door/Window Type (`create_opening_type`), Load Library Element Type (`load_library_component`) |
| 2. Creation | Create Wall (`create_wall`), Create Slab (`create_slab`), Create Slab Opening (`create_slab_opening`), Create Door (`place_door`), Create Window (`place_window`), Create Stair (`create_stair`), Create Room/Zone (`create_room`) |
| 3. Editing | Move Element (`move_element`), Move with Constraints (`move_with_constrain`), Flip Element (`flip_element`), Replace Element Type (`replace_type`) |
| 4. Deletion | Delete Element (`delete_element`) |
| 5. Query & Selection | Inspect Project (`observation`), Check Clash (`clash_check`), Query Materials (`list_materials`), Query Types (`list_types`), Query Library (`list_library`) |

23 capabilities (6 + 7 + 4 + 1 + 5), all with a GUI operational skill on BOTH applications
(46 skill files). `create_opening_type` has an atomic task template on Revit only (on
ArchiCAD the opening type is a saved Favorite and its size rides Create Door / Create
Window); `load_library_component` and `move_with_constrain` exist on both but have no backend
action on one or both sides (marked below).

---

## 1. Config. & Types

### set_stories — Create Stories

**Create and configure building stories, including their names, elevations, and vertical relationships.**

Set up the project's vertical structure: storey names and elevations, the datum every
element homes onto.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `set_stories` | `set_stories` | Tapir `SetStories` replaces the WHOLE stack — a call must carry every storey |
| Revit | `set_stories` | `set_stories` | Levels; a plan view per level is created on demand |

### set_active_story — Switch Active Story

**Navigate between building stories and activate the target story for subsequent modeling operations.**

Change which storey's floor plan is the active drawing target.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `set_active_story` | `set_active_story` | not a property — the active storey is WHICH WINDOW IS OPEN (Tapir `ChangeWindow` on the Project Map item) |
| Revit | `set_active_story` | `set_active_story` | switches (or creates) the level's floor-plan view |

### create_wall_type — Create Wall Type

**Define a reusable wall type with specified construction, material, thickness, and layer properties.**

Author a named layered build-up for walls (layer materials + thicknesses), available for
new walls and type swaps. Every skin must name an EXISTING material (→ query_materials).

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_composite_wall` | `create_composite` | a "composite" attribute |
| Revit | `create_type_wall` | `create_composite` | a wall TYPE (compound structure) |

### create_slab_type — Create Slab Type

**Define a reusable slab type with specified construction, material, thickness, and layer properties.**

Same as create_wall_type, for horizontal build-ups.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_composite_slab` | `create_composite` | |
| Revit | `create_type_slab` | `create_composite` | a floor type |

### create_opening_type — Create Door/Window Type

**Define reusable door or window types with specified dimensions and properties.**

Define a door/window type at a target width/height; nothing is placed. On Revit opening W/H
are TYPE parameters, so a new size means a new (duplicated) family type. On ArchiCAD the
reusable type is a library part + settings saved as a named FAVORITE; the backend has no
action for it (the size rides `place_door` / `place_window`), so there is no ArchiCAD atomic
template — the capability is exercised there inside the main-bench cases.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | — | **none (GUI only)** | a saved Favorite; size rides `place_door` / `place_window` |
| Revit | `create_type_door` | `create_family_type` | duplicate at W/H |
| Revit | `create_type_window` | `create_family_type` | duplicate at W/H |

### load_library_component — Load Library Element Type

**Load predefined building element types from the software library into the current project for reuse.**

Make a door/window part that exists in the application's installed library (but not yet in
the project) placeable. **The hard ArchiCAD/Revit asymmetry**: Tapir cannot load a library
part (GUI-only — Library Manager), while Revit's add-in resolves a named family through
`EnsureSymbol` and loads the `.rfa` on demand (the API templates below, and even a plain
`place_door` naming an unloaded family, do it implicitly).

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `load_library_door` | **none (GUI only)** | Library Manager |
| ArchiCAD | `load_library_window` | **none (GUI only)** | Library Manager |
| Revit | `load_family_type_door` | `load_family_type` | loads the `.rfa` from the installed library |
| Revit | `load_family_type_window` | `load_family_type` | |

## 2. Creation

### create_wall — Create Wall

**Create wall elements according to specified geometry, wall types, dimensions, and placement conditions.**

Create a straight wall between two points: reference/location line convention, type or
material, height, storey.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_wall` | `create_wall` | reference line outside/center/inside; composite by name / basic material |
| Revit | `create_wall` | `create_wall` | Location Line (Finish Face: Exterior …); type by name |

### create_slab — Create Slab

**Create slab elements according to specified boundaries, slab types, elevations, and properties.**

Create a slab from a closed outline, reusing an existing compound type, at a given level.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_slab` | `create_composite_slab` | reuse an existing composite by name |
| Revit | `create_slab` | `create_composite_slab` | floor by sketch; type by name |

### create_slab_opening — Create Slab Opening

**Create openings within existing slab elements according to specified boundaries and dimensions.**

Cut a hole (stairwell etc.) in an existing slab. Neither application auto-voids a slab for
a stair — the opening is an explicit step.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_slab_opening` | `create_slab_opening` | |
| Revit | `create_slab_opening` | `create_slab_opening` | |

### place_door — Create Door

**Create door elements in host walls with the required type, position, orientation, and dimensions.**

Place a door in a host wall: position along the wall, swing direction, hinge side — and on
ArchiCAD the library part + size too (see create_opening_type).

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `place_door` | `place_door` | favorite + width/height in the same call |
| Revit | `place_door` | `place_door` | type selected beforehand (create_opening_type / load_library_component) |

### place_window — Create Window

**Create window elements in host walls with the required type, position, orientation, and dimensions.**

Place a window in a host wall: position, facing (exterior side), sill height.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `place_window` | `place_window` | favorite + size in the call |
| Revit | `place_window` | `place_window` | sill is instance-level (→ replace_type) |

### create_stair — Create Stair

**Create stair elements connecting specified building levels while satisfying requirements.**

Create a straight-run stair between levels (both APIs are limited to straight runs; U/L
stairs are composed from straight runs + landings).

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_stair` | `create_stair` | 2-point baseline only (Tapir) |
| Revit | `create_stair` | `create_stair` | StairsEditScope |

### create_room — Create Room/Zone

**Define room or zone regions within the building model and assign the specified names and numbers.**

Create the named space entity from a boundary. Application asymmetry in what bounds it:
ArchiCAD zones take an explicit polygon; Revit rooms are bounded by walls plus explicit
room separation lines where an edge has no wall (that extra line-drawing is part of this
capability, as its own Revit template).

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `create_zone` | `create_zone` | polygon boundary |
| Revit | `create_room` | `create_zone` | seed point in a bounded region |
| Revit | `create_room_separation_line` | `create_zone_separation_line` | where a room edge is not a wall |

## 3. Editing

### move_element — Move Element

**Move existing building elements from their current locations to specified target positions.**

Every placement-geometry change of a single element: translate, rotate, lengthen,
trim/extend a wall; reposition a door/window along (or between) host walls; change a slab's
OUTLINE or LEVEL (the `modify_slab` template — a geometry edit, so it is counted here). One capability
because it is one gesture family (select + drag/enter distance) and one API pattern
(endpoint / offset rewrite) in both applications.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `move_wall` | `modify_wall` | every endpoint-geometry change |
| ArchiCAD | `move_door` | `modify_door` | along/between walls (also re-host, E9) |
| ArchiCAD | `move_window` | `modify_window` | |
| Revit | `move_wall` | `modify_wall` | |
| Revit | `move_door` | `modify_door` | reposition / re-host |
| Revit | `move_window` | `modify_window` | |
| ArchiCAD | `modify_slab` | `modify_slab` | LEVEL + OUTLINE (level = delete+recreate) |
| Revit | `modify_slab` | `modify_slab` | outline in place via SketchEditScope |

### move_with_constrain — Move with Constraints

**Move existing elements while preserving specified geometric or relational constraints.**

Move wall(s) such that joined walls, hosted openings, slabs and rooms stay consistent.
**No single API call on either application** — the capability is real in both GUIs
(ArchiCAD: marquee stretch; Revit: Move with joins — openings/rooms follow natively, the
floor sketch is re-shaped separately) but decomposes to move_element chains through the API.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `move_with_constrain` | **none (composite)** | GUI: marquee stretch |
| Revit | `move_with_constrain` | **none (composite)** | joins/openings/rooms follow the move natively; slab reshape separate |

### flip_element — Flip Element

**Change the orientation or facing direction of an existing building element.**

Reverse which side an element faces: a wall's layer side, a door's swing direction, a
door's hinge jamb, a window's facing.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `flip_wall` | `flip_wall` | endpoint swap |
| ArchiCAD | `flip_door` | `modify_door` | swing in ↔ out |
| ArchiCAD | `flip_door_hinge` | `modify_door` | hinge left ↔ right |
| ArchiCAD | `flip_window` | `modify_window` | facing |
| Revit | `flip_wall` | `flip_wall` | `Wall.Flip` about the location line |
| Revit | `flip_door` | `modify_door` | facing flip |
| Revit | `flip_door_hinge` | `modify_door` | hand flip |
| Revit | `flip_window` | `modify_window` | facing flip |

### replace_type — Replace Element Type

**Replace the type of an existing element with another available type while preserving its placement.**

Swap an existing element's compound type / library part / family type for another one,
keeping the element in place — AND the in-place parameter edits that amount to the same thing
(the `modify_*` templates other than `modify_slab`): a door/window's size and sill, a wall's
height / top constraint, a room/zone's name and number. The boundary is application-dependent
anyway — a door's width/height is a TYPE parameter on Revit (a new size IS a new type) and an
instance parameter on ArchiCAD — so the taxonomy counts them as ONE capability. Mechanism asymmetry: Revit swaps IN PLACE (`ChangeTypeId`,
id kept); ArchiCAD swaps openings by delete+recreate (NEW guid) and walls/slabs in place.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `replace_wall_composite` | `modify_wall` | in place |
| ArchiCAD | `replace_door_type` | `replace_door` | delete+recreate — NEW guid |
| ArchiCAD | `replace_window_type` | `replace_window` | delete+recreate |
| ArchiCAD | `replace_slab_composite` | `modify_slab` | in place |
| Revit | `replace_wall_type` | `modify_wall` | in place |
| Revit | `replace_door_type` | `replace_door` | in place; size change = create_opening_type + this |
| Revit | `replace_window_type` | `replace_window` | in place |
| Revit | `replace_slab_type` | `modify_slab` | in place |
| ArchiCAD | `modify_wall` | `modify_wall` | height … |
| ArchiCAD | `modify_door` | `modify_door` | size / sill |
| ArchiCAD | `modify_window` | `modify_window` | size / sill |
| ArchiCAD | `modify_zone` | `modify_zone` | boundary / name / number |
| Revit | `modify_wall` | `modify_wall` | height, top constraint … |
| Revit | `modify_window` | `modify_window` | SILL (W/H are type-level) |
| Revit | `modify_room` | `modify_zone` | rename / renumber |

## 4. Deletion

### delete_element — Delete Element

**Remove specified building elements without unintentionally modifying unrelated model components.**

Remove any element from the model.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `delete_element` | `delete_element` | |
| Revit | `delete_element` | `delete_element` | |

## 5. Query & Selection

### observation — Inspect Project

**Inspect the current project settings, model element types, and element properties.**

The baseline read before acting and the verify-after read: what exists, ids, geometry,
storeys. Counted in EVERY bench case. Reading and setting the UI SELECTION (the
`select_elements` / `get_selection` templates) is part of this capability.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `observation` | `model_snapshot` | mm; guids |
| Revit | `observation` | `model_snapshot` | mm; UniqueIds |
| ArchiCAD | `select_elements` | **none (GUI only)** | set the UI selection |
| ArchiCAD | `get_selection` | **none (GUI only)** | read the selection back |
| Revit | `select_elements` | **none (GUI only)** | set |
| Revit | `get_selection` | **none (GUI only)** | read back |

### clash_check — Check Clash

**Identify unintended geometric intersections or spatial conflicts between building elements.**

Detect element pairs in geometric conflict.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `clash_check` | `clash.check` | Tapir 3D + 2D, per storey |
| Revit | `clash_check` | `clash.check` | 2D snapshot checks |

### list_materials — Query Materials

**Inspect and identify predefined materials available in the software for use in building element type composition.**

What materials exist to name in a compound type's skins.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `list_materials` | **none (GUI only)** | building materials; graded off the agent's answer |
| Revit | `list_materials` | **none (GUI only)** | |

### list_types — Query Types

**Inspect the building element types currently loaded and available within the project.**

What wall/slab compound types exist to reuse (reuse-over-author is the norm).

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `list_composites` | `list_composites` | composites |
| Revit | `list_types` | `list_composites` | wall/floor types |

### list_library — Query Library

**Inspect reusable and predefined building element types available in the software library.**

What door/window components can be placed — in the project AND in the installed library
beyond it. **The visibility asymmetry**: ArchiCAD's API sees only the project
(`list_favorites`); the library itself is invisible to Tapir, so browsing it is GUI-only
(Library Manager). Revit's one call returns loaded types PLUS every loadable library
family.

| application | atomic task template | backend action | notes |
|---|---|---|---|
| ArchiCAD | `list_favorites` | `favorites` | project favorites only |
| ArchiCAD | `list_library_door` | **none (GUI only)** | Library Manager browse |
| ArchiCAD | `list_library_window` | **none (GUI only)** | Library Manager browse |
| Revit | `list_families` | `favorites` | loaded + loadable in one read |

## Summary: 23 capabilities → atomic task templates

| family | capability | id | ArchiCAD templates | Revit templates |
|---|---|---|---|---|
| Config. & Types | Create Stories | set_stories | set_stories | set_stories |
| Config. & Types | Switch Active Story | set_active_story | set_active_story | set_active_story |
| Config. & Types | Create Wall Type | create_wall_type | create_composite_wall | create_type_wall |
| Config. & Types | Create Slab Type | create_slab_type | create_composite_slab | create_type_slab |
| Config. & Types | Create Door/Window Type | create_opening_type | — (GUI skill only) | create_type_door, create_type_window |
| Config. & Types | Load Library Element Type | load_library_component | load_library_door*, load_library_window* | load_family_type_door, load_family_type_window |
| Creation | Create Wall | create_wall | create_wall | create_wall |
| Creation | Create Slab | create_slab | create_slab | create_slab |
| Creation | Create Slab Opening | create_slab_opening | create_slab_opening | create_slab_opening |
| Creation | Create Door | place_door | place_door | place_door |
| Creation | Create Window | place_window | place_window | place_window |
| Creation | Create Stair | create_stair | create_stair | create_stair |
| Creation | Create Room/Zone | create_room | create_zone | create_room, create_room_separation_line |
| Editing | Move Element | move_element | move_wall, move_door, move_window, modify_slab | move_wall, move_door, move_window, modify_slab |
| Editing | Move with Constraints | move_with_constrain | move_with_constrain* | move_with_constrain* |
| Editing | Flip Element | flip_element | flip_wall, flip_door, flip_door_hinge, flip_window | flip_wall, flip_door, flip_door_hinge, flip_window |
| Editing | Replace Element Type | replace_type | replace_wall_composite, replace_door_type, replace_window_type, replace_slab_composite, modify_wall, modify_door, modify_window, modify_zone | replace_wall_type, replace_door_type, replace_window_type, replace_slab_type, modify_wall, modify_window, modify_room |
| Deletion | Delete Element | delete_element | delete_element | delete_element |
| Query & Selection | Inspect Project | observation | observation, select_elements*, get_selection* | observation, select_elements*, get_selection* |
| Query & Selection | Check Clash | clash_check | clash_check | clash_check |
| Query & Selection | Query Materials | list_materials | list_materials* | list_materials* |
| Query & Selection | Query Types | list_types | list_composites | list_types |
| Query & Selection | Query Library | list_library | list_favorites, list_library_door*, list_library_window* | list_families |

`*` = no backend action on that application (GUI-only). Every atomic task template of both
applications is mapped exactly once (ArchiCAD 40, Revit 40). The capability ids double as the
GUI skill file bases: `authoring_framework/software_skills/<id>.<application>.md`.
