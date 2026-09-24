---
name: create_opening_type
description: Create/resize a Revit door or window family type — duplicate a loaded type, edit type-level Width/Height under Dimensions; nothing is placed. Sizes are TYPE parameters on Revit.
software: Revit
---

# Create an opening type (capability)

Door/window **Width/Height are TYPE properties** on Revit: a new size = a duplicated type.
The family must already be loaded (else (load_library_component.revit.md) first). No ArchiCAD
counterpart — there the type + size ride the place call.

> ⚠️ Editing an existing type resizes EVERY instance of it — **Duplicate before editing**,
> unless the instruction explicitly targets an existing type.

## Recipe — element = door | window (same flow)
1. Activate the tool: click the **Door** / **Window** icon on the **Architecture** ribbon
   (Build panel), or the shortcut (`dr` / `wn`) — `activate-ribbon-tool`. The **Modify |
   Place Door/Window** tab appears and the LEFT **Properties palette** now shows the
   currently active door/window type.
   > ⚠️ Do NOT click in the drawing area anywhere in this flow — hovering a wall previews an
   > instance and a click would place it; this capability creates only a type.
2. `pick-from-type-selector(<closest loaded type of the required family>)` — the dropdown at
   the TOP of the Properties palette; prefer the intended construction/non-size properties.
   Family not loaded → (load_library_component.revit.md), then pick.
3. Click **Edit Type** — the button sits DIRECTLY BELOW the Type Selector in the Properties
   palette (`open-type-properties / duplicate-type`) → **Duplicate…** → type the required
   NAME → OK in the **Name** dialog. The **Type Properties** dialog stays open on the
   duplicate — confirm the new name at the top BEFORE touching any parameter.
4. The dialog lists MANY parameters — scroll to the **Dimensions** group and set **Width**
   and **Height** only (commit the first by clicking the second cell, the second by clicking
   a non-editable area). A window's default sill only when the task names it: **Default Sill
   Height** (a TYPE parameter — the placed instance's **Sill Height** is a different,
   instance one: (replace_type.revit.md)).
   > ⚠️ Only **Width**/**Height** — not Rough Width/Rough Height/Thickness/trim, and not the
   > instance Head/Sill Height; lookalike parameters do not define the type's size.
5. **OK** in Type Properties (never Cancel — the edits would be lost). The new type is now
   active in the Type Selector.
6. **Esc** to leave the tool without placing.

Variants:
- **Required name already exists** as the intended type → skip Duplicate: pick that type,
  Edit Type, set Width/Height, OK (only when the instruction clearly means that existing
  type — its placed instances all resize).
- **Rename a duplicate:** **Rename…** inside Type Properties, confirm the naming dialog.

## Verification

The new type exists with the required name and Width/Height, and nothing was
placed — and nothing else.
