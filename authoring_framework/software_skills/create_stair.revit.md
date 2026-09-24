---
name: create_stair
description: Create a Revit component stair between two Levels — straight, winder or spiral runs; the riser count follows from the level heights.
software: Revit
---

# Create a stair (capability)

Create **one Revit Stair by Component**.

## Recipe

1. Start the Stair command:

   `activate-ribbon-tool(Architecture, Stair)`

   Revit enters:

   **Modify | Create Stair**

   The component workflow should be active.

   Ensure **Run** is selected.

   Do **not** switch to **Create Sketch** unless the task explicitly requires custom stair
   boundaries and riser lines.

2. Set the stair constraints **before placing any run**.

   In Properties, set or verify:

   * `Base Level = <required base level>`
   * `Top Level = <required top level>`
   * `Base Offset = <required value>` if specified
   * `Top Offset = <required value>` if specified

   If the task names a specific Stair Type:

   `pick-from-type-selector(<existing Stair Type>)`

   Otherwise preserve the appropriate existing/default type.

3. Keep **Run** active and choose the required component run type.

   Use the plan geometry to select among:

   * **Straight**
   * **Full-Step Spiral**
   * **Center-Ends Spiral**
   * **L-Shape Winder**
   * **U-Shape Winder**

   Do not choose a shape merely because it is geometrically similar; match the intended stair
   layout shown in the drawing.

4. Before placing the run, set its alignment when required.

   Check **Location Line** when the run must align with a wall, opening, grid, or dimensioned
   edge.

   Depending on the selected run type, available references may include:

   * Exterior Support: Left
   * Run: Left
   * Run: Center
   * Run: Right
   * Exterior Support: Right

   Left / Right are interpreted relative to the stair's **UP direction**.

   Verify this orientation before placing the run.

5. Place the required run geometry.

   ### A. Straight run

   The **first point is the lower end** of the run.

   Place the run in the direction of travel shown by the stair's **UP arrow**.

   Use the required model references, dimensions, and snapping to establish:

   * start position,
   * run direction,
   * run width,
   * required run extent.

   When supported by the interaction workflow:

   `draw-segment-by-length(<required run extent>, <UP direction>)`

   Treat this as **component-run placement**, not as an ordinary sketch line.

   While placing, watch Revit's run preview and riser feedback.

   Do not complete the stair with an unintentionally incomplete climb when additional risers
   are required to reach the Top Level.

   ### B. L-Shape / U-Shape Winder

   Position the generated stair preview at the required location.

   Use:

   * `Spacebar` to rotate the preview when applicable;
   * **Mirror Preview** when the required hand/layout is reversed.

   Verify both:

   * overall footprint,
   * UP direction.

   A component winder may be generated as a complete shaped run from a single placement
   operation; do not manually redraw its individual treads.

   ### C. Full-Step Spiral

   Place the spiral according to the required center, radius, start position, and climb
   direction.

   Typical placement sequence:

   1. define the center;
   2. define the radius/start relationship;
   3. complete the required spiral extent.

   If the generated rotation is opposite to the required plan:

   use the available **Flip** control while still in Create Stair mode.

   ### D. Center-Ends Spiral

   Place according to the component prompts, typically:

   1. center,
   2. start,
   3. endpoint.

   Match the drawing's radius, extent, and UP direction.

6. For stairs requiring more than one run, construct only the runs required by the task.

   Example:

   ```text
   lower run
       ↓
   landing
       ↓
   upper run
   ```

   Revit may generate an automatic landing when compatible runs are connected.

   If the required stair is a simple one-run stair, do **not** add:

   * a second run,
   * an unnecessary landing,
   * extra components.

   If the task requires multiple runs, verify each run's orientation and connection before
   finishing.

7. Commit the stair:

`finish-sketch`

Use the green **Finish Edit Mode ✓** control in **Modify | Create Stair**.

This commits the complete Stair assembly.

Do not use the red ✗ unless abandoning the current stair.

> Automatic railings or other generated stair subcomponents may become visible only after
> the stair is committed. Their absence while still in Create Stair mode is not by itself
> a failure.

## Verification

Before finishing, verify: create Stair mode is exited via the green ✓ and the stair matches what the
instruction states (levels, shape, width, direction — only the stated ones) — and nothing
else.
