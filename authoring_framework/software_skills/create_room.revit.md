---
name: create_room
description: Create a Revit Room with its name and number in an enclosed plan region — closing any wall-less boundary edge with a Room Separation Line first.
software: Revit
---

# Create a room (capability)

A **Room** is bounded by room-bounding elements (walls, Room Separation Lines) — the boundary
is detected, never drawn as part of placement. An edge with NO wall (open-plan split) needs a
**Room Separation Line** first (Part B). Open the target level's plan FIRST
((set_active_story.revit.md)) — a Room's **Level** is read-only, fixed by the plan it is
placed in.

## Part A — place a Room, then name it
1. `activate-ribbon-tool(Architecture, Room)` (**Room & Area panel > Room**, shortcut `rm`) —
   the **Modify | Place Room** tab + Options Bar appear.
2. **Tag on Placement** (Tag panel) must be ACTIVE — blue-highlighted. Toggle it on if not.
   That is the ONLY setting to check: leave the rest of the Options Bar (Upper Limit, Offset,
   Room list) and all properties at their defaults.
3. **Place:** click ONCE at a clear interior point of the CORRECT enclosed region (away from
   walls, tags, other graphics) — the room is created with a DEFAULT name and number, and its
   tag appears. More rooms: just click the next region.
4. **Esc** to leave placement, then **rename on the tag**: double-click the room's NAME text
   in the tag — it becomes editable in place; type the name, Enter. The NUMBER is edited the
   same way (double-click the number text).

▸ **CHECK.** Each required Room exists in its intended region with the required
name/number — and nothing else.

## Part B — Room Separation Line (a boundary edge with no wall)
Room-bounding like a wall, but no wall geometry. Used when the region you want a room in is
NOT closed by walls.
1. **Room & Area panel > Room Separator** — the button right next to **Room** (no dialog; the
   canvas waits for the first point).
2. It draws a straight line: click the FIRST point, move to the SECOND point, click — the
   line appears; that line is the separation line. Snap each end onto the room-bounding
   wall/element on its side — an end that merely approaches a wall does not close the
   boundary. Chain more segments if the gap needs them.
3. **Esc** (twice if still drawing) — the committed lines stay.
4. An existing room re-bounds immediately; otherwise place the room via Part A. Line
   invisible → View > Visibility/Graphics > Model Categories > **Lines > <Room Separation>**
   (the specific row, not the general Lines toggle). Wrong line → delete it like any element
   ((delete_element.revit.md)).

## Verification

The intended region is enclosed — and nothing else.
