---
name: list_types
description: Read the project's composite (layered wall/slab type) inventory and each composite's skins — read-only, nothing edited.
software: Archicad
---

# List types (capability)

Composites are ATTRIBUTES — the inventory is a dialog read, not a canvas read. This capability
only LOOKS; assigning one to a wall/slab is `pick-from-structure` / `open-selection-settings`,
and authoring a new one is (create_wall_type.archicad.md) / (create_slab_type.archicad.md).

## Recipe
1. Menu **Options > Element Attributes > Composites** — the LEFT panel lists the project's
   composites (search field, folder vs flat-list view as in every attribute dialog).
2. Click a composite row to READ it:
   - the **Use With** icons (wall / slab / roof / shell) say which tools may use it — a
     composite missing from a tool's structure pop-up usually lacks its Use With tick;
   - the **Edit skin and line structure** panel lists its skins, each a Building Material
     with a thickness. The FIRST listed skin is the **Outside** on a wall / the **Top** on a
     slab.
3. Screenshot each composite you care about, then close with **Cancel** (nothing was edited).
   > ⚠️ `close-dialog` exception: inherited from an earlier step's unfinished work → **OK**,
   > never Cancel.

## Verification

The composite names (skins/thicknesses only when the task asks) are stated
verbatim. Nothing else.
