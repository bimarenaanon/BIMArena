---
name: clash_check
description: Detect geometric conflicts in a Revit model — judge from screenshots per the defect rules; Run Interference Check (Collaborate tab) only for candidates the screenshots leave uncertain.
software: Revit
---

# Check for clashes (capability)

**SCREENSHOTS FIRST**: run the visual plan pass and reach a verdict per candidate (clash /
clean, by defect number) from what the view shows — that verdict is the result. Only a
candidate the screenshots genuinely cannot settle (typically a subtle solid intersection) is
escalated to **Interference Check**, and only for that candidate. The tool can never replace
the visual pass: it reports SOLID INTERSECTIONS ONLY — a duplicate wall that doesn't
intersect, an opening past its host's end, or an opening straddling a junction may not
appear, so an empty report is NOT a clean model. Record the whole defect list before fixing
anything, and re-check after any model change.

## The defects and their screen signatures
**Walls**
1. **Bodies intersecting** — a wall runs THROUGH another instead of a clean junction (the one
   Interference Check reports most reliably).
2. **Duplicate (coincident) walls** — near-parallel, same location; at close zoom: doubled
   edges or a persistent hairline. Reliable test: select one wall and see what stays visible
   beside/under it.
3. **Isolated wall** — a free-floating stub from a mis-snapped endpoint (a defect only where
   the model should connect to it).

**Doors / windows**
4. **Hanging off the wall end** — the span runs past the host's endpoint.
5. **Overlapping another opening** — two spans on one host intrude into each other.
6. **Cut by a crossing wall** — a DIFFERENT wall's body crosses the span.

**Stairs**
7. **Stair through a wall** — the flight/landing footprint runs into a wall body in plan;
   the solid intersection shows up in an Interference Check with the Stairs and Walls
   categories ticked.

## What is NOT a clash
> ⚠️ An opening inside its OWN host is correct (Revit cuts the host); only a DIFFERENT wall is
> defect 6. Revit openings always HAVE a host — don't hunt for floating ones.
> ⚠️ A stair on its own floor is expected. Same footprint on another level ≠ duplicate. A
> clean corner/T is a junction, not defect 1.

## Recipe — visual pass (the primary judgment)
1. **Walls, per level's plan:** walk every junction (through-running vs clean corner — 1),
   every long wall at close zoom (doubled edges / hairline — 2; select-and-look to confirm),
   every endpoint (stub — 3). Don't diagnose a duplicate from whole-plan zoom — annotation,
   underlay or a joined edge mimics one.
2. **Openings, per host wall:** `zoom-gently` until jambs + host endpoint + junctions are
   readable; span past the host end (4)? another span intruding (5)? a crossing wall (6)?
   Tags/swing graphics touching ≠ overlap. Screenshot each candidate with the conflicting
   geometry in frame.
3. **Stairs, per level's plan:** `zoom-gently` at each stair until its footprint edges and
   the nearby walls are readable — the flight/landing must stop clear of every wall body (7).
4. **Verdict per candidate:** clash (defect number + elements + location) or clean. A
   candidate the screenshots cannot settle at close zoom — typically a possible solid
   intersection (1, 7) — goes on the escalation list for the Interference Check below;
   everything else is decided here.

## Recipe — Interference Check (only for the escalation list)
Run this ONLY when the visual pass left candidates uncertain — never as the first move, and
never let an empty report overturn a clash the screenshots clearly showed.
0. Leave any active mode first (`finish-sketch`/`cancel-sketch`, Esc until nothing waits;
   `focus-canvas` if the ribbon holds focus). The check dialogs are modal — close them before
   any edit.
1. **Collaborate tab > Coordinate panel > Interference Check > Run Interference Check** — the
   category dialog opens (two category lists).
2. Tick the categories the uncertain candidates involve (e.g. Walls vs Walls, Stairs vs
   Walls) → click **OK** (not Enter — focus in a list makes Enter move the selection).
3. **Read the result dialog:** screenshot it FIRST; then per row: select the row → **Show**
   (highlights the pair in the view) → record elements + location. A row of an opening vs its
   OWN host is expected — skip it. No rows = clean for SOLID intersections only — it clears
   the escalated candidates, nothing else.
4. **Close** the report, then correct via the edit capabilities ((move_element.revit.md) /
   (replace_type.revit.md)).

## After corrections
Re-walk the area around every change visually (a moved wall can push its openings past the
new end; a deleted wall strands neighbours); if the Interference Check was used, re-run it
with the same categories and capture the new report.

## Verification

Every clash you report is named with its elements and location off a
screenshot; report "no interferences" only after the sweep actually ran. Check nothing beyond
what the instruction asked.
