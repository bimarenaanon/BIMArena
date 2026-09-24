---
name: observation
description: Read the live Archicad model state through the GUI — screenshot the floor plan, navigate to see everything, and read a selected element's numbers (info tag, Info Box, its Settings dialog) — including SELECTING elements on purpose and reading the current selection back.
software: Archicad
---

# Observe the model (capability)

The GUI counterpart of an API model read. You are shown a fresh screenshot at the
start of every turn (there is no tool to call): what a change did is visible on the NEXT turn.
View and storey moves are (set_active_story.archicad.md); this doc is WHAT to look at and how to
read numbers off it.

## Recipe
1. **See the whole picture.** Screenshot the current floor plan; `zoom-gently` a notch or two
   if an edge is cut off. Other storeys' plans: `story-settings / story-nav`.
   > ⚠️ A **View > Fit in Window** command exists (also: double-click the middle mouse button)
   > but fits EVERYTHING incl. far-out elevation markers — never use it mid-authoring; it
   > destroys the working scale (`zoom-gently` instead).
2. **Identify elements without selecting.** With the **Arrow** tool active, hovering an
   element shows its **element info tag** pop-up on its own (with any other tool, hold Shift).
   Overlapping elements show **"Multiple Elements (TAB)"** — press Tab to cycle the highlight.
3. **Read ONE element's numbers.** `select-element` it (`select-opening` for a door/window) —
   the Info Box switches to that element's tool and shows its key fields. For the full record
   (sizes, levels, composite, library part), `open-selection-settings` (Ctrl+T), read the
   fields off the screenshot, then close with **Cancel** — nothing was edited (`close-dialog`
   rules apply if the dialog was inherited from an earlier step).
4. **Count by type.** `find-and-select(Element Type = …)`, click **+** — the palette's
   bottom-left **Selected and Editable** values report the match count. Esc afterwards.

▸ **CHECK.** State what was seen (elements, counts, numbers) from the LATEST screenshot,
never from memory of an earlier one; when the screen state is in doubt, observe again.

# Select elements and read the selection back

Two directions of one bridge: SET the selection so the next op (settings edit, drag, delete,
or an API read of the selection) acts on exactly what is highlighted — and READ BACK what is
currently selected before acting on it.

## A. SET the selection

1. **ONE element:** `select-element` (Esc first, plain Arrow click on its drawn geometry).
   A door/window: `select-opening` — the Shift-hover flow, NEVER a plain click (it grabs the
   host wall or the slab under the doorway).
2. **ADD to the selection:** hold Shift and click the next element (the help's "Shift +
   click"; keep the Shift-hover discipline for openings). Where elements OVERLAP the info tag
   shows **"Multiple Elements (TAB)"** — press Tab to cycle the highlight and click when the
   RIGHT one is lit.
3. **ALL of one type on the active storey:** `select-all-of-type` — activate that tool, then
   Ctrl+A (**Edit > Select All** becomes "Select All Walls" etc.).
4. **By criteria:** `find-and-select(criteria)` — **Edit > Find & Select**, add criteria
   (Element Type, Layer, Property, …), click the **+** button; all matches select.
   > ⚠️ Both 3 and 4 reach only VISIBLE layers of the ACTIVE window — for a cross-storey
   > selection open the 3D window first ((set_active_story.archicad.md)).
5. **Clear:** `press_esc` (also cancels any pending input) — do this BEFORE building a fresh
   selection so leftovers don't ride along.

▸ **CHECK.** The intended element(s) are the highlighted ones before any op acts on the
selection — and nothing else.

## B. READ BACK the current selection

Report what IS selected — after your own set step (A), or when an instruction says "the
selected element(s)".

1. **Screenshot first.** Selected elements carry **selection dots** on their nodes and a
   highlight; the **Info Box** switches to the selected element's TOOL (its header names the
   element type) and shows key fields. Nothing dotted = nothing selected.
2. **Count it.** Open **Edit > Find & Select** — the palette's bottom-left **Selected and
   Editable** values report the current selection's size (no criteria needed). Close the
   palette after reading; do NOT press its +/− (they would CHANGE the selection).
3. **Identify + numbers.** `open-selection-settings` (Ctrl+T) — the dialog's title names the
   type (e.g. Wall Selection Settings; mixed selections open the LAST-activated tool's
   subset), and its fields carry sizes, levels, composite, the library part name. Read off
   the screenshot, close with **Cancel** — this is a read, nothing may be committed.
4. **Just identifying, not selected?** Hover with the Arrow tool — the element info tag
   pop-up names an element WITHOUT selecting it ((observation.archicad.md)).

> ⚠️ Any plain click on the canvas, Esc, or a tool change DESTROYS the selection being read —
> observe and report before doing anything else.

## Verification

Before finishing, verify: state counts/types read off the latest screenshot, matching the Selected
counter — and nothing else.
