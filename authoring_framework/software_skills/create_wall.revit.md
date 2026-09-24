---
name: create_wall
description: Create straight Revit walls from an existing Wall Type.
software: Revit
---

# Create a wall

Create straight Revit architectural walls using the required existing Wall Type. Open the
target floor plan before placement and enter required dimensions numerically.

## Setup

1. Activate Architecture > Wall.
2. Verify the required Draw mode:
   - Line: individually dimensioned walls
   - Rectangle: simple rectangular footprints

   If another mode is active, select the required mode before starting wall creation.
3. Select the required Wall Type using the Type Selector. Verify the exact type before
   placing any wall.
4. Set the Location Line according to the wall function:
   - Exterior walls: Finish Face: Exterior
   - Interior walls: Wall Centerline
5. Verify the required vertical constraints:
   - Base Constraint
   - Top Constraint
   - Unconnected Height, when applicable

## Common Warnings

- Enable Chain only when creating a continuous connected wall run.
- Do not leave Chain enabled when individually specified wall segments are required.

## Wall Creation

For Line mode:

1. Click the exact required start point.
2. Move the cursor in the required direction.
3. Type the required wall length.
4. Press Enter.

With Chain enabled, continue directly from the endpoint of the previous wall without
clicking a new start point.

For a rectangular footprint, Rectangle mode may be used by selecting two diagonal corners
and subsequently correcting the required dimensions.

## Common Warnings

Do not estimate required production dimensions from the screenshot. Use the values typed
during wall placement. Temporary dimensions may measure between wall faces and can therefore
differ from the typed wall length around joined walls.

## Connectivity

- Snap directly to existing wall geometry.
- Continue connected exterior walls from the previous endpoint.
- Interior walls terminating at another wall must snap directly onto the host wall.
- The final exterior wall must return exactly to the original starting point.

## Recovery

If the wall chain is interrupted by Esc, a dialog, or a mode change:

1. Reactivate the Wall tool if necessary.
2. Verify the Wall Type and Location Line.
3. Re-enable Chain when required.
4. Snap precisely to the exterior finish-face endpoint of the previously created wall.
5. Continue with the required typed length.

If a wall is created with the wrong type or location line, correct or recreate the affected
wall before proceeding.

## Verification

Before finishing, verify:

- the required Wall Type;
- the correct Location Line;
- the typed wall length;
- Base and Top Constraints;
- wall orientation and connectivity;
- closure of the exterior perimeter;
- absence of unintended additional walls.

Judge wall lengths from the entered numerical values rather than visual estimation from the
screenshot.
