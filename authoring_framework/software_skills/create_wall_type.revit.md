---
name: create_wall_type
description: Author a new layered Wall Type in Revit — duplicate an existing Basic Wall and define its Structure layers from existing materials; no wall is placed.
software: Revit
---

# Create a wall type (capability)

Author the layered **Wall Type** only — draw NO wall. Reuse existing Basic Wall types and
Material names ((list_types.revit.md), (list_materials.revit.md)); never invent.

> ⚠️ Type edits hit EVERY instance of the edited type — **Duplicate BEFORE touching
> Structure**; editing the source type alters the walls already using it.

> ⚠️ Never open **Visibility/Graphics** (`VG`/`VV`) — it only toggles what the view draws
> and helps nothing in this flow.

## Recipe — per required Wall Type
1. `activate-ribbon-tool(Architecture, Wall)` (**Wall: Architectural**, shortcut `wa`; NOT
   Wall: Structural). Do NOT click in the drawing area anywhere in this flow — a click while
   the Wall tool is active begins a wall.
2. `pick-from-type-selector(<closest existing Basic Wall>)` (similar thickness/build-up) →
   `open-type-properties / duplicate-type` with the required new name → **Type Properties**
   stays open on the duplicate — verify the new name at the top before any edit.
3. **Construction → Structure → Edit…** — the **Edit Assembly** dialog: layer table with
   **Function / Material / Thickness** columns, ordered **EXTERIOR (top) → INTERIOR
   (bottom)**, two **Core Boundary** marker rows around the core, plus **Total thickness**.
   (**Width** in Type Properties is a result, not a substitute for editing Structure.)
4. **Build the stack:**
   - Rows: select by the row number → **Insert** / **Duplicate** / **Delete** until one row
     per required layer (Core Boundary rows are markers, not layers) → **Up/Down** into the
     exterior→interior order; required core layers BETWEEN the boundaries. Order is meaning —
     right materials in the wrong order is a different wall.
   - Per row: **Function** from the drop-down (**Structure [1] / Substrate [2] / Thermal/Air
     [3] / Finish 1 [4] / Finish 2 [5] / Membrane Layer**; the numbered priority drives
     layer joins — not decorative) → **Material**: click the Material cell once, then
     click the small **`…` button at the cell's RIGHT EDGE** — only that opens the
     Material Browser (a plain click merely selects, a double-click does nothing, and
     Enter just jumps to the Thickness cell). In the browser: search the
     EXACT existing name → select → **Apply** → **OK** (Apply before OK is the commit;
     a lookalike library material is not the project material) →
     **Thickness** typed, committed by clicking another cell. A **Membrane Layer** stays
     zero-thickness and cannot sit in the core; a rejected value means fixing the layer, not
     forcing another.
5. **Verify in Edit Assembly:** order, every Function/Material/Thickness, core between the
   boundaries, **Total thickness** = the required sum (same total ≠ same type — read the
   rows).
6. **Commit BOTH dialogs:** OK in **Edit Assembly** → verify **Width** in **Type Properties**
   → OK there. (Cancelling the first loses the table; skipping the second leaves the type
   uncommitted.)
7. **Esc** to leave the Wall tool without placing; the new type shows as current in the Type
   Selector and under the project's wall types.

## Verification

The new Basic Wall type exists with the required layers, and no wall was
placed — and nothing else.
