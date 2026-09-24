---
name: place_door
description: Place a door of an existing Door Type on a Revit wall — exact position corrected after placement, swing and hinge adjusted to the plan.
software: Revit
---

# Place a door (capability)

Place **wall-hosted doors** on existing walls using the required Door Type.

Open the target floor plan before placement.

Doors are placed by clicking the host wall first, then correcting their exact position and swing afterward.

## Setup — before placing doors

1. Start the Door tool:

   `activate-ribbon-tool(Architecture, Door)`

   Shortcut:

   `DR`

   Revit enters:

   **Modify | Place Door**

2. Select the required Door Type:

   `pick-from-type-selector(<door type>)`

   Before clicking the canvas, verify that the **Type Selector** shows the exact required Door Type.

3. Keep **Tag on Placement** OFF unless the task explicitly requires door tags.

## Place each door

1. `focus-canvas`

2. Move the cursor onto the required **host wall**.

   Make sure the door preview is hosted by the correct wall.

3. Click once at approximately the required location.

   The door is created immediately.

   Do not try to achieve the exact position from the initial click.

4. After placement, keep/select the new door and wait for the temporary dimensions to appear.

5. Correct the door's exact horizontal position.

   First place the door roughly, then edit the temporary dimension beside it:

   1. move the cursor onto the required dimension value;
   2. double-click the number;
   3. type the required distance in mm;
   4. press **Enter**.

   Use the distance from the wall end or other reference shown in the drawing.

> ⚠️ Revit normally measures the door position from the **door centerline**. If the drawing
> gives the distance to the door centerline, edit this value directly.

> ⚠️ If the drawing gives the distance to a **door edge**, make sure the temporary dimension
> references that edge before entering the value. Do not enter an edge distance into a
> centerline dimension.

6. Check the door swing and hinge side.

   After placement, compare the door symbol with the floor plan.

   If necessary, use the visible flip controls to change:

   * **swing side** — which side of the wall the door opens toward;
   * **hinge side** — whether the hinge is on the left or right along the wall.

   Only flip the door when the current orientation does not match the drawing.

7. One glance at the placed door (host, type, position, hinge, swing) — then move on.
   Do NOT re-select or re-measure a door that already looks right.

8. Repeat for every required door:

   `rough placement → edit temporary dimension → adjust swing/hinge`

## Finish

After all doors are placed:

`focus-canvas`

Press **Esc** until no active Door placement preview remains.

## Verification

Each door: the required Door Type on the correct wall at the required offset,
swing per the plan — and nothing else.
