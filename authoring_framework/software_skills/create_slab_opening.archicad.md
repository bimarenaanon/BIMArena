---
name: create_slab_opening
description: Cut a hole in an existing Archicad slab — a closed contour drawn fully inside the slab's boundary; the slab is modified in place, no new slab is created.
software: Archicad
---

# Create a slab opening (capability)

Create a **hole inside an existing Archicad slab**.

The slab must already exist before creating the opening.

> ⚠️ The slab must be **selected before drawing the opening**. If no slab is selected, the Slab tool creates a new slab instead of cutting a hole.

> ⚠️ Use the **Slab tool**, not the Opening tool.

## Recipe

1. Select the existing slab.

   ### Method A — Slab tool + Select All

   1. Activate the **Slab** tool.
   2. Press **Ctrl+A**.
   3. Verify that the intended slab is highlighted as selected.

   Use this method only when it does not unintentionally select multiple slabs.

   ### Method B — Arrow + Tab

   Use this when the slab overlaps walls or other elements in plan.

   1. Activate the **Arrow** tool.
   2. Hover near the slab edge.
   3. Press **Tab** to cycle through overlapping elements.
   4. Continue until the **slab** pre-highlights.
   5. Click to select it.

   Before continuing, verify that the slab itself is selected.

2. With the slab still selected, activate the **Slab** tool again.

   The selected slab must remain highlighted.

3. Choose the required Geometry Method.

   Use either:

   * **Polygon** — for an irregular opening;
   * **Rectangle** — for a rectangular opening.

4. Draw the opening **completely inside the selected slab**.

   ### Polygon

   1. Click the first opening corner.
   2. Click each following corner in order.
   3. Return to the first corner.
   4. Click the first corner again to close the contour.

   Once the contour closes, the hole is created.

   Do not press **Enter**.

   ### Rectangle

   1. Click the first corner approximately.
   2. Click the diagonally opposite corner.

   The second click creates the rectangular hole.

   If exact dimensions are required, create the opening roughly first, then edit the dimension values around the contour one by one until the opening has the required width, length, and position.

5. Verify that the new contour appears as a **void inside the selected slab**.

6. Press **Esc** when finished.

> ⚠️ The entire opening contour must remain **inside the outer slab boundary**. Do not let the opening touch or cross the slab edge.

> ⚠️ The opening is an additional inner contour of the existing slab. Do not accidentally create a separate slab.

## Verification

The intended slab carries the hole at the required shape and position — and
nothing else.
