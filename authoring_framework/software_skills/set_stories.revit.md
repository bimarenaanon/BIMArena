---
name: set_stories
description: Define the Revit storey stack by creating, renaming, and setting elevations for Levels in a section or elevation view.
software: Revit
---

# Define the storey stack (capability)

In Revit, building storeys are represented by **Levels**.

Read the required **storey names, absolute elevations, and floor-to-floor heights** from the drawing's section or elevation before editing the model.

> ⚠️ Create and edit Levels in a **Section or Elevation view**, not in a floor plan.

## Recipe

1. Open a building **Elevation** or **Section** view (bottom-left views) where the existing horizontal Level lines are visible.

   Each Level line shows:

   * the Level name;
   * its elevation value.

2. Create each missing Level using one of the following methods.

   ### Method A — Create a new Level

   Activate:

   **Architecture → Datum → Level** (`LL`)

   Then:

   1. click a start point;
   2. move horizontally;
   3. click an end point.

   Place the Level at approximately the required height first. Set the exact elevation afterward.

   Before drawing, check the **Options Bar** directly below the Ribbon.

   Keep **Make Plan View** enabled when a floor-plan view should be created for the new Level.

   > ⚠️ The Options Bar appears only while the Level tool is active.

   ### Method B — Copy an existing Level

   Select an existing Level line and use **Copy** (`CO`).

   Then:

   1. click a base point;
   2. move the cursor vertically upward or downward;
   3. type the required floor-to-floor distance in mm;
   4. press **Enter**.

   This places the copied Level at the corresponding offset from the original.

   > ⚠️ A copied Level may not automatically create a corresponding Floor Plan view. Create
   > the plan view separately if required.

3. Set the exact **Level name**.

   At the Level head:

   1. click the blue Level name;
   2. click the name again to enter text-edit mode if necessary;
   3. select the existing text;
   4. type the required storey name;
   5. press **Enter**.

   If Revit asks whether corresponding views should also be renamed, confirm when the views are intended to use the same storey name.

4. Set the exact **Level elevation**.

   At the Level head:

   1. click the blue elevation value;
   2. click it again to enter edit mode if necessary;
   3. select the current value;
   4. type the required **absolute elevation in mm**;
   5. press **Enter**.

   Repeat for every required Level.

5. After editing each Level, compare its elevation with the section/elevation drawing before continuing.

   Verify both:

   * the absolute elevation;
   * the floor-to-floor distance to adjacent Levels.

6. Delete surplus Levels only when explicitly required.

   Select the Level line and press **Delete**.

   > ⚠️ Deleting a Level can also delete associated views and model elements hosted by that
   > Level. Do not delete an existing Level merely because it is not needed for the current
   > task.

## Verification

Before finishing, verify: one Level per required storey with the required name and elevation (plan views
only where the task needs them) — and nothing else.
