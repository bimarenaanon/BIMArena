---
name: observation
description: Read the live Revit model state through the GUI — navigate views, select an element and read its numbers off the Properties palette and temporary dimensions; the GUI counterpart of an API model-state read — including SELECTING elements on purpose and reading the current selection back.
software: Revit
---

# Observe the model (capability)

Nothing reports the model to you — you LOOK: switch to the right view, read the next turn's
screenshot (one arrives automatically every turn), and read numbers off the Properties palette / temporary dimensions. The palette is
always already open on the left (`the application basics`).

## Recipe
1. Open the view that shows what you need ((set_active_story.revit.md)) — normally the level's
   Floor Plan; vertical numbers (heights, sills, offsets) are read off the Properties palette
   (step 2), not by switching views. `zoom-gently` until the area fills the canvas, then take
   a screenshot.
2. To read ONE element's data: `select-element(it)`. The **status bar** (bottom left) names it
   (`Walls : Basic Wall : <type>`); the **Properties palette** now shows its instance
   properties — read-only ones display shaded. Blue **temporary dimensions** show its offsets
   to nearby references.
3. Type-level numbers (width of a door type, layer thicknesses): with it selected, click
   **Edit Type** (`open-type-properties / duplicate-type`) and READ the **Type Properties**
   dialog — then **Cancel**, never OK.
4. A distance no temp dimension shows: **Modify** tab → **Measure** panel → Measure drop-down →
   **Measure Between Two References** — click the two points, read the dimension; **Esc** twice
   to exit the tool.
5. **Esc** to deselect when done; take a fresh screenshot after every navigation — the screen
   you were last given does not update by itself.

> ⚠️ With NOTHING selected the Properties palette shows the **active view's** properties, not an
> element's — check the filter line under the Type Selector names the category you expect.

▸ **CHECK.** The numbers you report came off the LATEST screenshot, with the status bar naming
the element they belong to.

# Select elements and read the selection back

Two directions of one bridge: build EXACTLY the selection you mean — the ribbon context
(Modify | <category> tab) and every subsequent edit act on it — and read back what IS
selected before acting on it. `select-element` in `the application basics` is the single-pick
core.

## A. SET the selection

1. **Esc** first — an active placement/sketch tool eats the click.
2. Single: `select-element(what)` — click its EDGE; **Tab** cycles overlapping candidates under
   the cursor before the click (status bar previews each; Shift+Tab cycles in reverse).
3. Add / remove: **Ctrl+click** adds an element, **Shift+click** removes it from the set.
4. Box select: drag a rectangle over empty canvas — **left→right** selects only what is
   COMPLETELY inside; **right→left** (crossing) selects anything even partially inside.
5. Prune by category: with the box selection live, click **Modify | Multi-Select** tab →
   **Filter** panel → **Filter**. The **Filter** dialog lists each selected category with its
   count; clear the check boxes you don't want (Check All / Check None) → **OK** — here OK IS
   the point: it commits the pruned selection.
6. All of one type: right-click an element → **Select All Instances** → **Visible in View** or
   **In Entire Project**.
7. Cleared it by accident? **Ctrl+Left Arrow** (or right-click → **Select Previous**) restores
   the previous selection — only while the Modify tool is active.

> ⚠️ A click on empty canvas DESELECTS everything — after building a multi-selection, do not
> `focus-canvas` until the selection has been used.

▸ **CHECK.** The status bar / selection count matches what you intended — and nothing
else.

## B. READ BACK the current selection

Read WHAT is selected before acting on it — every surface below is on-screen, so the read is a
screenshot.

1. Take a screenshot and read, cheapest first:
   - **Status bar** (bottom of the window): a single highlighted/selected element is named as
     `<Category> : <Family> : <Type>`; the **selection count** shows on its right side.
   - **Properties palette** (left): the filter line just under the Type Selector states the
     category and number selected (e.g. `Walls (3)`); the palette below shows the instance
     properties COMMON to the whole set. The ribbon also grew a **Modify | <category>** tab.
2. For a mixed selection's exact breakdown: click the **selection count** on the status bar —
   the **Filter** dialog opens listing each category, its **Count** column, and the total at
   the bottom. Screenshot it, then close WITHOUT clearing any check box (clearing + OK would
   CHANGE the selection — that is part A's job).
3. Nothing selected? The palette shows the active VIEW's properties and no Modify tab is up —
   that IS the answer "selection is empty".

> ⚠️ Reading is safe, clicking is not: a stray click on empty canvas clears the selection.
> If that happens, **Ctrl+Left Arrow** restores the previous selection (Modify tool active).

## Verification

Before finishing, verify: state the selection (categories + counts, or the one element's Category :
Family : Type) off the screenshot — and nothing else.
