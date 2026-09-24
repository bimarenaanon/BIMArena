---
name: create_slab_type
description: Author a new layered slab composite in Archicad's attribute library — define its skins from existing Building Materials; no slab is drawn.
software: Archicad
---

# Create a slab type (capability)

Create one new **Slab Composite** with the required layered build-up.

This capability edits the **Composite attribute only**.
Do **not** place or draw any slab geometry.

> 🛑 **Do NOT open the Building Materials list first.** Go STRAIGHT to the Composites dialog —
> never open Options > Element Attributes > **Building Materials** (or any material list)
> beforehand "to see what exists": the skin row's own material picker (step 6) searches the
> same library, so a browsing detour only wastes steps. Look a material up in the picker at
> the moment the skin needs it.

> ⚠️ All changes remain inside the **Composites** dialog until the final main **OK** is clicked.
> Do not close the main dialog with **Cancel**.

## Recipe

1. Open:

   **Options → Element Attributes → Composites**

2. Click **New…**

3. In **New Composite Structure**:

   * choose **Duplicate**;

   * select an existing **slab/floor composite** with a similar layer build-up;

   * make sure **Use With** includes **Slab**;

   * replace the duplicated name with the exact required new composite name;

   * click this dialog's **OK**.

   > ⚠️ Duplicate a slab-compatible composite, not a wall-only composite.

4. Read the duplicated skin table before editing.

   For a slab, the skins are interpreted **TOP → BOTTOM**:

   * first skin = top surface / floor finish;
   * last skin = underside.

   The two solid boundary rows mark the outside/top and inside/bottom limits and are **not material skins**.

5. Adjust the number of skins.

   * Too many skins → select the unwanted skin row → **Remove Skin**.
   * Too few skins → select the neighbouring skin row → **Insert Skin**.

   After every insert or removal, re-check the complete top-to-bottom order.

   > ⚠️ **Insert Skin** and **Remove Skin** act on the currently selected row. Confirm the row highlight before clicking.

   > ⚠️ Never remove the top or bottom Solid boundary rows.

6. Set the Building Material for every skin, from **top to bottom**.

   For each skin:

   1. select the skin row;
   2. click the small **`>`** control in its Building Material cell;
   3. search/select the required **existing Building Material**;
   4. confirm the selection;
   5. verify that the correct material name now appears in the skin row.

   Do not create a new Building Material.

7. Set the thickness for every skin.

   For each row:

   1. double-click the thickness value;
   2. select the existing number;
   3. type the required thickness in mm;
   4. click another row or field to commit the value.

   Do not rely on **Enter** to commit the cell.

   The **Total Thickness** updates from the sum of all skin thicknesses.

   > ⚠️ Slab thickness is defined by the composite's skin thicknesses. Do not try to set a separate overall slab thickness elsewhere.

8. Set the required **core designation**.

   In the **Type** column, assign the required structural skin as **Core**.

   If the duplicated composite has the wrong skin marked as Core, clear or change that designation.

   Use the task's required structural layer to determine the Core — do not infer it only from the skin's position.

9. Verify the complete composite before committing.

   Check:

   * exact composite name;
   * **Use With** includes **Slab**;
   * correct number of skins;
   * correct **top → bottom** order;
   * correct Building Material for every skin;
   * correct thickness for every skin;
   * correct Core designation;
   * both Solid boundary rows remain present;
   * **Total Thickness** equals the sum of all required skins.

10. Click the main **OK** in the **Composites** dialog.

This is the final commit.

> ⚠️ Do not click **Cancel** after editing. Cancel discards the composite changes made in the current dialog session.

## Verification

The composite exists under the exact name with the required skins in order,
and no slab was drawn — and nothing else.
