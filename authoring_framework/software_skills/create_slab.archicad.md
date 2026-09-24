---
name: create_slab
description: Create an Archicad slab from an existing slab composite — the footprint traced as one closed polygon on the right storey, with the required reference plane and offset; no new composite is authored.
software: Archicad
---

# Create a slab (capability)

Create one **Archicad slab** using the required existing slab composite.

Set the slab's structure and vertical placement **before drawing the footprint**.

## Setup — before drawing

1. Open the storey where the slab should be created.

   A newly created slab uses the current storey as its **Home Story**, so verify the active storey before placement.

2. Activate the **Slab** tool.

3. Open **Slab Settings** and go to:

   **Slab Geometry and Positioning**

4. Select the required existing **Composite**.

   Verify that the exact required composite is selected before continuing.

   > ⚠️ For a composite slab, the total slab thickness comes from the sum of its composite skins. Do not switch to a Basic structure just to enter a thickness manually.

5. Set the required **Reference Plane** before creating the slab.

   Use:

   * **Top** — when the slab elevation is defined from its top surface;

   * **Core Top** — when defined from the top of the structural core;

   * **Core Bottom** — when defined from the bottom of the structural core;

   * another available plane only when explicitly required.

   > ⚠️ Set the Reference Plane before placement. Changing the reference plane of an existing slab can change its vertical position.

6. Verify:

   * `Home Story`
   * `Offset to Home Story`

   Enter the required numerical offset when specified.

7. Click **OK** to close Slab Settings.

   Do not use **Cancel**, because it discards the settings changes.

8. In the Info Box, select the **Polygonal** geometry method.

   Use Polygonal when the slab must follow a footprint defined by multiple wall corners.

## Create the slab footprint

1. Identify the complete required slab boundary before clicking.

   Use the actual building geometry as reference.

   Snap to **real wall corners / nodes**, not to nearby lines or visually approximate points.

2. Click the first required corner.

3. Continue around the footprint, clicking each corner in order.

4. At every corner:

   * move the cursor onto the exact wall corner;
   * wait for the snap;
   * click the snapped point.

5. Continue tracing until all required edges have been defined.

   If a corner is off-screen, navigate or zoom as needed and then continue the same polygon.

6. Close the slab by returning to the **first point**.

   Snap exactly onto the original first node and click it.

   The closing click completes and creates the slab.

   Do **not** press Enter to finish.

> ⚠️ A point merely close to the first point does not correctly close the polygon. Always snap back to the original node.

> ⚠️ If a wrong corner was used and the slab footprint is substantially incorrect, correct the geometry before continuing rather than building additional elements from the wrong slab boundary.

## Verification

The slab exists with the outline, composite and level the instruction states —
and nothing else.
