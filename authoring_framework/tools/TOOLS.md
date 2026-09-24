# Tool Catalog — `authoring_framework/tools`

Auto-generated from the tool registry (`Tool` specs) by `gen_tools_md.py`. This is the
exact action space the agent is handed as function declarations — one entry per registered
tool, with every parameter exactly as declared. The action space is the application's USER
INTERFACE: mouse / keyboard operations plus the retrieval lookups. The screen itself is NOT a
tool — the loop captures it at the start of every turn and shows the current and the previous
capture.

**Total: 17 GUI tools.**

Which lookups a run gets is the `--tools` MODE: `gui-raw` = the GUI operations alone (no
retrieval tool); `gui-docs` = plus `documentation_retrieval` (the vendors' official help);
`gui-support` = that PLUS
`operational_skill_retrieval` (the hand-written per-capability procedures). (The knowledge
lookups `search_standards`/`search_web` ride along when enabled and are not listed here.)

## How to read the entries

- **(read-only)** marks a tool that changes NOTHING in the model or UI — the lookups.
  Everything else acts on the UI.
- **Usage** is the tool's own guidance text, verbatim from the declaration the model reads.
- Parameters are split into **required** and **optional** — an optional parameter can be
  omitted entirely (its behaviour when omitted is in its description).
- Parameter **types**: `int`/`number` (a number), `string`, `bool`, `keys` = a list of key
  names.
- **Units**: `px` params are SCREEN pixels, read off the current screenshot (or points on a
  0-1000 grid under `GUI_COORD_WORDING=norm1000`). Model lengths are TYPED into the
  application as their raw millimetre number.

## GUI tools (computer-use) (17)

Every mode gets the mouse / keyboard operations. `documentation_retrieval` (the official help corpus) is served in `gui-docs` and `gui-support`; `operational_skill_retrieval` (the hand-written `software_skills/` procedures) only in `gui-support`.

### Mouse Interaction

**`mouse_move_to`** — move the cursor to an absolute screen pixel WITHOUT clicking

> **Usage:** Only for hover-positioning (before `scroll`, or to read a tracker/tooltip). To CLICK a target, call mouse_click(x, y) directly — a separate move first buys nothing.

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `x` | int | px | target's x in screen pixels, read off the current screenshot |
| `y` | int | px | target's y in screen pixels (y grows DOWNWARD) |

**`mouse_click`** — left-click — with (x, y) it moves there and clicks in ONE call; without, it clicks at the current cursor position

*Optional:*

| parameter | type | unit | description |
|---|---|---|---|
| `x` | int | px | target's x in screen pixels — give x AND y to MOVE there and click in ONE call (the preferred form); omit both to click at the current cursor position |
| `y` | int | px | target's y in screen pixels (y grows DOWNWARD) |

**`mouse_double_click`** — double-click — with (x, y) it moves there and double-clicks in ONE call; without, at the current cursor position

> **Usage:** Use where the application ends a multi-point input this way (e.g. finishing a polyline/baseline), as the application's help describes.

*Optional:*

| parameter | type | unit | description |
|---|---|---|---|
| `x` | int | px | target's x in screen pixels — give x AND y to MOVE there and click in ONE call (the preferred form); omit both to click at the current cursor position |
| `y` | int | px | target's y in screen pixels (y grows DOWNWARD) |

**`mouse_press_hold`** — press the left button and HOLD it for `seconds` before releasing — with (x, y) it moves there first in the same call

> **Usage:** For controls whose VARIANTS pop out on a press-and-hold (a toolbar/Info Box icon hiding sibling modes behind a flyout). Hold, read the NEXT screenshot to see the flyout, then mouse_click the wanted variant. A plain mouse_click does not open a flyout — it only re-fires the icon's current mode.

*Optional:*

| parameter | type | unit | description |
|---|---|---|---|
| `x` | int | px | target's x in screen pixels — give x AND y to MOVE there and click in ONE call (the preferred form); omit both to click at the current cursor position |
| `y` | int | px | target's y in screen pixels (y grows DOWNWARD) |
| `seconds` | number | — | how long to keep the button down before releasing (default 1.0; a flyout usually needs about 1 s) |

**`shift_hover`** — hold Shift and move to (x, y) WITHOUT clicking, so the element there PRE-HIGHLIGHTS

> **Usage:** How a DOOR/WINDOW is selected: hover on its marker, let the NEXT screenshot show whether the OPENING (not the host wall) is highlighted, and only THEN `commit_select`. Shift stays held across rounds. Do this as its OWN round — do not also click in the same batch.

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `x` | int | px | target's x in screen pixels, read off the current screenshot |
| `y` | int | px | target's y in screen pixels (y grows DOWNWARD) |

**`commit_select`** — click where shift_hover parked the cursor (on the highlighted element) and release Shift

> **Usage:** Only once a screenshot has confirmed the intended element is the highlighted one.

*No parameters.*

**`shift_click`** — one-shot Shift+click at (x, y) — the atomic shift_hover + commit_select

> **Usage:** For when the element's exact pixel is trusted without a highlight check.

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `x` | int | px | target's x in screen pixels, read off the current screenshot |
| `y` | int | px | target's y in screen pixels (y grows DOWNWARD) |

### Keyboard Interaction

**`type`** — type the given characters on the keyboard

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `text` | string | — | the characters to type — a length is typed as its raw mm number, never converted |

**`select_all`** — select all text in the focused field (Ctrl/Cmd+A)

> **Usage:** ONLY immediately after clicking INTO a text/number field. With the canvas focused this selects ALL ELEMENTS of the active tool, and a following type/delete would corrupt the model.

*No parameters.*

**`press_enter`** — press the Enter / Return key

*No parameters.*

**`press_esc`** — press the Escape key (also releases a held Shift)

*No parameters.*

**`press_tab`** — press the Tab key — move focus / cycle the active input field, where the application's help calls for it

*No parameters.*

**`delete_selected`** — delete the CURRENTLY SELECTED element(s) (the Delete key)

> **Usage:** You MUST select first — mouse_move_to the element on the canvas + mouse_click (or shift_click for an opening) — THEN delete_selected. With nothing selected it is a no-op.

*No parameters.*

**`hotkey`** — press a keyboard SHORTCUT (the listed keys are held together)

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `keys` | list of key names | — | modifier(s) + final key, e.g. the story-up/story-down or view-switch combos the application's help names. Use the token "mod" for the primary modifier so the same combo works on both OSes (Command on macOS, Ctrl elsewhere). Other usable keys: arrows up/down/left/right, digits, f1-f12, shift, alt, delete, space, home/end, pageup/pagedown |

### Navigation

**`scroll`** — scroll the mouse wheel at the CURRENT cursor position

> **Usage:** Over a LIST / DROPDOWN / DIALOG it scrolls to reveal off-screen rows; OVER THE WHITE CANVAS the wheel ZOOMS (dy<0 = zoom out, dy>0 = zoom in). Always mouse_move_to the target panel first — it acts where the cursor is.

*Optional:*

| parameter | type | unit | description |
|---|---|---|---|
| `dy` | int | — | vertical wheel steps; >0 scrolls UP/away, <0 DOWN/toward |
| `dx` | int | — | horizontal wheel steps (right > 0) |

### External Support

**`documentation_retrieval`** *(read-only)* — LOOK IT UP: search the application's official help for how an operation is done in this user interface

> **Usage:** The AUTHORITATIVE reference for this application's UI: exact tool/menu/dialog labels, option names, where a setting lives, and the click/commit sequence an operation takes. Look an operation up BEFORE performing it for the first time, and again whenever a gesture keeps failing — one lookup is cheaper than three wrong clicks. HOW TO QUERY: ONE operation per query (split 'draw walls and place a door' into two lookups); prefer the words the UI itself shows — read them off the current screenshot; on a miss, retry with the exact on-screen label or another word the application might use. The result's `related_articles` are REAL page titles — re-query one verbatim to open it. The matching help pages' screenshots are attached as images alongside the result: the dialog pictures usually carry the labels the text refers to.

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `query` | string | — | 2-6 words in the application's OWN vocabulary: the element or tool noun plus ONE operation verb (create / place / edit / move / stretch / delete / settings), or the EXACT label you can read on a menu, dialog or tool in the screenshot |

*Optional:*

| parameter | type | unit | description |
|---|---|---|---|
| `max_pages` | int | — | how many help articles to return (default 3) |

**`operational_skill_retrieval`** *(read-only)* — LOOK IT UP FIRST: read this application's written recipe for an operation you are unsure how to perform — the PREFERRED lookup over documentation_retrieval

> **Usage:** The recipe comes back as this call's RESULT: the exact controls, keys and click/commit sequence this application takes, plus the traps (which highlight really means the element is the target, which control opens the WRONG dialog, the reliable fallback when a pick keeps missing). Read it BEFORE inventing a gesture or repeating one that failed — the gestures are application-specific and are NOT in your prompt. When the operation is on the menu below, this recipe beats a documentation_retrieval lookup: consult it FIRST and fall back to the official help only for what no recipe covers.
TOPICS ON OFFER (ask for one of these):
  - clash_check: Find geometric clashes in an the application model visually — judge from screenshots per the defect rules; Collision Detection only for candidates the screenshots leave uncertain.
  - create_opening_type: Define a reusable the application door or window type at a given size — pick the library part, set Width/Height in the tool's Default Settings and save it as a named Favorite; nothing is placed.
  - create_room: Create an the application Zone (room) with its name and number inside an existing boundary — automatic Inner Edge detection for enclosed rooms, a manual polygon otherwise.
  - create_slab: Create an the application slab from an existing slab composite — the footprint traced as one closed polygon on the right storey, with the required reference plane and offset; no new composite is authored.
  - create_slab_opening: Cut a hole in an existing the application slab — a closed contour drawn fully inside the slab's boundary; the slab is modified in place, no new slab is created.
  - create_slab_type: Author a new layered slab composite in the application's attribute library — define its skins from existing Building Materials; no slab is drawn.
  - create_stair: Create an the application stair by drawing its baseline on the floor plan — straight, L- or U-shaped, with width, risers, direction and railing set before placement.
  - create_wall: Create straight the application walls from an existing basic or composite structure.
  - create_wall_type: Author a new layered wall composite in the application's attribute library — define its skins from existing Building Materials; no wall is drawn.
  - delete_element: Delete an existing the application element or a composite from the attribute library — verify the selection highlights the intended element first; a deleted wall takes its hosted doors/windows with it.
  - flip_element: Flip an existing the application element's orientation in place — wall layer side, door swing direction or hinge side, and window facing. Never delete and redraw an element only to correct orientation.
  - list_library: Inspect the application door and window parts placeable now (tool Settings browser, Favorites) and the wider library content — read-only, nothing loaded or changed.
  - list_materials: Read the project's Building Material inventory — exact existing material names, read-only, nothing edited.
  - list_types: Read the project's composite (layered wall/slab type) inventory and each composite's skins — read-only, nothing edited.
  - load_library_component: Select an existing the application Door or Window library part, configure its required parameters in Tool Settings, and make it the active component ready for placement.
  - move_element: Move/reposition an existing the application element — a wall (typed-distance Drag or endpoint marquee-stretch), a door/window along or between host walls, or a whole slab. Single-element placement geometry only; connected geometry following is move_with_constrain — also changing an existing slab/floor's OUTLINE or LEVEL.
  - move_with_constrain: Move connected the application building geometry with a Marquee Stretch so selected walls shift, joined walls stretch, hosted doors/windows follow, and framed slab nodes move with them.
  - observation: Read the live the application model state through the GUI — screenshot the floor plan, navigate to see everything, and read a selected element's numbers (info tag, Info Box, its Settings dialog) — including SELECTING elements on purpose and reading the current selection back.
  - place_door: Place a door on an existing the application wall — exact typed center offset along the host, swing side set at placement.
  - place_window: Place a window on an existing the application wall — exact typed center offset along the host, exterior facing set at placement.
  - replace_type: Switch an EXISTING the application element to a different type — a wall or slab to another composite/basic structure (Ctrl+T Structure panel), or a placed door/window to another library part (Settings dialog swap). In place, never re-create — AND editing an existing element's own parameters: wall height / constraints, door or window size and sill, room or zone name and number.
  - set_active_story: Switch the ACTIVE storey in the application — open another storey's floor plan for editing (Ctrl+Up/Down or Navigator), no Story Settings dialog involved — and view navigation: floor plan vs 3D window, getting back to the right storey's plan, zoom.
  - set_stories: Define the FULL storey stack in the application's Story Settings dialog — count, names, elevations / heights, read from the section first.

*Required:*

| parameter | type | unit | description |
|---|---|---|---|
| `topic` | string | — | 2-6 words naming the element kind and the operation you need the gesture for |

*Optional:*

| parameter | type | unit | description |
|---|---|---|---|
| `application` | string | — | which application's recipe you want — the one you have worked out you are working in. Gestures differ per application, so naming it gets you the right recipe instead of every application's at once |

