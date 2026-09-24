---
name: place_window
description: Place a window on an existing Archicad wall — exact typed center offset along the host, exterior facing set at placement.
software: Archicad
---

# Place a window (capability)

Place a **Window** in an existing Archicad wall.

The host wall must already exist.

Before placement, verify that the correct Window library part, size, and sill height are active.

## Setup

1. Activate the **Window** tool.

2. Verify the active Window component.

   Before placing anything, confirm that:

   * the exact required Window library part is selected;
   * **Width** is correct;
   * **Height** is correct;
   * **Sill Height** is correct;
   * any other explicitly required parameters are correct.

3. If necessary, open **Window Settings**, select the required component, set its parameters, and close the dialog with **OK**.

4. Return to the Floor Plan with the Window tool active.

## Place each window

The exact horizontal position is entered numerically.

The placement uses **two Enter presses**:

* first **Enter** → fixes the Window position;
* second **Enter** → fixes its facing.

### 1. Choose the host wall

Move the cursor onto the required wall near the intended Window position.

**Do not click.**

The hover identifies which wall will host the Window.

### 2. Activate numerical positioning

Press **Tab**.

Then **stop and take a screenshot**. Read the tracker: which wall end is the distance
measured from? Wrong end → press **Tab** again, screenshot again. **Never type before
you have seen the reference end** — a blind offset lands mirrored from the wrong end.

### 3. Enter the exact Window position

Type the required distance in mm.

The distance is measured **along the host wall from the selected wall end to the Window center**.

Press **Enter**.

The Window's position along the wall is now fixed.

> ⚠️ Do not place the Window approximately by clicking a screen position. The hover selects the host wall; the typed distance determines the exact Window position.

### 4. Set the exterior facing

After the first Enter, Archicad waits for the Window orientation.

Move the cursor slightly toward the **building exterior**.

Then press **Enter** again.

The Window is now placed.

> ⚠️ Send Tab / type / Enter as SMALL batches with a screenshot between steps — and
> **never put Esc in the same batch after the two Enters**: Esc cancels a pending input
> and silently undoes the placement. Esc only after a screenshot confirms the result.

> If the typed placement has missed twice: click-place it approximately on the host
> instead, then select the placed opening and **Drag** it (Edit > Move > Drag, type the
> exact distance along the wall, Enter) onto the required offset.

The complete sequence is:

`hover host wall → Tab → choose correct distance reference → type offset → Enter → nudge toward exterior → Enter`

## Repeat for additional windows

Before each new Window, verify that the active component, size, and sill height are still correct.

For every Window:

1. hover the correct host wall;
2. press **Tab**;
3. confirm the distance is measured from the required wall end;
4. type the center offset;
5. press **Enter**;
6. move the cursor toward the building exterior;
7. press **Enter** again.

## Verification

Each window: the required part, size and sill on the correct wall, centre at
the typed offset, exterior side outward — and nothing else. Press **Esc** to leave the
placement command when done.
