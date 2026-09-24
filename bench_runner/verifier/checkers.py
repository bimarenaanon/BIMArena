"""Per-bucket checkers: expected_result entries -> CHECKPOINTS.

A checkpoint is one binary point:

    {"id": str, "desc": str, "score": 1.0 | 0.0 | None, "detail": str}

The case PASSES only when EVERY checkpoint passes; the score (passed/total) is
reported alongside. score None = "unchecked" (the data isn't available — e.g.
door swing is not in the snapshot): excluded from both the score and the pass
decision, but kept in the report.

Tolerances are deliberately buffered (roughly-right passes); precise cases
tighten them per-case in their expected_result.

ctx = {
  "exp":       the expected_result dict,
  "final":     final snapshot (mm),
  "base":      baseline snapshot (mm) or {},
  "created":   {bucket: [elements in final but not in baseline (by guid)]},
  "existing":  {bucket: [final elements whose guid IS in baseline]},
  "shift":     [dx, dy] applied to CREATED geometry (wall-set alignment, so a
               GUI run drawn away from the instruction origin isn't punished),
  "composites_created": [{name, skins: [{material, thickness_mm}]}] | None,
  "composites_final":   the final project's WHOLE composite inventory | None
                        (attribute-deletion checkpoints; names only matter),
  "tol", "wall_tol", "pos_tol", "size_tol", "iou_min": tolerances,
}
"""
from __future__ import annotations

import re

from . import geometry as g


def _cp(cid, desc, ok, detail=""):
    """One checkpoint. ok: True/False, or None = unchecked."""
    return {"id": cid, "desc": desc,
            "score": None if ok is None else (1.0 if ok else 0.0), "detail": detail}


def _ci_eq(a, b) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _contains(name, keywords) -> bool:
    """Case-insensitive: the name carries any of the keywords."""
    n = (name or "").lower()
    return any(k.lower() in n for k in keywords or [])


def _label(entry, i, kind) -> str:
    return entry.get("label") or f"{kind}[{i}]"


def _new_composite_name(ctx, idx):
    """The created composite paired with expected composites[idx] — the same
    greedy best-fit pairing check_composites uses, so a "$new:<idx>" reference
    on a wall/slab agrees with the composite checkpoints. None = unresolvable."""
    built = ctx.get("composites_created")
    exp = ctx["exp"].get("composites") or []
    if built is None or not (0 <= idx < len(exp)):
        return None
    paired, taken = {}, set()
    for i, e in enumerate(exp):
        cands = [(j, c) for j, c in enumerate(built) if j not in taken]
        if e.get("name_contains"):
            named = [(j, c) for j, c in cands if _contains(c.get("name"), e["name_contains"])]
            cands = named or cands
        if not cands:
            continue
        j, best = max(cands, key=lambda jc: _composite_fit(e.get("skins") or [], jc[1])[0])
        taken.add(j)
        paired[i] = best.get("name")
    return paired.get(idx)


def _faces_ok(wall, want, floor_walls):
    """Judge a wall's ORIENTATION from its `orient` enrichment (reference-line
    location + the body's perpendicular extents each side of the line).

    want "outward": the finish/inner face must point toward the building
    interior (the centroid of the storey's walls) — i.e. the outer face out.
    Rules: an outside-face ref line puts the body on the inner side; an
    inside-face ref line puts it on the outer side; a centre ref line tells by
    the thicker (finish) side, unreadable when the extents are symmetric.
    Returns (ok | None, detail)."""
    o = wall.get("orient") or {}
    ref = (o.get("ref") or "").lower()
    left, right = o.get("left_mm"), o.get("right_mm")
    beg, end = wall.get("beg"), wall.get("end")
    if left is None or right is None or not beg or not end:
        return None, "no orientation data"

    # A backend that reports the EXTERIOR-face normal directly (Revit's
    # Wall.Orientation) settles this exactly: probe just beyond that face and
    # ask whether the point is still inside the building. No reference-line
    # semantics, no thicker-side heuristic, immune to the mirror flag.
    ext = o.get("exterior")
    if ext is None and "exterior" in o:
        # that backend reports the normal only for COMPOUND types — a single-layer
        # wall has no finish side, so leave it unchecked rather than let the
        # ArchiCAD thicker-side heuristic invent a verdict from a name it cannot read
        return None, "basic (single-layer) wall type has no finish side"
    if ext and len(ext) >= 2:
        import math
        ex, ey = float(ext[0]), float(ext[1])
        n = math.hypot(ex, ey)
        if n > 1e-9:
            ex, ey = ex / n, ey / n
            dx, dy = end[0] - beg[0], end[1] - beg[1]
            L = math.hypot(dx, dy)
            if L > 0:
                lx, ly = -dy / L, dx / L                 # left of beg->end
                # how far the body reaches on the exterior side
                reach = (left if (ex * lx + ey * ly) > 0 else right) or 0
                mid = ((beg[0] + end[0]) / 2, (beg[1] + end[1]) / 2)
                fp = g.walls_footprint(floor_walls)
                if fp and len(fp) >= 4:
                    from shapely.geometry import Point, Polygon
                    probe = Point(mid[0] + ex * (reach + 100),
                                  mid[1] + ey * (reach + 100))
                    ext_inside = Polygon(fp).contains(probe)
                    ok = (not ext_inside) if want == "outward" else ext_inside
                    return ok, (f"exterior normal {[round(ex, 2), round(ey, 2)]} points "
                                f"{'INTO' if ext_inside else 'away from'} the building")
    if "outside" in ref:
        inner_side = 1 if left >= right else -1          # body side = inner
    elif "inside" in ref:
        inner_side = -1 if left >= right else 1          # body side = outer
    else:                                                # centre-type ref line
        if abs(left - right) < 2:
            return None, (f"ref '{o.get('ref')}', symmetric extents "
                          f"({left:.0f}/{right:.0f} mm) — orientation unreadable")
        inner_side = 1 if left > right else -1           # thicker = finish side
    import math
    dx, dy = end[0] - beg[0], end[1] - beg[1]
    n = math.hypot(dx, dy)
    if n == 0:
        return None, "zero-length wall"
    n_left = (-dy / n, dx / n)                           # left of beg->end
    ux, uy = n_left[0] * inner_side, n_left[1] * inner_side
    inner_extent = (left if inner_side == 1 else right) or 0
    mid = ((beg[0] + end[0]) / 2, (beg[1] + end[1]) / 2)
    # interior test: a point just beyond the inner face must fall INSIDE the
    # walls' closed footprint (correct for concave/L-shaped plans, where the
    # naive centroid lands on the wrong side of a re-entrant wall)
    fp = g.walls_footprint(floor_walls)
    inward = None
    if fp and len(fp) >= 4:
        from shapely.geometry import Point, Polygon
        probe = Point(mid[0] + ux * (inner_extent + 100), mid[1] + uy * (inner_extent + 100))
        inward = Polygon(fp).contains(probe)
    else:                                                # open layout: centroid fallback
        mids = [((w["beg"][0] + w["end"][0]) / 2, (w["beg"][1] + w["end"][1]) / 2)
                for w in floor_walls if w.get("beg") and w.get("end")]
        if not mids:
            return None, "no walls to derive the building interior from"
        cx = sum(m[0] for m in mids) / len(mids)
        cy = sum(m[1] for m in mids) / len(mids)
        inward = ux * (cx - mid[0]) + uy * (cy - mid[1]) > 0
    ok = inward if want == "outward" else not inward
    return ok, (f"ref '{o.get('ref')}', extents L{left:.0f}/R{right:.0f} mm -> "
                f"finish face {'toward' if inward else 'away from'} the interior")


# ---------------------------------------------------------------- stories

def check_stories(ctx):
    """The storey STACK (`stories`) and which storey is OPEN (`active_story`).

    The two are independent keys: switching the active storey changes no storey,
    so a set_active_story case carries `active_story` ALONE. Returning early on a
    missing `stories` dropped that checkpoint silently and the case then passed on
    its own untouched start (fixed 2026-08-13)."""
    exp = ctx["exp"].get("stories")
    if not exp and "active_story" not in ctx["exp"]:
        return []
    exp = exp or []
    cps = []
    live = sorted(ctx["final"].get("stories") or [], key=lambda s: s.get("elevation_mm", 0))
    if exp and ctx["exp"].get("stories_exact", True):
        cps.append(_cp("stories.count", f"storey count == {len(exp)}",
                       len(live) == len(exp),
                       f"built {len(live)}: {[s.get('name') for s in live]}"))
    def name_ok(built, want):
        """Equal, or one contains the other ('Ground Floor' ~ 'Ground Floor Level')."""
        b, w = (built or "").strip().lower(), (want or "").strip().lower()
        return bool(b) and (b == w or b in w or w in b)

    elev_tol = ctx["exp"].get("story_elev_tolerance_mm", 10)
    for i, e in enumerate(exp):
        s = live[i] if i < len(live) else None
        if e.get("name"):                    # an entry without a name grades elevation only
            cps.append(_cp(f"stories.{i}.name", f"storey {i} named '{e['name']}'",
                           s is not None and name_ok(s.get("name"), e["name"]),
                           f"built '{s.get('name') if s else None}'"))
        cps.append(_cp(f"stories.{i}.elev", f"storey {i} at {e['elevation_mm']} mm",
                       s is not None
                       and abs(s.get("elevation_mm", 0) - e["elevation_mm"]) <= elev_tol,
                       f"built {s.get('elevation_mm') if s else None} mm"))
    if "active_story" in ctx["exp"]:                     # e.g. "leave '3 Floor' open"
        want = ctx["exp"]["active_story"]
        act = next((s for s in live if s.get("active")), None)
        # a LIST accepts any of its entries — for floor-naming ambiguity ("the
        # second floor" reads as index 1 or 2 depending on ground-floor counting)
        wants = want if isinstance(want, list) else [want]
        oks = []
        for w in wants:
            if isinstance(w, int):           # positional: the i-th storey bottom-up, any name
                oks.append(act is not None and w < len(live) and live[w] is act)
            else:
                oks.append(bool(act and _ci_eq(act.get("name"), w)))
        cps.append(_cp("stories.active",
                       "active storey is " + " or ".join(
                           f"#{w} (bottom-up)" if isinstance(w, int) else f"'{w}'"
                           for w in wants),
                       any(oks),
                       f"active '{act.get('name') if act else None}' "
                       f"(#{live.index(act) if act in live else '?'})"))
    return cps


# ---------------------------------------------------------------- composites

def _skin_hits(exp_skin, built_skin):
    """(material ok, thickness ok) for one layer pairing."""
    mat = _contains(built_skin.get("material"), exp_skin.get("material_contains"))
    thk = True
    if "thickness_mm" in exp_skin:
        want = exp_skin["thickness_mm"]
        got = built_skin.get("thickness_mm") or 0
        if isinstance(want, dict):               # range: {"min": 10, "max": 15}, inclusive
            thk = want.get("min", float("-inf")) <= got <= want.get("max", float("inf"))
        else:
            want = want if isinstance(want, list) else [want]   # any-of ("10 / 12 / 15")
            thk = any(abs(got - w) <= 2 for w in want)
    return mat, thk


def _thk_label(want):
    """Human form of a thickness spec for the checkpoint description."""
    if isinstance(want, dict):
        return f"{want.get('min', '...')}-{want.get('max', '...')}"
    return want


def _skin_alignments(n_exp, n_built):
    """Index mappings of expected layers onto built layers, in order. Same
    count -> 1:1; more built layers (e.g. an extra air gap) -> every increasing
    subsequence; fewer built -> every way to skip expected layers (a missing
    layer must not shift-break every pairing after it)."""
    if n_exp == n_built:
        yield tuple(range(n_exp))
        return
    from itertools import combinations
    if n_exp < n_built:
        yield from combinations(range(n_built), n_exp)
    else:
        for keep in combinations(range(n_exp), n_built):
            m = dict(zip(keep, range(n_built)))
            yield tuple(m.get(i) for i in range(n_exp))


def _composite_fit(exp_skins, built):
    """Best alignment (given order or reversed) -> (hit count,
    [matched built skin per expected layer])."""
    best, best_map = -1, [{} for _ in exp_skins]
    for skins in (built["skins"], list(reversed(built["skins"]))):
        for align in _skin_alignments(len(exp_skins), len(skins)):
            pick = [skins[j] if j is not None else {} for j in align]
            hits = sum(m + t for m, t in (_skin_hits(e, s)
                                          for e, s in zip(exp_skins, pick)))
            if hits > best:
                best, best_map = hits, pick
    return best, best_map


def check_composites(ctx):
    exp = ctx["exp"].get("composites")
    if exp is None and not ctx["exp"].get("no_extra_composites"):
        return []
    exp = exp or []
    built = ctx.get("composites_created")
    if built is None:
        return [_cp("composites.available", "created-composite list available", None,
                    "no composite data from this source — unchecked")]
    cps, used = [], set()
    for i, e in enumerate(exp):
        lab = _label(e, i, "composite")
        exp_skins = e.get("skins") or []
        cands = [(j, c) for j, c in enumerate(built) if j not in used]
        if e.get("name_contains"):
            named = [(j, c) for j, c in cands if _contains(c.get("name"), e["name_contains"])]
            cands = named or cands
        if not cands:
            cps.append(_cp(f"composites.{i}.found", f"{lab}: a new composite was created",
                           False, f"created composites: {[c.get('name') for c in built]}"))
            continue
        j, best = max(cands, key=lambda jc: _composite_fit(exp_skins, jc[1])[0])
        used.add(j)
        cps.append(_cp(f"composites.{i}.found", f"{lab}: a new composite was created",
                       True, f"matched '{best.get('name')}'"))
        if e.get("total_thickness_mm") is not None:
            want = e["total_thickness_mm"]
            total = round(sum(s.get("thickness_mm") or 0 for s in best["skins"]), 1)
            cps.append(_cp(f"composites.{i}.total_thickness",
                           f"{lab}: total build-up thickness {want} mm",
                           abs(total - want) <= e.get("thickness_tolerance_mm", 5),
                           f"built total {total} mm over {len(best['skins'])} layers"))
        if e.get("layers_exact", True):
            cps.append(_cp(f"composites.{i}.layers", f"{lab}: {len(exp_skins)} layers",
                           len(best["skins"]) == len(exp_skins),
                           f"built {len(best['skins'])}: "
                           f"{[(s.get('material'), s.get('thickness_mm')) for s in best['skins']]}"))
        _, ordered = _composite_fit(exp_skins, best)
        for k, se in enumerate(exp_skins):
            sb = ordered[k] if k < len(ordered) else {}
            mat, thk = _skin_hits(se, sb)
            got = f"built {sb.get('thickness_mm')} mm '{sb.get('material')}'"
            if se.get("material_contains"):
                cps.append(_cp(f"composites.{i}.skin{k}.material",
                               f"{lab}: layer {k} material has "
                               f"{'/'.join(se['material_contains'])}", mat, got))
            if "thickness_mm" in se:
                cps.append(_cp(f"composites.{i}.skin{k}.thickness",
                               f"{lab}: layer {k} is {_thk_label(se['thickness_mm'])} mm",
                               thk, got))
    if ctx["exp"].get("no_extra_composites"):
        cps.append(_cp("composites.no_extra", f"exactly {len(exp)} new composite(s)",
                       len(built) == len(exp),
                       f"created {len(built)}: {[c.get('name') for c in built]}"))
    return cps


def check_composites_absent(ctx):
    """Attribute-library DELETIONS. `composites_absent` names composites that must be
    GONE from the final project's inventory — one checkpoint (and one reward unit) per
    name, matched by WHOLE-name case-insensitive equality, never substring (deleting
    '100 Block Insulated Cavity' must not score while its 'Plastered' sibling is the
    one that died). `composites_preserved` is the guard constraint: every listed name
    must still be present, folded into ONE checkpoint so a long survivor list does not
    drown the delete in the score."""
    absent = ctx["exp"].get("composites_absent") or []
    kept = ctx["exp"].get("composites_preserved") or []
    if not absent and not kept:
        return []
    final = ctx.get("composites_final")
    if final is None:
        return [_cp("composites_absent.available", "final composite inventory available",
                    None, "no composite inventory from this source — unchecked")]
    names = [c.get("name") for c in final]
    cps = []
    for i, want in enumerate(absent):
        gone = not any(_ci_eq(n, want) for n in names)
        cps.append(_cp(f"composites_absent.{i}.gone", f"composite '{want}' deleted",
                       gone, "" if gone else "still present in the composite inventory"))
    if kept:
        missing = [w for w in kept if not any(_ci_eq(n, w) for n in names)]
        cps.append(_cp("composites.preserved",
                       f"the other {len(kept)} composite(s) survive",
                       not missing, f"missing: {missing}" if missing else ""))
    return cps


# ---------------------------------------------------------------- walls

def _body_side_ok(wall, want, exp_entries):
    """The wall BODY (its mass, from the orient extents) must sit on `want` side
    ('inside' | 'outside') of the polygon the expected coordinate segments enclose.
    PURE GEOMETRY — immune to reference-line semantics and the mirror/flip flag no
    API exposes: a modify that reverses a wall's direction flips the body to the
    reference line's other side while the line itself still matches, silently
    shrinking (or growing) the room by one wall thickness."""
    o = wall.get("orient") or {}
    left, right = o.get("left_mm"), o.get("right_mm")
    beg, end = wall.get("beg"), wall.get("end")
    if left is None or right is None or not beg or not end:
        return None, "no body-extent data"
    segs = [e2 for e2 in exp_entries if e2.get("beg") and e2.get("end")]
    fp = g.walls_footprint(segs)
    if not fp or len(fp) < 4:
        return None, "the expected outline does not close"
    import math
    dx, dy = end[0] - beg[0], end[1] - beg[1]
    n = math.hypot(dx, dy)
    if n == 0:
        return None, "zero-length wall"
    body_side = 1 if left >= right else -1        # body left(+) / right(-) of travel
    extent = max(left or 0, right or 0)
    ux, uy = (-dy / n) * body_side, (dx / n) * body_side
    mid = ((beg[0] + end[0]) / 2, (beg[1] + end[1]) / 2)
    from shapely.geometry import Point, Polygon
    probe = Point(mid[0] + ux * (extent / 2 + 10), mid[1] + uy * (extent / 2 + 10))
    inside = Polygon(fp).contains(probe)
    ok = inside if want == "inside" else not inside
    return ok, (f"body extends {'INTO' if inside else 'away from'} the outline "
                f"(extents L{left:.0f}/R{right:.0f} mm)")


def check_walls(ctx):
    exp = ctx["exp"].get("walls")
    if not exp:
        return []
    cps, tol = [], ctx["wall_tol"]
    created, existing = ctx["created"]["walls"], ctx["existing"]["walls"]
    new_comp_names = {c.get("name") for c in (ctx.get("composites_created") or [])}

    def comp_ok(wall, want):
        if isinstance(want, str) and want.startswith("$new"):
            if ctx.get("composites_created") is None:
                return None
            if ":" in want:                      # "$new:<i>" = the created composite
                name = _new_composite_name(ctx, int(want.split(":", 1)[1]))
                # created-list AVAILABLE but no pairable composite -> nothing
                # was created, so "$new" can never be satisfied: fail, not skip
                return False if name is None else _ci_eq(wall.get("composite"), name)
            return wall.get("composite") in new_comp_names   # "$new" = any of them
        if isinstance(want, list):               # keyword form
            return _contains(wall.get("composite"), want)
        return _ci_eq(wall.get("composite"), want)

    consumed = set()
    for i, e in enumerate(exp):
        lab = _label(e, i, "wall")
        # "existing": a pre-existing wall (convert task); "match": "any": the
        # final layout regardless of guid (an adjust-walls task MOVES existing
        # walls, so created-only would never see them)
        if e.get("match") == "any":
            pool = created + existing
        elif e.get("existing"):
            pool = existing
        else:
            pool = created
        if e.get("floor") is not None:      # multi-storey builds: per-floor walls
            pool = [w for w in pool if w.get("floor") == e["floor"]]

        if "length_mm" in e and not e.get("beg"):   # position-free wall spec
            etol = e.get("tolerance_mm", tol)       # per-wall override of wall_tol
            best, best_d = None, None
            for w in pool:
                if id(w) in consumed or not w.get("beg") or not w.get("end"):
                    continue
                d = abs(g.seg_len(w["beg"], w["end"]) - e["length_mm"])
                if best is None or d < best_d:
                    best, best_d = w, d
            found = best is not None and best_d <= etol
            cps.append(_cp(f"walls.{i}.geom", f"{lab}: a {e['length_mm']} mm wall built",
                           found,
                           f"nearest length off by {best_d:.0f} mm" if best is not None
                           else "no candidate wall"))
            if not found:
                continue
            consumed.add(id(best))
            if e.get("height_mm"):
                cps.append(_cp(f"walls.{i}.height", f"{lab}: {e['height_mm']} mm high",
                               best.get("height") is not None
                               and abs(best["height"] - e["height_mm"]) <= tol,
                               f"built {best.get('height')} mm"))
            if e.get("composite"):
                cps.append(_cp(f"walls.{i}.composite", f"{lab}: composite {e['composite']}",
                               comp_ok(best, e["composite"]),
                               f"built '{best.get('composite')}'"))
            if e.get("composite_not"):
                cps.append(_cp(f"walls.{i}.composite",
                               f"{lab}: composite NOT {e['composite_not']}",
                               not _contains(best.get("composite"), e["composite_not"]),
                               f"built '{best.get('composite')}'"))
            cps += _wall_attr_cps(e, [best], i, lab, ctx)
            if e.get("faces"):
                ok, det = _faces_ok(best, e["faces"],
                                    [w for w in (ctx["final"].get("walls") or [])
                                     if w.get("floor") == best.get("floor")])
                cps.append(_cp(f"walls.{i}.faces", f"{lab}: faces {e['faces']}", ok, det))
            continue

        etol = e.get("tolerance_mm", tol)        # per-wall override of wall_tol
        seg_l = g.seg_len(e["beg"], e["end"])
        cov, used = g.match_segment(e["beg"], e["end"], pool, etol)
        cps.append(_cp(f"walls.{i}.geom", f"{lab}: segment {e['beg']}->{e['end']} built",
                       cov >= 0.90 or (1 - cov) * seg_l <= etol,
                       f"coverage {cov:.0%} by {len(used)} wall(s)"))
        if not e.get("existing"):
            consumed.update(id(pool[j]) for j in used)
        # attribute checks judge only the walls carrying a MEANINGFUL share of
        # the segment — a collinear neighbour overlapping a T-junction by
        # ~100 mm must not drag its width/composite into this segment
        major = [j for j in used
                 if g.match_segment(e["beg"], e["end"], [pool[j]], etol)[0] >= 0.25]
        attr = major or used
        if e.get("composite"):
            if not attr:
                cps.append(_cp(f"walls.{i}.composite", f"{lab}: composite {e['composite']}",
                               False, "no matched walls"))
            else:
                oks = [comp_ok(pool[j], e["composite"]) for j in attr]
                cps.append(_cp(f"walls.{i}.composite", f"{lab}: composite {e['composite']}",
                               None if any(v is None for v in oks) else all(oks),
                               f"built {sorted({pool[j].get('composite') for j in attr}, key=str)}"))
        # composite_not: the matched walls' type names must contain NONE of the
        # keywords (e.g. every non-front facade must not be a Brick/masonry type)
        if e.get("composite_not"):
            if not attr:
                cps.append(_cp(f"walls.{i}.composite",
                               f"{lab}: composite NOT {e['composite_not']}",
                               False, "no matched walls"))
            else:
                cps.append(_cp(f"walls.{i}.composite",
                               f"{lab}: composite NOT {e['composite_not']}",
                               all(not _contains(pool[j].get("composite"), e["composite_not"])
                                   for j in attr),
                               f"built {sorted({pool[j].get('composite') for j in attr}, key=str)}"))
        cps += _wall_attr_cps(e, [pool[j] for j in attr], i, lab, ctx)
        if e.get("faces"):
            if not attr:
                cps.append(_cp(f"walls.{i}.faces", f"{lab}: faces {e['faces']}",
                               False, "no matched walls"))
            else:
                w0 = pool[attr[0]]
                ok, det = _faces_ok(w0, e["faces"],
                                    [w for w in (ctx["final"].get("walls") or [])
                                     if w.get("floor") == w0.get("floor")])
                cps.append(_cp(f"walls.{i}.faces", f"{lab}: faces {e['faces']}", ok, det))
        if e.get("body_side") in ("inside", "outside"):
            if not attr:
                cps.append(_cp(f"walls.{i}.body_side",
                               f"{lab}: body on the {e['body_side']} of the outline",
                               False, "no matched walls"))
            else:
                ok, det = _body_side_ok(pool[attr[0]], e["body_side"], exp)
                cps.append(_cp(f"walls.{i}.body_side",
                               f"{lab}: body on the {e['body_side']} of the outline",
                               ok, det))
    if ctx["exp"].get("no_extra_walls"):
        extra = [w for w in created if id(w) not in consumed]
        # matched walls must also STAY WITHIN the expected outline: a wall that
        # covers its segment but was stretched past it is excess geometry the
        # per-segment coverage check cannot see
        exp_segs = [{"beg": e["beg"], "end": e["end"]} for e in exp
                    if e.get("beg") and e.get("end")]
        overhang = []
        # position-free specs (length_mm only) define NO outline — with an empty
        # segment list every matched wall would read as 100% "beyond" it and the
        # CORRECT wall itself gets flagged; only extras are checkable then
        for w in (created + existing) if exp_segs else []:
            if id(w) not in consumed or not w.get("beg") or not w.get("end"):
                continue
            cov, _ = g.match_segment(w["beg"], w["end"], exp_segs, tol)
            over = (1 - cov) * g.seg_len(w["beg"], w["end"])
            # a JOINED corner moves the location-curve endpoints by up to one wall
            # thickness relative to the true face corner (an outer corner trims the
            # curve short, a REENTRANT corner overshoots it — the solid itself is
            # mitred clean), so endpoint-derived overhang within one thickness is a
            # join artifact, not excess geometry. The relevant thickness is the
            # JOINED wall's, not this wall's own (a thin partition butting into a
            # thick exterior wall overshoots by the exterior's thickness), so allow
            # the largest wall width in the model.
            def _thick(wl):
                o = wl.get("orient") or {}
                return (wl.get("width")
                        or ((o.get("left_mm") or 0) + (o.get("right_mm") or 0)) or 0)
            join_t = max([_thick(x) for x in created + existing], default=0)
            if over > tol + join_t:
                overhang.append(f"{w.get('id')} extends {over:.0f} mm beyond the "
                                "expected outline")
        cps.append(_cp("walls.no_extra", "no walls beyond the expected segments",
                       not extra and not overhang,
                       "; ".join(
                           ([f"{len(extra)} unexpected new wall(s): "
                             f"{[(w.get('id'), w.get('beg'), w.get('end')) for w in extra][:4]}"]
                            if extra else []) + overhang[:4])
                       or "all matched walls within the outline"))
    return cps


def _norm_ref(s: str) -> str:
    """A wall reference-line name, comparable across the spellings the two applications
    and the case author use: "Core Center" / "core centre" / "core_center" are one value,
    and the word "face" carries no information ("Outside Face" == "outside")."""
    words = [w for w in re.split(r"[\s_/:-]+", (s or "").strip().lower())
             if w and w not in ("face", "line", "the")]
    return " ".join("center" if w in ("centre", "centerline", "centreline") else w
                    for w in words)


def _wall_attr_cps(e, matched, i, lab, ctx):
    """width_mm / height_mm / material_contains checkpoints for the walls an entry
    matched (width falls back to the orient-enrichment bbox extents when the
    snapshot carries none).

    PER-ENTRY height is the one-wall counterpart of the model-wide
    `wall_height_mm` (check_wall_heights): a case that raises ONE wall cannot use
    the global key, and until 2026-08-13 a `height_mm` written on a wall entry was
    silently ignored — the case then graded only geometry and passed on its own
    untouched start."""
    cps = []

    def _width(w):
        if w.get("width") is not None:
            return w["width"]
        o = w.get("orient") or {}
        if o.get("left_mm") is not None and o.get("right_mm") is not None:
            return o["left_mm"] + o["right_mm"]
        return None

    if e.get("width_mm") is not None:
        want, tol = e["width_mm"], ctx["size_tol"]
        got = [_width(w) for w in matched]
        if not matched:
            cps.append(_cp(f"walls.{i}.width", f"{lab}: {want} mm thick", False,
                           "no matched walls"))
        elif any(g is None for g in got):
            cps.append(_cp(f"walls.{i}.width", f"{lab}: {want} mm thick", None,
                           "wall thickness unavailable"))
        else:
            cps.append(_cp(f"walls.{i}.width", f"{lab}: {want} mm thick",
                           all(abs(g - want) <= tol for g in got),
                           f"built {sorted(set(round(g) for g in got))} mm"))
    if e.get("height_mm") is not None:
        want = e["height_mm"]
        tol = ctx["exp"].get("wall_height_tolerance_mm", 1)
        got = [w.get("height") for w in matched]
        if not matched:
            cps.append(_cp(f"walls.{i}.height", f"{lab}: {want} mm high", False,
                           "no matched walls"))
        elif any(h is None for h in got):
            cps.append(_cp(f"walls.{i}.height", f"{lab}: {want} mm high", None,
                           "wall height unavailable"))
        else:
            cps.append(_cp(f"walls.{i}.height", f"{lab}: {want} mm high",
                           all(abs(h - want) <= tol for h in got),
                           f"built {sorted(set(round(h) for h in got))} mm"))
    if e.get("material_contains"):
        kws = e["material_contains"]
        if not matched:
            cps.append(_cp(f"walls.{i}.material", f"{lab}: material has {'/'.join(kws)}",
                           False, "no matched walls"))
        else:
            mats = [w.get("material") for w in matched]
            if any(m is None for m in mats):
                cps.append(_cp(f"walls.{i}.material", f"{lab}: material has {'/'.join(kws)}",
                               None, "wall material unavailable"))
            else:
                cps.append(_cp(f"walls.{i}.material", f"{lab}: material has {'/'.join(kws)}",
                               all(_contains(m, kws) for m in mats),
                               f"built {sorted(set(mats))}"))
    if e.get("reference"):
        # WHICH line of the wall its coordinates describe (Archicad's Reference Line
        # Location / Revit's Location Line), read from the snapshot's orient.ref. Compared
        # on words, so "Core Center" == "core centre" == "core_center" and "Outside Face"
        # == "outside"; a wall whose orientation could not be read scores UNCHECKED.
        want = _norm_ref(e["reference"])
        got = [(w.get("orient") or {}).get("ref") for w in matched]
        if not matched:
            cps.append(_cp(f"walls.{i}.reference", f"{lab}: referenced on the {e['reference']}",
                           False, "no matched walls"))
        elif any(r is None for r in got):
            cps.append(_cp(f"walls.{i}.reference", f"{lab}: referenced on the {e['reference']}",
                           None, "reference line unavailable"))
        else:
            cps.append(_cp(f"walls.{i}.reference", f"{lab}: referenced on the {e['reference']}",
                           all(_norm_ref(r) == want for r in got),
                           f"built {sorted(set(got))}"))
    return cps


# ---------------------------------------------------------------- openings

def _entry_anchor(e, walls):
    """Expected position for an opening entry: explicit centre/near, or the
    midpoint of the named side's wall."""
    if e.get("center"):
        return e["center"]
    if e.get("near"):
        return e["near"]
    if e.get("host_side"):
        for w in walls:
            if g.wall_side(w, walls) == g.side_key(e["host_side"]):
                return g.wall_midpoint(w)
    return None


def check_openings(ctx, kind):
    exp = ctx["exp"].get(kind)
    if not exp:
        return []
    cps, pos_tol, size_tol = [], ctx["pos_tol"], ctx["size_tol"]
    final_walls = ctx["final"].get("walls") or []
    wall_by_id = {}
    for w in final_walls:                       # ids can repeat across storeys
        wall_by_id.setdefault(w.get("id"), w)

    def host_wall(o):
        return wall_by_id.get(o.get("host"))

    all_final = ctx["final"].get(kind) or []
    created = ctx["created"][kind]

    def _attr_fit(e, o):
        """How well a candidate's attributes fit the entry — used to pick the
        right candidate when several are in range (e.g. a replace case where
        the agent ADDED a new door next to the old one)."""
        sc = 0.0
        if e.get("width_mm") and o.get("width") is not None:
            sc += 1.0 if abs(o["width"] - e["width_mm"]) <= size_tol else 0.0
        if e.get("height_mm") and o.get("height") is not None:
            sc += 1.0 if abs(o["height"] - e["height_mm"]) <= size_tol else 0.0
        if e.get("type_contains"):
            sc += 1.0 if _contains(o.get("type"), e["type_contains"]) else 0.0
        return sc

    # greedy assignment: prefer in-range candidates by attribute fit, then
    # distance; when the pool is no bigger than the expected list, everything
    # must correspond — assign best-effort so a misplaced element fails on
    # position instead of counting as "not placed" at all.
    # GLOBAL assignment (2026-09-06): every (entry, candidate) pair is scored once
    # and the pairs are consumed best-first across ALL entries — in-range pairs
    # (within cap) first, by attribute fit then distance; then, for entries whose
    # pool is no bigger than the expected list ("loose"), any remaining pair so a
    # misplaced element fails on position instead of counting as "not placed".
    # The old per-entry greedy loop consumed candidates in key order, so one
    # missing door let entry N take entry N+1's exactly-placed door (off 7949 mm,
    # swing fails) and reported N+1 as "no candidate" — one error, four
    # checkpoints (D_model_completion2/3 audit).
    assigned, taken = {}, set()
    cap = max(pos_tol * 3, 1500)
    in_range, spare = [], []
    for i, e in enumerate(exp):
        pool = all_final if e.get("near") else created
        anchor = _entry_anchor(e, final_walls)
        loose = len(pool) <= len(exp)
        for o in pool:
            if not o.get("center"):
                continue
            if e.get("floor") is not None and o.get("floor") != e["floor"]:
                continue
            d = g.dist(o["center"], anchor) if anchor else 0.0
            rec = (-_attr_fit(e, o), d, i, o)
            (in_range if d <= cap else spare if loose else []).append(rec)
    for bucket in (in_range, spare):
        for fit, d, i, o in sorted(bucket, key=lambda r: (r[0], r[1], r[2])):
            if i in assigned or id(o) in taken:
                continue
            assigned[i] = (o, d)
            taken.add(id(o))

    one = "door" if kind == "doors" else "window"
    for i, e in enumerate(exp):
        lab = _label(e, i, one)
        got = assigned.get(i)
        cps.append(_cp(f"{kind}.{i}.found", f"{lab}: placed", got is not None,
                       "" if got else "no candidate near the expected position"))
        if not got:
            continue
        o, d = got
        oid = o.get("id")
        if e.get("center") or e.get("near"):
            cps.append(_cp(f"{kind}.{i}.pos", f"{lab}: at {e.get('center') or e.get('near')}",
                           d <= pos_tol, f"{oid} at {o['center']} (off {d:.0f} mm)"))
        if e.get("host_side"):
            hw = host_wall(o)
            side = g.wall_side(hw, final_walls) if hw else None
            cps.append(_cp(f"{kind}.{i}.host", f"{lab}: on the {e['host_side']} wall",
                           side == g.side_key(e["host_side"]),
                           f"{oid} hosted on {o.get('host')} ({side})"))
        if e.get("width_mm") or e.get("height_mm"):
            oks, want = [], []
            if e.get("width_mm"):
                oks.append(abs((o.get("width") or 0) - e["width_mm"]) <= size_tol)
                want.append(f"w{e['width_mm']}")
            if e.get("height_mm"):
                oks.append(abs((o.get("height") or 0) - e["height_mm"]) <= size_tol)
                want.append(f"h{e['height_mm']}")
            cps.append(_cp(f"{kind}.{i}.size", f"{lab}: {'x'.join(want)} mm", all(oks),
                           f"{oid} built {o.get('width')}x{o.get('height')} mm"))
        if e.get("min_area_m2") is not None:
            # daylight-style LOWER bound on the opening AREA (width x height):
            # >= passes, so any compliant-or-larger resize is accepted; 0.001 m²
            # slack absorbs float noise on a window sized exactly at the limit
            w_, h_ = o.get("width"), o.get("height")
            cps.append(_cp(f"{kind}.{i}.min_area",
                           f"{lab}: area >= {e['min_area_m2']} m²",
                           None if (w_ is None or h_ is None)
                           else (w_ * h_) / 1e6 >= e["min_area_m2"] - 1e-3,
                           "opening size unavailable" if (w_ is None or h_ is None)
                           else f"{oid} built {w_:.0f} x {h_:.0f} mm = "
                                f"{w_ * h_ / 1e6:.3f} m²"))
        if e.get("min_width_mm") is not None:
            # accessibility-style LOWER bound: any clear width >= the limit
            # passes (an exact width_mm would wrongly fail a wider-than-minimum
            # but perfectly compliant fix)
            cps.append(_cp(f"{kind}.{i}.min_width",
                           f"{lab}: clear width >= {e['min_width_mm']} mm",
                           None if o.get("width") is None
                           else o["width"] >= e["min_width_mm"] - 1,
                           f"{oid} built width {o.get('width')} mm"))
        if e.get("sill_mm") is not None:
            # sill_tolerance_mm: per-entry override of the ±50 default — a case whose
            # target sits within 50 mm of the seeded sill needs it tighter to be failable
            s_tol = e.get("sill_tolerance_mm", 50)
            cps.append(_cp(f"{kind}.{i}.sill", f"{lab}: sill {e['sill_mm']} mm",
                           o.get("sill") is not None and abs(o["sill"] - e["sill_mm"]) <= s_tol,
                           f"{oid} sill {o.get('sill')} mm"))
        if e.get("type"):                        # EXACT library-part name match
            cps.append(_cp(f"{kind}.{i}.type", f"{lab}: type is '{e['type']}'",
                           (o.get("type") or "").strip() == e["type"].strip(),
                           f"{oid} type '{o.get('type')}'"))
        elif e.get("type_contains"):
            cps.append(_cp(f"{kind}.{i}.type", f"{lab}: type has {e['type_contains']}",
                           _contains(o.get("type"), e["type_contains"]),
                           f"{oid} type '{o.get('type')}'"))
        if e.get("type_not_contains"):
            # EXCLUSION keywords: a family that matches the inclusion words can still
            # be the wrong kind (e.g. an EXTERIOR sliding family on an interior door)
            cps.append(_cp(f"{kind}.{i}.type_excl",
                           f"{lab}: type must NOT have {e['type_not_contains']}",
                           not _contains(o.get("type"), e["type_not_contains"]),
                           f"{oid} type '{o.get('type')}'"))
        if e.get("open_into"):
            # geometric swing: the leaf must sweep toward the given side. Anchor
            # to the EXPECTED centre (not the built one) so a door placed a bit
            # off along its wall is still judged on DIRECTION only.
            n = g.opening_normal(o.get("swing_raw"), host_wall(o))
            into = e["open_into"]
            anchor = e.get("center") or e.get("near") or o.get("center")
            if n is not None and anchor:
                v = (into[0] - anchor[0], into[1] - anchor[1])
                cps.append(_cp(f"{kind}.{i}.swing", f"{lab}: opens toward {into}",
                               (n[0] * v[0] + n[1] * v[1]) > 0,
                               f"{oid} leaf normal {[round(x, 2) for x in n]}"))
            else:
                cps.append(_cp(f"{kind}.{i}.swing", f"{lab}: opens toward {into}", None,
                               "swing not readable from the snapshot"))
        elif e.get("swing"):
            if o.get("swing") is not None:       # a backend that reports it directly
                cps.append(_cp(f"{kind}.{i}.swing", f"{lab}: opens {e['swing']}",
                               o["swing"] == e["swing"], f"{oid} swings {o['swing']}"))
            else:
                # geometric: leaf normal vs the walls' closed footprint —
                # "in" = the leaf sweeps toward the building interior
                n = g.opening_normal(o.get("swing_raw"), host_wall(o))
                floor_walls = [w for w in final_walls
                               if w.get("floor") == o.get("floor")]
                fp = g.walls_footprint(floor_walls)
                if n is None or not o.get("center") or not fp or len(fp) < 4:
                    cps.append(_cp(f"{kind}.{i}.swing", f"{lab}: opens {e['swing']}", None,
                                   "swing not readable from the snapshot"))
                else:
                    from shapely.geometry import Point, Polygon
                    c = o["center"]
                    inward = Polygon(fp).contains(Point(c[0] + n[0] * 800,
                                                        c[1] + n[1] * 800))
                    ok = inward if e["swing"] == "in" else not inward
                    cps.append(_cp(f"{kind}.{i}.swing", f"{lab}: opens {e['swing']}", ok,
                                   f"{oid} leaf sweeps {'inward' if inward else 'outward'}"))
        if e.get("hinge_near"):
            # hinge side: the doorway end the leaf pivots on must be the end
            # NEARER the given point (derive expected points from the GT)
            hp = g.hinge_point(o.get("swing_raw"), host_wall(o),
                               o.get("center"), o.get("width"))
            if hp is None:
                cps.append(_cp(f"{kind}.{i}.hinge", f"{lab}: hinge near {e['hinge_near']}",
                               None, "hinge not readable from the snapshot"))
            else:
                # Compare the hinge SIDE, not the absolute distance (2026-09-06):
                # the hinge direction of the built door (its centre -> its hinge
                # jamb) must agree with the direction from the EXPECTED centre to
                # the expected jamb. The old nearest-jamb rule failed a door that
                # sat more than half its width off position even when it was
                # hinged on the required side (C_model_editing7 audit). Without
                # an expected centre the nearest-jamb rule still applies.
                ec = e.get("center") or e.get("near")
                ux, uy = hp[0] - o["center"][0], hp[1] - o["center"][1]
                if ec and (ux or uy):
                    ok = (e["hinge_near"][0] - ec[0]) * ux + (e["hinge_near"][1] - ec[1]) * uy > 0
                else:
                    other = [2 * o["center"][0] - hp[0], 2 * o["center"][1] - hp[1]]
                    ok = g.dist(hp, e["hinge_near"]) < g.dist(other, e["hinge_near"])
                cps.append(_cp(f"{kind}.{i}.hinge", f"{lab}: hinge near {e['hinge_near']}", ok,
                               f"{oid} hinge end at {[round(v) for v in hp]}"))
    return cps


# ---------------------------------------------------------------- slabs

def _resolve_floor(spec, ctx):
    if spec == "active":
        act = next((s for s in (ctx["base"].get("stories") or ctx["final"].get("stories") or [])
                    if s.get("active")), None)
        return act.get("index") if act else 0
    return spec


def check_slabs(ctx):
    exp = ctx["exp"].get("slabs")
    if not exp:
        return []
    cps, tol, iou_min = [], ctx["tol"], ctx["iou_min"]
    used = set()
    for i, e in enumerate(exp):
        lab = _label(e, i, "slab")
        floor = _resolve_floor(e.get("floor"), ctx) if e.get("floor") is not None else None
        # match "any": accept the slab whichever way it was produced — an
        # in-place boundary edit keeps the guid (existing pool) while a
        # delete+redraw gets a new one (created pool); both are legitimate
        # outcomes of "adjust the slab"
        if e.get("match") == "any":
            pool = ctx["created"]["slabs"] + ctx["existing"]["slabs"]
        else:
            pool = ctx["existing"]["slabs"] if e.get("existing") else ctx["created"]["slabs"]
        cands = [s for s in pool
                 if id(s) not in used and (floor is None or s.get("floor") == floor)]
        outline = e.get("outline")
        if outline == "footprint":               # the walls' exterior-face envelope
            walls = [w for w in (ctx["final"].get("walls") or [])
                     if floor is None or w.get("floor") == floor]
            outline = g.walls_outer_footprint(walls)
        if not cands:
            cps.append(_cp(f"slabs.{i}.found", f"{lab}: slab created"
                           + (f" on floor {floor}" if floor is not None else ""), False,
                           f"{len(pool)} candidate slab(s), none on the right floor"))
            continue
        # ignore_holes: judge the OUTER boundary only — for a slab whose opening
        # follows another element (e.g. a stairwell cut wherever the agent put
        # its stair), pair with clear_of_stair instead of exact expected holes
        if outline:
            best = max(cands, key=lambda s: g.iou(s.get("polygonOutline") or [], outline,
                                                  holes_a=None if e.get("ignore_holes")
                                                  else s.get("holes"),
                                                  holes_b=e.get("holes")))
        else:
            best = cands[0]
        used.add(id(best))
        cps.append(_cp(f"slabs.{i}.found", f"{lab}: slab created"
                       + (f" on floor {floor}" if floor is not None else ""), True,
                       f"matched {best.get('id')}"))
        if outline:
            v = g.iou(best.get("polygonOutline") or [], outline,
                      holes_a=None if e.get("ignore_holes") else best.get("holes"),
                      holes_b=e.get("holes"))
            cps.append(_cp(f"slabs.{i}.outline", f"{lab}: outline matches"
                           + (" the wall footprint" if e.get("outline") == "footprint" else ""),
                           v >= iou_min, f"IoU {v:.2f} (min {iou_min})"))
        elif e.get("outline") == "footprint":
            cps.append(_cp(f"slabs.{i}.outline", f"{lab}: outline matches the wall footprint",
                           None, "wall footprint could not be resolved"))
        if e.get("composite"):
            if isinstance(e["composite"], str) and e["composite"].startswith("$new"):
                if ctx.get("composites_created") is None:
                    cps.append(_cp(f"slabs.{i}.composite", f"{lab}: uses the new composite",
                                   None, "created-composite list unavailable"))
                elif ":" in e["composite"]:      # "$new:<i>" = that specific one
                    name = _new_composite_name(ctx, int(e["composite"].split(":", 1)[1]))
                    # created list available but empty -> fail, not unchecked
                    cps.append(_cp(f"slabs.{i}.composite", f"{lab}: uses the new composite",
                                   False if name is None
                                   else _ci_eq(best.get("composite"), name),
                                   f"built '{best.get('composite')}', want '{name}'"))
                else:
                    names = [c.get("name") for c in ctx["composites_created"]]
                    cps.append(_cp(f"slabs.{i}.composite", f"{lab}: uses the new composite",
                                   best.get("composite") in names,
                                   f"built '{best.get('composite')}', new: {names}"))
            elif isinstance(e["composite"], list):
                cps.append(_cp(f"slabs.{i}.composite", f"{lab}: composite has {e['composite']}",
                               _contains(best.get("composite"), e["composite"]),
                               f"built '{best.get('composite')}'"))
            else:
                cps.append(_cp(f"slabs.{i}.composite", f"{lab}: composite '{e['composite']}'",
                               _ci_eq(best.get("composite"), e["composite"]),
                               f"built '{best.get('composite')}'"))
        if e.get("level_mm") is not None:
            cps.append(_cp(f"slabs.{i}.level", f"{lab}: level {e['level_mm']} mm",
                           abs((best.get("level") or 0) - e["level_mm"]) <= tol,
                           f"built {best.get('level')} mm"))
        if e.get("reference_plane") or e.get("reference_plane_offset_mm") is not None:
            # Tapir reports the reference plane as its offset below the slab's top
            # surface: "Top" = 0; any other location (e.g. "Core Top") needs the
            # expected offset given explicitly as reference_plane_offset_mm (it
            # depends on the composite's layer stack, which the grader can't derive)
            off = best.get("offset_from_top")
            want = e.get("reference_plane_offset_mm")
            ref = e.get("reference_plane") or f"{want} mm below top"
            rp = (e.get("reference_plane") or "").replace(" ", "").lower()
            if want is None and rp == "top":
                want = 0
            if rp == "coretop":
                # Core Top sits below the layers ABOVE the core — which depend on
                # the layer stack the run VALIDLY authored (composite specs often
                # pin only the total thickness + finish, so different stacks are
                # accepted). Derive the expected offset from the built slab's OWN
                # composite; the static reference_plane_offset_mm stays as the
                # fallback for REUSED composites (not in the created list).
                comp = next((c for c in (ctx.get("composites_created") or [])
                             if _ci_eq(c.get("name"), best.get("composite"))), None)
                if comp and any((s.get("type") or "").lower() == "core"
                                for s in comp.get("skins") or []):
                    acc = 0.0
                    for s in comp["skins"]:
                        if (s.get("type") or "").lower() == "core":
                            break
                        acc += s.get("thickness_mm") or 0
                    want = acc
            cps.append(_cp(f"slabs.{i}.refplane", f"{lab}: reference plane {ref}",
                           None if (off is None or want is None)
                           else abs(off - want) <= 1,
                           "reference-plane offset unavailable" if off is None
                           else f"reference plane {off:.0f} mm below the slab top"
                           + ("" if want is not None
                              else f" — set reference_plane_offset_mm for '{ref}'")))
        if e.get("hole_count") is not None or e.get("hole_size_mm"):
            # A hole ANYWHERE: the case fixes the opening's SIZE and leaves its
            # position to the agent, so neither exclude_region (a named spot) nor
            # clear_of_stair (wherever the stair is) applies. Judged on the hole's
            # bounding box, orientation-free — a 1000x2000 cut reads the same
            # whichever way round it was drawn.
            holes = best.get("holes") or []
            if e.get("hole_count") is not None:
                cps.append(_cp(f"slabs.{i}.hole_count",
                               f"{lab}: {e['hole_count']} opening(s) cut into it",
                               len(holes) == e["hole_count"], f"{len(holes)} found"))
            if e.get("hole_size_mm"):
                want = sorted(float(v) for v in e["hole_size_mm"])
                htol = e.get("hole_size_tolerance_mm", ctx["size_tol"])
                sizes = []
                for h in holes:
                    pts = [p for p in h if p]
                    if len(pts) < 3:
                        continue
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    sizes.append(sorted((max(xs) - min(xs), max(ys) - min(ys))))
                fit = [s for s in sizes
                       if all(abs(a - b) <= htol for a, b in zip(s, want))]
                cps.append(_cp(f"slabs.{i}.hole_size",
                               f"{lab}: an opening {'x'.join(f'{v:g}' for v in e['hole_size_mm'])} mm"
                               f" (±{htol:g})", bool(fit),
                               f"cut {[[round(v) for v in s] for s in sizes] or 'no opening'}"))
            if e.get("holes_clear_of_walls"):
                # A hole the case lets the agent PLACE FREELY still has one hard
                # constraint: it may not land under a wall. Free position is not
                # arbitrary position, and "anywhere" without this reads as a
                # licence to cut through the structure above.
                pad = e.get("hole_clearance_mm", 0)
                bodies = []
                for w in (ctx["final"].get("walls") or []):
                    if floor is not None and w.get("floor") != floor:
                        continue
                    if w.get("beg") and w.get("end"):
                        bodies.append((w.get("id"), w["beg"], w["end"],
                                       (w.get("width") or 200) / 2 + pad))
                clashes = []
                for h in holes:
                    pts = [p for p in h if p]
                    if len(pts) < 3:
                        continue
                    for wid, b, en, half in bodies:
                        if g.rect_hits_wall(pts, b, en, half):
                            clashes.append(wid)
                cps.append(_cp(f"slabs.{i}.hole_clear",
                               f"{lab}: the opening clears every wall"
                               + (f" by {pad} mm" if pad else ""),
                               not clashes,
                               f"cut under {sorted(set(clashes))}" if clashes
                               else f"{len(holes)} opening(s), none under a wall"))
        if e.get("exclude_region"):
            # a hole CUT into the slab clears the region just like a boundary notch
            ov = g.overlap_fraction(best.get("polygonOutline") or [], e["exclude_region"],
                                    holes=best.get("holes"))
            cps.append(_cp(f"slabs.{i}.exclude", f"{lab}: keeps clear of {e['exclude_region']}",
                           ov <= 0.10, f"covers {ov:.0%} of it"))
        if e.get("clear_of_stair"):
            # the slab's opening must clear WHEREVER the stair actually is (the
            # stair's own position is graded separately, usually region-based)
            fps = [st.get("footprint") for st in (ctx["final"].get("stairs") or [])
                   if st.get("footprint")]
            if not fps:
                cps.append(_cp(f"slabs.{i}.stair_opening",
                               f"{lab}: opening clears the stair", False,
                               "no stair in the final model"))
            else:
                fracs = [g.overlap_fraction(best.get("polygonOutline") or [], fp,
                                            holes=best.get("holes")) for fp in fps]
                cps.append(_cp(f"slabs.{i}.stair_opening",
                               f"{lab}: opening clears the stair",
                               all(f <= 0.10 for f in fracs),
                               "slab covers " + ", ".join(f"{f:.0%}" for f in fracs)
                               + " of the stair footprint(s)"))
                # ...and only there: every hole must sit within the stair's
                # padded footprint — an oversized or misplaced cut fails even
                # though the stair itself is cleared
                pad = e.get("hole_fit_pad_mm", 300)
                regions = [[fp[0] - pad, fp[1] - pad, fp[2] + pad, fp[3] + pad]
                           for fp in fps]
                outs = [o for o in (g.outside_fraction(h, regions)
                                    for h in best.get("holes") or [])
                        if o is not None]
                cps.append(_cp(f"slabs.{i}.hole_fit",
                               f"{lab}: openings only where the stair is (±{pad} mm)",
                               all(o <= 0.10 for o in outs),
                               "no holes" if not outs else
                               "hole area outside the stair zone: "
                               + ", ".join(f"{o:.0%}" for o in outs)))
    return cps


# ---------------------------------------------------------------- rooms

def check_rooms(ctx):
    exp = ctx["exp"].get("rooms")
    if not exp:
        return []
    cps, used = [], set()
    created = ctx["created"]["rooms"]

    def _squash(n):
        return re.sub(r"\s+", "", n or "").lower()

    for i, e in enumerate(exp):
        lab = e.get("name") or _label(e, i, "room")
        names = e.get("name_contains") or ([e["name"]] if e.get("name") else [])
        # "existing": a pre-existing zone (adjust-walls tasks reshape zones
        # in place, same guid — the created pool never sees them)
        pool = created + (ctx["existing"]["rooms"] if e.get("existing") else [])
        # whitespace-insensitive: the drawing label "Bedroom 1" must match a
        # zone the author/agent typed as "Bedroom1" (and vice versa)
        cands = [r for r in pool if id(r) not in used
                 and (_squash(r.get("name")) == _squash(e.get("name"))
                      or _contains(r.get("name"), names)
                      or any(k and _squash(k) in _squash(r.get("name")) for k in names))]
        best = None
        if e.get("inside"):
            best = next((r for r in cands
                         if g.point_in_outline(e["inside"], r.get("polygonOutline") or [])), None)
        if best is None and cands:
            best = cands[0]
        if best is None:
            cps.append(_cp(f"rooms.{i}.found", f"zone '{lab}' created", False,
                           f"zones: {[r.get('name') for r in pool]}"))
            continue
        used.add(id(best))
        cps.append(_cp(f"rooms.{i}.found", f"zone '{lab}' created", True,
                       f"matched '{best.get('name')}' ({best.get('id')})"))
        if e.get("inside"):
            ok = g.point_in_outline(e["inside"], best.get("polygonOutline") or [])
            cps.append(_cp(f"rooms.{i}.pos", f"zone '{lab}' covers {e['inside']}", ok,
                           f"zone outline {'contains' if ok else 'misses'} the point"))
        if e.get("outside"):
            # The zone must NOT reach this point — how a case asserts that a space was
            # DIVIDED without dictating where the division lands. `inside` alone cannot:
            # a single zone covering the whole undivided space contains that point too.
            out = not g.point_in_outline(e["outside"], best.get("polygonOutline") or [])
            cps.append(_cp(f"rooms.{i}.excludes", f"zone '{lab}' stops short of {e['outside']}",
                           out, f"zone outline {'stays clear of' if out else 'covers'} the point"))
        if e.get("number") is not None:
            # both snapshots carry the zone/room number as `numberStr` (Archicad via _KEEP,
            # Revit from BuiltInParameter.ROOM_NUMBER). Compare as text, but treat "2" and
            # "02" as the same number — the padding is a display convention, not an answer.
            got, want = (best.get("numberStr") or "").strip(), str(e["number"]).strip()
            same = got == want
            if not same:
                try:
                    same = int(got) == int(want)
                except (TypeError, ValueError):
                    pass
            cps.append(_cp(f"rooms.{i}.number", f"zone '{lab}' numbered {want}", same,
                           f"numbered '{got}'" if got else "no number set"))
        if e.get("area_m2"):
            # per-entry override: an OPEN-PLAN zone's boundary is a judgment line
            # (no wall to snap to), so its area deserves a looser band than the
            # wall-bounded rooms graded by the case-wide ratio
            ratio = e.get("area_ratio", ctx["room_area_ratio"])
            got = g.outline_area_m2(best.get("polygonOutline") or [])
            if got is None:
                cps.append(_cp(f"rooms.{i}.area", f"zone '{lab}' area ~{e['area_m2']} m²",
                               None, "zone has no usable outline"))
            else:
                ok = abs(got - e["area_m2"]) <= ratio * e["area_m2"]
                cps.append(_cp(f"rooms.{i}.area",
                               f"zone '{lab}' area ~{e['area_m2']} m² (±{ratio:.0%})",
                               ok, f"built {got:.1f} m²"))
        if e.get("min_area_m2") is not None:
            # area LOWER bound (habitable-room minimums): >= passes, so a
            # larger-than-minimum compliant room isn't punished; 0.05 m² slack
            # absorbs snapshot float noise on a room sized exactly at the limit
            got_a = g.outline_area_m2(best.get("polygonOutline") or [])
            cps.append(_cp(f"rooms.{i}.min_area",
                           f"zone '{lab}' area >= {e['min_area_m2']} m²",
                           None if got_a is None
                           else got_a >= e["min_area_m2"] - 0.05,
                           "zone has no usable outline" if got_a is None
                           else f"built {got_a:.2f} m²"))
        if e.get("min_width_mm") is not None:
            # corridor-style LOWER bound: the zone outline bbox's SHORT side is
            # the clear width (zones trace the finished wall faces); >= passes,
            # so a wider-than-minimum compliant fix isn't punished
            ol = [p for p in (best.get("polygonOutline") or []) if p]
            if len(ol) < 3:
                cps.append(_cp(f"rooms.{i}.min_width",
                               f"zone '{lab}' clear width >= {e['min_width_mm']} mm",
                               None, "zone has no usable outline"))
            else:
                xs, ys = [p[0] for p in ol], [p[1] for p in ol]
                short = min(max(xs) - min(xs), max(ys) - min(ys))
                cps.append(_cp(f"rooms.{i}.min_width",
                               f"zone '{lab}' clear width >= {e['min_width_mm']} mm",
                               short >= e["min_width_mm"] - 1,
                               f"built clear width {short:.0f} mm"))
        if e.get("min_dims_mm"):
            # per-axis LOWER bounds {"x": ..., "y": ...}: the zone outline
            # bbox's x/y extents must each reach their minimum (room-sizing
            # tasks where any compliant-or-larger room passes)
            ol = [p for p in (best.get("polygonOutline") or []) if p]
            want = e["min_dims_mm"]
            wtxt = f"x >= {want.get('x', 0)} / y >= {want.get('y', 0)} mm"
            if len(ol) < 3:
                cps.append(_cp(f"rooms.{i}.min_dims", f"zone '{lab}' clear dims {wtxt}",
                               None, "zone has no usable outline"))
            else:
                xs, ys = [p[0] for p in ol], [p[1] for p in ol]
                wx, wy = max(xs) - min(xs), max(ys) - min(ys)
                cps.append(_cp(f"rooms.{i}.min_dims", f"zone '{lab}' clear dims {wtxt}",
                               wx >= want.get("x", 0) - 1 and wy >= want.get("y", 0) - 1,
                               f"built {wx:.0f} x {wy:.0f} mm"))
        if e.get("dims_mm"):
            # clear internal dimensions: the zone outline's bbox (zones trace
            # the finished wall faces, so bbox == wall-to-wall clear dims)
            ol = [p for p in (best.get("polygonOutline") or []) if p]
            if len(ol) < 3:
                cps.append(_cp(f"rooms.{i}.dims", f"zone '{lab}' clear dims {e['dims_mm']} mm",
                               None, "zone has no usable outline"))
            else:
                xs, ys = [p[0] for p in ol], [p[1] for p in ol]
                got_d = sorted([max(xs) - min(xs), max(ys) - min(ys)])
                want = sorted(float(x) for x in e["dims_mm"])
                cps.append(_cp(f"rooms.{i}.dims", f"zone '{lab}' clear dims {e['dims_mm']} mm",
                               all(abs(gv - wv) <= ctx["tol"] for gv, wv in zip(got_d, want)),
                               f"built {[round(v) for v in got_d]} mm"))
    return cps


# ---------------------------------------------------------------- stairs

def check_stairs(ctx):
    exp = ctx["exp"].get("stairs")
    if not exp:
        return []
    cps, tol = [], ctx["tol"]
    created = ctx["created"]["stairs"]
    used = set()
    for i, e in enumerate(exp):
        lab = _label(e, i, "stair")
        cands = [s for s in created if id(s) not in used
                 and (e.get("floor") is None or s.get("floor") == e["floor"])]
        if not cands:
            cps.append(_cp(f"stairs.{i}.found", f"{lab}: stair created", False,
                           f"{len(created)} new stair(s) total"))
            continue
        best = cands[0]
        used.add(id(best))
        cps.append(_cp(f"stairs.{i}.found", f"{lab}: stair created", True,
                       f"matched {best.get('id')}"))
        fp = best.get("footprint")
        if e.get("region"):
            if fp:
                cps.append(_cp(f"stairs.{i}.region", f"{lab}: inside {e['region']}",
                               g.rect_inside(fp, e["region"], tol), f"footprint {fp}"))
            else:
                cps.append(_cp(f"stairs.{i}.region", f"{lab}: inside {e['region']}",
                               None, "no footprint readable"))
        if e.get("axis") and fp:
            axis = "y" if (fp[3] - fp[1]) >= (fp[2] - fp[0]) else "x"
            cps.append(_cp(f"stairs.{i}.axis", f"{lab}: runs along {e['axis']}",
                           axis == e["axis"], f"footprint axis {axis}"))
        if e.get("height_mm") is not None:
            h = best.get("height")
            cps.append(_cp(f"stairs.{i}.height", f"{lab}: rises {e['height_mm']} mm",
                           None if h is None else abs(h - e["height_mm"]) <= 150,
                           f"built height {h} mm"))
        if e.get("width_mm") is not None:
            # flight_width comes from the Stair_FlightWidth property (the 2D bbox is
            # inflated by the stair's symbol, so it cannot supply this); None when the
            # property read found nothing, which scores UNCHECKED rather than failed.
            w = best.get("flight_width")
            cps.append(_cp(f"stairs.{i}.width", f"{lab}: {e['width_mm']} mm wide",
                           None if w is None else abs(w - e["width_mm"]) <= ctx["size_tol"],
                           f"built width {w} mm"))
        if e.get("riser_height_mm") is not None:
            rh = best.get("riser_height")
            cps.append(_cp(f"stairs.{i}.riser_height",
                           f"{lab}: {e['riser_height_mm']} mm risers",
                           None if rh is None else abs(rh - e["riser_height_mm"]) <= 5,
                           f"built riser height {rh} mm"))
        if e.get("risers") is not None:
            # DERIVED in the snapshot (height / riser height) — Archicad exposes no
            # riser-count property. An unreadable riser height scores UNCHECKED.
            n = best.get("risers")
            cps.append(_cp(f"stairs.{i}.risers", f"{lab}: {e['risers']} risers",
                           None if n is None else n == e["risers"],
                           f"built {n} risers"
                           f" (rise {best.get('riser_height')} mm)"))
    return cps


# ---------------------------------------------------------------- constraints

def check_walls_axis(ctx):
    """walls_axis_aligned: EVERY wall in the final model must run exactly
    horizontal or vertical (straighten-the-skewed-walls tasks;
    ±axis_tolerance_mm, default 1, absorbs float noise)."""
    if not ctx["exp"].get("walls_axis_aligned"):
        return []
    tol = ctx["exp"].get("axis_tolerance_mm", 1)
    bad = []
    for w in ctx["final"].get("walls") or []:
        b, e = w.get("beg"), w.get("end")
        if not b or not e:
            continue
        skew = min(abs(e[0] - b[0]), abs(e[1] - b[1]))
        if skew > tol:
            bad.append(f"{w.get('id')} off-axis by {skew:.0f} mm")
    n = len(ctx["final"].get("walls") or [])
    return [_cp("walls.axis_aligned", "every wall runs horizontal or vertical",
                not bad, "; ".join(bad[:8]) if bad else f"all {n} walls axis-aligned")]


def check_wall_heights(ctx):
    """wall_height_mm: EVERY wall in the final model must have this height
    (uniform-height adjust tasks; ±wall_height_tolerance_mm, default 1).
    A DICT gives per-floor targets ({"0": 2750, "1": 3500}); walls on floors
    the dict does not list are unchecked."""
    want = ctx["exp"].get("wall_height_mm")
    if want is None:
        return []
    tol = ctx["exp"].get("wall_height_tolerance_mm", 1)
    walls = ctx["final"].get("walls") or []
    if isinstance(want, dict):
        bad, n = [], 0
        for w in walls:
            tgt = want.get(str(w.get("floor")))
            if tgt is None:
                continue
            n += 1
            if w.get("height") is None or abs(w["height"] - tgt) > tol:
                bad.append(f"{w.get('id')} (floor {w.get('floor')}) at {w.get('height')} mm")
        desc = " / ".join(f"floor {k}: {v} mm" for k, v in sorted(want.items()))
        return [_cp("walls.height_all", f"wall heights {desc}", not bad,
                    "; ".join(bad[:8]) if bad else f"all {n} walls at target")]
    bad = [f"{w.get('id')} at {w.get('height')} mm" for w in walls
           if w.get("height") is None or abs(w["height"] - want) > tol]
    return [_cp("walls.height_all", f"every wall {want} mm high", not bad,
                "; ".join(bad[:8]) if bad else f"all {len(walls)} walls at {want} mm")]


def check_no_clash(ctx):
    """openings_no_clash: every door/window must sit fully INSIDE its host wall
    (along the wall AND vertically) and no two openings on one wall may overlap
    — the repair-the-clashing-window tasks' pass criterion (position-free)."""
    if not ctx["exp"].get("openings_no_clash"):
        return []
    from shapely.geometry import LineString, Point
    walls = {}
    for w in ctx["final"].get("walls") or []:
        walls.setdefault(w.get("id"), w)
    bad, by_wall = [], {}
    for kind in ("doors", "windows"):
        for o in ctx["final"].get(kind) or []:
            hw = walls.get(o.get("host"))
            off, wd = o.get("center_offset"), o.get("width")
            if hw is None or off is None or wd is None:
                continue
            L = g.seg_len(hw["beg"], hw["end"])
            lo, hi = off - wd / 2, off + wd / 2
            if lo < -1 or hi > L + 1:
                bad.append(f"{o.get('id')} sticks past its wall end "
                           f"(span {lo:.0f}..{hi:.0f} of {L:.0f} mm)")
            sill, h, wh = o.get("sill"), o.get("height"), hw.get("height")
            if None not in (sill, h, wh) and (sill < -1 or sill + h > wh + 1):
                bad.append(f"{o.get('id')} pokes out vertically "
                           f"(sill {sill:.0f} + height {h:.0f} vs wall {wh:.0f} mm)")
            # ...and clear of every OTHER wall's body along the host — a
            # perpendicular wall joining at a corner covers the last
            # half-thickness of the host, where a door must not sit
            hseg = LineString([hw["beg"], hw["end"]])
            for w2 in ctx["final"].get("walls") or []:
                if w2 is hw or w2.get("floor") != hw.get("floor") \
                        or not w2.get("beg") or not w2.get("end"):
                    continue
                body = LineString([w2["beg"], w2["end"]]).buffer(
                    (w2.get("width") or 100) / 2, cap_style=2)
                inter = hseg.intersection(body)
                for seg_b in (x for x in getattr(inter, "geoms", [inter])
                              if x.geom_type == "LineString" and x.length > 0):
                    b0, b1 = sorted(hseg.project(Point(c))
                                    for c in (seg_b.coords[0], seg_b.coords[-1]))
                    if min(hi, b1) - max(lo, b0) > 10:
                        bad.append(f"{o.get('id')} overlaps {w2.get('id')} "
                                   "at a wall junction")
                        break
                else:
                    continue
                break
            by_wall.setdefault((o.get("floor"), o.get("host")), []).append(
                (lo, hi, o.get("id")))
    for (_, host), spans in by_wall.items():
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            if b[0] < a[1] - 1:
                bad.append(f"{a[2]} and {b[2]} overlap on {host}")
    return [_cp("openings.no_clash",
                "no opening clashes (inside the wall, no overlaps)",
                not bad, "; ".join(bad[:6]) if bad else "all openings clear")]


def check_counts(ctx):
    exp = ctx["exp"].get("exact_counts")
    if not exp:
        return []
    cps = []
    for bucket, n in exp.items():
        got = len(ctx["final"].get(bucket) or [])
        cps.append(_cp(f"counts.{bucket}", f"exactly {n} {bucket} in the final model",
                       got == n, f"found {got}"))
    return cps


_GEOM_KEYS = {"walls": ("beg", "end"), "doors": ("center",), "windows": ("center",),
              "slabs": ("polygonOutline", "level"), "rooms": ("polygonOutline",),
              "stairs": ("footprint",), "objects": ("center",)}


def _geom_equal(a, b, keys, tol=20.0):
    def flat(v):
        if isinstance(v, (int, float)):
            return [float(v)]
        if isinstance(v, (list, tuple)):
            return [x for p in v for x in flat(p)]
        return []

    def close(fa, fb):
        return len(fa) == len(fb) and all(abs(x - y) <= tol for x, y in zip(fa, fb))

    # walls are UNDIRECTED segments: flipping one (an orientation fix) reverses
    # beg/end but leaves the wall exactly where it was. Compare the LOCATION
    # CURVE (loc_beg/loc_end, kept by normalize's face shift) when present —
    # "did the wall move" is a curve question: a convert-type task legitimately
    # changes the thickness, which moves the FACE-shifted segment while the
    # curve stays put.
    if set(keys) == {"beg", "end"}:
        ab, ae = a.get("loc_beg") or a.get("beg"), a.get("loc_end") or a.get("end")
        bb, be = b.get("loc_beg") or b.get("beg"), b.get("loc_end") or b.get("end")
        fwd = close(flat(ab), flat(bb)) and close(flat(ae), flat(be))
        rev = close(flat(ab), flat(be)) and close(flat(ae), flat(bb))
        if fwd or rev:
            return True
        # END trims/extensions are not "moves": when a NEW wall joins an
        # existing one, Revit slides the existing curve's endpoint along its
        # own axis. Accept when the old segment lies on the new segment's
        # AXIS (perpendicular offsets within tol) and the spans still overlap
        # over at least half the old length — lateral moves stay caught.
        import math
        try:
            (ax1, ay1), (ax2, ay2) = ab[:2], ae[:2]
            (bx1, by1), (bx2, by2) = bb[:2], be[:2]
            dx, dy = bx2 - bx1, by2 - by1
            L = math.hypot(dx, dy)
            if L < 1e-9:
                return False
            ux, uy = dx / L, dy / L
            perp = max(abs(-uy * (ax1 - bx1) + ux * (ay1 - by1)),
                       abs(-uy * (ax2 - bx1) + ux * (ay2 - by1)))
            if perp > tol:
                return False
            t1 = ux * (ax1 - bx1) + uy * (ay1 - by1)
            t2 = ux * (ax2 - bx1) + uy * (ay2 - by1)
            lo, hi = min(t1, t2), max(t1, t2)
            overlap = min(hi, L) - max(lo, 0)
            return overlap >= 0.5 * abs(hi - lo)
        except Exception:
            return False
    for k in keys:
        va, vb = a.get(k), b.get(k)
        # outlines are compared as GEOMETRY, not vertex lists: a re-derived room
        # boundary can gain collinear/noise vertices (observed: a 2 mm jog after
        # a wall was moved and moved back) without the region actually changing —
        # Hausdorff distance is exactly "no boundary point moved more than tol"
        if k == "polygonOutline" and va and vb:
            try:
                from shapely.geometry import Polygon
                pa, pb = Polygon(va), Polygon(vb)
                if pa.is_valid and pb.is_valid and not pa.is_empty and not pb.is_empty:
                    if pa.hausdorff_distance(pb) > tol:
                        return False
                    continue
            except Exception:
                pass
        if not close(flat(va), flat(vb)):
            return False
    return True


def check_preserve(ctx):
    """Pre-existing elements must survive untouched (geometry; attributes may
    legitimately change in convert-type tasks). Entries: bucket name, or
    {"bucket": ..., "except_near": [[x,y], ...]} to exempt replaced elements."""
    spec = ctx["exp"].get("preserve")
    if not spec:
        return []
    cps = []
    for item in spec:
        bucket = item if isinstance(item, str) else item["bucket"]
        exempt = [] if isinstance(item, str) else (item.get("except_near") or [])
        base = ctx["base"].get(bucket) or []
        final_by_guid = {el.get("guid"): el for el in (ctx["final"].get(bucket) or [])}
        keys = _GEOM_KEYS.get(bucket, ())
        bad, total = [], 0
        for el in base:
            anchor = el.get("center") or (el.get("beg") and g.wall_midpoint(el)) or None
            if anchor is None:                   # rooms/slabs: outline centroid
                ol = [p for p in (el.get("polygonOutline") or []) if p]
                if ol:
                    anchor = [sum(p[0] for p in ol) / len(ol),
                              sum(p[1] for p in ol) / len(ol)]
            if exempt and anchor and any(g.dist(anchor, p) <= 600 for p in exempt):
                continue
            total += 1
            live = final_by_guid.get(el.get("guid"))
            if live is None:
                bad.append(f"{el.get('id')} removed")
            elif not _geom_equal(el, live, keys):
                bad.append(f"{el.get('id')} moved/reshaped")
        cps.append(_cp(f"preserve.{bucket}", f"pre-existing {bucket} untouched",
                       not bad,
                       "; ".join(bad[:8]) if bad else f"all {total} intact"))
    return cps


# ------------------------------------------------------------------ the ANSWER
# A READ atom's deliverable is the agent's FINAL TEXT, not the model: the ReAct
# loop ends on a reply carrying no tool calls and stores it as memory.json's
# `answer`, which the runner hands to grade(answer=...). These checkers are the
# only ones reading ctx["answer"] instead of a snapshot.
#
# They can only be automatic because each such case PINS ITS OUTPUT FORMAT in
# the instruction — "one line per item, `label: value`". Without that the key
# would fall back to substring matching, which an answer that simply names
# everything would satisfy. Three shapes cover the atoms:
#   answer_values  a labelled NUMBER per line   (counts, widths, areas)
#   answer_items   a labelled LIST, one per line (material / type / part names)
#   answer_pairs   an unordered SET of type pairs (clash_check)

_PAIR_TOKEN = re.compile(r"[A-Za-z_]+")
# "- Walls: 6" / "1) exterior wall type = Cavity 300" — a leading bullet or
# number is stripped, the label may carry spaces/underscores/slashes.
_LINE_RE = re.compile(r"^[\s\-*•>#]*(?:\d+[.)]\s*)?([A-Za-z][A-Za-z _/&-]*?)\s*[:=]\s*(.+?)\s*$")
_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _norm_label(s: str) -> str:
    """Labels compare on words, singularised — 'Exterior wall type' matches
    'exterior_wall_types'. Spelling of the label is the instruction's business,
    not the agent's memory."""
    words = re.split(r"[\s_/&-]+", (s or "").strip().lower())
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w)


def _answer_lines(answer: str) -> list[tuple]:
    """[(normalised label, value text)] for every 'label: value' line."""
    out = []
    for raw in (answer or "").splitlines():
        m = _LINE_RE.match(raw)
        if m:
            out.append((_norm_label(m.group(1)), m.group(2).strip()))
    return out


def _answer_stub(ctx, cps: list) -> list | None:
    """The two no-answer states, shared by every answer checker. None = the final
    text was never COLLECTED (an older results tree) -> unchecked, never a silent
    zero. "" = the run ENDED WITHOUT ANSWERING (turn cap, crash) -> failed, since
    for a read case the text is the whole deliverable."""
    answer = ctx.get("answer")
    if answer is None:
        return [{**c, "score": None, "detail": "no final answer collected"} for c in cps]
    if not answer.strip():
        return [{**c, "score": 0.0, "detail": "the run produced no final answer"}
                for c in cps]
    return None


def check_answer_values(ctx):
    """READ atoms reporting LABELLED NUMBERS — counts, a width, an area.

    `answer_values`: {"<label>": 6} or {"<label>": {"value": 16.0, "tol": 0.5,
    "unit": "m²"}}. The label is matched on singularised words, the value is the
    first number on that line (thousands separators and a trailing unit are fine).
    """
    spec = ctx["exp"].get("answer_values")
    if not spec:
        return []
    stub = [_cp(f"answer.value.{lab}", f"answer reports {lab} = "
                f"{v['value'] if isinstance(v, dict) else v}", False)
            for lab, v in spec.items()]
    early = _answer_stub(ctx, stub)
    if early is not None:
        return early
    lines = dict(_answer_lines(ctx["answer"]))
    cps = []
    for lab, want in spec.items():
        tol = want.get("tol", 0.0) if isinstance(want, dict) else 0.0
        val = float(want["value"] if isinstance(want, dict) else want)
        text = lines.get(_norm_label(lab))
        if text is None:
            cps.append(_cp(f"answer.value.{lab}", f"answer reports {lab} = {val:g}", False,
                           f"no '{lab}: ...' line; answer holds {sorted(lines) or 'no labelled line'}"))
            continue
        m = _NUM_RE.search(text)
        got = float(m.group(0).replace(",", "")) if m else None
        cps.append(_cp(f"answer.value.{lab}", f"answer reports {lab} = {val:g}",
                       got is not None and abs(got - val) <= tol,
                       f"reported '{text}'"))
    return cps


def _norm_name(s: str) -> str:
    """An item compared by EQUALITY: case and runs of whitespace do not count,
    everything else does — the name is the application's own, and the case asked
    for it verbatim."""
    return " ".join((s or "").split()).lower()


def _contains_desc(lab: str, e: dict) -> str:
    kws = e.get("contains") or []
    if e.get("exact"):
        return f"every {lab} listed is one of the {len(kws)} real names"
    return f"every {lab} listed matches {kws}"


def check_answer_items(ctx):
    """READ atoms reporting a LIST OF NAMES — materials, composites/types,
    library parts, favorites.

    `answer_items`: [{"label": "material", "min": 5, "must_match": [["brick"],
    ["concrete"]], "contains": ["garage"], "distinct": true}]. Every
    'label: value' line with that label is one item; `min` is how many the
    instruction asked for, and the two keyword shapes differ in WHICH items they
    bind (both case-insensitive, matching on containment):

      must_match  one checkpoint per group, satisfied by ANY item containing ANY
                  of the group's keywords — the key pins what must be THERE, for
                  a ground truth the case cannot enumerate.
      contains    ONE checkpoint over EVERY item: each listed item must contain
                  one of the keywords. Use it where the label names a CATEGORY
                  the whole answer has to stay inside (three GARAGE doors), so an
                  answer padded with off-category parts cannot score.
                  With `"exact": true` the same list is matched by EQUALITY
                  instead (case- and whitespace-insensitive) — for a read whose
                  ground truth IS enumerable (the project's 59 building
                  materials), where a substring key would accept an invented
                  name that merely carries a real one inside it.
    """
    spec = ctx["exp"].get("answer_items")
    if not spec:
        return []
    stub = []
    for e in spec:
        lab = e["label"]
        if e.get("min"):
            stub.append(_cp(f"answer.items.{lab}.count",
                            f"answer lists >= {e['min']} {lab}(s)", False))
        for kws in e.get("must_match") or []:
            stub.append(_cp(f"answer.items.{lab}.{kws[0]}",
                            f"answer's {lab}s include one matching {kws}", False))
        if e.get("contains"):
            stub.append(_cp(f"answer.items.{lab}.contains",
                            _contains_desc(lab, e), False))
    early = _answer_stub(ctx, stub)
    if early is not None:
        return early
    lines = _answer_lines(ctx["answer"])
    cps = []
    for e in spec:
        lab = e["label"]
        got = [v for k, v in lines if k == _norm_label(lab)]
        if e.get("distinct", True):
            seen, uniq = set(), []
            for v in got:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    uniq.append(v)
            got = uniq
        if e.get("min"):
            cps.append(_cp(f"answer.items.{lab}.count",
                           f"answer lists >= {e['min']} {lab}(s)", len(got) >= e["min"],
                           f"{len(got)} listed: {got[:8]}"))
        for kws in e.get("must_match") or []:
            hit = next((v for v in got if _contains(v, kws)), None)
            cps.append(_cp(f"answer.items.{lab}.{kws[0]}",
                           f"answer's {lab}s include one matching {kws}", bool(hit),
                           f"matched '{hit}'" if hit else f"none of {got[:8]} matches"))
        kws = e.get("contains")
        if kws:
            # EVERY item must match; an EMPTY list is a fail, not a vacuous pass —
            # an answer with no line under this label reported no category at all.
            if e.get("exact"):
                want = {_norm_name(k) for k in kws}
                bad = [v for v in got if _norm_name(v) not in want]
            else:
                bad = [v for v in got if not _contains(v, kws)]
            cps.append(_cp(f"answer.items.{lab}.contains",
                           _contains_desc(lab, e), bool(got) and not bad,
                           (f"{'not on the list' if e.get('exact') else 'off-category'}: "
                            f"{bad[:8]}") if bad else
                           (f"all {len(got)} match" if got else f"no '{lab}: ...' line")))
    return cps


def _pair_key(a: str, b: str) -> tuple:
    """An UNORDERED pair of element types, singularised — 'door conflicts with
    window' and 'windows conflict with door' are the same answer."""
    def one(w):
        w = (w or "").strip().lower()
        return w[:-1] if len(w) > 3 and w.endswith("s") else w
    return tuple(sorted((one(a), one(b))))


def check_answer_pairs(ctx):
    """READ atoms whose answer is a SET OF TYPE PAIRS (clash_check: one
    '<type> conflicts with <type>' line per clash).

    The atom's real output is the agent's final text, not the model — so this is
    the one checker reading `ctx["answer"]` instead of the snapshot. The pairs
    are graded as a SET, which is why the instruction pins the output format:
    one checkpoint per expected pair, PLUS a no-extra checkpoint, because a
    contains-style key would be satisfied by an answer that simply lists every
    type combination there is.
    """
    spec = ctx["exp"].get("answer_pairs")
    if not spec:
        return []
    want = [_pair_key(*p) for p in (spec.get("pairs") or [])]
    rel = (spec.get("relation") or "conflicts with").strip().lower()
    early = _answer_stub(ctx, [_cp(f"answer.pair.{i}", f"answer reports {a} {rel} {b}", False)
                               for i, (a, b) in enumerate(spec.get("pairs") or [])])
    if early is not None:
        return early
    # Every "<type> <relation> <type>" occurrence in the final text, whatever
    # else the line carries — the model may bullet or number its lines, and the
    # verb agrees with whichever number it wrote ("walls conflict with a wall").
    verb = r"\s+".join(w.rstrip("s") + "s?" for w in _PAIR_TOKEN.findall(rel))
    rx = re.compile(r"([A-Za-z_]+?)s?\s+" + verb + r"\s+(?:a\s+|an\s+|the\s+)?([A-Za-z_]+)",
                    re.I)
    got = {_pair_key(m.group(1), m.group(2)) for m in rx.finditer(ctx["answer"])}
    cps = [_cp(f"answer.pair.{i}", f"answer reports {a} {rel} {b}", key in got,
               "reported" if key in got else f"missing; answer holds {sorted(got) or 'no pair'}")
           for i, (key, (a, b)) in enumerate(zip(want, [p for p in (spec.get("pairs") or [])]))]
    extra = sorted(got - set(want))
    cps.append(_cp("answer.no_extra", "no pair beyond the expected ones", not extra,
                   f"extra: {extra}" if extra else f"{len(got)} pair(s), all expected"))
    return cps


ALL_CHECKS = (check_stories, check_composites, check_composites_absent, check_walls,
              lambda ctx: check_openings(ctx, "doors"),
              lambda ctx: check_openings(ctx, "windows"),
              check_slabs, check_rooms, check_stairs, check_walls_axis,
              check_wall_heights, check_no_clash, check_counts, check_preserve,
              check_answer_values, check_answer_items, check_answer_pairs)
