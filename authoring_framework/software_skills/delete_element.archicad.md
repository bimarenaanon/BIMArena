---
name: delete_element
description: Delete an existing Archicad element or a composite from the attribute library — verify the selection highlights the intended element first; a deleted wall takes its hosted doors/windows with it.
software: Archicad
---

# Delete an element (capability)

SELECT first, THEN `delete_selected` (the Delete key) — never the other way round:

- a **wall / slab / zone / stair**: `select-element` (the plain Arrow-tool click);
- a **door / window**: `select-opening` (Shift-hover until the OPENING itself pre-highlights
  light-blue → `commit_select`) — ⚠️ a plain click would grab the HOST WALL and delete THAT
  instead;
- **several at once**: `find-and-select(criteria)` or `select-all-of-type`, then ONE
  `delete_selected`.

> ⚠️ **CHECK the highlight before pressing delete** — whatever is selected is what dies; with
> nothing selected `delete_selected` is a no-op (that is the safe failure).
> ⚠️ Deleting a WALL also deletes every door/window HOSTED in it (a native opening cannot
> exist outside a wall). If the openings must survive, note their types/positions first and
> re-place them on the replacement wall after.

A delete needs no dialog and no Enter — the element vanishes immediately.

▸ **CHECK.** On the next screenshot the RIGHT element is gone and nothing that had to stay
is missing. That is the whole check — verify nothing else.

## Delete a composite (attribute, not a placed element)

A composite lives in the ATTRIBUTE library, not on the canvas — there is nothing to select
in the plan. Delete it in its own dialog:

1. Menu **Options → Element Attributes → Composites…** — the Composite Structures dialog
   opens with the composite list on the left.
2. Click the target composite's ROW in the list so it is the highlighted one — scroll the
   list if needed; ⚠️ names can be near-duplicates ("… Cavity" vs "… Cavity Plastered"), so
   read the FULL name of the highlighted row before deleting.
3. Click the **red ✕ (Delete)** button under the list. If Archicad asks to confirm
   (it warns when the composite is used by elements), confirm the delete.
4. Click **OK** to close the dialog — Cancel would discard the deletion.

## Verification

Before finishing, verify: reopen the dialog (or re-scan the list before OK): the deleted name is gone
and every other composite is still listed.
