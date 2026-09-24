---
name: list_materials
description: Read the Revit project's material inventory — exact existing material names, read-only, nothing edited.
software: Revit
---

# List materials (capability)

Inspect which **Materials** already exist in the current Revit project.

This is a **read-only** capability.

Read material names exactly as displayed in Revit.
Do **not** create, rename, duplicate, or modify any material.

## Recipe

1. Press **Esc** until no placement or edit command is active.

2. Open:

   **Manage → Settings → Materials**

   The **Material Browser** dialog opens.

3. Inspect the **project materials list** on the left side of the dialog.

   Only materials already loaded in the current project count.

   > ⚠️ Materials shown only in an external/library section are not project materials until they are added to the project.

4. To find a particular material, click the **search field** and type a keyword such as:

   * `brick`
   * `concrete`
   * `gypsum`

   Read the matching material names exactly as displayed.

5. Clear or change the search term when necessary and scroll through the list to inspect additional materials.

6. If a material name is truncated or unclear:

   1. click the material once;
   2. read its full name from the material information shown in the dialog;
   3. do not edit any property.

7. When finished, click **Cancel** to close the Material Browser.

   Do not use **OK** for a read-only inspection.

> ⚠️ The Material Browser is modal. Close it before attempting any other Revit operation.

## Verification

The names you report are project materials, spelled exactly as displayed.
Nothing else.
