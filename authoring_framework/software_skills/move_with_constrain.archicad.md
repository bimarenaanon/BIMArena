---
name: move_with_constrain
description: Move connected Archicad building geometry with a Marquee Stretch so selected walls shift, joined walls stretch, hosted doors/windows follow, and framed slab nodes move with them.
software: Archicad
---

# Move with constraints (capability)

Use **Marquee Stretch** when a design change moves an existing wall while the connected model geometry must remain consistent.

Typical cases:

* widen or narrow a room;
* shift an interior partition;
* move an exterior wall while keeping joined perpendicular walls connected;
* move a wall together with the slab edge beneath it.

> ⚠️ Do not move the wall alone when connected walls or slab nodes must follow. A simple element move translates only the selected element and can break the surrounding geometry.

## Recipe

1. Activate the **Marquee** tool.

   Use the **Single-Story Marquee** so the operation affects only the current storey.

2. Draw the marquee with **two corner clicks**.

   The marquee must contain exactly the nodes that are supposed to move.

   Include:

   * the wall or walls that must translate;
   * the near endpoints of joined walls that must stretch;
   * slab corner nodes that must move with the wall.

   Exclude:

   * endpoints that must remain fixed;

   * slab corners that must remain fixed;

   * unrelated walls or components.

   > ⚠️ The marquee controls the stretch by node inclusion. If both endpoints of a wall are inside the marquee, the whole wall moves. If only one endpoint is inside, that end stretches while the other remains fixed.

   > ⚠️ Be careful with nodes lying directly on the marquee boundary. Draw the box clearly around the nodes that should move rather than placing the dashed boundary directly through them.

3. With the Marquee still active, click a **real model node inside the marquee** to start the stretch.

   Use a wall endpoint or another clear geometry node.

   Do not click the dashed marquee border.

4. Move the cursor in the required direction.

   Keep the movement strictly horizontal or vertical when the task requires an axis-aligned shift.

5. Press **Tab** to activate numerical input.

6. Type the required movement distance in mm.

7. Press **Enter**.

   The framed geometry stretches/moves by the typed distance.

## What should follow

After the stretch:

* walls fully inside the marquee move together;
* joined walls with only one endpoint inside stretch to maintain the connection;
* hosted **Doors and Windows** move with their host walls;
* slab nodes included inside the marquee move with the stretched side.

## What may need correction afterward

### Zones

Zones do not necessarily reflect the changed room geometry immediately.

After moving room-bounding walls, verify each affected Zone and update it so its area/boundary matches the new room.

### Slab edges

Only slab nodes included in the marquee move.

If the required slab corner was not framed, the slab edge may remain at its old position.

Inspect every slab edge along the moved wall and reshape it if necessary.

### Other storeys

A **Single-Story Marquee** affects only the active storey.

Elements on other storeys remain unchanged unless the task explicitly requires separate edits there.

## Verification

The framed geometry moved exactly the typed distance and what the ledger says
must follow did follow (joined walls stretched and connected, hosted openings on their walls,
framed slab corners) — check only the elements the move involved.
