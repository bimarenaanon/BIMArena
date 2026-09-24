---
name: replace_type
description: Switch an existing Revit element to another type via the Type Selector — a wall or floor to a different Wall/Floor Type, a placed door or window to another family type. In place; the target type must already exist — AND editing an existing element's own parameters: wall height / constraints, door or window size and sill, room or zone name and number.
software: Revit
---

# Replace an element's type (capability)

Changing an element's TYPE swaps its build-up / family size in place — the element, its joins
and its hosted parts survive. The target type must EXIST (else author it first:
(create_wall_type.revit.md) / (create_slab_type.revit.md) / (create_opening_type.revit.md)).
Every section COMPOSES `pick-from-type-selector` from `the application basics`.

## WALL — switch the Wall Type

1. Select the wall (`select-element`, see `the application basics`; gather every wall getting the
   same type — the Type Selector shows only while the selection is one category).
2. `pick-from-type-selector(<new wall type>)` — the wall rebuilds as that type immediately. If
   the type is not listed, it doesn't exist in the project — create it, don't invent a name.
3. **Esc** to deselect.

▸ **CHECK.** A different total thickness moves the far face about the Location Line —
verify only that the face the drawing dimensions still sits at its mm offset (fix via
(move_element.revit.md)).

▸ **CHECK.** A Pick-Walls floor boundary can be dragged by the thickness change — re-check
the floor outline only when the task's floor touches the swapped wall
((replace_type.revit.md)).

Notes:
- This is the TYPE swap only; instance parameters (height, constraints) are
  (replace_type.revit.md).

## DOOR — swap the family type

Swapping the TYPE changes family/size in place — the door keeps its host wall, offset, and
swing.

1. Select the door (`select-element`; gather every door getting the same type).
2. `pick-from-type-selector(<new door type>)` — type a few letters to filter; the doors rebuild
   immediately.
   - Type not listed → the family isn't loaded: (load_library_component.revit.md), then repeat.
   - Size not offered by the family → duplicate a type: (create_opening_type.revit.md), then
     repeat.
3. **Esc** to deselect.

▸ **CHECK.** Leaf width grows about the door centre — re-check an edge-referenced dimension
only when the instruction uses one ((move_element.revit.md)).

▸ **CHECK.** The swing still matches the symbol ((flip_element.revit.md)) — and nothing
else.

## WINDOW — swap the family type

The door twin with the window selected:

1. Select the window(s) (`select-element`, see `the application basics`).
2. `pick-from-type-selector(<new window type>)`.
   - Not listed → load the family: (load_library_component.revit.md).
   - Size not offered → duplicate a type: (create_opening_type.revit.md).
3. **Esc** to deselect.

▸ **CHECK.** As for doors: width grows about the centre; Sill Height still as stated — and
nothing else.

## FLOOR — switch the Floor Type

Switches WHICH Floor Type an existing floor uses — in place, nothing is redrawn. Outline and
level edits are (replace_type.revit.md).

1. Select the floor (`select-element`) — Tab-cycle until the status bar reads the FLOOR, not
   a wall under it.
2. `pick-from-type-selector(<new floor type>)` — the type must EXIST
   ((create_slab_type.revit.md) authors a new one). Thickness follows the type.
3. **Esc** to deselect.

▸ **CHECK.** Only the Floor Type changed; footprint and openings untouched — and nothing
else.

# Edit an element's own parameters (type-level properties)

Size, sill, height and name edits of an EXISTING element belong to this capability: on one application a door's width is a type, on the other an instance value, so they are one capability here.

Modify the **instance-level properties** of an existing Revit element.

Use the **Properties palette** for parameter edits.

This capability does **not** cover:

* changing an element to another Type;
* moving an element horizontally;
* flipping its orientation;
* editing Type-level construction or dimensions.

> ⚠️ Before editing a value, verify that the correct element is selected and that the field is
> an **Instance Property**, not a Type Property.

## WALL — constraints, height, offsets, Location Line (parameter edit)

1. Select the required wall.

2. In the **Properties** palette, edit the required fields under **Constraints**.

   ### Base Constraint

   Defines the Level on which the wall starts.

   To change it:

   * click the small arrow on the right side of the field;
   * select the required Level from the dropdown.

   Do not type the Level name manually.

   ### Base Offset

   Controls the vertical offset from the Base Constraint.

   Click the numerical value, select the existing number, type the required value in mm, and
   press **Enter**.

   ### Top Constraint

   Defines how the top of the wall is controlled.

   It may be:

   * **Unconnected**, or
   * constrained to another Level.

   To change it:

   * click the small arrow on the right side of the field;
   * select the required option or Level.

   ### Unconnected Height

   When:

   `Top Constraint = Unconnected`

   the wall height is controlled by **Unconnected Height**.

   Select the existing numerical value, type the required height in mm, and press **Enter**.

   > ⚠️ If the wall is constrained to a Top Level, Unconnected Height is not the active height
   > control.

   ### Top Offset

   When the wall is constrained to a Top Level, **Top Offset** controls its vertical offset
   relative to that Level.

   Enter the required numerical value directly.

   ### Location Line

   Location Line defines the wall's reference plane:

   * Wall Centerline
   * Core Centerline
   * Finish Face: Exterior
   * Finish Face: Interior
   * Core Face: Exterior
   * Core Face: Interior

   To change it:

   * click the small arrow on the right side of the field;
   * select the required option from the dropdown.

   Do not type the Location Line value manually.

   > ⚠️ Changing the Location Line property of an already-created wall changes its reference
   > definition; do not use this field as a substitute for moving the wall to a new position.

3. After each edit, verify that the displayed property value matches the requirement.

4. Press **Esc** when finished.

▸ **CHECK.** The changed values read back correctly off the Properties palette — and
nothing else.

## WINDOW — sill / vertical placement (parameter edit)

Select the required window.

### Sill Height

The window's vertical position on its host wall is controlled by:

`Sill Height`

1. Find **Sill Height** in Properties.
2. Select the numerical value.
3. Type the required height in mm.
4. Press **Enter**.

The model updates immediately.

If several windows require different sill heights, edit each window individually.

### Head Height

If **Head Height** is exposed as an editable instance parameter for the selected family, it can
be edited in the same way.

Do not assume changing Sill Height changes the window Type's width or height.

### Window size

Window **Width / Height** are commonly controlled by the Window Type rather than by the
individual instance.

If the required Width or Height is not editable in the instance Properties, do not try to
force the value here.

▸ **CHECK.** The required Sill Height (and Head Height when named) reads back on the same
host — and nothing else.

## ROOM — rename / renumber (parameter edit)

A Room's extent is normally determined by surrounding room-bounding geometry.

Use this section to modify the Room's **data**, especially its name and number.

### Select the Room

1. Open the relevant floor plan.
2. Move the cursor inside the Room.
3. Wait until the Room itself highlights.
4. Click to select it.

> ⚠️ Do not accidentally select the **Room Tag**. The tag is a separate annotation element.

### Rename

In Properties, find:

`Name`

1. select the existing text;
2. type the required room name;
3. press **Enter**.

### Renumber

If the task requires a specific room number, edit:

`Number`

in the same way.

Do not change the number when the task only specifies the room name.

## Verification

The Room itself (not its tag) carries the required Name/Number — and nothing
else.
