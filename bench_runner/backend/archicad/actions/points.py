"""Shared point normalization for the action modules.

The actor's mm->m converter can hand a point through as an [x, y] sequence OR an {x, y}
dict — every polygon/baseline consumer must accept both. This helper used to exist as
per-module `_pt` copies (zones, stairs) while slabs unpacked `for x, y in polygon_xy`
directly, which explodes on a dict point (it unpacks to its KEYS -> "could not convert
string to float: 'x'"). One normalizer, imported everywhere.
"""


def pt(p):
    """Normalize one point — [x, y] sequence OR {x, y} dict — to (float, float).
    Raises on anything else, so callers can validate BEFORE destructive steps."""
    if isinstance(p, dict):
        return float(p["x"]), float(p["y"])
    return float(p[0]), float(p[1])
