---
name: clash_check
description: Find geometric clashes in an Archicad model visually — judge from screenshots per the defect rules; Collision Detection only for candidates the screenshots leave uncertain.
software: Archicad
---

# Check for clashes (capability)

An INSPECTION: collect the whole defect list before fixing anything — a correction destroys
the visual evidence and can create a new defect nearby. **SCREENSHOTS FIRST**: run the sweeps
below and reach a verdict per candidate (clash / clean, by defect number) from what the plan
shows — that verdict is the result. Only a candidate the screenshots genuinely cannot settle
is escalated to **Collision Detection**, and only for that candidate: the tool never replaces
the visual passes (coincident walls, isolated walls and invalid opening placement are
visual-only). Judge per storey (`story-settings / story-nav`) and never
clear an area from whole-plan zoom — `zoom-gently` until wall edges and opening spans are
readable.

## The 8 defects and their screen signatures
**Walls**
1. **Bodies intersecting** — one wall runs THROUGH another's poché instead of ending in a
   clean corner/T.
2. **Duplicate / coincident walls** — near-parallel, overlapping along their length: doubled
   poché edges, a centre hairline, unusually dark linework, tiny end offsets. Inspect the full
   overlap, not one endpoint.
3. **Isolated wall** — both endpoints touch no other wall (a defect only where the model says
   it should connect).

**Doors / windows**
4. **No host wall** — the symbol floats where no wall body runs beneath its span.
5. **Hanging off the wall end** — the span continues past the host's endpoint into empty plan.
6. **Overlapping another opening** — two spans on one wall intrude into each other.
7. **Cut by a crossing wall** — a different wall's body crosses the span (typically at a
   corner/T the opening straddles).

**Stairs**
8. **Stair through a wall** — in plan, the stair's footprint (tread outline / landing) runs
   into a wall's poché instead of stopping clear of it.

## What is NOT a clash
> ⚠️ An opening inside its OWN host wall is correct — only overlap with a DIFFERENT wall,
> another opening, or the host's end is a defect. Never pull an opening out of its host.
> ⚠️ A stair resting on its own slab is expected (the stairwell void is a separate task).
> ⚠️ The same footprint on ANOTHER storey is not a duplicate — compare within one storey only.
> ⚠️ A clean corner/T junction is not defect 1.

## Recipe — per affected storey
1. **Whole-plan scan** for obvious candidates (isolated stubs, detached symbols, wall
   continuations) — record, don't edit. A clean whole-plan view clears nothing (thin gaps
   vanish at that scale).
2. **Wall sweep.** Follow every wall endpoint to endpoint; at corners, T's, stubs and close
   pairs `zoom-gently` and check in order: doubled poché/hairline (2) → disconnected endpoint
   (3) → a wall continuing through another (1). Capture a close view per candidate.
   - Don't diagnose a duplicate from dark poché alone; don't call a wall isolated after
     checking only one endpoint.
3. **Opening sweep.** Stop at every door/window with its whole span + both host portions in
   view: wall body under the full span? (else 4) → host continues past both ends? (else 5) →
   another opening intruding? (6) → a different wall crossing? (7). Keep whole junctions in
   view — a corner overlap hides when only the centre is examined. 5 and 7 can be a very
   narrow strip: zoom again before clearing.
4. **Stair sweep.** At each stair, `zoom-gently` until its footprint edges and the nearby
   wall poché are both readable — the tread outline/landing must stop clear of every wall
   body (8).
5. **Collision Detection — only for the still-uncertain.** After the sweeps, most candidates
   should already carry a verdict; run this ONLY for the ones the screenshots could not
   settle (e.g. a solid intersection too subtle to read in plan). Look under the **Design**
   menu; not found → skip and record the candidate as unresolved. If run, define the two
   element groups and review the marked candidates — never treat an empty result as a clean
   model, and never let it overturn a clash the screenshots clearly showed. (If a solid seems
   excluded: Building Materials carry a **Participates in Collision Detection** property —
   Options > Element Attributes > Building Materials, look only, close without changes.)
6. **Record → correct → recheck.** Record each clash as: defect number, element types,
   location/storey, confirmed in plan. After each separate correction, re-check the same
   spot — fixing one defect can create another (a moved wall strands its openings; a
   deleted wall isolates a neighbour).

## Verification

Every clash you report is named with its elements and location off a readable
screenshot, and every storey the instruction covers was swept. Check nothing beyond what the
instruction asked.
