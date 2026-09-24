---
name: create_wall
description: Create straight Archicad walls from an existing basic or composite structure.
software: Archicad
---

# Create a wall

Create straight Archicad walls using the required existing basic or composite structure.
Work in the Floor Plan and use exact geometric snaps and numerical dimensions.

## Setup

1. Activate the Wall tool.
2. Ensure that the Straight Wall Geometry Method is active. If another geometry method is
   selected, press and hold the left-most geometry-method icon in the Info Box and select
   Straight Wall from the available options.
3. Select the required Wall Composite / Basic Structure. Verify the exact structure name in
   the Info Box before placing any wall.
4. Set the Reference Line according to the wall function:
   - Exterior walls: Outside
   - Interior walls: Center
5. Verify and set the required wall height and vertical properties in the Info Box.

## Common Warnings

- Do not use Chained Wall mode when individual wall segments are required.

## Wall Creation

For each wall:

1. Click the exact snapped start point.
2. Move the cursor in the required direction.
3. Press Tab to activate numerical input.
4. Type the required wall length.
5. Press Enter to commit the wall.

## Common Warnings

Do not click an additional endpoint after pressing Enter; the wall has already been created.
For connected exterior walls, continue from the previous wall endpoint and construct the
perimeter counter-clockwise.

## Connectivity

- Use exact geometry snaps for all wall connections.
- Each following exterior wall should start from the previous wall endpoint.
- T-junctions must terminate directly on the host wall body.
- The final exterior wall must snap exactly to the original starting point to close the
  perimeter.
- Do not place endpoints approximately near existing geometry. If a snap point is unclear,
  zoom in before committing the wall.

## Recovery

If the wall command is interrupted:

1. Reactivate the Wall tool.
2. Restore the required structure and Reference Line.
3. Snap to the last valid wall endpoint.
4. Continue using the required direction and typed length.

If an incorrect structure or reference line was active, correct the setting before creating
additional walls rather than continuing with the wrong configuration.

## Verification

Before finishing, verify:

- the correct Wall Composite / Basic Structure;
- the correct Reference Line;
- the required wall length and orientation;
- exact wall-to-wall connectivity;
- closure of the exterior perimeter;
- absence of unintended additional walls.

Press Esc when all required walls have been completed.
