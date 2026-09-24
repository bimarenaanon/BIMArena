---
name: place_door
description: Place a door on an existing Archicad wall — exact typed center offset along the host, swing side set at placement.
software: Archicad
---

# Place a door (capability)

Place a **Door** in an existing Archicad wall.

The host wall must already exist.

Before placement, verify that the correct Door library part and required size are active.

## Setup

1. Activate the **Door** tool.

2. Verify the active Door component.

   Before placing anything, confirm that:

   * the exact required Door library part is selected;
   * **Width** is correct;
   * **Height** is correct;
   * any other explicitly required parameters are correct.

3. If necessary, open **Door Settings**, select the required component, set its parameters, and close the dialog with **OK**.

4. Return to the Floor Plan with the Door tool active.

## Place each door

The exact horizontal position is entered numerically.

The placement uses **two Enter presses**:

* first **Enter** → fixes the door position;
* second **Enter** → fixes the opening direction.

### 1. Choose the host wall

Move the cursor onto the required wall near the intended Door position.

**Do not click.**

The hover identifies which wall will host the Door.

### 2. Activate numerical positioning

Press **Tab**.

Then **stop and take a screenshot**. Read the tracker: which wall end is the distance
measured from? Wrong end → press **Tab** again, screenshot again. **Never type before
you have seen the reference end** — a blind offset lands mirrored from the wrong end.

### 3. Enter the exact Door position

Type the required distance in mm.

The distance is measured **along the host wall from the selected wall end to the Door center**.

Press **Enter**.

The Door's position along the wall is now fixed.

> ⚠️ Do not place the Door approximately by clicking a screen position. The hover selects the host wall; the typed distance determines the exact Door position.

### 4. Set the opening direction

After the first Enter, Archicad waits for the Door orientation.

Move the cursor slightly toward the side where the Door should open.

Use the plan symbol to determine the required:

* opening side;
* swing direction.

Then press **Enter** again.

The Door is now placed.

> ⚠️ Send Tab / type / Enter as SMALL batches with a screenshot between steps — and
> **never put Esc in the same batch after the two Enters**: Esc cancels a pending input
> and silently undoes the placement. Esc only after a screenshot confirms the result.

> If the typed placement has missed twice: click-place it approximately on the host
> instead, then select the placed opening and **Drag** it (Edit > Move > Drag, type the
> exact distance along the wall, Enter) onto the required offset.

The complete sequence is:

`hover host wall → Tab → choose correct distance reference → type offset → Enter → nudge toward swing side → Enter`

## Repeat for additional doors

Before each new Door, verify that the active component and dimensions are still correct.

For every Door:

1. hover the correct host wall;
2. press **Tab**;
3. confirm the distance is measured from the required wall end;
4. type the center offset;
5. press **Enter**;
6. move toward the required opening side;
7. press **Enter** again.

## Verification

Each door: the required part on the correct wall, centre at the typed offset,
swing per the drawing — and nothing else. Press **Esc** to leave the placement command when
done.
