---
name: move_with_constrain
description: Move a wall in Revit while preserving intended relationships. Check what follows automatically, then repair any dependent geometry that does not.
software: Revit
---

# Move with constraints (capability)

Move an existing wall while keeping the surrounding model consistent.

Revit is parametric: moving one wall may automatically update joined walls, hosted doors/windows,
room boundaries, and other constrained geometry.

Do not assume every nearby element follows automatically.
After the move, inspect all geometry affected by that wall.

## What usually follows automatically

### Hosted doors and windows

Doors and windows hosted by the moved wall normally move with it.

After the wall move, verify that each hosted opening:

* is still hosted by the correct wall;
* keeps the required position along the wall;
* remains on the required side/location.

### Joined walls

Walls joined to the moved wall may stretch or shorten automatically to maintain their corner
connection.

For example, moving one exterior wall outward may lengthen the perpendicular walls connected
to its ends.

> ⚠️ Keep **Disjoin** OFF when the intention is to preserve existing wall joins.

After moving, verify every affected corner. Do not assume the automatic join produced the
required final geometry.

### Rooms

Room boundaries normally update when room-bounding walls move.

Afterward, verify that:

* the room still exists;
* its boundary follows the new wall position;
* no unexpected gap has caused the room to become unbounded.

### Constrained or associated geometry

Geometry explicitly constrained or associated with the wall may follow it automatically.

Always verify the result rather than relying only on the existence of a constraint.

## What may NOT follow automatically

### Floor boundaries

A floor edge may or may not follow the moved wall depending on how the floor boundary was
created and constrained.

After moving a wall, always inspect every floor edge adjacent to that wall.

If the floor boundary remains at the old location:

1. select the floor;
2. choose **Edit Boundary**;
3. move or redraw the affected boundary line to the required new position;
4. verify that the complete boundary is still valid;
5. finish the boundary edit.

> ⚠️ A stale floor edge can leave an unwanted strip, gap, or overlap after the wall has moved.

### Freestanding components

Furniture, generic models, equipment, and other non-hosted components usually stay where they
were unless they have an explicit constraint or relationship.

Move these separately when the drawing requires them to maintain their relationship to the
wall.

### Independent annotation or model geometry

Independent lines, reference geometry, and other unconstrained elements may remain at their
original locations.

Inspect and correct them only when they are part of the required model geometry.

## Recipe

1. Select the wall that must move.

2. Start **Move** (shortcut `MV` or click the icon under Modify).

3. Keep:

   * **Constrain = ON** when the move must stay horizontal or vertical;
   * **Disjoin = OFF** when existing wall joins should remain connected.

4. Define the move:

   1. click a reliable base point;
   2. move the cursor in the required direction;
   3. type the required distance;
   4. press **Enter**.

   Use the typed value for precision rather than estimating the final location with the mouse.

5. Verify the moved wall itself:

   * correct new position;
   * correct move direction;
   * correct distance;
   * correct Wall Type;
   * correct vertical constraints.

6. Inspect everything directly affected by the moved wall:

   * hosted doors;
   * hosted windows;
   * walls joined at both ends;
   * room boundaries;
   * floor edges;
   * nearby components that are expected to maintain their relative position.

7. Correct anything that did not follow as intended.

   For example:

   * repair a floor boundary with **Edit Boundary**;
   * move a freestanding component separately;
   * correct a wall join or endpoint;
   * reposition an opening if its required offset is no longer correct.

## Verification

The wall moved exactly the typed distance and what must follow did follow
(hosted openings, joined walls, floor edges) — check only the elements the move involved.
