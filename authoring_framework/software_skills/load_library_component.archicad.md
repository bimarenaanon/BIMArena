---
name: load_library_component
description: Select an existing Archicad Door or Window library part, configure its required parameters in Tool Settings, and make it the active component ready for placement.
software: Archicad
---

# Load a library component (capability)

Select and configure an existing **Door** or **Window library part** so it becomes the active component ready for placement.

Use the component browser inside the corresponding **Tool Settings** dialog.

> 🛑 **Open the library browser ONLY through the tool's Settings dialog.** Never go through
> the **File** menu to open the **Library Manager** (File → Libraries and Objects → Library
> Manager…) for this: Library Manager manages which libraries are LOADED into the project —
> it cannot select or configure a part for placement, so opening it here is a dead end that
> wastes steps. The browser you need lives in the upper part of the Door/Window **Tool
> Settings** dialog (step 2).

## Recipe

1. Activate the required tool:

   * **Door**, or
   * **Window**.

2. Open the tool's **Settings** dialog.

3. In the upper part of the Settings dialog, use the **library-part browser**.

   It contains:

   * folder/category tree;
   * thumbnail or item list;
   * search field;
   * selected component preview and name.

4. Find the required Door or Window part.

   Use the **Search** field with a distinctive keyword when necessary.

5. Select the required component.

   Verify its **full exact name** before continuing.

   > ⚠️ Do not choose a component only because its thumbnail looks similar. Confirm the exact library-part name.

6. Configure the required parameters in the Settings dialog.

   Set only parameters required by the task, such as:

   * **Width**
   * **Height**
   * sill height for Windows, when applicable;
   * frame / leaf / panel parameters;
   * opening or representation settings;
   * other explicitly required component parameters.

   For numerical fields:

   1. click the value;
   2. select the existing number;
   3. type the required value;
   4. click another field to commit it.

   Verify each value after entering it.

7. Before closing the dialog, verify:

   * correct Door / Window library part;
   * correct Width;
   * correct Height;
   * all other required parameters;
   * no unintended parameter was changed.

8. Click **OK**.

   Do not use **Cancel**.

   The Settings dialog closes and the selected Door or Window component becomes the active component for the tool.

9. Back in the Floor Plan, verify that the tool is still active and the selected component is now ready to place.

   Do not place it yet unless placement is part of the current task.

## Verification

The exact required part is the active component at the required size,
committed with OK, nothing placed — and nothing else.
