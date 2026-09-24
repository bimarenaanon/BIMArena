---
name: create_slab_type
description: Author a new layered Floor Type in Revit — duplicate an existing floor type and define its Structure layers from existing materials; no floor is placed.
software: Revit
---

# Create a slab type (capability)

Create or modify a layered **Floor Type only**.  
**Do NOT create, sketch, or place any floor instance.**

Reuse only existing Revit **Floor Types** and **Materials**
((list_types.revit.md), (list_materials.revit.md)). Never invent a type or material name.

> ⚠️ Editing a Floor Type changes every floor using that type.  
> **Always DUPLICATE the source type before editing its Structure.**

## Recipe

1. Open the architectural Floor tool:
   `activate-ribbon-tool(Architecture, Floor)` → **Floor: Architectural**.

   This enters Floor sketch mode. Leave the canvas alone while the type work happens in
   dialogs (steps 2–8) — one throwaway rectangle is drawn only in step 9, because
   finishing the sketch is what makes the new type permanent and Revit will not finish
   an empty one.

2. From the **Type Selector**, choose the existing Floor Type whose build-up is closest to
   the requested type:
   `pick-from-type-selector(<existing Floor type>)`.

   Prefer a type with a similar:
   - number of layers,
   - structural/core arrangement,
   - overall construction.

3. Open and click **Edit Type** and immediately **Duplicate** the selected Floor Type. 

   Enter the exact required new type name.

   Before editing anything else, verify that the **Type Properties** dialog is now showing
   the duplicated type name.

   **Never edit the original type.**

4. In **Type Properties**, go to:

   **Construction → Structure → Edit…**

   This opens **Edit Assembly**.

   The layer table contains:
   - Function
   - Material
   - Thickness

   and two **Core Boundary** marker rows.

   The Core Boundary rows are markers only; they are not material layers.

5. Build the required layer stack.

   For a Floor assembly, read the table **TOP → BOTTOM**:

   - first material row = top / walking-surface side,
   - last material row = underside.

   Do not interpret the table like a Wall assembly.

   Adjust rows using **Insert**, **Duplicate**, **Delete**, **Up**, and **Down** until there is
   exactly one material row for each required layer.

   Place all required core layers **between the two Core Boundary rows**.

6. Configure every layer completely.

   For each material row, set:

   **Function**
   - Select the required Revit layer function.
   - Function priorities affect joins and assembly behavior; they are not cosmetic labels.

   **Material**
   - Click the row's Material cell ONCE to select it, then click the small **`…`
     browse button at the cell's RIGHT EDGE** — that button is what opens the Material
     Browser.
     > A plain click only selects the cell. A double-click does nothing. **Enter** just
     > moves focus to the Thickness cell. Only the right-edge `…` opens the browser.
   - In the Material Browser: search the exact existing material name
     ((list_materials.revit.md)) → select it → **Apply** → **OK**. The layer table shows
     the name — move on.

   **Thickness**
   - Enter the required thickness.
   - Click another cell afterward so the value is committed.
   - Do not assign thickness to a membrane-function layer.
   - If Revit rejects a thickness value, check whether the Function is set incorrectly rather
     than forcing the value.

7. Before leaving **Edit Assembly**, ONE glance at the layer table: rows in the right
   top→bottom order with the exact Materials and Thicknesses. The table is authoritative
   (ignore the Preview). Do NOT re-open cells or re-verify row by row — one screenshot
   read is enough.

8. Commit the assembly in the correct order.

   First:
   **OK** in **Edit Assembly**.

   Back in **Type Properties**, verify:
   - duplicated type name,
   - **Default Thickness** equals the expected total thickness.

   Then:
   **OK** in **Type Properties**.

   Both dialogs must be committed.

   - Cancelling **Edit Assembly** discards the layer edits.
   - Closing/cancelling **Type Properties** may leave the intended type changes uncommitted.

9. Exit Floor sketch mode by **FINISHING**, never by cancelling:

   > ⚠️ **TRAP — cancel-sketch destroys the new type.** The whole Floor placement runs
   > inside ONE transaction group, and a type duplicated from inside the sketch belongs
   > to it. The red ✗ (Cancel Edit Mode) rolls the group back — the new Floor Type
   > silently disappears WITH it, even though Type Properties showed it committed.
   > The OK in Type Properties commits only into the group, not into the document.

   Revit REFUSES to finish an empty sketch ("Sketch is empty"), so:

   1. Draw ONE small temporary rectangle anywhere on the canvas (Rectangle tool, two
      clicks — size and position do not matter).
   2. Click the green ✓ (**Finish Edit Mode**). The transaction group commits and the
      new Floor Type becomes permanent.
   3. The finish created one temporary floor. Select it and `delete-selected`.
      Deleting the instance does NOT delete the type.

## Verification

The Floor Type exists under the exact name with the required layers in order,
and no floor instance remains — and nothing else.
