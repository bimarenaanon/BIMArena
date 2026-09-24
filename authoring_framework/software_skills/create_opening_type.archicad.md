---
name: create_opening_type
description: Define a reusable Archicad door or window type at a given size — pick the library part, set Width/Height in the tool's Default Settings and save it as a named Favorite; nothing is placed.
software: Archicad
---

# Create an opening type (capability)

Archicad has no separate "door type" object: a reusable door/window type is a **library part
plus its settings**, saved as a named **Favorite**. Width and Height are settings of that
preset, so a new size = a new Favorite. Nothing is placed in the model by this capability.

> ⚠️ Do NOT click in the Floor Plan anywhere in this flow — with the Door/Window tool active a
> click on a wall places an instance; this capability creates only the type.

## Setup

1. Activate the **Door** / **Window** tool in the Toolbox.
2. Make sure NOTHING is selected (press **Esc** once): with an element selected the Settings
   dialog edits THAT element instead of the tool's defaults. The dialog title must read
   **Door Default Settings** / **Window Default Settings**, not "Selection Settings".

## Recipe — element = door | window (same flow)

1. Open the tool's **Default Settings** dialog (double-click the tool icon, or **Ctrl+T** with
   nothing selected).
2. In the part browser on the left, select the required **library part**. Read its name
   exactly as shown; if the required part is not listed, it is not loaded —
   (load_library_component.archicad.md) first.
3. In the size fields at the top of the settings, type the required **Width** and **Height**
   (millimetres) — commit each field with **Tab**. Set a window's **sill height** only when
   the task names one.
4. Open the **Favorites** control (the **star** icon in the dialog) and choose **New
   Favorite…** / *Save Current Settings as Favorite*. Type the required NAME and confirm.
5. Re-open the Favorites list and verify the new name is there
   ((list_library.archicad.md), section B).
6. Close the Settings dialog with **OK**, then press **Esc** to leave the tool without
   placing anything.

## Common warnings

- A Favorite stores the settings AT THE MOMENT it is saved: set the part and the size FIRST,
  save SECOND. Editing the dialog afterwards does not change the saved Favorite.
- Only **Width** / **Height** define the type's size — not the wall-hole oversize, reveal or
  frame parameters.
- Saving over an existing Favorite name redefines it for every later placement; use a new
  name unless the task explicitly targets an existing one.

## Recovery

If the dialog showed "Selection Settings", cancel it, press **Esc** until nothing is selected,
and start again from Setup. If an instance was placed by accident, select it and delete it
((delete_element.archicad.md)) before finishing.

## Verification

Before finishing, verify: the Favorite exists under the required name; applying it shows the
required library part, Width and Height; no door/window was added to the model.
