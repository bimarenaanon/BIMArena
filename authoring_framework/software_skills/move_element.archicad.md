---
name: move_element
description: Move/reposition an existing Archicad element — a wall (typed-distance Drag or endpoint marquee-stretch), a door/window along or between host walls, or a whole slab. Single-element placement geometry only; connected geometry following is move_with_constrain — also changing an existing slab/floor's OUTLINE or LEVEL.
software: Archicad
---

# Move an element (capability)

Relocate or stretch ONE existing element's placement geometry. Pick the section by element
kind; the shared gesture is `move-element-by-distance` — **Drag** with a TYPED mm distance,
never an eyeballed drop. The moment connected geometry must follow (joined walls, the slab
edge, room layouts), this is the wrong capability — use
(move_with_constrain.archicad.md).

## WALL — move / stretch an endpoint

Pick the gesture by CONNECTIVITY — this decision is the whole trap:

### A. Move a DETACHED wall (nothing joined must follow)
`move-element-by-distance(direction, mm)` — select the wall (`select-element`) → **Drag**
(top-left toolbar command, or `hotkey ["mod","d"]`) → click a reference point ON the wall →
move strictly H/V (Shift held via `shift_hover` so it runs dead straight) → **type the mm** →
Enter. Typed distance, never an eyeballed drop.

> ⚠️ The moment the move must carry CONNECTED geometry along — a wall with the slab edge under
> it, an interior wall repositioned to change a room's area/layout — this gesture TEARS the
> joints. Use (move_with_constrain.archicad.md) instead.

### B. Stretch ONE endpoint (lengthen/shorten, or straighten a skewed wall)
`marquee-stretch(box, node, direction, distance_mm)` with a SMALL box framing ONLY that
endpoint's node: Marquee tool (Single-Story, thin) → click-click the box around the endpoint →
click the node inside → move strictly H/V (Shift held) → Tab → type the mm → Enter. The other
endpoint stays fixed, so the wall lengthens/shortens in place.
- **Straighten a skewed wall to H/V:** frame its OFF-AXIS endpoint and stretch PERPENDICULAR to
  the intended axis by the offset. Geometry too tangled to frame one node cleanly → delete the
  wall and redraw it straight (typed anchor + typed length, per (create_wall.archicad.md)).

### C. Small position correction after drawing
A partition sitting visibly off its planned line (a few hundred mm) → gesture A with the typed
single-axis delta — do NOT delete/redraw for a small offset.

▸ **CHECK.** The wall moved as stated and both ends still meet their adjoining walls (zones
do not auto-follow — update them only when the task involves rooms) — and nothing else.

## DOOR — move along its wall / re-host

### A. Move ALONG its wall (the common case)
1. `select-opening(<door centre>)` — Shift-hover the door's leaf line until the DOOR itself
   pre-highlights light-blue, then `commit_select` (never a plain click — it grabs the wall).
2. `move-element-by-distance(direction, mm)` — **Drag** (`hotkey ["mod","d"]`) → click a
   reference point on the door → move ALONG the wall axis, strictly H/V with Shift held →
   **type the mm** → Enter. The door slides along its host; the typed value gives the exact
   new offset (compute it as new centre − old centre along the wall).

### B. Move to ANOTHER wall
`drag-element(<target wall>)` — same select + Drag, dropping on the target wall.
> ⚠️ Works ONLY if the target wall's reference plane is COPLANAR with the old one (e.g. two
> collinear wall runs). Otherwise RE-CREATE: read the old door's type/size/params (Ctrl+T),
> place a same-type door on the target wall per (place_door.archicad.md), THEN delete the old
> one ((delete_element.archicad.md)).
> ⚠️ A native door cannot exist outside a wall — a truly "floating" door is likely an
> Object/Morph, not a native opening.

▸ **CHECK.** The door centre sits at the intended position (judge by the typed offset) —
and nothing else.

## WINDOW — move along its wall / re-host

Same gestures as the door section, with the window's own aim points:

### A. Move ALONG its wall
1. `select-opening(<window centre>)` — Shift-hover the window's CENTRE (mid-glazing) or its
   jamb, nudging toward the wall's OUTER side until the WINDOW pre-highlights light-blue, then
   `commit_select` (never a plain click — it grabs the wall).
2. `move-element-by-distance(direction, mm)` — **Drag** (`hotkey ["mod","d"]`) → reference
   point on the window → move ALONG the wall axis, strictly H/V with Shift held → **type the
   mm** (new centre − old centre along the wall) → Enter.

### B. Move to ANOTHER wall
`drag-element(<target wall>)` — ⚠️ only if the target wall's reference plane is COPLANAR with
the old one (collinear runs). Otherwise RE-CREATE: read the old window's type/size/sill
(Ctrl+T), place a same-type window on the target wall per (place_window.archicad.md), then
delete the old one ((delete_element.archicad.md)). A native window cannot float outside a wall.

▸ **CHECK.** The window centre sits at the intended position — and nothing else.

## SLAB — move the whole slab / offset one edge

### A. Move the WHOLE slab
1. `select-element` the slab (click its edge or fill; where a wall overlaps the click, Tab
   cycles the candidates — confirm the SLAB is the one highlighted).
2. `move-element-by-distance(direction, mm)` — **Drag** (`hotkey ["mod","d"]`) → click a
   reference point ON the slab → move strictly H/V (Shift held) → **type the mm** → Enter.
   Typed distance, never an eyeballed drop.

### B. OFFSET one edge (extend/shrink the slab in one direction)
Moves ONE boundary edge by an exact distance while the two neighbouring edges
lengthen/shorten to follow — one polygon, composite unchanged, walls untouched. The right
tool when "make the slab X mm wider/longer on this side" is the ask.
1. With the slab SELECTED, **click ON the edge to move** (its midpoint is a safe aim) — the
   **pet palette** opens at the cursor. Nothing is committed by this click.
2. **Identify the `Offset edge` command by TOOLTIP, never by icon position**: hover each
   top-row icon and read the tooltip / status bar until one names **Offset edge**, then
   click it. (Observed live: the palette OPENS on **Insert New Slab Polygon Node** — a
   stray canvas click there adds a node; the icons next to it are curve/tangent edits.
   Any large deformation preview while hovering is uncommitted.)
3. Move the cursor to the SIDE the edge must move toward — that sets the direction/sign —
   then **type the mm distance** (the tracker takes it) and press **Enter**. The edge
   shifts by exactly that amount.

- VERTICAL is not a Drag: a slab's height is a parameter — change its level per
  (replace_type.archicad.md) section C.
- Corner/node-level reshapes are (replace_type.archicad.md) section A; the moment WALLS
  must follow the slab (or the slab a wall), that is (move_with_constrain.archicad.md).

▸ **CHECK.** The slab outline/edge moved exactly the typed distance — and nothing else.

## SLAB — outline and level (reshape / re-level an existing one)

Edit an already-placed slab. Cutting a hole is (create_slab_opening.archicad.md); creating one
is (create_slab.archicad.md).

### A. Reshape the OUTLINE
- **Shift ONE straight edge by an exact distance:** the pet-palette **Offset edge** route is
  the simplest — (move_element.archicad.md) SLAB section B (select slab → click the edge →
  identify Offset edge by tooltip → type the mm).
- **Shift one edge/corner region:** `marquee-stretch(box, node, direction, distance_mm)` —
  frame JUST that slab's corner nodes to move (Single-Story marquee, box by two corner clicks),
  click a node inside, stretch strictly H/V (Shift held) → Tab → type the mm → Enter.
  ⚠️ If the WALLS on that edge must move with it, that is the composite move —
  (move_with_constrain.archicad.md) — frame their endpoints too.
- **A wholly different outline:** delete the slab and re-trace it per
  (create_slab.archicad.md) — re-cut any hole after.

### B. Switch the COMPOSITE
That is (replace_type.archicad.md).

### C. Change the LEVEL
Select → `open-selection-settings` → the slab's **Offset to Home Story** / elevation field →
type the value → OK.
> ⚠️ A composite slab's total THICKNESS is NOT editable here — it is the sum of the composite's
> layers; a thickness change is a composite swap (B) or a composite edit.

### D. Change the REFERENCE PLANE
Select the slab → the **Info Box** (the bar along the TOP of the window) has a **Reference
Plane Location** row with FOUR modes (Top / Bottom / Core Top / Core Bottom ) — click the
wanted one directly. No settings dialog, no Edit anything.
> ⚠️ Switching the reference plane can shift the slab vertically (the level value now
> references a different face) — re-check the slab's level right after, and correct it via C
> if it moved.

## Verification

The edited outline/level is as stated and existing holes survived — and
nothing else.
