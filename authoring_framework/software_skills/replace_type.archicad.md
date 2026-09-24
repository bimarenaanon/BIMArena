---
name: replace_type
description: Switch an EXISTING Archicad element to a different type — a wall or slab to another composite/basic structure (Ctrl+T Structure panel), or a placed door/window to another library part (Settings dialog swap). In place, never re-create — AND editing an existing element's own parameters: wall height / constraints, door or window size and sill, room or zone name and number.
software: Archicad
---

# Replace an element's type (capability)

Reassign WHICH type/composite/library part an existing element uses, keeping the element in
place — never delete + redraw for a type change, and never confuse this with EDITING a
composite's layers (that changes every element using it —
(create_wall_type.archicad.md) / (create_slab_type.archicad.md)).

## WALL — switch to another composite / a basic structure

1. **Select the wall** (`select-element`). Many walls at once: `select-all-of-type`
   (Wall tool active → Ctrl+A) or `find-and-select(criteria)` first.
2. `open-selection-settings` — **Ctrl+T** (`hotkey ["mod","t"]`), or double-click the wall.
   ⚠️ NEVER a "Settings" button in the LOWER-RIGHT corner — that opens STORY Settings.
3. In the **Wall Structure** panel (three icons **Basic / Composite / Complex Profile**, with
   the name bar below — the same read-the-bar-first discipline as `pick-from-structure`):
   - **→ a named COMPOSITE:** pick **Composite**, then on the name bar pick the EXISTING
     composite from the pop-up. Width is FIXED by the composite — hands off the width field.
   - **→ a BASIC single-material wall:** pick **Basic**, pick the Building Material on the bar,
     type the stated thickness into the width field.
4. **OK**.

> ⚠️ Composite missing from the pop-up → its **Use With** (Options > Element Attributes >
> Composites) must allow Wall.
> ⚠️ Only the Structure row and the bar are touched — the look-alike hatched triplets BELOW the
> bar are cross-section geometry (slanted/curved) and must not be clicked (see
> `pick-from-structure`).

▸ **CHECK.** The wall shows the new build-up (mirrored facing → (flip_element.archicad.md))
— and nothing else.

## DOOR — swap the library part

In Archicad a "door type" is a LIBRARY PART, not a type string — replacing it swaps the part on
the placed door IN PLACE (position and host kept).

1. `activate-tool(Door)`
2. `select-opening(<the door>)` — Shift-hover its leaf line until the DOOR pre-highlights
   light-blue, then `commit_select` (fallback after ~2–3 misses:
   `find-and-select(Element Type = Door)`).
3. `open-selection-settings` — **Ctrl+T**. In the **Library Part Browser** (top of the dialog)
   search + pick the requested OTHER door part — ⚠️ verify the FULL NAME matches EXACTLY
   (sibling parts differ by one word).
4. **RE-CHECK Width / Height / Reveal / opening direction** — a different library part carries
   different custom parameters; the old values do not all survive the swap. Set what the
   instruction states.
5. **OK**.

> ⚠️ **After OK, if a placement/orientation PREVIEW appears (a ghost door follows the cursor),
> press Esc ONCE** — the in-place swap is already applied; do NOT click, or a new door gets
> placed.
> ⚠️ The requested part missing from the browser → try a shorter search word; still missing →
> (load_library_component.archicad.md).

▸ **CHECK.** The door at the SAME position shows the new part at the stated size — and
nothing else.

## WINDOW — swap the library part

A "window type" is a LIBRARY PART — replacing it swaps the part on the placed window IN PLACE
(position and host kept).

1. `activate-tool(Window)`
2. `select-opening(<the window>)` — Shift-hover its CENTRE (mid-glazing) or jamb, nudging
   toward the wall's OUTER side until the WINDOW pre-highlights light-blue, then
   `commit_select` (fallback after ~2–3 misses: `find-and-select(Element Type = Window)`).
3. `open-selection-settings` — **Ctrl+T**. In the **Library Part Browser** search + pick the
   requested OTHER window part — ⚠️ verify the FULL NAME matches EXACTLY.
4. **RE-CHECK Width / Height / Sill (Sill/Header) value** in Preview and Positioning — a
   different part carries different parameters; the old values do not all survive the swap.
5. **OK**.

> ⚠️ **After OK, if a placement/orientation PREVIEW appears (a ghost follows the cursor),
> press Esc ONCE** — the in-place swap is already applied; do NOT click, or a new window gets
> placed.
> ⚠️ Part missing from the browser → shorter search word; still missing →
> (load_library_component.archicad.md).

▸ **CHECK.** The window at the SAME position shows the new part at the stated size/sill —
and nothing else.

## SLAB — switch to another composite

Switches WHICH composite an existing slab uses — in place, nothing is redrawn. Outline and
level edits are (replace_type.archicad.md).

1. Select the slab (`select-element`).
2. `open-selection-settings` (**Ctrl+T** — never the lower-right "Settings" button, that is
   STORY Settings) → **Slab Structure** panel → structure kind **Composite** (of Basic /
   Composite / Complex Profile) → pick the EXISTING composite from the pop-up → **OK**.

> ⚠️ Composite missing from the list → its **Use With** (Options > Element Attributes >
> Composites) must allow Slab.
> ⚠️ A composite slab's total THICKNESS is never typed directly — it is the sum of the
> composite's layers, so a thickness change IS this composite swap (or a composite edit,
> (create_slab_type.archicad.md) overwrite-by-name).

▸ **CHECK.** Only the build-up changed; outline, holes and level untouched — and nothing
else.

# Edit an element's own parameters (type-level properties)

Size, sill, height and name edits of an EXISTING element belong to this capability: on one application a door's width is a type, on the other an instance value, so they are one capability here.

Edit an already-built element's OWN fields. Adjacent capabilities: type/composite/part swap →
(replace_type.archicad.md); reposition/stretch → (move_element.archicad.md); orientation →
(flip_element.archicad.md).

🛑 **Info Box FIRST — Settings only as fallback.** With the element selected, look at the
**Info Box** (the bar along the top of the window) BEFORE opening any dialog: if the
parameter to change is visible there (wall height, opening width/height, sill, offsets…),
edit it DIRECTLY in the Info Box — click the field, `select_all`, `type` the value, commit by
clicking another field/the canvas — and skip the Settings dialog entirely (fewer steps, no
modal to manage). Open `open-selection-settings` (Ctrl+T) ONLY when the field is not shown
in the Info Box. ⚠️ The Info Box edits the SELECTED element only while the selection is
live — with nothing selected it sets the TOOL'S DEFAULTS for the next new element, so
confirm the selection highlight before typing.

## WALL — height and other parameters (parameter edit)

1. **Select the wall** (`select-element`).
2. **Info Box first:** if the field (height, offsets…) is visible in the top Info Box, edit
   it there and skip to the CHECK. Otherwise `open-selection-settings` — **Ctrl+T**
   (`hotkey ["mod","t"]`), or double-click the wall, or
   right-click → Wall Selection Settings.
   ⚠️ NEVER a "Settings" button in the LOWER-RIGHT corner — that opens STORY Settings, not the
   wall's.
3. Change the field, then **OK**:
   - **Height:** in **Wall Geometry**. ⚠️ If the wall is **Top-Linked** the Height field is
     LOCKED — change **Top Offset**, or set **Wall Top = Not Linked** first, then type the
     height.
   - Other named fields (offsets, ID, classification…): set exactly what the instruction names;
     leave everything else at its current value.

> ⚠️ `open-selection-settings` edits the SELECTED existing element; `open-tool-settings`
> (double-click the toolbar button) only sets defaults for the NEXT new wall — the wrong one
> silently changes nothing on the existing wall.
> ⚠️ A composite wall's total WIDTH is not an editable field — it is the sum of the composite's
> layers (a width change is a composite swap — (replace_type.archicad.md)).

**Batch — the same edit on many walls:** `select-all-of-type` (Wall tool active → Ctrl+A, all
walls on the active storey) or `find-and-select(criteria)` for a subset → ONE
`open-selection-settings` → change the shared field → OK. Cross-storey selection needs the 3D
window — (set_active_story.archicad.md).

▸ **CHECK.** Read the changed value back (on screen or reopen Ctrl+T) — that value alone is
the check.

## DOOR — size and other parameters (parameter edit)

Change a PLACED door's dimensions/parameters, keeping its library part. Swapping the part is
(replace_type.archicad.md); moving it is (move_element.archicad.md); swing is
(flip_element.archicad.md).

1. `activate-tool(Door)`
2. `select-opening(<the door>)` — Shift-hover the door's straight leaf line (near the hinge
   end / the jamb) until the DOOR itself pre-highlights light-blue, then `commit_select`.
   ⚠️ Never a plain click — it grabs the host wall; editing THAT is the classic mis-edit here.
   Fallback after ~2–3 misses: `find-and-select(Element Type = Door)`.
3. **Info Box first:** Width/Height visible in the top Info Box → edit there, skip steps
   4–5. Otherwise `open-selection-settings` — **Ctrl+T** (or double-click the selected
   door). ⚠️ Never the lower-right "Settings" button (that is STORY Settings).
4. In **Preview and Positioning** set **Width / Height** (and any named parameter — reveal,
   threshold…) to the stated values. Touch only the fields the instruction names.
5. **OK**. If a placement ghost follows the cursor afterwards, press **Esc** once — the edit
   is already applied.

▸ **CHECK.** The door shows the new size at the same position — and nothing else.

## WINDOW — size and sill (parameter edit)

Change a PLACED window's dimensions/sill, keeping its library part.

1. `activate-tool(Window)`
2. `select-opening(<the window>)` — Shift-hover its CENTRE (mid-glazing) or the window-wall
   jamb, nudging toward the wall's OUTER side until the WINDOW itself pre-highlights
   light-blue, then `commit_select`.
   ⚠️ Never a plain click — it grabs the host wall. Fallback after ~2–3 misses:
   `find-and-select(Element Type = Window)`.
3. **Info Box first:** Width/Height/Sill visible in the top Info Box → edit there, skip
   steps 4–5. Otherwise `open-selection-settings` — **Ctrl+T** (or double-click the selected
   window). ⚠️ Never the lower-right "Settings" button (that is STORY Settings).
4. In **Preview and Positioning** set **Width / Height / the Sill (Sill/Header) value** — mind
   the sill's REFERENCE point (sill vs header) when the instruction states one. Touch only the
   fields the instruction names.
5. **OK**. A placement ghost afterwards → press **Esc** once; the edit is already applied.

▸ **CHECK.** The window shows the new size/sill (sill is invisible in plan — read it back
via Ctrl+T) — and nothing else.

## ZONE (room) — name/number and boundary (parameter edit)

Edit an already-placed zone. Creating one is (create_room.archicad.md).

### A. Rename / renumber
1. **Select the zone** (`select-element`) — or double-click the placed zone's stamp to open
   its settings directly.
2. `open-selection-settings` (**Ctrl+T**) → **Zone Name & Positioning** → change **Zone Name**
   / **Zone Number** → **OK**.

### B. Boundary after walls moved — zones do NOT auto-follow
`update-zones`: **Design > Update Zones** → **Update Selected Zones** (zone selected) or
**Update All Zones** — the zone refits the moved walls and its area recomputes.
> ⚠️ Only AUTO zones (built from Inner Edge / Reference Line) update this way. A
> MANUAL-polygon zone must be **deleted + re-created** — auto-detection or a re-traced polygon,
> per (create_room.archicad.md), keeping the same name + number.
> ⚠️ The enclosing walls' **Relation to Zones** must be **Zone Boundary**, or the auto-fit
> ignores them.

### C. A deliberately DIFFERENT boundary (not wall-following)
Delete the zone ((delete_element.archicad.md)) and re-create it in **Manual (polygon)** mode,
tracing the required boundary (`trace-polygon-by-snapping`) with the same name + number.

## Verification

The stamp shows the intended name/number (a boundary edit: the zone hugs the
new walls) — and nothing else.
