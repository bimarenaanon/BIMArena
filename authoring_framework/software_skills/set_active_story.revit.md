---
name: set_active_story
description: Switch which storey you are working on in Revit — open that Level's floor-plan view from the Project Browser; elements land on the active view's level — and view navigation: floor plan vs 3D window, getting back to the right storey's plan, zoom.
software: Revit
---

# Switch the active storey (capability)

In Revit the "active storey" is simply **whichever floor-plan view is open** — walls, doors,
rooms… land on the open plan view's Level. There is NO story-up/story-down hotkey.

## Recipe
1. `navigate-project-browser(Floor Plans, <level's plan view>)` (see `the application basics`) —
   the view name matches the Level, e.g. the storey name set in (set_stories.revit.md).

▸ **CHECK** the view's name in the title bar / Project Browser bold entry before authoring
— and nothing else.

Notes:
- **No plan view listed for the level?** (Levels made by Copy don't get one.) Create it:
  **View** tab → **Plan Views** → **Floor Plan** → select the level in the dialog → **OK** — the
  new plan view opens.
- Getting to other view kinds (elevation, 3D) is (set_active_story.revit.md).

# Navigate views (plan / 3D, zoom)

Not an authoring atom — the view-switching moves the recipes lean on. Everything an element
lands on is decided by the OPEN view, so always know which view you are in (title bar; the bold
entry in the Project Browser).

## Project Browser (left panel)
The gesture is `navigate-project-browser` (see `the application basics`, incl. its ⚠️ on Ceiling
Plans and open ≠ active). The categories that matter:
- **Floor Plans** → a level's plan — this is how the active storey is set
  ((set_active_story.revit.md)).
- **Elevations (Building Elevation)** → East/South/… — where Levels are edited
  ((set_stories.revit.md)).
- **Sections** — only present once a section has been drawn.
- **3D Views** — saved 3D views.

## Default 3D View
- Click **Default 3D View** (the house icon) on the **Quick Access Toolbar** (top edge) — ONLY
  when the task itself needs a 3D view. ⚠️ Do NOT detour here to re-check finished work: read
  the numbers off the Properties palette in the plan instead. Orbit: hold **Shift + middle
  mouse**; `zoom-gently` (see `the application basics`) still applies.
- Return to the plan via the Project Browser (the 3D view stays open as another tab).

## View tab
- **View** tab → **Plan Views** → **Floor Plan** — create a missing plan view for a level.

## Verification

Before authoring anything: the open view's LEVEL is where the element will land.
