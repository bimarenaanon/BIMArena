# Benchmark cases overview

> Auto-generated from the per-case `task.json` files by `bench_runner/dataset/gen_cases_readme.py` - do not edit by hand; regenerate after changing a case.

**73 cases**, each present ONCE PER AUTHORING TOOL: `bench_cases/reasoning_tasks/archicad/<id>/` and `bench_cases/reasoning_tasks/revit/<id>/`, each with its own single-tool `task.json` (the two tools' instructions and expected_results genuinely differ) and its own `env/`. 36 cases are drawing-driven, 37 are text-only. Each carries `required_capabilities` - the fundamental capabilities (`bench_cases/CAPABILITIES.md`) it needs, with occurrence counts. `v2_template` names the V2 template a case instantiates and `legacy_id` its pre-re-classification id. `Status` names the tool trees a case exists in and flags a drawing that is a sourced figure (`input.source`, not shipped - see `bench_runner/dataset/extract_figures.py`).

## Case index

| Case | V2 | Category | Input | Status |
|---|---|---|---|---|
| [A_setup_types1](#a_setup_types1) | A01 | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit |
| [A_setup_types2](#a_setup_types2) | A02 | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit, sourced figure |
| [A_setup_types3](#a_setup_types3) | A05 | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit |
| [A_setup_types4](#a_setup_types4) | A06 | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit |
| [A_setup_types5](#a_setup_types5) | A07 | Project Initialization (1) | `drawing1.png, drawing2.png, drawing3.png` | ArchiCAD+Revit |
| [A_setup_types6](#a_setup_types6) | - | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit |
| [A_setup_types7](#a_setup_types7) | - | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit, sourced figure |
| [A_setup_types8](#a_setup_types8) | - | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit |
| [A_setup_types9](#a_setup_types9) | - | Project Initialization (1) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation1](#b_element_creation1) | A03 | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation2](#b_element_creation2) | B01 | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation3](#b_element_creation3) | - | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit, sourced figure |
| [B_element_creation4](#b_element_creation4) | B02 | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation5](#b_element_creation5) | B02 | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation6](#b_element_creation6) | B03 | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation7](#b_element_creation7) | B06 | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation8](#b_element_creation8) | - | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation9](#b_element_creation9) | C01 | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation10](#b_element_creation10) | C03 | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation11](#b_element_creation11) | - | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation12](#b_element_creation12) | - | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation13](#b_element_creation13) | D01 | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation14](#b_element_creation14) | - | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation15](#b_element_creation15) | - | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation16](#b_element_creation16) | D04 | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation17](#b_element_creation17) | E01 | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation18](#b_element_creation18) | - | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation19](#b_element_creation19) | - | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation20](#b_element_creation20) | F02 | Model Authoring (2) | `drawing.png` | ArchiCAD+Revit |
| [B_element_creation21](#b_element_creation21) | - | Model Authoring (2) | `text-only` | ArchiCAD+Revit |
| [B_element_creation22](#b_element_creation22) | - | Model Authoring (2) | `drawing1.png, drawing2.png` | ArchiCAD+Revit |
| [C_model_editing1](#c_model_editing1) | B07 | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [C_model_editing2](#c_model_editing2) | B05 | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [C_model_editing3](#c_model_editing3) | C04 | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [C_model_editing4](#c_model_editing4) | - | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [C_model_editing5](#c_model_editing5) | F06 | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [C_model_editing6](#c_model_editing6) | G01 | Model Revision (3) | `drawing.png` | ArchiCAD+Revit |
| [C_model_editing7](#c_model_editing7) | G02 | Model Revision (3) | `drawing.png` | ArchiCAD+Revit |
| [C_model_editing8](#c_model_editing8) | G03 | Model Revision (3) | `drawing.png` | ArchiCAD+Revit |
| [C_model_editing9](#c_model_editing9) | G04 | Model Revision (3) | `drawing.png` | ArchiCAD+Revit |
| [C_model_editing10](#c_model_editing10) | G05 | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [C_model_editing11](#c_model_editing11) | G06 | Model Revision (3) | `text-only` | ArchiCAD+Revit |
| [D_model_completion1](#d_model_completion1) | B04 | Model Completion (4) | `drawing.png` | ArchiCAD+Revit |
| [D_model_completion2](#d_model_completion2) | - | Model Completion (4) | `drawing.png` | ArchiCAD+Revit |
| [D_model_completion3](#d_model_completion3) | C02 | Model Completion (4) | `drawing.png` | ArchiCAD+Revit |
| [D_model_completion4](#d_model_completion4) | C05 | Model Completion (4) | `drawing.png` | ArchiCAD+Revit |
| [D_model_completion5](#d_model_completion5) | - | Model Completion (4) | `drawing.png` | ArchiCAD+Revit |
| [D_model_completion6](#d_model_completion6) | - | Model Completion (4) | `drawing.png` | ArchiCAD+Revit |
| [D_model_completion7](#d_model_completion7) | - | Model Completion (4) | `drawing.png` | Revit only |
| [D_model_completion8](#d_model_completion8) | - | Model Completion (4) | `drawing.png` | Revit only |
| [E_model_checking1](#e_model_checking1) | B08 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking2](#e_model_checking2) | F07 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking3](#e_model_checking3) | F08 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking4](#e_model_checking4) | - | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking5](#e_model_checking5) | H01 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking6](#e_model_checking6) | H02 | Model Checking (5) | `drawing.png` | ArchiCAD+Revit |
| [E_model_checking7](#e_model_checking7) | H03 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking8](#e_model_checking8) | H04 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking9](#e_model_checking9) | I01 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking10](#e_model_checking10) | I01 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking11](#e_model_checking11) | I02 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking12](#e_model_checking12) | I04 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking13](#e_model_checking13) | I05 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking14](#e_model_checking14) | I07 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking15](#e_model_checking15) | I09 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking16](#e_model_checking16) | I10 | Model Checking (5) | `text-only` | ArchiCAD+Revit |
| [E_model_checking17](#e_model_checking17) | I11 | Model Checking (5) | `text-only` | ArchiCAD only |
| [F_end_to_end1](#f_end_to_end1) | - | End-to-End Modeling (6) | `text-only` | ArchiCAD+Revit |
| [F_end_to_end2](#f_end_to_end2) | - | End-to-End Modeling (6) | `text-only` | ArchiCAD+Revit |
| [F_end_to_end3](#f_end_to_end3) | - | End-to-End Modeling (6) | `drawing.png` | ArchiCAD+Revit |
| [F_end_to_end4](#f_end_to_end4) | - | End-to-End Modeling (6) | `text-only` | ArchiCAD+Revit |
| [F_end_to_end5](#f_end_to_end5) | - | End-to-End Modeling (6) | `drawing.png` | ArchiCAD+Revit |
| [F_end_to_end6](#f_end_to_end6) | - | End-to-End Modeling (6) | `drawing.pdf` | ArchiCAD+Revit |

## Project Initialization (1)

### A_setup_types1

- **Input:** `drawing.png` - **V2 template:** A01
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> Based on the build-up drawing, create the matching wall composite.

**Revit instruction:**

> Based on the build-up drawing, create the matching wall type.

### A_setup_types2

- **Input:** `drawing.png` - **V2 template:** A02
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Status:** ArchiCAD+Revit, sourced figure

**ArchiCAD instruction:**

> Based on the build-up drawing, create the matching wall composite.

**Revit instruction:**

> Based on the build-up drawing, create the matching wall type.

### A_setup_types3

- **Input:** `drawing.png` - **V2 template:** A05 - **was:** `A_setup_types4`
- **Required capabilities (ArchiCAD):** Create Slab Type (×1); Replace Element Type (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Slab Type (×1); Replace Element Type (×1); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> Based on the build-up drawing, create the matching slab composite. An intermediate floor slab already exists within the exterior-wall footprint. Change this existing slab to use the newly created composite. Do not modify the slab's boundary, elevation, thickness positioning, or the existing exterior walls.

**Revit instruction:**

> Based on the build-up drawing, create the matching slab type. An intermediate floor slab already exists within the exterior-wall footprint. Change this existing slab to use the newly created floor type. Do not modify the slab's boundary, its level, its height offset from that level, or the existing exterior walls.

### A_setup_types4

- **Input:** `drawing.png` - **V2 template:** A06 - **was:** `A_setup_types5`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Inspect Project (×1)

**Instruction (both tools):**

> Based on the provided section view, set up the corresponding storeys in the project, including the correct number of levels, elevations, and storey heights.

### A_setup_types5

- **Input:** `drawing1.png, drawing2.png, drawing3.png` - **V2 template:** A07 - **was:** `A_setup_types6`
- **Required capabilities (ArchiCAD):** Create Wall Type (×2); Create Slab Type (×1); Replace Element Type (×8); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×2); Create Slab Type (×1); Replace Element Type (×9); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> The project contains four exterior walls, three interior walls, and one slab, all using generic types. Three build-up drawings are provided: an exterior wall, an interior wall, and a floor slab. Create one matching composite from each wall drawing and one slab composite from the slab drawing (layers, materials, thicknesses, and order as drawn). Then switch the four exterior walls to the new exterior composite, the three interior walls to the new interior composite, and the slab to the new slab composite. Do not change any wall or slab geometry.

**Revit instruction:**

> The project contains exterior walls, interior walls, and one slab, all using generic types. Three build-up drawings are provided: an exterior wall, an interior wall, and a floor slab. Create one matching wall type from each wall drawing and one floor type from the slab drawing (layers, materials, thicknesses, and order as drawn). Then switch the exterior walls to the new exterior wall type, the interior walls to the new interior wall type, and the slab to the new floor type. Do not change any wall or slab geometry.

### A_setup_types6

- **Input:** `drawing.png` - **was:** `A_setup_types7`
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> Based on the build-up drawing, create the matching wall composite.

**Revit instruction:**

> Based on the build-up drawing, create the matching wall type.

### A_setup_types7

- **Input:** `drawing.png` - **was:** `A_setup_types8`
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Status:** ArchiCAD+Revit, sourced figure

**ArchiCAD instruction:**

> Based on the build-up drawing, create the matching wall composite using 3DF bricks.

**Revit instruction:**

> Based on the build-up drawing, create the matching wall type using 3TF bricks.

### A_setup_types8

- **Input:** `drawing.png` - **was:** `A_setup_types9`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Switch Active Story (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Switch Active Story (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> Based on the provided section view, set up the corresponding storeys in the project, including the correct number of levels, elevations, and storey heights: create one storey for every level datum marked on the section, including the eaves and the ridge datums.  When done, make the second floor the active storey and leave its floorplan open.

**Revit instruction:**

> Based on the provided section view, set up the corresponding storeys in the project, including the correct number of levels, elevations, and storey heights: create one storey for every level datum marked on the section, including the eaves and the ridge datums. When done, make the second floor the active storey and leave its floor plan open.

### A_setup_types9

- **Input:** `drawing.png` - **was:** `A_setup_types10`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Switch Active Story (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Switch Active Story (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> Based on the provided section view, set up the corresponding storeys in the project, including the correct number of storeys, elevations, and storey heights. When done, make the third floor the active storey and leave its floor plan open.

**Revit instruction:**

> Based on the provided section view, set up the corresponding storeys in the project, including the correct number of levels, elevations, and storey heights. When done, make the fourth floor the active storey and leave its floor plan open.

## Model Authoring (2)

### B_element_creation1

- **Input:** `drawing.png` - **V2 template:** A03 - **was:** `A_setup_types3`
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Create Wall (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Create Wall (×1); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> Based on the build-up drawing, create the matching wall composite. Create a 6 m long, 3 m high external cavity wall using it.

**Revit instruction:**

> Based on the build-up drawing, create the matching wall type. Create a 6 m long, 2.7 m high external cavity wall using it.

### B_element_creation2

- **Input:** `text-only` - **V2 template:** B01 - **was:** `B_walls1`
- **Required capabilities (ArchiCAD):** Create Wall (×6); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×6); Inspect Project (×1)

**ArchiCAD instruction:**

> The building's footprint is the union of two rectangular volumes: the WEST wing spans 5800 mm in x and 10700 mm in y, with its south-west corner at (0, 0); the EAST wing spans 5350 mm in x and 5250 mm in y, attached to the east side of the west wing and flush with its north edge. All wing dimensions and the (0, 0) corner are measured on the OUTSIDE face of the walls. Derive the outline of the combined footprint and create its perimeter as exterior walls, one continuous closed loop, using only the existing exterior wall composite '100 Block Insulated Cavity' with every wall's exterior face pointing outward; do not create or modify a composite. Wall ONLY the perimeter of the union. All corners must close cleanly with no duplicate segments. Create no other walls.

**Revit instruction:**

> The building's footprint is the union of two rectangular volumes: the WEST wing spans 5800 mm in x and 10700 mm in y, with its south-west corner at (0, 0); the EAST wing spans 5350 mm in x and 5250 mm in y, attached to the east side of the west wing and flush with its north edge. All wing dimensions and the (0, 0) corner are measured on the OUTSIDE face of the walls. Derive the outline of the combined footprint and create its perimeter as exterior walls, one continuous closed loop, using only the existing exterior wall type 'Exterior - Brick on Mtl. Stud' with every wall's exterior face pointing outward; do not create or modify a wall type. Wall ONLY the perimeter of the union. Set every wall's top constraint to Level 2. All corners must close cleanly with no duplicate segments. Create no other walls.

### B_element_creation3

- **Input:** `drawing.png` - **was:** `B_walls2`
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Create Wall (×10); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Create Wall (×10); Inspect Project (×1); Query Materials (×1)
- **Status:** ArchiCAD+Revit, sourced figure

**ArchiCAD instruction:**

> Based on the drawing, first create the required exterior wall composite: match the layers, materials, thicknesses, and layer order shown. Then draw all exterior walls with this wall composite as one continuous closed loop through these vertices, returning to the start (the coordinates are the OUTSIDE face of the walls; draw the loop so every wall's exterior finish faces outward): (2225, 7825) → (11100, 7825) → (11100, 2200) → (9850, 2200) → (9850, 0) → (2225, 0) → (2225, 425) → (0, 425) → (0, 4375) → (2225, 4375) → (2225, 7825)

**Revit instruction:**

> Based on the drawing, first create the required exterior wall type: match the layers, materials, thicknesses, and layer order shown. Then draw all exterior walls with this wall type as one continuous closed loop through these vertices, returning to the start (the coordinates are the OUTSIDE face of the walls; draw the loop so every wall's exterior finish faces outward): (2225, 7825) → (11100, 7825) → (11100, 2200) → (9850, 2200) → (9850, 0) → (2225, 0) → (2225, 425) → (0, 425) → (0, 4375) → (2225, 4375) → (2225, 7825)

### B_element_creation4

- **Input:** `drawing.png` - **V2 template:** B02 - **was:** `B_walls3`
- **Required capabilities (ArchiCAD):** Create Wall (×6); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×6); Inspect Project (×1)

**ArchiCAD instruction:**

> The exterior walls of the building already exist as a closed loop; do not create, move, or modify them. Based on the provided floor plan, create the six interior partition walls using only the existing interior wall composite 'Brick Double Plastered' with clean connections to the adjoining walls:
> - IntWall_1: (4225, 6175) → (0, 6175)
> - IntWall_2: (4225, 10700) → (4225, 3075)
> - IntWall_3: (0, 3825) → (4225, 3825)
> - IntWall_4: (2825, 6175) → (2825, 3825)
> - IntWall_5: (9725, 10700) → (9725, 5450)
> - IntWall_6: (4225, 0) → (4225, 1400)
> Do not create any other walls and do not create wall composites.

**Revit instruction:**

> The exterior walls of the building already exist as a closed loop; do not create, move, or modify them. Based on the provided floor plan, create the six interior partition walls using only the existing interior wall type 'Interior - 135mm Partition (2-hr)' with clean connections to the adjoining walls:
> - IntWall_1: (4225, 6175) → (0, 6175)
> - IntWall_2: (4225, 10700) → (4225, 3075)
> - IntWall_3: (0, 3825) → (4225, 3825)
> - IntWall_4: (2825, 6175) → (2825, 3825)
> - IntWall_5: (9725, 10700) → (9725, 5450)
> - IntWall_6: (4225, 0) → (4225, 1400)
> Do not create any other walls and do not create wall types.

### B_element_creation5

- **Input:** `drawing.png` - **V2 template:** B02 - **was:** `B_walls4`
- **Required capabilities (ArchiCAD):** Create Wall (×2); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×2); Inspect Project (×1)

**ArchiCAD instruction:**

> The rectangular exterior-wall loop is already built. Create the interior walls shown in the drawing, matching the wall thickness dimensioned on it; any wall type or composite of that thickness is fine. Walls only - do not place any zones. Do not modify the exterior walls or create anything else.

**Revit instruction:**

> The rectangular exterior-wall loop is already built. Create the interior walls shown in the drawing, matching the wall thickness dimensioned on it; any wall type of that thickness is fine. Walls only - do not place any room elements. Do not modify the exterior walls or create anything else.

### B_element_creation6

- **Input:** `drawing.png` - **V2 template:** B03 - **was:** `B_walls5`
- **Required capabilities (ArchiCAD):** Create Wall (×12); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×11); Inspect Project (×1)

**ArchiCAD instruction:**

> Based on the provided floorplan drawing, create the corresponding BIM model. Reproduce the walls shown in the drawing. The following room dimensions are clear internal dimensions between finished wall faces:
> - Kitchen: 3350 × 4200 mm
> - Bedroom: 4500 × 4200 mm
> - Balcony: 1550 × 4200 mm
> - Living room: 6000 × 4350 mm
> - Entry area including WC: 2900 × 4350 mm
> - WC: 1750 × 2650 mm
> . Wall type Generic - structural with width 200 mm should be used for the exterior and interior walls. Read the wall openings from the drawing and treat the two kinds differently. Where a DOOR or a WINDOW symbol sits in a wall, that wall runs through behind it: build it as one continuous wall and leave no gap there. Where a wall simply STOPS and starts again with no door or window symbol — an open passage between two rooms — leave that gap exactly as drawn. Place no doors, no windows, no zones and no slabs anywhere in the model. Every wall must otherwise be properly connected to its neighbours.

**Revit instruction:**

> Based on the provided floorplan drawing, create the corresponding BIM model. Reproduce the walls shown in the drawing. The following room dimensions are clear internal dimensions between finished wall faces:
> - Kitchen: 3350 × 4200 mm
> - Bedroom: 4500 × 4200 mm
> - Balcony: 1550 × 4200 mm
> - Living room: 6000 × 4350 mm
> - Entry area including WC: 2900 × 4350 mm
> - WC: 1750 × 2650 mm
> All exterior and interior walls must be 200 mm wide - use the project's generic 200 mm basic wall type and with the height 3000mm. Read the wall openings from the drawing and treat the two kinds differently. Where a DOOR or a WINDOW symbol sits in a wall, that wall runs through behind it: build it as one continuous wall and leave no gap there. Where a wall simply STOPS and starts again with no door or window symbol — an open passage between two rooms — leave that gap exactly as drawn. Place no doors and no windows anywhere in the model. Every wall must otherwise be properly connected to its neighbours.

### B_element_creation7

- **Input:** `text-only` - **V2 template:** B06 - **was:** `B_walls7`
- **Required capabilities (ArchiCAD):** Create Wall (×12); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×13); Inspect Project (×1)

**ArchiCAD instruction:**

> The room boundaries have already been created in the project. Based on the room boundaries shown in the project, create the exterior and interior walls so that the room layout is properly enclosed and connected. Use only the existing exterior wall composite '100 Block Insulated Cavity' and only the existing interior wall composite 'Brick Double Plastered'. Do not create or modify wall composites; ensure exterior walls form the building envelope — each with its exterior face pointing outward and ALIGNED ON the room boundary shown (do not offset the envelope outward by the wall thickness) — and interior walls centred on their boundary lines, correctly separating the rooms.

**Revit instruction:**

> Boundaries are already drawn in the project. Based on them, create the exterior and interior walls so that the layout is properly enclosed and connected. Use only the existing exterior wall type 'Exterior - Block on Mtl. Stud' and only the existing interior wall type 'Interior - 138mm Partition (1-hr)' and with the height 3500mm. Do not create or modify wall types; ensure exterior walls form the building envelope - each with its exterior face pointing outward and ALIGNED ON the boundary shown (do not offset the envelope outward by the wall thickness) - and interior walls centred on their boundary lines, correctly separating the rooms.

### B_element_creation8

- **Input:** `drawing.png` - **was:** `B_walls11`
- **Required capabilities (ArchiCAD):** Create Wall (×8); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×7); Inspect Project (×1)

**ArchiCAD instruction:**

> Based on the floorplan drawing, draw the walls only. Read the outline and every wall length from the drawing's dimension lines. All exterior walls use the same existing composite '100 Block Insulated Cavity'; do not create a new one. All interior walls use the existing composite 'Brick Double Plastered'. Author every exterior wall with its exterior finish facing outward.

**Revit instruction:**

> Based on the floorplan drawing, draw the walls only. Read the outline and every wall length from the drawing's dimension lines. All exterior walls use the same existing wall type 'Exterior - Brick on Mtl. Stud'; do not create a new one. All interior walls use the existing wall type 'Interior - 79mm Partition (1-hr)'. Wall height is connected to the level 2 storey. Author every exterior wall with its exterior finish facing outward.

### B_element_creation9

- **Input:** `text-only` - **V2 template:** C01 - **was:** `C_openings1`
- **Required capabilities (ArchiCAD):** Create Door (×4); Replace Element Type (×4); Inspect Project (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×1); Create Door (×4); Inspect Project (×1)

**ArchiCAD instruction:**

> The room is a simple rectangle with four exterior walls already built; do not create, move, or modify them. Place four doors, one roughly centred on each wall: single-leaf 900 x 2100 mm on the top and bottom walls, double-leaf 1500 x 2100 mm on the left and right walls. The two double doors are escape doors; by code an escape door swings in the escape direction, and every other door swings into the room it serves. Place no additional doors.

**Revit instruction:**

> The room is a simple rectangle with four exterior walls already built; do not create, move, or modify them. Place four doors, one roughly centred on each wall: single-leaf 915 x 2134 mm on the top and bottom walls, double-leaf 1700 x 2000 mm on the left and right walls. The two double doors are escape doors; by code an escape door swings in the escape direction, and every other door swings into the room it serves. Place no additional doors.

### B_element_creation10

- **Input:** `text-only` - **V2 template:** C03 - **was:** `C_openings3`
- **Required capabilities (ArchiCAD):** Load Library Element Type (×2); Create Door (×2); Replace Element Type (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×2); Load Library Element Type (×2); Create Door (×2); Inspect Project (×1)

**ArchiCAD instruction:**

> The room is a simple rectangle with four exterior walls already built; do not modify them. Place exactly two openings; corner distances are measured along the host wall. On the top (north) wall: a Rectangular Door Opening, 900 x 2100 mm, its left edge 3000 mm from the top-left corner. On the right (east) wall: a Double Door with 2 Sidelights, 2300 x 2100 mm, its edge nearest the top-right corner 2500 mm from that corner; it is the building's escape door and must swing in the escape direction. Create no other doors or openings.

**Revit instruction:**

> The room is a simple rectangle with four exterior walls already built; do not modify them. Place exactly two doors. On the top (north) wall: an M_Door-Double-Sliding, 1800 x 2100 mm, its left edge 3000 mm from the top-left corner, measured along the wall. On the right (east) wall: an 'M_Door-Exterior-Double-Full Glass-Wood_Clad', 1800 x 2100 mm, its edge nearest the top-right corner 2500 mm from that corner, measured along the wall; it is the building's escape door and must swing in the escape direction. Create no other doors or openings.

### B_element_creation11

- **Input:** `text-only` - **was:** `C_openings7`
- **Required capabilities (ArchiCAD):** Create Window (×3); Replace Element Type (×3); Inspect Project (×1)
- **Required capabilities (Revit):** Create Window (×3); Replace Element Type (×3); Inspect Project (×1)

**ArchiCAD instruction:**

> The model contains one rectangular room enclosed by four exterior walls; do not create, move, or modify any walls. Place exactly three windows of the same existing window type, all with a 900 mm sill height: a square window with 3.24 m2 of glass area roughly centred on the left (west) wall; a square window with 2.25 m2 roughly centred on the right (east) wall; on the top (north) wall, roughly centred, a 900 mm wide window with the same height as the east one. Place no additional windows.

**Revit instruction:**

> The model contains one rectangular room enclosed by four exterior walls; do not create, move, or modify any walls. Place exactly three windows from the same existing window family, all with a 915 mm sill height: one 915 mm wide roughly centred on the left (west) wall and one 406 mm wide roughly centred on the right (east) wall, both 610 mm high; on the top (north) wall, roughly centred, one as wide as those two are high and twice as tall as it is wide. Place no additional windows.

### B_element_creation12

- **Input:** `text-only` - **was:** `C_openings8`
- **Required capabilities (ArchiCAD):** Load Library Element Type (×2); Create Window (×4); Replace Element Type (×4); Inspect Project (×1)
- **Required capabilities (Revit):** Load Library Element Type (×2); Create Window (×4); Replace Element Type (×4); Inspect Project (×1)

**ArchiCAD instruction:**

> The model contains one rectangular room enclosed by four exterior walls. On the active storey, place exactly four windows; do not create or modify any walls. All distances are measured along the host wall, with corner distances taken from the outer face of the adjoining wall. Use a Triple Window type for two windows, both 1500 x 1500 mm with a 1000 mm sill height: one on the bottom (south) wall with its right edge 1500 mm from that wall's right corner, and one on the top (north) wall with its left edge 2000 mm from that wall's left corner. Use a Double-Hung Window type for the other two, both 1500 mm high: on the right (east) wall, 900 mm wide with a 1000 mm sill, its top edge 1200 mm below the top-right corner; on the left (west) wall, 100 mm wider than the east one with its sill 100 mm higher, its bottom edge 2100 mm above the bottom-left corner.

**Revit instruction:**

> The model contains one rectangular room enclosed by four exterior walls. On the active storey, place exactly four windows; do not create or modify any walls. All distances are measured along the host wall, with corner distances taken from the inner (room-side) face of the adjoining wall. Use an 'M_Window-Double-Hung-Double' type for two windows, both 1900 x 1550 mm with a 1000 mm sill height: one on the bottom (south) wall with its right edge 1500 mm from that wall's right corner, and one on the top (north) wall with its left edge 2000 mm from that wall's left corner. Use an 'M_Window-Sliding-Four' type, 1650 mm wide, for the other two: on the left (west) wall 600 mm tall, its top edge 1200 mm below the top-left corner; on the right (east) wall 300 mm taller than the west one, its bottom edge 2100 mm above the bottom-right corner.

### B_element_creation13

- **Input:** `text-only` - **V2 template:** D01 - **was:** `D_slabs_stairs_rooms1`
- **Required capabilities (ArchiCAD):** Create Slab (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Slab (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> Create one floor slab on the active storey covering the entire footprint of the existing exterior walls. The slab boundary must be flush with the walls' outer surface (including any finish layer), not on the wall reference line. Set the slab's reference plane to Top, with the slab's top surface at the storey level. Reuse the existing slab composite 'Concrete Floor with 10mm Tile'; do not create a new one. Do not create or modify walls; only create the one slab.

**Revit instruction:**

> Create one floor slab on the active storey covering the entire footprint of the existing exterior walls. The slab boundary must be flush with the walls' outer face (including any finish layer), not on the wall centreline. Reuse the existing floor type that builds concrete over a metal deck; do not create a new type. Do not create or modify walls; only create the one slab.

### B_element_creation14

- **Input:** `text-only` - **was:** `D_slabs_stairs_rooms2`
- **Required capabilities (ArchiCAD):** Create Slab (×2); Create Slab Opening (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Slab (×2); Create Slab Opening (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> The walls and rooms of both floors are already created, but there are no slabs yet. Create the floor slab for BOTH floors, each following its storey's exterior-wall footprint, with the boundary flush with the exterior walls' OUTER face. Use existing slab composites — create none. Do not modify any walls or rooms.

**Revit instruction:**

> The walls and rooms of both floors are already created, but there are no slabs yet. Create the floor slab for BOTH floors, each following its storey's exterior-wall footprint, with the boundary flush with the exterior walls' OUTER face. Use existing floor types — create none. Do not modify any walls or rooms.

### B_element_creation15

- **Input:** `drawing.png` - **was:** `D_slabs_stairs_rooms3`
- **Required capabilities (ArchiCAD):** Create Slab Type (×1); Create Slab (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Slab Type (×1); Create Slab (×1); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> Two steps: (1) create a new slab composite with a timber parquet finish based on the provided section view; (2) create one floor slab on the active storey using this slab composite, covering the entire footprint of the existing exterior walls, flush with the walls' outer surface, tracing the outline from the live model. Set the slab's reference plane to Core Top, positioned at the storey level. Do not create or modify any walls; only create the new slab composite and the one slab on the active storey.

**Revit instruction:**

> Two steps: (1) create a new floor type with a timber parquet finish based on the provided section view; (2) create one floor slab on the active storey using this floor type, covering the entire footprint of the existing exterior walls, flush with the walls' outer surface, tracing the outline from the live model, and placed so its TOP surface sits at the storey level. Do not create or modify any walls; only create the new floor type and the one slab.

### B_element_creation16

- **Input:** `text-only` - **V2 template:** D04 - **was:** `D_slabs_stairs_rooms4`
- **Required capabilities (ArchiCAD):** Create Stair (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stair (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> The walls are already built and enclose the layout. Create exactly one straight stair inside the bottom-left room (the wall-enclosed space in the bottom-left corner), ascending to the right (walking line in +x). Size and position it to fit entirely inside that room, clashing with nothing. Do not create or modify walls, rooms, or slabs; only place the one stair.

**Revit instruction:**

> The walls are already built and enclose one L-shaped space. Create exactly one straight stair inside the bottom-left leg of that space, ascending to the right (walking line in +x). Size and position it to fit entirely inside that leg, clashing with nothing. Do not create or modify walls, rooms, or slabs; only place the one stair.

### B_element_creation17

- **Input:** `drawing.png` - **V2 template:** E01 - **was:** `D_slabs_stairs_rooms6`
- **Required capabilities (ArchiCAD):** Create Room/Zone (×3); Inspect Project (×1)
- **Required capabilities (Revit):** Create Room/Zone (×3); Inspect Project (×1)

**ArchiCAD instruction:**

> The walls are already built. Create one named zone for each room the floorplan drawing shows, placing each zone inside the matching enclosed area with the name shown in the drawing. The living room is open to the entrance hall through a wall-less gap: stop the Living Room zone on the line between the two wall ends and give the hall no zone. Do not move or create any walls; only place the zones.

**Revit instruction:**

> The walls are already built. Create one named room for each room the floorplan drawing shows, placing each room inside the matching enclosed area with the name shown in the drawing. Do not move or create any walls; only place the rooms.

### B_element_creation18

- **Input:** `drawing.png` - **was:** `D_slabs_stairs_rooms7`
- **Required capabilities (ArchiCAD):** Create Room/Zone (×11); Inspect Project (×1)
- **Required capabilities (Revit):** Create Room/Zone (×14); Inspect Project (×1)

**ArchiCAD instruction:**

> The walls are already built. Create one named zone for each room the floorplan drawing shows, placing each zone inside the matching enclosed area with the name shown in the drawing. Do not move or create any walls; only place the zones.

**Revit instruction:**

> The walls are already built. Create one named room for each room the floorplan drawing shows, placing each room inside the matching enclosed area with the name shown in the drawing. Do not move or create any walls; only place the rooms.

### B_element_creation19

- **Input:** `text-only` - **was:** `D_slabs_stairs_rooms8`
- **Required capabilities (ArchiCAD):** Create Room/Zone (×5); Inspect Project (×1)
- **Required capabilities (Revit):** Create Room/Zone (×5); Inspect Project (×1)

**ArchiCAD instruction:**

> Five rooms exist on the active storey: four are fully enclosed, and the top-left room and the central circulation space open into each other through a wall-less passage — split them on the line of the short wall stub between them. Do not move or create any walls. Create one named zone filling each enclosed area, working out which is which: the central circulation space is the Hallway; the smallest room is the Kitchen; of the two western rooms, the northern is the Living Room and the southern is Bedroom 1; the remaining room is Bedroom 2.

**Revit instruction:**

> Five areas are already enclosed by existing walls; do not move or create any walls. Create one named room filling each enclosed area, working out which is which: the central space is the Hallway; the largest of the four outer rooms is Bedroom 1 and the smallest is the Kitchen; of the remaining two, the western is the Living Room and the eastern is Bedroom 2.

### B_element_creation20

- **Input:** `drawing.png` - **V2 template:** F02 - **was:** `E_cross_view1`
- **Required capabilities (ArchiCAD):** Switch Active Story (×1); Create Window (×6); Inspect Project (×1)
- **Required capabilities (Revit):** Switch Active Story (×1); Create Window (×6); Inspect Project (×1)

**ArchiCAD instruction:**

> The two-storey building's walls are already created, but there are no windows yet. Read the provided drawing and create the windows on BOTH floors, each 1500 x 1500 mm, matching the host walls, positions, and sill heights shown. Do not create or modify any walls, and place no extra windows.

**Revit instruction:**

> The two-storey building's walls are already created, but there are no windows yet. Read the provided drawing and create the windows on BOTH floors, each an 'M_Window-Double-Hung' type at 1500 x 1500 mm, matching the host walls, positions, and sill heights shown. Do not create or modify any walls, and place no extra windows.

### B_element_creation21

- **Input:** `text-only` - **was:** `E_cross_view2`
- **Required capabilities (ArchiCAD):** Switch Active Story (×1); Create Wall (×16); Inspect Project (×1)
- **Required capabilities (Revit):** Switch Active Story (×1); Create Wall (×16); Inspect Project (×1)

**ArchiCAD instruction:**

> The project is empty. Create ONLY the exterior walls of a two-storey building; use the wall type 'Generic Wall/Shell' for every wall. Ground-floor outline, one closed loop (mm): (3500, 10200) → (3500, 8300) → (0, 8300) → (0, 800) → (3500, 800) → (3500, 0) → (10700, 0) → (10700, 8300) → (8000, 8300) → (8000, 10200) → back to (3500, 10200). The SECOND floor reuses the same outline minus the northern projection: everything north of y = 8300 is single-storey, so the upper outline closes straight along y = 8300. The outline coordinates are the OUTSIDE face of the walls; orient every wall so its exterior face points outward. Create nothing else.

**Revit instruction:**

> The project is empty. Create ONLY the exterior walls of a two-storey building, all 200 mm wide, using the project's generic 200 mm basic wall type. Ground-floor outline, one closed loop (mm): (3500, 10200) → (3500, 8300) → (0, 8300) → (0, 800) → (3500, 800) → (3500, 0) → (10700, 0) → (10700, 8300) → (8000, 8300) → (8000, 10200) → back to (3500, 10200). The SECOND floor reuses the same outline minus the northern projection: everything north of y = 8300 is single-storey, so the upper outline closes straight along y = 8300. The outline coordinates are the OUTSIDE face of the walls. Create nothing else.

### B_element_creation22

- **Input:** `drawing1.png, drawing2.png` - **was:** `E_cross_view3`
- **Required capabilities (ArchiCAD):** Create Wall (×6); Inspect Project (×1); Query Types (×1)
- **Required capabilities (Revit):** Create Wall (×6); Inspect Project (×1); Query Types (×1)

**ArchiCAD instruction:**

> drawing1 is the ground-floor plan; drawing2 shows the front and rear elevations. Create ONLY the exterior walls from the floorplan, reading the outline and lengths from its dimension lines (walls only - ignore all doors, windows, stairs, and furniture). Choose the wall composites from the elevations: the front facade uses the finish shown in the FRONT elevation, and every other exterior wall uses the finish shown in the REAR elevation. Do NOT create any new wall composite — pick suitable EXISTING composites from the project. Author every wall with its exterior face pointing outward (reference line on the outside).

**Revit instruction:**

> drawing1 is the ground-floor plan; drawing2 shows the front and rear elevations. Create ONLY the exterior walls from the floor plan, reading the outline and lengths from its dimension lines (walls only - ignore all doors, windows, stairs, and furniture). Choose the wall types from the elevations: the front facade uses the finish shown in the FRONT elevation, and every other exterior wall uses the finish shown in the REAR elevation. Judge which side is the front from the drawings. Do NOT create any new wall type - pick suitable EXISTING wall types from the project. Author every wall with its exterior face pointing outward. Create nothing else.

## Model Revision (3)

### C_model_editing1

- **Input:** `text-only` - **V2 template:** B07 - **was:** `B_walls8`
- **Required capabilities (ArchiCAD):** Replace Element Type (×7); Inspect Project (×1); Query Types (×1)
- **Required capabilities (Revit):** Replace Element Type (×7); Inspect Project (×1); Query Types (×1)

**ArchiCAD instruction:**

> The model's walls all use a generic wall type. Convert every exterior wall to the composite 'Double 50 Block Cavity Plastered' and every interior wall to the composite 'Brick Double Plastered'. Preserve all wall centreline geometry and do not create new composites.

**Revit instruction:**

> The model's walls all use a basic generic type. Convert every exterior wall to the wall type 'Exterior - Block on Mtl. Stud' and every interior wall to 'Interior - 79mm Partition (1-hr)'. Preserve all wall centreline geometry and do not create new wall types.

### C_model_editing2

- **Input:** `text-only` - **V2 template:** B05 - **was:** `B_walls10`
- **Required capabilities (ArchiCAD):** Move with Constraints (×3); Inspect Project (×1)
- **Required capabilities (Revit):** Move Element (×1); Move with Constraints (×3); Inspect Project (×1)

**ArchiCAD instruction:**

> The project contains a finished room layout with room labels. By moving the EXTERIOR walls only, resize two rooms: the Kitchen to 2000 mm clear width and 7.0 m2 clear area, the Living room to a square of 25.0 m2 clear area. Keep every interior wall on its existing line (trim or extend endpoints only for clean connections), keep every door and window at its position along its wall, update the room zones to the new layout, and do not create, move, or modify any room labels or wall types.

**Revit instruction:**

> The project contains a finished room layout with room labels. By moving the EXTERIOR walls only, resize two rooms: the Kitchen to 2000 mm clear width and 7.0 m2 clear area, the Livingroom to a square of 25.0 m2 clear area. Keep every interior wall on its existing line (trim or extend endpoints only for clean connections), update the rooms to the new layout, and keep the floor slab flush with the moved exterior walls' outer face. Do not create, move, or modify any room labels or wall types.

### C_model_editing3

- **Input:** `text-only` - **V2 template:** C04 - **was:** `C_openings4`
- **Required capabilities (ArchiCAD):** Replace Element Type (×5); Inspect Project (×1); Query Library (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×3); Replace Element Type (×3); Inspect Project (×1); Query Library (×1)

**ArchiCAD instruction:**

> The floorplan layout and all room labels are already created; every door is single-leaf 900 x 2100 mm. Work out which door is which and modify exactly three: the entrance door (connecting the building to the outside) becomes a Pivot Door, 300 mm wider at the same height; the bathroom door becomes a Sliding Door of unchanged size; the balcony door becomes an Exterior Double Sliding Door, as wide as it is tall at the current height.

**Revit instruction:**

> The floorplan layout and all room labels are already created; every door is single-leaf 915 x 2134 mm. Work out which door is which and modify exactly three: the entrance door (connecting the building to the outside) becomes an 'M_Door-Exterior-Double-Full Glass-Wood_Clad', 1800 x 2400 mm; the bathroom door becomes an 'M_Door-Interior-Single-2_Panel-Wood', 900 x 2100 mm; the balcony door becomes an 'M_Door-Double-Glass', as wide as it is tall at 2100 mm.

### C_model_editing4

- **Input:** `text-only` - **was:** `C_openings9`
- **Required capabilities (ArchiCAD):** Replace Element Type (×6); Inspect Project (×1); Query Library (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×3); Replace Element Type (×6); Inspect Project (×1); Query Library (×1)

**ArchiCAD instruction:**

> The floorplan layout and all room labels are already created; all windows currently share one size and type. Work out which window serves which room and replace exactly three: the bedroom window with a Horizontal Multi-Sash Window, 2100 x 1500 mm, sill 500 mm; the kitchen window with a Triple Window matching the bedroom window's width, 1200 mm high, sill 1250 mm; the living room window with a Triple Window with Side Transoms, 100 mm narrower than the others, 1500 mm high, sill 1000 mm.

**Revit instruction:**

> The floorplan layout and all room labels are already created; all windows currently share one size and type. Work out which window serves which room and replace exactly three: the bedroom window with a casement double window, 1400 x 1800 mm, sill 900 mm; the kitchen window with a four-panel sliding window, 1650 x 600 mm, sill 1250 mm; the living room window with a double-hung window, 900 mm wide and a third taller than it is wide, sill 1000 mm.

### C_model_editing5

- **Input:** `text-only` - **V2 template:** F06 - **was:** `E_cross_view4`
- **Required capabilities (ArchiCAD):** Replace Element Type (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Replace Element Type (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> The project opens in a 3D view showing two stacked floor slabs. Identify the one that does not rest on the ground and change it to the existing slab composite 'Concrete Floor Insulated with Parquet'. Preserve its footprint and top elevation, and do not alter the ground-floor slab or any other element.

**Revit instruction:**

> The project opens in a 3D view showing two stacked floor slabs. Identify the upper one and change it to the existing floor type 'Standard Timber-Wood Finish'. Preserve its footprint, top elevation, and stair opening, and do not alter the ground-floor slab or any other element.

### C_model_editing6

- **Input:** `drawing.png` - **V2 template:** G01 - **was:** `F_design_change1`
- **Required capabilities (ArchiCAD):** Create Wall (×2); Move with Constraints (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×2); Move Element (×1); Move with Constraints (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> The model in the project is already built. The attached drawing marks the required changes in red: every red line is a wall change that must be applied (a wall to add, or the new position of an existing wall). Apply exactly those changes, and update ALL related elements so the model stays consistent — not only the walls: the floor slab, the zones, and any door or window hosted on a changed wall must follow the change. Newly added walls must use the same wall type and width as the existing walls they connect to. Leave everything that is not affected untouched.

**Revit instruction:**

> The model in the project is already built. The attached drawing marks the required changes in red: every red line is a wall change that must be applied (a wall to add, or the new position of an existing wall). Apply exactly those changes, and update ALL related elements so the model stays consistent - not only the walls: the floor slab, the rooms, and any door or window hosted on a changed wall must follow the change. Newly added walls must use the same wall type and width as the existing walls they connect to. Leave everything that is not affected untouched.

### C_model_editing7

- **Input:** `drawing.png` - **V2 template:** G02 - **was:** `F_design_change2`
- **Required capabilities (ArchiCAD):** Create Wall (×1); Create Door (×1); Create Window (×1); Delete Element (×2); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×1); Create Door (×1); Create Window (×1); Delete Element (×2); Inspect Project (×1)

**ArchiCAD instruction:**

> The floorplan shown in the attached drawing has already been built in the current model. The drawing carries redline annotations marking the required design changes: every RED door, window, and wall is an element that must be ADDED to the model, and every element marked with a RED CROSS must be DELETED. Create the red elements at the marked positions — for the added door, match the swing shown in the drawing, including the hinge side and whether it opens into or out of the room — delete the crossed-out ones, and do not touch any unmarked element.

**Revit instruction:**

> The floor plan shown in the attached drawing has already been built in the current model. The drawing carries redline annotations marking the required design changes: every RED door, window, and wall is an element that must be ADDED to the model, and every element marked with a RED CROSS must be DELETED. Create the red elements at the marked positions - for the added door, match the swing shown in the drawing, including the hinge side and whether it opens into or out of the room - delete the crossed-out ones, and do not touch any unmarked element.

### C_model_editing8

- **Input:** `drawing.png` - **V2 template:** G03 - **was:** `F_design_change3`
- **Required capabilities (ArchiCAD):** Move with Constraints (×2); Inspect Project (×1)
- **Required capabilities (Revit):** Move Element (×1); Move with Constraints (×2); Inspect Project (×1)

**ArchiCAD instruction:**

> The project's walls, doors, windows, and rooms have already been built and match the attached floor plan. The drawing carries redline annotations marking the walls that must be changed. Apply exactly those wall changes, and update ALL related elements so the model stays consistent — not only the walls: the floor slab, the zones, and any door or window hosted on a changed wall must follow the change. Newly added walls must use the same wall type and width as the existing walls they connect to. Everything unmarked must remain untouched.

**Revit instruction:**

> The project's walls, doors, windows, and rooms have already been built and match the attached floor plan. The drawing carries redline annotations marking the walls that must be changed. Apply exactly those wall changes, and update ALL related elements so the model stays consistent - not only the walls: the floor slab, the rooms, and any door or window hosted on a changed wall must follow the change. Newly added walls must use the same wall type and width as the existing walls they connect to. Everything unmarked must remain untouched.

### C_model_editing9

- **Input:** `drawing.png` - **V2 template:** G04 - **was:** `F_design_change4`
- **Required capabilities (ArchiCAD):** Delete Element (×7); Inspect Project (×1)
- **Required capabilities (Revit):** Delete Element (×7); Inspect Project (×1)

**Instruction (both tools):**

> The project's layout has already been built. The attached drawing shows the required design changes as annotations. Read the drawing and apply exactly those changes to the model. Everything unmarked must remain untouched.

### C_model_editing10

- **Input:** `text-only` - **V2 template:** G05 - **was:** `F_design_change5`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Move Element (×1); Replace Element Type (×5); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Replace Element Type (×16); Inspect Project (×1)

**ArchiCAD instruction:**

> The two-storey project is already built. Change the storey heights: the ground floor becomes 2750 mm and the first floor 3500 mm. Raise the first-floor slab to sit 300 mm ABOVE the new first-storey level, and raise every first-floor window's sill by 300 mm relative to its storey (1000 -> 1300 mm). Ground-floor elements keep their storey-relative positions; do not move, add, or delete anything else.

**Revit instruction:**

> The two-storey project has already been built. The ground floor's height up to Level 2 becomes 2750 mm and the second storey's wall height becomes 3500 mm. Raise every ground-floor (Level 1) window's sill height by 300 mm relative to its storey; the second-storey windows keep their sills. Do not move, add, or delete anything else.

### C_model_editing11

- **Input:** `text-only` - **V2 template:** G06 - **was:** `F_design_change6`
- **Required capabilities (ArchiCAD):** Create Window (×1); Move with Constraints (×1); Replace Element Type (×3); Inspect Project (×1); Query Library (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×1); Create Window (×1); Move Element (×1); Move with Constraints (×1); Replace Element Type (×2); Inspect Project (×1); Query Library (×1)

**ArchiCAD instruction:**

> Execute this combined client change on the single-storey model: enlarge the Bedroom by moving its west wall 1500 mm further west, handling the knock-on effects so the floor slab, the zone boundaries, and every element attached to the moved wall follow; replace the Bedroom's 900 mm swing door with a sliding door 600 mm wider at the same position and height; add a window in the Bedroom's south exterior wall, 1800 mm wide with 2.7 m2 of glass, anywhere along it; and rename the Bedroom zone to 'Accessible Bedroom'. Leave everything else untouched.

**Revit instruction:**

> Execute this combined client change on the single-storey model: enlarge the Bedroom by moving its west wall 1500 mm further west, handling the knock-on effects so the floor slab, the room boundaries, and every element attached to the moved wall follow; replace the Bedroom's 915 mm swing door with a 1500 x 2100 mm 'M_Door-Interior-Double-Sliding-2_Panel-Wood' at the same position; add a window of any type in the Bedroom's south exterior wall, 1800 mm wide with 2.7 m2 of glass, anywhere along it; and rename the Bedroom to 'Accessible Bedroom'. Leave everything else untouched.

## Model Completion (4)

### D_model_completion1

- **Input:** `drawing.png` - **V2 template:** B04 - **was:** `B_walls6`
- **Required capabilities (ArchiCAD):** Create Wall (×6); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×7); Inspect Project (×1)

**ArchiCAD instruction:**

> The floorplan drawing is the target layout; most walls already exist in the project. Create only the missing wall segments so the model matches the drawing. Reuse the composites already in use: exterior segments get the existing exterior-wall composite, interior segments the existing interior-wall composite. Do not create new composites. Author exterior segments with their outer finish facing outward.

**Revit instruction:**

> The floorplan drawing is the target layout; most walls already exist in the project. Create only the missing wall segments so the model matches the drawing. Reuse the wall types already in use: exterior segments get the existing exterior wall type, interior segments the existing interior wall type. Do not create new wall types.

### D_model_completion2

- **Input:** `drawing.png` - **was:** `I_long_sequence3`
- **Required capabilities (ArchiCAD):** Load Library Element Type (×2); Create Wall (×15); Create Slab (×1); Create Slab Opening (×1); Create Door (×5); Create Window (×2); Inspect Project (×1); Query Types (×1)
- **Required capabilities (Revit):** Load Library Element Type (×2); Create Wall (×15); Create Slab (×1); Create Slab Opening (×1); Create Door (×5); Create Window (×2); Inspect Project (×1); Query Types (×1)

**Instruction (both tools):**

> The ground floor (shown on the right) is already created in the project. Create the upper floor from the floorplan on the left: all exterior and interior walls, doors, windows, and the floor slab, matching the layout, positions, and connections shown. Reuse the wall, door, window, and slab types already used on the ground floor. Do not create or modify any types, and do not alter the ground floor.

### D_model_completion3

- **Input:** `drawing.png` - **V2 template:** C02 - **was:** `C_openings2`
- **Required capabilities (ArchiCAD):** Create Door (×5); Inspect Project (×1)
- **Required capabilities (Revit):** Create Door (×5); Inspect Project (×1)

**ArchiCAD instruction:**

> The walls in this floorplan are already built. Add the doors so the model matches the drawing: place every door the plan shows, each a single-leaf 900 × 2100 mm door. Judge each door's host wall and position along that wall from the plan, and set its swing (hinge side + opening direction) to match the arc drawn. The plan has no dimensions, so roughly correct positions are fine.

**Revit instruction:**

> The walls in this floorplan are already built. Add the doors so the model matches the drawing: place every door the plan shows, each a single-flush 915 × 2134 mm door. Judge each door's host wall and position along that wall from the plan, and set its swing (hinge side + opening direction) to match the arc drawn. The plan has no dimensions, so roughly correct positions are fine.

### D_model_completion4

- **Input:** `drawing.png` - **V2 template:** C05 - **was:** `C_openings5`
- **Required capabilities (ArchiCAD):** Create Window (×3); Inspect Project (×1)
- **Required capabilities (Revit):** Load Library Element Type (×1); Create Window (×3); Inspect Project (×1); Query Library (×1)

**ArchiCAD instruction:**

> The walls in this floorplan drawing are already built. Add the windows so the model matches the drawing exactly: place every window the plan shows; host each window on its correct wall, and make its position and size match the drawing. Do not touch the walls.

**Revit instruction:**

> The walls in this floorplan drawing are already built. Add the windows so the model matches the drawing: place every window the plan shows, hosting each on its correct wall. Use the 'M_Window-Casement-Triple-Side-Transom' window family and choose a suitable type size yourself so that each window's width and position roughly match the drawing; set every sill height to 900 mm. Do not touch the walls.

### D_model_completion5

- **Input:** `drawing.png` - **was:** `C_openings6`
- **Required capabilities (ArchiCAD):** Create Door (×4); Inspect Project (×1); Query Library (×1)
- **Required capabilities (Revit):** Load Library Element Type (×2); Create Door (×4); Inspect Project (×1); Query Library (×1)

**ArchiCAD instruction:**

> The walls in the floorplan are already built. Add all doors shown, without creating, moving, or modifying any walls. Use single-leaf 900 × 2100 mm doors where the plan shows a single door and double-leaf 1800 × 2100 mm doors where it shows a double door. Judge each door's host wall and approximate position from the drawing; exact positions are not required. Match the swing arc shown, including the hinge side and whether the door opens into or out of the room. Do not add extra doors.

**Revit instruction:**

> The walls in the floorplan are already built. Add all doors shown, without creating, moving, or modifying any walls. Use single-leaf 915 mm wide doors where the plan shows a single door and double-leaf 1700 mm wide doors where it shows a double door. Judge each door's host wall and approximate position from the drawing; exact positions are not required. Match the swing arc shown, including the hinge side and whether the door opens into or out of the room. Do not add extra doors.

### D_model_completion6

- **Input:** `drawing.png` - **was:** `D_slabs_stairs_rooms5`
- **Required capabilities (ArchiCAD):** Create Slab (×1); Create Slab Opening (×1); Create Stair (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Slab (×1); Create Slab Opening (×1); Create Stair (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> The drawing shows a two-storey building; both floors, with the same layout, are already created in the project, but no stair exists yet. Create the stair connecting the ground floor and the first floor: match the location, orientation, and run direction shown in the drawing, and make it start and end at the correct storey levels with valid connections to both floors. Then create the upper floor's slab using the existing slab composite 'Concrete Floor with 10mm Tile', following the exterior-wall footprint, with its reference plane set to Core Top positioned at the second storey level, and cut an opening in it where the stair passes through. Do not modify the existing walls.

**Revit instruction:**

> The drawing shows a two-storey building; both floors, with the same layout, are already created in the project, but no stair exists yet. Create the stair connecting the ground floor and the first floor: match the location, orientation, and run direction shown in the drawing, and make it start and end at the correct storey levels with valid connections to both floors. Then create the upper floor's slab using the existing floor type 'Standard Timber-Wood Finish', following the exterior-wall footprint, and cut an opening in it where the stair passes through. Do not modify the existing walls.

### D_model_completion7

- **Input:** `drawing.png` - **was:** `I_long_sequence3`
- **Required capabilities (Revit):** Create Wall (×11); Create Slab (×1); Create Slab Opening (×1); Create Door (×2); Create Window (×4); Inspect Project (×1); Query Types (×1); Query Library (×1)
- **Status:** Revit only

**Instruction (both tools):**

> The ground floor (shown on the left) is already created in the project. Create the upper floor from the floorplan on the right: all exterior and interior walls, doors, windows, and the floor slab, matching the layout, positions, and connections shown. Reuse the wall, door, window, and slab types already used on the ground floor. Do not create or modify any types, and do not alter the ground floor.

### D_model_completion8

- **Input:** `drawing.png` - **was:** `I_long_sequence3`
- **Required capabilities (Revit):** Create Wall (×5); Create Slab (×1); Create Door (×6); Create Window (×3); Move Element (×1); Inspect Project (×1); Query Types (×1); Query Library (×1)
- **Status:** Revit only

**Instruction (both tools):**

> The apartment shown in the floorplan is only partly modelled in the project. Complete it: add every wall, door, window, and floor slab that is still missing, matching the layout, positions, and connections shown in the drawing. Match what is already built — reuse the wall, door, window, and slab types already present in the project,. Do not create or modify any types, and do not change or delete what is already correctly built. Door and window sizes are not critical - the default size of the matching family is fine.

## Model Checking (5)

### E_model_checking1

- **Input:** `text-only` - **V2 template:** B08 - **was:** `B_walls9`
- **Required capabilities (ArchiCAD):** Flip Element (×4); Inspect Project (×1)
- **Required capabilities (Revit):** Flip Element (×4); Inspect Project (×1)

**ArchiCAD instruction:**

> The project has six exterior walls, all using the same exterior wall composite whose brick layers must face OUTSIDE. Some of them are mounted reversed. Find out which walls are flipped and turn them around so every outer brick layer faces outdoors. Keep all wall positions unchanged and do not touch the correctly oriented walls.

**Revit instruction:**

> The project has six exterior walls, all using the same asymmetric exterior wall type whose render and insulation layers must face OUTSIDE. Some of them are mounted reversed. Find out which walls are flipped and turn them around so every outer layer faces outdoors. Keep all wall positions unchanged and do not touch the correctly oriented walls.

### E_model_checking2

- **Input:** `text-only` - **V2 template:** F07 - **was:** `E_cross_view5`
- **Required capabilities (ArchiCAD):** Move Element (×1); Inspect Project (×1); Check Clash (×1)
- **Required capabilities (Revit):** Move Element (×3); Inspect Project (×1); Check Clash (×1)

**ArchiCAD instruction:**

> The project opens in a 3D view in which one of the windows is clearly wrong. Diagnose the problem and repair it, keeping the window's type and size. Do not modify any walls, and leave the correct openings untouched.

**Revit instruction:**

> The project opens in a 3D view in which some of the windows are clearly wrong. Diagnose what the problems are and repair them, keeping every window's type and size. Do not modify any walls, and leave the correct openings untouched.

### E_model_checking3

- **Input:** `text-only` - **V2 template:** F08 - **was:** `E_cross_view6`
- **Required capabilities (ArchiCAD):** Replace Element Type (×4); Inspect Project (×1)
- **Required capabilities (Revit):** Replace Element Type (×12); Inspect Project (×1)

**Instruction (both tools):**

> The project opens in a 3D view. The wall heights are visibly inconsistent. Unify all walls to a height of 3000 mm, keeping every wall's plan position unchanged.

### E_model_checking4

- **Input:** `text-only` - **was:** `E_cross_view7`
- **Required capabilities (ArchiCAD):** Switch Active Story (×1); Move Element (×3); Inspect Project (×1)
- **Required capabilities (Revit):** Switch Active Story (×1); Move Element (×5); Inspect Project (×1)

**ArchiCAD instruction:**

> The building's ground floor and upper floor are both already built, but their exterior-wall outlines currently differ. Adjust the UPPER floor's exterior walls — move them, and add wall segments where necessary — so its outline matches the ground floor's outline exactly. Do not modify any ground-floor element, and keep the upper floor's interior walls unchanged.

**Revit instruction:**

> The building's ground floor and upper floor are both already built, but their exterior-wall outlines currently differ. Adjust the UPPER floor's exterior walls - move them, and add wall segments where necessary - so its outline matches the ground floor's outline exactly. Do not modify any ground-floor element, and keep the upper floor's interior walls unchanged.

### E_model_checking5

- **Input:** `text-only` - **V2 template:** H01 - **was:** `G_model_check1`
- **Required capabilities (ArchiCAD):** Move Element (×8); Inspect Project (×1)
- **Required capabilities (Revit):** Move Element (×3); Inspect Project (×1)

**ArchiCAD instruction:**

> The Bathroom and Bedroom zones are not fully enclosed by their walls. Repair each broken wall into ONE continuous straight wall — merge fragmented or offset collinear segments instead of leaving a wall assembled from several pieces.

**Revit instruction:**

> The Bathroom room and the Bedroom room are not enclosed. Fix the model so both rooms become enclosed.

### E_model_checking6

- **Input:** `drawing.png` - **V2 template:** H02 - **was:** `G_model_check2`
- **Required capabilities (ArchiCAD):** Create Wall (×1); Create Door (×2); Create Window (×1); Move Element (×1); Delete Element (×1); Inspect Project (×1); Query Library (×2)
- **Required capabilities (Revit):** Create Door (×1); Create Window (×1); Move Element (×2); Inspect Project (×1); Query Library (×1)

**ArchiCAD instruction:**

> The attached drawing shows the intended layout. Correct every wall, door and window that does not match it — including each door's position, size, opening direction, and hinge side. Leave everything that already matches untouched.

**Revit instruction:**

> The attached drawing shows the intended layout. Some doors, windows, and walls in the current model do not match it. Compare the model against the drawing and correct the walls, doors, and windows so they match the drawing - including each door's position, size, opening direction, and hinge side. Leave everything that already matches untouched.

### E_model_checking7

- **Input:** `text-only` - **V2 template:** H03 - **was:** `G_model_check3`
- **Required capabilities (ArchiCAD):** Flip Element (×5); Inspect Project (×1); Check Clash (×1)
- **Required capabilities (Revit):** Flip Element (×4); Inspect Project (×1); Check Clash (×1)

**Instruction (both tools):**

> Many doors in the current project have obvious clashes. Check which doors are clashing, and resolve the clashes by flipping the door swing direction.

### E_model_checking8

- **Input:** `text-only` - **V2 template:** H04 - **was:** `G_model_check4`
- **Required capabilities (ArchiCAD):** Move Element (×8); Inspect Project (×1)
- **Required capabilities (Revit):** Move Element (×6); Inspect Project (×1)

**Instruction (both tools):**

> All walls in the layout are supposed to be horizontal or vertical. Find the skewed walls and straighten them so every wall runs exactly horizontal or vertical, without adding or removing walls.

### E_model_checking9

- **Input:** `text-only` - **V2 template:** I01 - **was:** `G_model_check5`
- **Required capabilities (ArchiCAD):** Move Element (×5); Inspect Project (×1); Check Clash (×1)
- **Required capabilities (Revit):** Replace Element Type (×6); Inspect Project (×1); Query Types (×1)

**ArchiCAD instruction:**

> Many doors and windows in the current model are not attached to any wall. Find these detached doors and windows, and attach each of them to its nearest wall.

**Revit instruction:**

> The project's walls and rooms have already been created, but every internal wall currently uses the most generic wall type. Based on the uses of the rooms on both sides of each partition, infer the acoustic, moisture, or fire performance it requires, and assign the matching wall type - reuse the wall types that already exist in the project, do not create new ones. Preserve all wall centrelines and room boundaries.

### E_model_checking10

- **Input:** `text-only` - **V2 template:** I01 - **was:** `H_domain_reasoning1`
- **Required capabilities (ArchiCAD):** Replace Element Type (×9); Inspect Project (×1); Query Types (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> The project's walls and rooms have already been created, but every internal wall currently uses the most generic wall composite. Based on the uses of the rooms on both sides of each partition, infer the performance requirements and assign the matching composite for internal walls - reuse the composites that already exist in the project, do not create new ones. Preserve all wall centrelines and room boundaries.

**Revit instruction:**

> Create an external load-bearing wall type for a heated room consisting of: 10 mm external render, lambda = 0.70 W/(m*K); 240 mm sand-lime masonry, lambda = 0.99 W/(m*K); 10 mm internal plaster, lambda = 0.70 W/(m*K). Use Rse = 0.04 m2*K/W and Rsi = 0.13 m2*K/W. Add a mineral-wool insulation layer between the sand-lime masonry and the external render; mineral wool has lambda = 0.040 W/(m*K). Select the minimum insulation thickness that satisfies U <= 0.30 W/(m2*K).

### E_model_checking11

- **Input:** `text-only` - **V2 template:** I02 - **was:** `H_domain_reasoning2`
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×1); Move with Constraints (×1); Replace Element Type (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> Create an external load-bearing wall composite for a heated room consisting of: 10 mm external render, lambda = 0.70 W/(m*K); 240 mm sand-lime masonry, lambda = 0.99 W/(m*K); 10 mm internal plaster, lambda = 0.70 W/(m*K). Use Rse = 0.04 m2*K/W and Rsi = 0.13 m2*K/W. Add a mineral-wool insulation layer between the sand-lime masonry and the external render; mineral wool has lambda = 0.040 W/(m*K). Select the minimum insulation thickness that satisfies U <= 0.30 W/(m2*K).

**Revit instruction:**

> The layout has an entrance door, a corridor, a waiting area, and a destination room, but parts of the circulation space are undersized and noncompliant with the accessibility standards for wheelchair users. Check the continuous accessible route and fix them - modify only the noncompliant spots. Where a space is undersized, fix it by moving the internal walls (the room areas may change accordingly).

### E_model_checking12

- **Input:** `text-only` - **V2 template:** I04 - **was:** `H_domain_reasoning3`
- **Required capabilities (ArchiCAD):** Move with Constraints (×1); Replace Element Type (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Move with Constraints (×4); Inspect Project (×1)

**ArchiCAD instruction:**

> The layout has an entrance door, a corridor, a waiting area, and a destination room, but parts of the circulation space are undersized and noncompliant with the accessibility standards for wheelchair users. Check the continuous accessible route and fix them - modify only the noncompliant spots. Where a space is undersized, fix it by moving the internal walls (the room areas may change accordingly).

**Revit instruction:**

> A dwelling floor plan for a three-person household has already been created in the project. Bedroom 01 is the parents' bedroom, bedroom 02 is the child's bedroom. Check whether the room sizes are reasonable. If a room is undersized, resize it by MOVING the interior walls and update the rooms accordingly.

### E_model_checking13

- **Input:** `text-only` - **V2 template:** I05 - **was:** `H_domain_reasoning4`
- **Required capabilities (ArchiCAD):** Move with Constraints (×3); Inspect Project (×1)
- **Required capabilities (Revit):** Move with Constraints (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> A dwelling floor plan for a three-person household has already been created in the project. Bedroom 01 is the parents' bedroom, bedroom 02 is the child's bedroom. Check whether the room sizes are reasonable. If a room is undersized, resize it by MOVING the interior walls and update the zones accordingly.

**Revit instruction:**

> A student-residence floor plan has already been created in the project. Check whether the students' living areas are reasonable; if not, adjust the interior walls to correct the room areas.

### E_model_checking14

- **Input:** `text-only` - **V2 template:** I07 - **was:** `H_domain_reasoning5`
- **Required capabilities (ArchiCAD):** Move with Constraints (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×3); Create Room/Zone (×4); Inspect Project (×1)

**ArchiCAD instruction:**

> A student-residence floor plan has already been created in the project. Check whether the students' living areas are reasonable; if not, adjust the interior walls to correct the room areas.

**Revit instruction:**

> An office floor plan has already been created in the project: a Group Office and, beside it, an empty strip enclosed by the existing walls. Subdivide the empty strip by creating interior walls into two single offices and one double office, sized to the standard minimum office dimensions, and let the remaining space be a storage room. Create the matching rooms, named 'Single office', 'Double office' and 'Storage'. Leave the Group Office and the existing walls untouched.

### E_model_checking15

- **Input:** `text-only` - **V2 template:** I09 - **was:** `H_domain_reasoning7`
- **Required capabilities (ArchiCAD):** Create Wall (×3); Create Room/Zone (×4); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall Type (×1); Replace Element Type (×6); Inspect Project (×1); Query Materials (×1)

**ArchiCAD instruction:**

> An office floor plan has already been created in the project: a Group Office and, beside it, an empty strip enclosed by the existing walls. Subdivide the empty strip with new interior walls into two single offices and one double office at the standard minimum office dimensions; the leftover space becomes the storage room. Create the matching zones, named 'Single office', 'Double office' and 'Storage'. Leave the Group Office and the existing walls untouched.

**Revit instruction:**

> All exterior walls currently use an uninsulated wall type whose single layer is 300 mm reinforced concrete. Upgrade the building envelope to achieve U <= 0.20 W/(m2*K) by adding a layer of mineral-wool insulation on the exterior face of the reinforced-concrete core. Use the following thermal data: mineral wool lambda = 0.035 W/(m*K) and reinforced concrete lambda = 2.30 W/(m*K). Use Rsi = 0.13 m2*K/W and Rse = 0.04 m2*K/W. Insulation boards are available only in 10 mm increments from 100 mm to 200 mm. Select the thinnest available board that satisfies the target U-value. Create a new wall type named 'External Wall EW-U020'. The completed wall build-up should be suitable for normal exterior exposure, using an appropriate existing project material to protect the insulation as the outer finish. Assign the new wall type to all exterior walls. Do not modify any internal partitions, wall geometry, wall location lines, openings, heights, or constraints.

### E_model_checking16

- **Input:** `text-only` - **V2 template:** I10 - **was:** `H_domain_reasoning8`
- **Required capabilities (ArchiCAD):** Create Wall Type (×1); Replace Element Type (×6); Inspect Project (×1); Query Materials (×1)
- **Required capabilities (Revit):** Replace Element Type (×3); Inspect Project (×1)

**ArchiCAD instruction:**

> All exterior walls currently use the uninsulated composite 'Existing External Wall 225'. Its skins, from exterior to interior, are: 10 mm 'Plaster - Lime Sand', 200 mm 'Reinforced Concrete - Structural', and 15 mm 'Plaster - Gypsum'. Upgrade the building envelope to achieve U <= 0.20 W/(m2*K) by adding a layer of 'Insulation - Mineral Soft' between the reinforced-concrete core and the external render. Use the following thermal data: 'Insulation - Mineral Soft' lambda = 0.035 W/(m*K), 'Plaster - Lime Sand' lambda = 1.00 W/(m*K), 'Reinforced Concrete - Structural' lambda = 2.30 W/(m*K), and 'Plaster - Gypsum' lambda = 0.51 W/(m*K). Use Rsi = 0.13 m2*K/W and Rse = 0.04 m2*K/W. Insulation boards are available only in 10 mm increments from 100 mm to 200 mm. Calculate the required insulation thickness and select the thinnest available board that satisfies the target U-value. Create a new composite named 'External Wall EW-U020' with the correct skin order and assign it to all exterior walls. Set 'Reinforced Concrete - Structural' as the structural core. Do not modify any internal partitions, wall geometry, wall reference lines, openings, heights, or constraints.

**Revit instruction:**

> Check whether every wall-enclosed space in the project (whether or not a room element is placed in it) complies with the daylight requirement for habitable rooms: the window area must be at least 1/8 of the floor area. Judge EACH window: if its room is non-compliant, resize that window so the room complies, keeping the existing sill height and window position. Do not modify the walls, the rooms, or anything else.

### E_model_checking17

- **Input:** `text-only` - **V2 template:** I11 - **was:** `H_domain_reasoning9`
- **Required capabilities (ArchiCAD):** Replace Element Type (×3); Inspect Project (×1)
- **Status:** ArchiCAD only

**Instruction (both tools):**

> Check whether every wall-enclosed space in the project (whether or not a room element is placed in it) complies with the daylight requirement for habitable rooms: the window area must be at least 1/8 of the floor area. Judge EACH window: if its room is non-compliant, resize that window so the room complies, keeping the existing sill height and window position. Do not modify the walls, the zones, or anything else.

## End-to-End Modeling (6)

### F_end_to_end1

- **Input:** `text-only` - **was:** `I_long_sequence1`
- **Required capabilities (ArchiCAD):** Create Wall (×11); Create Slab (×1); Create Door (×5); Create Window (×4); Inspect Project (×1)
- **Required capabilities (Revit):** Create Wall (×11); Create Slab (×1); Create Door (×5); Create Window (×4); Inspect Project (×1)

**ArchiCAD instruction:**

> Create the exterior walls with a Generic Wall as one closed loop: (0,11150) → (11825,11150) → (11825,0) → (5625,0) → (5625,4725) → (0,4725) → (0,11150). Create these interior walls with any existing interior wall type: (7350,5100) → (11825,5100); (7350,3400) → (8975,3400); (1575,11150) → (1575,4725); (7350,11150) → (7350,0); (8975,3400) → (8975,0). Add five 900 × 2100 mm single doors at (7350,7300), (1575,6400), (7350,1975), (7350,4200), (6525,0) and four 900 × 1500 mm standard windows at (0,7950), (1575,8750), (11825,7925), (11825,2725), each opening hosted by the wall at its position. Create one generic slab covering the complete exterior-wall footprint. Create nothing else.

**Revit instruction:**

> Create the exterior walls with a Generic/Basic Wall as one closed loop: (0,11150) → (11825,11150) → (11825,0) → (5625,0) → (5625,4725) → (0,4725) → (0,11150). Create these interior walls with any existing interior wall type: (7350,5100) → (11825,5100); (7350,3400) → (8975,3400); (1575,11150) → (1575,4725); (7350,11150) → (7350,0); (8975,3400) → (8975,0). Add five 900 × 2100 mm single doors at (7350,7300), (1575,6400), (7350,1975), (7350,4200), (6525,0) and four 900 × 1500 mm standard windows at (0,7950), (1575,8750), (11825,7925), (11825,2725), each opening hosted by the wall at its position. Create one generic slab covering the complete exterior-wall footprint. Create nothing else.

### F_end_to_end2

- **Input:** `text-only` - **was:** `I_long_sequence2`
- **Required capabilities (ArchiCAD):** Switch Active Story (×1); Create Wall (×28); Create Slab (×2); Create Slab Opening (×1); Create Door (×8); Create Window (×6); Create Stair (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Switch Active Story (×1); Create Wall (×28); Create Slab (×2); Create Slab Opening (×1); Create Door (×8); Create Window (×6); Create Stair (×1); Inspect Project (×1)

**Instruction (both tools):**

> Create this two-storey building using any suitable existing types. Exterior walls, one closed outline: (0,10725) → (7750,10725) → (7750,9075) → (11950,9075) → (11950,2725) → (7625,2725) → (7625,0) → (0,0) → (0,10725). Interior walls: (0,4800) → (4125,4800); (0,2775) → (4350,2775); (4125,10725) → (4125,4800); (2300,4800) → (2300,2775); (5225,1700) → (5225,0); (4350,2775) → (5225,1700). Windows at (2150,10725), (6400,10725), (10400,9075) and doors at (3275,4800), (2300,3875), (4764,2266), (6525,0), (8400,9075), each opening hosted by the wall at its position. Repeat the full layout on BOTH storeys, except that a door in an exterior wall only makes sense at grade - place exterior-wall doors on the ground floor only. Create one slab per storey following the exterior-wall footprint, keeping the upper slab clear where the stair rises. Place one stair in the east wing (the part of the plan east of x = 7750), rising from the ground storey to the first, sized and oriented to fit. Storey levels and heights may be any suitable values.

### F_end_to_end3

- **Input:** `drawing.png` - **was:** `I_long_sequence4`
- **Required capabilities (ArchiCAD):** Create Wall (×18); Create Slab (×1); Create Door (×7); Create Window (×11); Replace Element Type (×5); Inspect Project (×1); Query Types (×1)
- **Required capabilities (Revit):** Create Door/Window Type (×3); Create Wall (×18); Create Slab (×1); Create Door (×7); Create Window (×11); Replace Element Type (×11); Inspect Project (×1); Query Types (×1)

**Instruction (both tools):**

> Based on the provided dimensioned floorplan, create the complete single-storey building: all walls, doors, windows, and the floor slab. IMPORTANT: judge each wall's construction type from how it is represented in the drawing (hatch/fill pattern of its section) - not all walls use the same type - and create every wall with the matching wall type. Place doors and windows at the positions and sizes read from the drawing. Ignore all furniture.

### F_end_to_end4

- **Input:** `text-only` - **was:** `I_long_sequence5`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Switch Active Story (×2); Create Wall (×33); Create Slab (×3); Create Slab Opening (×2); Create Door (×10); Create Window (×6); Create Stair (×2); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Switch Active Story (×2); Create Wall (×33); Create Slab (×3); Create Slab Opening (×2); Create Door (×10); Create Window (×6); Create Stair (×2); Inspect Project (×1)

**Instruction (both tools):**

> Create this three-storey building using any suitable existing types. Exterior walls, one closed outline: (0,8280) → (8920,8280) → (8920,3020) → (7560,3020) → (7560,0) → (0,0) → (0,8280). Interior walls: (4480,4320) → (4480,8280); (0,3020) → (5380,3020); (2940,1400) → (5380,1400); (2940,3020) → (2940,1400); (5380,3020) → (5380,0). Windows (900 × 1500 mm, sill 1000 mm) at (6460,8280) and (0,1460); doors (900 × 2100 mm) at (720,8280), (2280,3020), (5380,2400), (5380,790), each opening hosted by the wall at its position. Repeat the full layout on ALL THREE storeys, except that a door in an exterior wall only makes sense at grade - place exterior-wall doors on the ground floor only. Create one slab per storey following the exterior-wall footprint, keeping the upper slabs clear where the stairs rise. Create stairs connecting the ground floor to the first and the first to the second, each fitting inside the east strip of the plan (east of x = 7560). Use any suitable and consistent storey levels and heights.

### F_end_to_end5

- **Input:** `drawing.png` - **was:** `I_long_sequence6`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Switch Active Story (×1); Create Wall (×18); Create Slab (×2); Create Slab Opening (×1); Create Door (×10); Create Window (×6); Create Stair (×1); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Switch Active Story (×1); Create Wall (×18); Create Slab (×2); Create Slab Opening (×1); Create Door (×10); Create Window (×6); Create Stair (×1); Inspect Project (×1)

**ArchiCAD instruction:**

> Create this two-storey building on both storeys using any suitable existing types. The attached drawing shows the complete floorplan; some walls are deliberately not listed below — infer their positions from the drawing. Create the exterior walls as one closed outline following the drawing; two of its runs are (0,6600) → (9140,6600) → (9140,0); complete the remaining outline segments from the drawing. Create these interior walls: (6640,3300) → (9140,3300); (3400,2120) → (6640,2120); (6640,2120) → (6640,6600); (7860,3300) → (7860,0); plus the remaining interior wall shown in the drawing. Add windows at (5000,6600), (2520,6600), and (7940,6600), and doors at (1260,6600), (7242,3300), (6100,2120), (7860,1600), (3400,1500), and (7240,0), each hosted by the corresponding wall. On the first floor, do not place any doors in the exterior walls. Create one slab per storey following the exterior-wall footprint. Finally, create a stair with its bottom-left point starting near (330,2120), rising from the ground floor to the first floor, fitting the available space. Build the same wall layout and windows on BOTH storeys. Set exactly three storey levels: 0, 3000 and 7000 mm (ground-floor height 3000 mm, first-floor height 4000 mm).

**Revit instruction:**

> Create this two-storey building on both storeys using any suitable existing types. The attached drawing shows the complete floor plan; some walls are deliberately not listed below — infer their positions from the drawing. Create the exterior walls as one closed outline following the drawing; two of its runs are (0,6600) → (9140,6600) → (9140,0); complete the remaining outline segments from the drawing. Create these interior walls: (6640,3300) → (9140,3300); (3400,2120) → (6640,2120); (6640,2120) → (6640,6600); (7860,3300) → (7860,0); plus the remaining interior wall shown in the drawing. Add windows at (5000,6600), (2520,6600), and (7940,6600), and doors at (1260,6600), (7242,3300), (6100,2120), (7860,1600), (3400,1500), and (7240,0), each hosted by the corresponding wall. On the first floor, do not place any doors in the exterior walls. Create one slab per storey following the exterior-wall footprint. Finally, create a stair with its bottom-left point starting near (330,2120), rising from the ground floor to the first floor, fitting the available space. Build the same wall layout and windows on BOTH storeys. Set exactly three storey levels: 0, 3000 and 7000 mm (ground-floor height 3000 mm, first-floor height 4000 mm).

### F_end_to_end6

- **Input:** `drawing.pdf` - **was:** `I_long_sequence7`
- **Required capabilities (ArchiCAD):** Create Stories (×1); Switch Active Story (×2); Create Wall (×32); Create Slab (×3); Create Slab Opening (×2); Create Door (×14); Create Window (×11); Create Stair (×2); Inspect Project (×1)
- **Required capabilities (Revit):** Create Stories (×1); Switch Active Story (×2); Create Wall (×32); Create Slab (×3); Create Slab Opening (×2); Create Door (×14); Create Window (×11); Create Stair (×2); Inspect Project (×1)

**ArchiCAD instruction:**

> Based on the provided floorplan, section view, and elevation view, create the corresponding BIM model in the software. Model all required walls, floors/slabs, doors, windows, stairs, storeys. Use the section and elevation views to set the correct levels, heights, and vertical dimensions. Ignore the roof and all furniture.

**Revit instruction:**

> Based on the provided floorplan, section view, and elevation view, create the corresponding BIM model in the software. Model all required walls, floors/slabs, doors, windows, stairs, storeys. Use the section and elevation views to set the correct levels, heights, and vertical dimensions. Ignore the roof and all furniture. Create the stair as one straight flight per storey: ground floor -> first floor and first floor -> second floor (two stair elements).
