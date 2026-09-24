---
name: create_slab_opening
description: Cut an opening in an existing Revit floor — an inner closed loop in the floor's own boundary sketch by default; the Opening or Shaft tools for special cases.
software: Revit
---

# Create a slab opening (capability)

Cut a hole in an **existing** floor ((create_slab.revit.md)) — Revit never auto-voids a floor.
Three routes, each a modal sketch with its OWN finish command; choose before drawing.

**Shared sketch rhythm:** one closed loop — commit each segment (click endpoints /
`draw-segment-by-length` / `correct-by-temp-dimension`; `focus-canvas` before typing), snap
the FINAL endpoint onto the first (slightly-off = still open). A sketch that refuses to
finish has a gap/overlap/crossing or an inner loop touching the outer one — even a tiny gap
makes Finish fail; fix in sketch mode, and if stuck `cancel-sketch` FIRST (modal). Wrong
host selected → `cancel-sketch` and restart — never finish onto the wrong element.

## Route A — Edit Boundary + inner loop (the DEFAULT)
A floor's outer closed loop defines the slab; any EXTRA inner closed loop in the same sketch
is a hole. The hole belongs to the floor's own sketch — no separate element.
1. **Open the FLOOR PLAN of the floor's level** (e.g. Level 2) — do not do this in 3D.
2. `select-element` the floor — two ways: click ONCE in the middle of the floor (it
   highlights selected), or hover over a wall edge and press **Tab** until the FLOOR's
   boundary highlights, then click. The **Modify | Floors** tab appears → **Edit Boundary**.
3. The existing boundary shows as magenta sketch lines. **Do not touch the outer loop.**
4. Draw a second closed loop fully INSIDE it — **ROUGHLY first, exact size later**. The
   Draw panel holds many icons — the straight-line icon is the POLYGON mode (segment after
   segment until the loop closes); **Rectangle** is the simplest: ONE single click on the
   first corner, ONE single click on the diagonal corner.
   > ⚠️ **Single clicks only — never double-click** a start or end point. Single-clicked
   > sketch lines are what carry the blue temporary dimensions the next step edits; a
   > double-click does not place the second point of a rough loop.
   > ⚠️ **After the single click places a line, press NOTHING — no Esc, no Enter.** The
   > line and its temporary dimension are already on screen; move the cursor STRAIGHT onto
   > the dimension number and edit it (step 5). Esc would drop the pending sketch state and
   > Enter commits nothing useful here — both just cost the dimension you were about to
   > edit.
5. **Correct the size with the temporary dimensions — that is the ONLY place** (there is NO
   "Opening Width" parameter; do NOT touch the Properties palette on the left, nothing
   there sets the hole's size or position). `correct-by-temp-dimension`, one dimension at
   a time:
   1. click a sketch line of the loop — blue temporary dimensions appear around it;
   2. **move the cursor ONTO the dimension NUMBER** to change, and double-click the
      number — it becomes an editable field;
   3. type the required mm value → **Enter** — the line jumps to that size/offset.
   Repeat around the loop until the hole's width, length AND its distances to the
   surrounding walls all read the required values (an Aligned Dimension can anchor a
   distance no temp dimension offers).
6. **Finish Edit Mode** (the green ✓ of THIS mode — not "Finish Opening") — the floor
   regenerates with the void.

## Route B — the Opening tool (a SEPARATE element)
1. `activate-ribbon-tool` → **Architecture > Opening panel > Vertical**, then CLICK the
   floor on the canvas once — only then does the **Create Opening Boundary** sketch mode
   open. Same Draw icons as Route A (straight-line icon = polygon mode segment by segment
   until closed; Rectangle = two clicks): draw the wanted shape on the slab → the green ✓
   (**Finish Opening**).

## Route C — Shaft (through several storeys)
For a stairwell/elevator shaft that must cut Level 1→3, do NOT Edit Boundary floor by floor —
ONE Shaft cuts every floor/ceiling/roof it passes.
1. Start from the plan whose level should be the shaft's base (the active plan supplies the
   default **Base Constraint**).
2. **Architecture > Opening panel > Shaft** — this drops STRAIGHT into the **Create Shaft
   Opening Sketch** mode (no element to pick first). Same drawing as above: sketch ONE
   closed shaft boundary → **Finish Opening** (symbolic lines are representation, not the
   cut).

## Verification

Before finishing, verify: sketch mode is exited and the void matches the required size and position —
and nothing else.
