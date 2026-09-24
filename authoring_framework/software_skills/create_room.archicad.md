---
name: create_room
description: Create an Archicad Zone (room) with its name and number inside an existing boundary — automatic Inner Edge detection for enclosed rooms, a manual polygon otherwise.
software: Archicad
---

# Create a room (capability)

Create one **Archicad Zone** for each required room.

A Zone represents the room area and stores its **Name**, **Number**, and calculated area.

The enclosing walls should already exist before creating the Zone.

## Setup

1. Activate the **Zone** tool:

   `activate-tool(Zone)`

2. Check the active **Construction Method** before clicking in the plan.

   The available methods include:

   * **Polygon** — manually trace the room boundary;
   * **Rectangle** — define a rectangular zone from two opposite corners;
   * **Inner Edge** — automatically detect the enclosed room from the inner faces of surrounding walls;
   * **Reference Line** — detect the room using wall reference lines.

   For normal enclosed rooms, use:

   **Inner Edge**

   Use **Polygon** when the room is not completely enclosed or when the required Zone boundary cannot be detected correctly from the walls.

## Create each room

### 1. Set the Zone Name and Number BEFORE placement

Before clicking inside the room, set:

* `Name = <required room name>`
* `Number = <required room number>`

Use the **Zone Name and Number** fields in the Info Box.

Enter the room label exactly as shown in the drawing.

The room number is required. Use the specified number when provided; otherwise follow the required room-numbering sequence.

> ⚠️ Set Name and Number before creating the Zone so the newly created Zone receives the correct identity immediately.

### 2. Create the Zone

#### Method A — Inner Edge

Use this for a room that is fully enclosed by walls.

1. Select **Inner Edge** as the Construction Method.
2. Move the cursor to a clear empty area **inside the required room**.
3. Click once to detect the surrounding room boundary.
4. Click again inside the room to place the Zone stamp and commit the Zone.

The exact click position is not important for the boundary, as long as the point is clearly inside the correct enclosed room.

Do not press **Enter** to finish.

> ⚠️ Make sure the first click is inside the intended room. Clicking inside a neighbouring enclosed space creates the Zone there instead.

#### Method B — Polygon

Use this when the room is not cleanly enclosed or when the Zone boundary must be defined manually.

1. Select **Polygon** as the Construction Method.
2. Click the first required boundary corner.
3. Continue clicking each boundary corner in order.
4. Snap to the actual room/wall corners whenever possible.
5. Return exactly to the first point to close the polygon.
6. After the boundary is closed, click once inside the polygon to place the Zone stamp and commit the Zone.

The manually traced polygon must follow the required room boundary.

> ⚠️ The polygon must be closed. Do not leave gaps or create overlapping/crossing boundary segments.

#### Method C — Rectangle

Use only when the required Zone boundary is rectangular and can be defined directly.

1. Select **Rectangle**.
2. Click the first corner.
3. Click the diagonally opposite corner.
4. Place the Zone stamp when prompted.

## Repeat for additional rooms

Before creating the next Zone:

1. update the **Name**;
2. update the **Number**;
3. verify the required Construction Method;
4. place the next Zone inside the correct room.

Do not reuse the previous room's Name or Number accidentally.

## Verification

Each required Zone exists in its intended room with the required Name and
Number — and nothing else.
