---
name: set_stories
description: Define the FULL storey stack in Archicad's Story Settings dialog — count, names, elevations / heights, read from the section first.
software: Archicad
---

# Define the storey stack (capability)

Build the building's vertical divisions. Read the storey names, elevations and floor-to-floor
heights from the drawing's SECTION / ELEVATION first, then enter one row per storey.

## Recipe
1. Open Story Settings via `story-settings / story-nav` — `hotkey ["mod","7"]`, or menu
   **Design > Story Settings…**.
2. In the dialog:
   - **Insert Above / Insert Below** — add a level above / below the selected one, until the
     storey COUNT matches the section.
   - **Editing ANY cell — Name, Elevation, Height to Next — is always the SAME gesture:** move
     onto the cell → **DOUBLE-CLICK** it (edit mode) → `select_all` → `type` the new value →
     move on and double-click the NEXT cell.
   - ⚠️ **Do NOT press Enter after a cell.** Typing is enough — in this dialog Enter is the
     DIALOG's confirm: pressing it mid-way commits and CLOSES Story Settings before the
     remaining rows are set.
   - Fill EVERY row: its **Name** (never leave one empty) and its **Elevation** (absolute, from
     Project Zero) / **Height to Next** (floor-to-floor), per the section.
3. Only when ALL rows are complete — count, names, elevations — press **Enter** ONCE (= the
   dialog's OK) to commit everything and close.

> ⚠️ Changing a storey height CLEARS the Undo queue — save first when editing an existing stack.
> 🛑 Never Cancel a Story Settings dialog holding edits — see `close-dialog` (OK saves, Cancel
> silently discards the whole session).

## Verification

Before finishing, verify: storey count, names and elevations match the section — and nothing else.
(Switching the ACTIVE storey is (set_active_story.archicad.md).)
