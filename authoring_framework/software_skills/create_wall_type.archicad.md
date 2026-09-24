---
name: create_wall_type
description: Author a new layered wall composite in Archicad's attribute library — define its skins from existing Building Materials; no wall is drawn.
software: Archicad
---

# Create a wall type (capability)

Create ONE named multi-layer WALL composite in the attribute library — draw NO wall
(assigning it to geometry is (create_wall.archicad.md)). Skins use EXISTING **Building
Material** names exactly as the project spells them — never create or edit a material here
(**Building Materials** is a different dialog; do not open it for this).

🛑 **Do NOT open the Building Materials list first.** Go STRAIGHT to the Composites dialog —
never open Options > Element Attributes > **Building Materials** (or any material list)
beforehand "to see what exists": the skin row's own material picker (step 4) searches the
same library, so a browsing detour only wastes steps. Look a material up in the picker at
the moment the skin needs it.

**Dialog discipline (the whole trap):** every edit lives only in the open **Composites**
dialog session until its main **OK** — one commit at the very end, **never Cancel**
(`close-dialog`), and **never press Enter** while editing (Enter can fire the main OK and
close the half-edited dialog). Commit a cell by moving focus (click the next cell/row).

## Recipe
1. **Open** Options > Element Attributes > **Composites** — attribute list LEFT; **Use With**
   + **Edit skin and line structure** panel RIGHT.
2. **New → Duplicate → name.** Click **New…** (lower-left; do NOT pre-select a template in
   the main list — the template is chosen inside the small dialog): choose **Duplicate**, pick
   an EXISTING WALL composite close to the required build-up, `select_all` + `type` the new
   name into **Name:**, then click the SMALL dialog's own **OK** (not the main dialog's, and
   not Enter). The new composite appears selected, its duplicated skins in the table.
3. **Use With:** enable the **wall** icon (only the types the task names). This governs which
   tools list the composite — it is not a skin setting.
4. **Edit the skins — OUTSIDE → INSIDE, top row = outer face.** Separator lines between rows
   are structure, not skins — never count or use one as a layer.
   1. Row count first: **Add Skin** until one row per required layer (surplus rows: select +
      remove). Adding/removing shifts which row is which layer — set counts before the
      material/thickness pass.
   2. Per skin, outside → inside:
      - **Select the row** (click it — whole row highlights blue), THEN click the small white
        **`>`** triangle at its far right → the material picker opens → `type` the exact
        existing Building Material name → click the exactly matching row. (Triangle without
        selecting the row first mis-targets; picker showing wrong content → close, re-select
        the row, retry.)
      - **Thickness:** double-click the row's rightmost numeric cell → `select_all` → `type`
        the mm value → commit by double-clicking the NEXT cell/row (no Enter).
5. **Verify in the open dialog:** row count = drawing; every row's material + thickness in
   outside→inside order; thicknesses sum to the required total; the preview shows the bands
   in order; **Use With** wall still on.
6. **ONE final OK** on the main **Composites** dialog (explicit click — Enter only if focus is
   demonstrably on that OK). Building several composites in one session: repeat 2–5 for each,
   then one OK at the end.

🛑 **Never Cancel the main Composites dialog** — it silently discards the composite, its name,
Use With and every skin edit. A Composites dialog inherited open from an earlier step is that
step's unfinished output: close it with OK, never Cancel.

## Verification

The composite exists under the exact name with the required build-up, and no
wall was drawn — and nothing else.
