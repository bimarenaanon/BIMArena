---
name: load_library_component
description: Load a door or window family (.rfa) into the Revit project so its types become available in the Type Selector.
software: Revit
---

# Load a library component (capability)

Load a **Door** or **Window family** into the current Revit project.

Only load a family when the required type is **not already available in the Type Selector**.

Use the exact family requested by the task. Do not substitute a similar-looking family.

## Before loading

1. Activate the corresponding placement tool:

   * Door → `activate-ribbon-tool(Architecture, Door)`
   * Window → `activate-ribbon-tool(Architecture, Window)`

2. Open the **Type Selector** and check whether the required family/type is already available.

3. If the required type already exists, do not load the family again.

4. If it is missing, load the required family using one of the routes below.

## Route A — Load Family from the active Door / Window tool

This is the preferred route when the Door or Window tool is already active.

### Door

1. Activate:

   `Architecture → Door`

2. Click **Load Family** on the ribbon.

3. The **Load Family** file browser opens.

4. Open the **Doors** library folder.

5. Find the exact required `.rfa` family.

6. Select or double-click the family file.

7. If a **Specify Types** dialog appears:

   * select the required type;
   * click **OK**.

8. Return to the Door tool and verify that the loaded family/type now appears in the **Type Selector**.

### Window

1. Activate:

   `Architecture → Window`

2. Click **Load Family** on the ribbon.

3. Open the **Windows** library folder.

4. Find the exact required `.rfa` family.

5. Select or double-click the family file.

6. If a **Specify Types** dialog appears:

   * select the required type;
   * click **OK**.

7. Return to the Window tool and verify that the loaded family/type now appears in the **Type Selector**.

## Route B — Load Family from the Insert tab

Use this route when no placement tool is active.

1. Exit any active placement or edit command with **Esc** if necessary.

2. Open:

   **Insert → Load from Library → Load Family**

3. In the file browser, open the appropriate category folder:

   * **Doors** for a door family;
   * **Windows** for a window family.

4. Find the exact required `.rfa` family.

5. Select the family and click **Open**, or double-click it.

6. If a **Specify Types** dialog appears:

   * select the required type;
   * click **OK**.

7. Activate the corresponding Door or Window tool.

8. Open the **Type Selector** and verify that the required family/type is now available.

## Route C — Load Autodesk Family

Use the Autodesk cloud library only when the required family is not available in the local library.

1. Exit any active placement or edit command with **Esc**.

2. Open:

   **Insert → Load from Library → Load Autodesk Family**

3. Search for the required family.

4. Select the exact requested content.

5. Click **Load**.

6. After loading, activate the Door or Window tool.

7. Verify that the family/type appears in the **Type Selector**.

> ⚠️ **Load Autodesk Family** requires an internet connection and appropriate Autodesk access.

> ⚠️ The command may be unavailable while another Revit command is active. Exit the current command first.

## Missing required size

Loading a family does not guarantee that it contains every required width or height.

After loading:

1. open the Type Selector;
2. inspect the available types;
3. verify that the exact required size/type exists.

If the family is present but the required size is not, do not repeatedly reload the same family. The missing size must be created from an appropriate existing type instead.

## Verification

The exact required family (no substitute) is loaded and visible in the Type
Selector — and nothing else.
