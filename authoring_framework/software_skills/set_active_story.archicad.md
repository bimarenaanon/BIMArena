---
name: set_active_story
description: Switch the ACTIVE storey in Archicad — open another storey's floor plan for editing (Ctrl+Up/Down or Navigator), no Story Settings dialog involved — and view navigation: floor plan vs 3D window, getting back to the right storey's plan, zoom.
software: Archicad
---

# Switch the active storey (capability)

The active storey is the floor plan you are editing — everything you draw lands on it. Jump
WITHOUT opening any settings dialog, per `story-settings / story-nav`:

- **Up one storey:** `hotkey ["mod","up"]` (Ctrl/Cmd + ↑).
- **Down one storey:** `hotkey ["mod","down"]` (Ctrl/Cmd + ↓).
- **To a specific (non-adjacent) storey:** press `["mod","up"]` / `["mod","down"]` ONCE PER
  STOREY, checking the screen after each press until the target storey's plan is open — or
  **double-click that storey** in **Navigator > Project Map** (there is NO direct go-to-storey
  hotkey).

> ⚠️ Do NOT go through a "Settings" button in the LOWER-RIGHT corner — that opens **Story
> Settings** (the stack editor), not a storey switch; defining the stack is
> (set_stories.archicad.md). Switching needs no dialog at all.
> ⚠️ Coming back from the 3D window first: `open-3d-window / back-to-floor-plan` (**F2**),
> THEN navigate storeys.

▸ **CHECK.** The next screenshot shows the TARGET storey's plan (title bar / Navigator
highlight) before building on it — and nothing else.

# Navigate views (plan / 3D, zoom)

Not a modelling atom — the view moves that other atoms lean on.

## Floor plan -> 3D and back
`open-3d-window / back-to-floor-plan`: **F3** opens the **3D Window** (whole model, generic
axonometry); **F2** returns to the floor-plan window. Open 3D ONLY when the instruction itself
asks for something there, or when a selection must span SEVERAL storeys at once (the 3D
view shows every storey — e.g. the UPPER slab is the one capping the lower storey's walls).
⚠️ Do NOT switch to 3D to double-check finished work — verify on the floor plan you authored
in (screenshot + read the element's numbers); the view trip adds steps and shows nothing the
plan and the settings dialog don't.

- **Selection works the SAME in 3D:** plain click a wall/slab/roof; `select-opening`
  (Shift-hover) for a door/window. `open-selection-settings` (**Ctrl+T**) opens the selected
  element's settings from 3D too — settings-based modifies need no trip back to the plan, and
  the change shows immediately in 3D for the next screenshot.
- `scroll` zooms (cursor over the 3D canvas). To RESET a lost view, double-click **Generic
  Axonometry** under **Navigator > Project Map > 3D**.
- ⚠️ Edits that need PLAN input — typed lengths, tracing outlines, typed coordinates, placing
  openings — are done back in the floor plan (**F2** first). 3D is for identifying, selecting,
  and dialog/settings changes. Do NOT delete-and-redraw from 3D.

## Back to the RIGHT storey's plan
After **F2** the plan shows whatever storey was active — navigate per
(set_active_story.archicad.md) (`story-settings / story-nav`: Ctrl+Up/Down one storey at a
time, or double-click the storey in **Navigator > Project Map**) and CONFIRM the target
storey's plan is open before editing.

## Zoom discipline
`zoom-gently` — a notch or two over the canvas middle, mid-input safe. ⚠️ NEVER zoom all the
way out while authoring: fit-to-everything includes far-out elevation markers and destroys the
working scale.

## Verification

Before authoring anything: the open window is the intended storey's floor plan —
everything drawn lands on the active storey.
