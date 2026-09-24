---
name: list_library
description: Inspect Revit door and window families — those loaded in the project and those loadable from the installed or cloud library — read-only, nothing loaded.
software: Revit
---

# List the library (capability)

Inspect available **Door** or **Window families**.

There are two different inventories:

* **Loaded families** — already inside the current project and immediately available for placement.
* **Loadable families** — available in the installed or Autodesk library but not yet loaded into the project.

This is a **read-only** capability. Do not load, create, rename, or modify anything.

## Loaded families

### Method A — Project Browser

1. In the **Project Browser**, expand:

   **Families**

2. Scroll down to find the category, then expand the required category:

   * **Doors**
   * **Windows**

3. Each family appears under the category, with its available Types underneath.

4. Expand families when necessary to inspect their Types.

5. Scroll through the Project Browser if the complete list is not visible.

6. Read every required family/type name exactly as displayed.

### Method B — Type Selector

Use this when checking which families/types are immediately placeable.

For doors:

1. Activate:

   `Architecture → Door`

2. Open the **Type Selector**.

3. Read the available loaded Door family/type names.

4. Scroll if necessary.

5. Close the dropdown and press **Esc** until the Door tool is inactive.

For windows:

1. Activate:

   `Architecture → Window`

2. Open the **Type Selector**.

3. Read the available loaded Window family/type names.

4. Scroll if necessary.

5. Close the dropdown and press **Esc** until the Window tool is inactive.

Do not click the canvas or place any component.

## Loadable library families

Use this to inspect families that are available in the local Revit library but are not necessarily loaded into the project.

1. Press **Esc** until no active command remains.

2. Open:

   **Insert → Load from Library → Load Family**

3. The **Load Family** dialog opens.

4. Navigate to the required category folder:

   * **Doors**
   * **Windows**

5. Inspect the available `.rfa` family files.

6. Scroll through the list when necessary.

7. Select a family once to inspect its name and preview.

   Do not double-click the file and do not click **Open**.

8. If useful, switch the file browser to a thumbnail view so multiple families can be inspected visually.

9. When finished, click **Cancel**.

> ⚠️ Do not click **Open** or otherwise confirm a family. This capability only inspects the library and must not load anything into the project.

## Autodesk cloud library

To inspect Autodesk-hosted content:

1. Press **Esc** until no active command remains.

2. Open:

   **Insert → Load from Library → Load Autodesk Family**

3. Search for the required Door or Window family.

4. Inspect the search results and exact family names.

5. Close the window without clicking **Load**.

> ⚠️ Cloud library content requires internet access and may require Autodesk account access.

## Important distinction

A family appearing in the **Load Family** or Autodesk library is only **available to load**.

It is not yet usable for placement unless it also appears in the project's:

* **Project Browser → Families**, or
* corresponding **Type Selector**.

Do not confuse these two inventories.

## Verification

The names you report are exactly the on-screen ones (loaded vs loadable kept
apart), and nothing was loaded or changed — report nothing else.
