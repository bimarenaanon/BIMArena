---
name: create_stair
description: Create an Archicad stair by drawing its baseline on the floor plan — straight, L- or U-shaped, with width, risers, direction and railing set before placement.
software: Archicad
---

# Create a stair (capability)

Create one **Archicad stair** from its **Stair Baseline**.

Read from the drawings:

* **PLAN:** start position, stair width, travel direction, and straight / L / U shape;
* **SECTION:** total rise, riser count, and vertical direction.

Set the stair parameters **before the first click**. Archicad generates the stair geometry from these parameters while the baseline is drawn.

## Setup

1. Open the target storey and activate the **Stair** tool.

2. Set:

   `Stair Baseline Position = Left`

   The baseline is interpreted relative to the drawing direction.

   Draw the baseline in the **upward travel direction** along the stair's left side.

   The stair body should preview on the **right side of the baseline**.

   > ⚠️ If the body previews on the wrong side, check the drawing direction before continuing.

3. Set the required stair parameters in the Info Box before drawing.

   When specified, set:

   * **Width**
   * **Number of Risers**
   * **Going**
   * **Input Stair Upward / Downward**
   * **Add Railing to Stair**

   For railings, enable only the required:

   * Left
   * Right
   * Both

   Do not change parameters that the task does not require.

4. For L-shaped or U-shaped stairs, use:

   `Turning Type = Automatic Landing`

   This allows Archicad to generate a landing automatically when the baseline changes direction.

   > ⚠️ **Turning Type** is different from the pet palette's segment type. Do not manually choose a Landing segment when an automatic corner landing is required.

5. Verify all stair parameters before the first click.

   In particular, confirm:

   * correct riser count;
   * correct stair width;
   * correct upward/downward direction;
   * correct railing setting;
   * correct baseline position.

   Do not change the riser count or going halfway through drawing the baseline.

## Draw the baseline

### Straight stair

1. Click the required **lower-end start point**.
2. Move the cursor in the required upward travel direction.
3. Keep the baseline straight and aligned with the plan.
4. Press **Enter** when the preview shows the complete required stair.

Do not double-click to finish.

Verify that the stair body appears on the right side of the baseline.

### L-shaped stair

1. Click the required lower-end start point.
2. Move in the direction of the first flight.
3. Define the first baseline segment with the required approximate/known leg length.
4. Turn the cursor **90°** into the direction of the second flight.
5. Verify that Archicad previews an **Automatic Landing** at the turn.
6. Continue in the second flight direction.
7. Press **Enter** when the complete stair preview matches the required L-shaped layout.

The first leg must leave enough remaining stair length for the second flight.

### U-shaped stair

1. Click the required lower-end start point.
2. Draw the first flight direction.
3. Turn **90°** into the intermediate direction.
4. Continue the baseline for the required intermediate segment.
5. Turn another **90°** into the final flight direction.
6. Verify that the two turns generate the required automatic landings.
7. Press **Enter** when the complete U-shaped stair preview matches the plan.

The earlier baseline segments must leave enough remaining stair length for the final flight.

## During placement

Continuously compare the live stair preview with the drawing.

Check:

* start position;
* upward travel direction;
* width;
* number of flights;
* turning direction;
* landing positions;
* final footprint;
* railing side.

Do not commit while the preview clearly has the wrong shape or direction.

## Recovery

If a baseline segment consumes too much of the available stair length and Archicad cannot complete the stair:

1. press **Esc**;
2. discard the unfinished stair;
3. start again with corrected leg lengths.

If a **Solver** dialog appears, the current path and stair rules cannot produce a valid stair.

Do not accept an arbitrary Solver modification merely to complete the command.

Instead:

1. close the Solver without applying an unintended solution;
2. correct the stair parameters or baseline geometry;
3. redraw the stair.

If the stair body previews on the wrong side of the baseline, cancel the unfinished stair and redraw with the correct baseline direction.

Do not compensate by changing `Stair Baseline Position` away from **Left**.

## Finish

Press **Enter** only when the live preview shows the intended complete stair.

After the stair is committed, press **Esc** if necessary to leave the Stair placement command.

## Verification

The stair matches what the instruction states (position, direction, shape,
width — only the stated ones) — and nothing else.
