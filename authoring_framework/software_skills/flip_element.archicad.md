---
name: flip_element
description: Flip an existing Archicad element's orientation in place — wall layer side, door swing direction or hinge side, and window facing. Never delete and redraw an element only to correct orientation.
software: Archicad
---

# Flip an element's orientation (capability)

Correct the orientation of an existing element **in place**.

Do not delete and recreate a correctly positioned element only because its facing, swing, or hand is wrong.

## WALL — flip the layer side

Use this when a wall's composite is mirrored and the exterior finish faces the wrong side.

1. Select the required wall.

   Make sure the **wall itself** is selected, not a hosted Door or Window.

2. Check the wall's composite hatch and identify which side contains the exterior finish.

3. In the **Info Box**, find the **Flip Wall Along Reference Line** button beside the Reference Line controls.

4. Click the Flip button once.

   The wall body flips to the opposite side of its Reference Line while the Reference Line itself stays in place. Hosted Doors and Windows keep their opening direction.

5. Inspect the wall again.

   Verify that the exterior finish now faces the intended exterior side.

> ⚠️ Judge orientation from the actual wall layers / hatch, not only from the direction in which the wall was originally drawn.

> ⚠️ Because the wall body flips around its Reference Line, re-check the wall's resulting physical position after the operation.

▸ **CHECK.** The wall's exterior finish now faces the required side — and nothing else.

## DOOR — flip the swing side

Use this when the door opens toward the wrong side of the wall.

1. Select the **Door itself**.

   In a crowded plan, aim at the door leaf or door symbol until the Door highlights rather than the host wall.

2. With the Door selected, the bar along the TOP of the window (the Info Box) shows a
   **Flip** button — click it ONCE. Nothing else: no dialog, no extra click on the canvas.

## DOOR — flip the hinge side

Use this when the door opens toward the correct side of the wall but the hinge is on the wrong jamb.

1. Select the **Door itself**.

2. Activate **Mirror**: click the **Mirror** button in the bar along the TOP of the window
   (the Info Box) — or press `Ctrl+M`.

3. **Click ONCE on the door's CENTER point** on the canvas — that click is the mirror axis,
   and the door flips over immediately, staying in its opening on the same host wall.

> ⚠️ The two buttons, by what they actually change (verified live 2026-08-20 on the plan
> symbol):
>
> * **Flip** → mirrors the door across the WALL's axis: the swing side changes, the hinge
>   stays on its jamb.
> * **Mirror** (+ one click on the door's center) → the hinge jamb changes.
>
> So: swing wrong → **Flip**; hinge wrong → **Mirror**; both wrong → both, checking the
> symbol after each step.

## WINDOW — flip the facing

Only flip a Window when its inside/outside orientation matters.

1. Select the **Window itself**.

   Aim at the center of the window symbol until the Window highlights rather than the host wall.

2. With the Window selected, find the **Flip** button in the Info Box.

3. Click **Flip** once.

   The opening direction/facing reverses while the frame remains in place.

4. Inspect the Window again.

   Verify that the required exterior side faces toward the building exterior.

If the Window is symmetric and the drawing does not distinguish its orientation, do not flip it unnecessarily.

## Verification

The intended element is flipped the required way, in place — and nothing
else.
