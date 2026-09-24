---
name: place_window
description: Place a window of an existing Window Type on a Revit wall — sill height set before placement, exact position corrected after.
software: Revit
---

# Place a window (capability)

Place **wall-hosted windows** on existing walls using the required Window Type.

Open the target floor plan before placement.

The horizontal position comes from the window's location along the host wall.
The vertical position is controlled by **Sill Height**.

## Setup — before placing windows

1. Start the Window tool:

   `activate-ribbon-tool(Architecture, Window)`

   Shortcut:

   `WN`

   Revit enters:

   **Modify | Place Window**

2. Select the required Window Type:

   `pick-from-type-selector(<window type>)`

   Before clicking the canvas, verify that the **Type Selector** shows the exact required Window Type.

3. Set the required sill height:

   `set-property(Sill Height, <mm>)`

   Set **Sill Height before placing** the window.

   The sill height is measured vertically from the window's Level to the bottom of the window opening.

4. Keep **Tag on Placement** OFF unless the task explicitly requires window tags.

## Place each window

1. `focus-canvas`

2. Move the cursor onto the required **host wall**.

   Wait until the window preview is visibly hosted by that wall.

3. Click once at approximately the required position.

   The window is created immediately.

   Do not try to obtain the exact horizontal position from the initial click.

4. After placement, keep/select the new window and wait for its temporary dimensions to appear.

5. Edit the temporary dimension corresponding to the required horizontal position:

   1. move the cursor onto the dimension value;
   2. double-click the number;
   3. type the required distance in mm;
   4. press **Enter**.

   The window is now positioned precisely along the wall.

> ⚠️ Revit usually dimensions a window from its **centerline**. If the drawing specifies the
> distance to the window center, use this dimension directly.

> ⚠️ If the drawing specifies the distance to a **window edge**, make sure the dimension is
> referencing that edge before editing it. Do not enter an edge distance into a centerline
> dimension.

6. One glance at the placed window (host, type, sill, position) — then move on.
   Do NOT re-select or re-measure a window that already looks right.

7. Repeat the same process for every required window:

   `set/check Sill Height → rough placement → edit temporary dimension`

   If several windows share the same Window Type and Sill Height, keep those settings unchanged and place them consecutively.

## Finish

After all windows are placed:

`focus-canvas`

Press **Esc** until no active Window placement preview remains.

## Verification

Each window: the required Window Type and Sill Height on the correct wall at
the required offset — and nothing else.
