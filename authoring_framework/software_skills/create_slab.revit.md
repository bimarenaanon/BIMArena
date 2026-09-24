---
name: create_slab
description: Create a Revit floor from an existing Floor Type — one closed boundary sketched on the target Level with the required offset; no new type is authored.
software: Revit
---

# Create a slab (capability)

Create **one Revit architectural Floor instance** using an **existing Floor Type**.

If the required Floor Type does not yet exist, create it first —
(create_slab_type.revit.md).

Open the target storey's floor plan first ((set_active_story.revit.md)).

The Floor Type defines the slab construction and thickness.
The Floor instance defines its horizontal footprint and vertical placement.

> ⚠️ Revit Floor creation uses a **modal sketch mode**.
> Once sketch mode is entered, complete or cancel the sketch before attempting unrelated actions.

## Recipe

1. Start the architectural Floor command:

   `activate-ribbon-tool(Architecture, Floor)` → **Floor: Architectural**

   Revit enters:

   **Modify | Create Floor Boundary**

   Do not draw yet.

2. Select the required existing Floor Type:

   `pick-from-type-selector(<exact existing Floor Type>)`

   Use only a Floor Type that already exists in the project.

3. Set the Floor instance's vertical placement before drawing.

   In **Properties**, verify or set:

   * `Level = <target level>`
   * `Height Offset From Level = <required offset>`

   Only change the offset when the task specifies one; otherwise preserve the intended/default
   value.

   `Height Offset From Level` is an **instance property controlling vertical placement**.
   It is not a temporary dimension attached to a sketch line.

   After editing Properties:

   `focus-canvas`

   Before continuing, verify that:

   * the correct Floor Type is selected,
   * the correct Level is shown,
   * the required Height Offset From Level is shown.

4. Create **exactly one closed outer boundary loop**.

   Choose the drawing method appropriate to the task.

   ### A. Pick Walls — preferred when the slab follows existing walls

   Select **Pick Walls** explicitly.

   Click the required perimeter walls one by one so that the generated boundary segments form
   one continuous closed loop.

   Pick the **walls themselves**, not:

   * doors,
   * windows,
   * reference planes,
   * existing floor edges,
   * unrelated model lines.

   Use **Extend into wall (to core)** only when the required floor boundary is explicitly
   defined relative to the wall core.

   Otherwise, preserve the appropriate wall-face relationship required by the task.

   After picking all perimeter walls, one glance that the loop is closed — then finish.

   ### B. Line / Rectangle — when dimensions define the footprint directly

   Select the required sketch tool explicitly.

   Anchor the first point to a reliable model reference such as a real wall face, wall
   intersection, grid-related reference, or specified coordinate.

   Create the required geometry using:

   * `draw-segment-by-length`
   * snaps
   * temporary dimensions
   * `correct-by-temp-dimension` when correction is required.

   For a line-based profile, the final endpoint must **snap exactly onto the first endpoint**.

   Visually close is not sufficient.

   Use `zoom-gently` when necessary to verify endpoint closure.

5. Inspect the complete sketch before finishing.

   The intended slab profile must contain:

   * exactly **one outer closed loop**,

   * connected endpoints,

   * no gaps,

   * no overlapping duplicate segments,

   * no self-intersections,

   * no stray sketch lines,

   * no unintended inner closed loops.

   > ⚠️ An additional closed loop inside the outer boundary is interpreted as an **opening**
   > in the Floor.

   If the task is only to create a slab, there must be **no inner loop**.

6. Commit the Floor sketch:

   `finish-sketch`

   Use the **green ✓ Finish Edit Mode** control.

   Do not treat Enter as a substitute for explicitly finishing the sketch.

   If Revit refuses to finish, assume the boundary is invalid and inspect for:

   * an open endpoint,
   * crossing lines,
   * overlapping segments,
   * duplicate lines,
   * an unintended extra loop.

   Correct the sketch before trying again.

   Use `cancel-sketch` only when abandoning an invalid or unintended sketch.

   > ⚠️ The red ✗ cancels the operation and discards the current sketch.

7. Handle any post-creation wall-attachment prompt.

   Revit may display a prompt asking whether walls extending to this level should attach to the
   bottom of the new floor.

   If the prompt appears:

   * choose **No** by default,
   * choose **Yes** only when the task explicitly requires wall attachment.

   If no prompt appears, continue normally; do not search for or manufacture one.

A stairwell, service opening, or other hole is a **separate capability** —
(create_slab_opening.revit.md).

## Verification

Sketch mode is exited and the floor exists with the Floor Type, Level/offset
and boundary the instruction states — and nothing else.
