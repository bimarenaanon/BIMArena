---
name: list_types
description: Read the Revit project's Wall and Floor Type inventory (and a type's layer structure) — exact existing type names, read-only, nothing edited.
software: Revit
---

# List types (capability)

Inspect which **Wall Types** or **Floor Types** already exist in the current Revit project.

This is a **read-only** capability.

Read type names exactly as displayed in Revit.
Do **not** invent, rename, duplicate, or modify any type.

## Method A — Project Browser

This is the preferred method when the complete type inventory is needed.

1. Find the **Project Browser** (bottom-left panel).

2. Expand:

   **Families**

3. For Wall Types, scroll down, find `Walls` and expand:

   **Walls → Basic Wall**

   The entries underneath are the available Basic Wall Types.

4. For Floor Types, scroll down, find `Floors` expand:

   **Floors → Floor**

   The entries underneath are the available Floor Types.

5. Read the type names exactly as displayed.

6. If the list extends beyond the visible area, scroll inside the Project Browser and continue reading the remaining types.

7. If only types containing a particular word are needed, use the Project Browser search/filter field when available.

> ⚠️ Do not double-click a type while listing it. Double-clicking or opening Type Properties may enter an editable dialog.

## Inspect a type's properties

If the task also requires checking a type's thickness or layer structure:

1. Right-click the required type in the Project Browser.
2. Open **Type Properties**.
3. Read the required information, such as:

   * type name;
   * Default Thickness;
   * Structure;
   * other relevant Type Parameters.
4. When finished, click **Cancel**.

> ⚠️ Use **Cancel**, not OK, because this capability is read-only. Do not change any field.

## Method B — Type Selector

Use this when only the types available for a particular placement tool are needed.

### Wall Types

1. Activate:

   `Architecture → Wall`

2. Open the **Type Selector** at the top of the Properties palette.

3. Read the available Wall Type names, scroll down and up to find the full list.

4. Scroll the dropdown if necessary.

5. Close the dropdown and press **Esc** until the Wall placement command is no longer active.

Do not click the canvas.

### Floor Types

1. Activate:

   `Architecture → Floor`

2. Before drawing anything, open the **Type Selector**.

3. Read the available Floor Type names.

4. Scroll the dropdown if necessary.

5. Close the dropdown.

6. Exit Floor creation with **Cancel / Esc** without drawing or finishing a floor.

> ⚠️ Activating the Floor tool enters a creation workflow. Do not draw any boundary lines while only inspecting types.

## Verification

The type names you report are verbatim, Wall Types not confused with Floor
Types. Nothing else.
