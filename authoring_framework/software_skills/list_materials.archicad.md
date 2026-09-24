---
name: list_materials
description: Read the project's Building Material inventory — exact existing material names, read-only, nothing edited.
software: Archicad
---

# List materials (capability)

Building Materials are ATTRIBUTES — the inventory lives in a dialog, not on the canvas. This
atom is a pure READ: open, screenshot, cancel. Assigning a material to a wall happens in the
Wall Settings instead (`pick-from-structure`).

## Recipe
1. Menu **Options > Element Attributes > Building Materials** — the dialog's LEFT panel lists
   the project's Building Materials by **Name, ID and Intersection Priority** (folder or
   flat-list view; the view-switch icons sit at the top of the list, and a **search field**
   finds an attribute by name).
2. Screenshot and read the names; scroll if the list is long. Clicking a row shows its Cut
   Fill / Surface details on the right — still just reading, touch no field.
3. Close with **Cancel** — this dialog was opened for a look and nothing was edited.
   > ⚠️ `close-dialog` exception: an attribute dialog INHERITED from an earlier step's
   > unfinished work is closed with **OK** — Cancel would discard that step's whole session.

## Verification

The material names you report/use later are stated VERBATIM off the screen —
never invented. Nothing else.
