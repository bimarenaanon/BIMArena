---
name: flip_element
description: Flip an existing Revit element in place — reverse a wall's exterior/interior side, a door's swing or hinge side, or a window's facing/hand orientation.
software: Revit
---

# Flip an element's orientation (capability)

Flip an existing element **in place** without changing its type.

Use the specific on-screen flip control whenever possible instead of Spacebar.

## WALL — flip exterior / interior side

Use this when a wall's exterior finish is facing the wrong side.

1. Select the wall.

   Make sure the **Wall itself** is selected, not a hosted door/window or another nearby element.

2. Locate the blue **double-arrow flip control** beside the wall.

3. Click the flip control once.

   The wall reverses its **Exterior / Interior orientation**.

4. Check the result immediately.

   Verify that the required exterior finish now faces the correct side of the building.

5. Press **Esc** to deselect.

> ⚠️ Flipping happens relative to the wall's **Location Line**. If the Location Line is a finish face rather than the centerline, flipping can also change which side of that reference line the wall body occupies. Re-check the wall position after flipping.

> ⚠️ Spacebar can also flip a selected wall, but prefer the visible flip control because its effect is easier to verify.

## DOOR — flip swing direction

Use this when the door opens toward the wrong side of its host wall.

1. Select the **door itself**, not its tag.

2. Locate the blue flip control **across the wall**.

3. Click **Flip the instance facing**.

4. Compare the door symbol with the plan.

   The swing arc should now appear on the required side of the wall.

5. Press **Esc** to deselect.

> ⚠️ This changes the **swing side / facing** only. It does not intentionally change which jamb contains the hinge.

## DOOR — flip hinge side

Use this when the door swings to the correct side of the wall but is hinged on the wrong jamb.

1. Select the door.

2. Locate the blue flip control **along the wall**.

3. Click **Flip the instance hand**.

4. Check the door symbol.

   The hinge should now be on the required left/right side while the swing remains on the same side of the wall.

5. Press **Esc** to deselect.

> ⚠️ Door facing and hand are two different flips:
>
> * **Across the wall** → swing/facing
> * **Along the wall** → hinge/hand
>
> Flip only the property that is wrong.

> ⚠️ Avoid Spacebar when only one of these needs changing, because it can cycle through multiple door orientations.

## WINDOW — flip orientation

Only flip a window when its asymmetric orientation matters in the drawing.

1. Select the **window itself**, not its tag.

2. Use the required blue flip control:

   * **across the wall** → Flip Facing;
   * **along the wall** → Flip Hand.

3. Click once.

4. Verify the resulting window symbol/orientation.

5. Press **Esc** to deselect.

If the window is symmetric and the drawing does not specify an orientation, leave it unchanged.

## Verification

The intended element is flipped the required way, in place — and nothing
else.
