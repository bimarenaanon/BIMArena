---
name: move_element
description: Reposition one existing Revit element precisely. Walls can be offset, moved, or have an endpoint adjusted; doors and windows move along their host wall or can be re-hosted to another wall — also changing an existing slab/floor's OUTLINE or LEVEL.
software: Revit
---

# Move an element (capability)

Relocate **one existing Revit element**.

Use numerical dimensions whenever possible instead of relying on visual dragging.

## WALL

Select the wall first.

Choose the method based on what needs to change.

### A — Exact parallel offset

Use this when the wall should stay parallel but move to a new exact position.

1. Select the wall.
2. Wait for the temporary dimensions to appear.
3. Find the dimension between the wall and the reference geometry the drawing measures from.
4. Double-click the dimension value.
5. Type the required distance in mm.
6. Press **Enter**.

Use the dimension from the correct side/reference.

> ⚠️ Check what the dimension is measuring before editing it. A temporary dimension may reference a wall centerline or face different from the one required by the drawing.

### B — Move the whole wall by a typed distance

Use this when the entire wall must shift by a known displacement.

1. Select the wall.
2. Activate **Move** (shortcut `MV` or click the icon under Modify).
3. Keep **Constrain** ON when the move must remain exactly horizontal or vertical.
4. Keep **Disjoin** OFF unless the task explicitly requires breaking existing wall joins.
5. Click a reliable base point.
6. Move the cursor slightly in the required direction.
7. Type the required move distance.
8. Press **Enter**.

One glance that the wall landed where required — then move on.

### C — Change one wall endpoint

Use this to lengthen, shorten, or reconnect a wall without translating the whole wall.

1. Select the wall.
2. Locate the **blue endpoint grip** at the end that must change.
3. Drag the endpoint toward the required new position.
4. Snap the grip exactly to the required wall, intersection, or other model reference.
5. Release to commit the new endpoint.

Do not drag the wall body when only one endpoint should move.

> ⚠️ Changing an endpoint can also affect joined walls at that corner. Inspect the surrounding wall joins afterward.

▸ **CHECK.** The wall sits at the required position and its joined corners still connect —
and nothing else.

## DOOR

A door is hosted by a wall.

It can:

* slide along its current host wall;
* move to another host wall using **Pick New Host**.

### Move along the same wall

1. Select the door in plan view.
2. Wait for the temporary dimensions to appear.
3. Find the dimension on the side/reference used by the drawing.
4. Double-click the dimension value.
5. Type the required distance in mm.
6. Press **Enter**.

This is the preferred method for exact positioning.

For rough repositioning, drag the door along the wall first, then correct the exact position using the temporary dimension.

> ⚠️ Revit commonly dimensions doors from the **door centerline**. If the drawing measures from a door edge, make sure the dimension references that edge before typing the value.

### Move to a different wall

Dragging cannot move a hosted door freely from one wall to another.

Instead:

1. Select the door.
2. In **Modify | Doors**, choose **Pick New Host**.
3. Move the cursor onto the required new wall.
4. Click when the door preview is hosted on the correct wall.
5. Correct the exact along-wall position afterward using temporary dimensions.

After re-hosting, verify the door's hinge side and swing direction.

▸ **CHECK.** Correct host wall and exact offset from the required reference — and nothing
else.

## WINDOW

A window uses the same host-wall movement logic as a door.

### Move along the same wall

1. Select the window.
2. Wait for the temporary dimensions.
3. Find the dimension corresponding to the required reference.
4. Double-click the value.
5. Type the required distance in mm.
6. Press **Enter**.

For rough movement, drag the window along its host wall first and then correct the exact position numerically.

> ⚠️ Revit commonly dimensions windows from the **window centerline**. If the drawing measures from an edge, make sure the correct edge reference is being dimensioned before entering the value.

### Move to a different wall

1. Select the window.
2. In **Modify | Windows**, choose **Pick New Host**.
3. Hover over the required wall.
4. Click when the window preview is correctly hosted.
5. Correct its exact horizontal position afterward.

### Change vertical position

Moving a window horizontally does not control its height up the wall.

To change the vertical position:

1. select the window;
2. locate **Sill Height** in Properties;
3. select the numerical value;
4. type the required height in mm;
5. press **Enter**.

▸ **CHECK.** Correct host wall, exact offset (and Sill Height when stated) — and nothing
else.

## FLOOR — boundary and vertical placement (reshape / re-level an existing one)

A Floor can be modified through its **boundary sketch** or through its instance-level vertical
properties.

### A — Modify the floor outline

1. Open a floor plan where the Floor is visible.

2. Select the **Floor itself**.

   Be careful not to select a wall, room, or other element above/below it.

   Use **Tab** when necessary to cycle through overlapping elements until the Floor highlights.

3. In:

   **Modify | Floors**

   click:

   **Edit Boundary**

   Revit enters modal floor-boundary sketch mode and displays the existing boundary lines.

4. Modify only the required part of the boundary.

   You can:

   * move an existing boundary line;
   * drag an endpoint;
   * delete a boundary line and redraw it;
   * use Line;
   * use Rectangle;
   * use Pick Walls.

5. When an exact dimension is required, first modify the boundary approximately, then edit the
   temporary dimension values until the required size and position are reached.

   One glance at the boundary when done — do not re-verify after every single edit.

6. The final outer boundary must remain:

   * closed;

   * connected;

   * non-self-intersecting.

   > ⚠️ An additional closed loop inside the outer boundary creates a hole in the Floor. Do
   > not accidentally leave an inner closed loop unless an opening is required.

7. Click the green **Finish Edit Mode ✓**.

   If Revit refuses to finish, inspect the sketch for:

   * gaps;
   * overlapping lines;
   * crossings;
   * duplicate segments;
   * invalid loops.

8. If a wall-attachment prompt appears after finishing, choose **No** unless wall attachment is
   explicitly required.

### B — Change floor vertical position

Select the Floor and edit:

`Height Offset From Level`

1. select the existing numerical value;
2. type the required offset in mm;
3. press **Enter**.

Also verify the Floor's:

`Level`

If the Level must change:

* click the small arrow on the right side of the Level field;
* select the required Level from the dropdown.

## Verification

The changed boundary/level values are as required and Edit Boundary mode is
exited — and nothing else.
