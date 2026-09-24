"""The TOOL contract shared by every tool family.

A TOOL is one thing the agent can do. There is ONE family, `gui` (`tools/gui/`): the low-level
screen/mouse/keyboard operations plus the two retrieval lookups — the computer-use action space.

Everything the LLM sees about a tool comes from its spec here (name, one-line summary, typed
params with units and docs) — `ToolRegistry.tool_specs()` renders the whole action space as
provider-neutral FUNCTION DECLARATIONS, so there is ONE source of truth for what exists and
what it takes. Everything the executor needs is here too: `validate_call` rejects an invented
tool name, a missing required param, or a param of the wrong shape.
"""
import math
import re
from dataclasses import dataclass, field

FAMILIES = ("gui",)                  # the action space: the application's user interface


@dataclass(frozen=True)
class Param:
    """One tool parameter: its shape, its unit, and what it means (the LLM reads `doc`)."""
    type: str                  # int | number | string | bool | point | points | segments | list | object | keys
    doc: str = ""
    required: bool = False
    unit: str | None = None    # "px" -> screen pixels; None -> unitless
    items: dict | None = None  # JSON Schema for the ELEMENTS of a "list" param. Required in
                               # practice: an array without an item schema is rejected outright
                               # by some providers' function-declaration validators, and on the
                               # rest it tells the model nothing about what to put in the list.


# Param.type -> JSON Schema fragment, for the provider-native function declarations. It MIRRORS
# `_shape_ok` (the execution-time gate below), never tightens it — a schema stricter than the
# gate would steer the model away from calls the harness happily accepts. Mirroring choices:
# "int" renders as number (the gate takes any finite real for both); a point renders as the
# documented [x, y] array (the gate also accepts {"x","y"} — the schema steers to the canonical
# form). "$id.field" cross-reference strings are deliberately NOT unioned into every param —
# outside string params (which admit them anyway) they are rare, and doubling the schema for
# them costs more than the tolerant execution-time acceptance does.
_PARAM_SCHEMA = {
    "int": {"type": "number"},
    "number": {"type": "number"},
    "string": {"type": "string"},
    "bool": {"type": "boolean"},
    "point": {"type": "array", "items": {"type": "number"}, "minItems": 2},
    "points": {"type": "array", "minItems": 2,
               "items": {"type": "array", "items": {"type": "number"}, "minItems": 2}},
    "segments": {"type": "array", "minItems": 1,
                 "items": {"type": "array", "items": {"type": "number"}, "minItems": 4}},
    "keys": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "list": {"type": "array", "items": {"type": "string"}},   # overridden by Param.items
    "object": {"type": "object"},
}

@dataclass(frozen=True)
class Tool:
    """One callable tool: `handler` is a plain callable (ctx, **args)."""
    name: str
    family: str
    group: str                                  # catalog heading it is listed under
    summary: str                                # one line: what it does
    params: dict = field(default_factory=dict)  # name -> Param
    handler: object | None = None               # callable(ctx, **args)
    writes: bool = True                         # mutates the model / UI (False = pure read)
    notes: str = ""                             # extra guidance appended to the description

    def required(self):
        return [n for n, p in self.params.items() if p.required]

    def args_schema(self):
        """This tool's ARGUMENTS as a JSON Schema object — the `parameters` /`input_schema` of
        a provider-native function declaration. Every property carries its `doc` as the schema
        description (that is where the model reads what a param means), with the unit spelled
        out, since a bare number in a BIM model is ambiguous by a factor of 1000."""
        props = {}
        for n, p in self.params.items():
            s = dict(_PARAM_SCHEMA.get(p.type) or {"type": "string"})
            if p.type == "list" and p.items:
                s["items"] = p.items
            doc = p.doc or ""
            if p.unit == "px":
                doc = (doc + " " if doc else "") + "(screen pixels)"
            if doc:
                s["description"] = doc
            props[n] = s
        out = {"type": "object", "properties": props}
        req = self.required()
        if req:
            out["required"] = req
        return out

    def spec(self):
        """This tool as a provider-neutral FUNCTION DECLARATION: {name, description,
        parameters}. `llm.chat` translates it into each provider's own shape. The description
        is the one-line summary plus the tool's notes — everything the old markdown catalog
        carried per tool, minus the formatting."""
        desc = self.summary
        if self.notes:
            desc += "\n" + " ".join(ln.strip() for ln in self.notes.strip().splitlines())
        if not self.writes:
            desc += "\nREAD-ONLY: this changes nothing in the model."
        return {"name": self.name, "description": desc, "parameters": self.args_schema()}


# ---------------------------------------------------------------- registry

class ToolRegistry:
    """The tools available to THIS run — built from the enabled families (`--tools`)."""

    def __init__(self, families):
        self.families = tuple(families)
        self._tools = {}
        self._specs = None      # tool_specs memo — the provider adapters key their
                                # works/doesn't memos on the object staying identical per turn

    def add(self, tool):
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name {tool.name!r} "
                             f"({self._tools[tool.name].family} vs {tool.family})")
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools.get(name)

    def has(self, name):
        return name in self._tools

    def names(self, family=None):
        return sorted(n for n, t in self._tools.items() if family in (None, t.family))

    def all(self, family=None):
        return [t for _, t in sorted(self._tools.items())
                if family in (None, t.family)]

    def has_family(self, family):
        return family in self.families

    # ------------------------------------------------------------ what the model is given
    def tool_specs(self):
        """Every tool as a provider-neutral FUNCTION DECLARATION, in catalog order. This is the
        WHOLE action space the model is handed — `llm.chat` translates it into each provider's
        native tool format, so there is no separate prose catalog that could drift from it.
        Memoized: the registry is immutable within a run, and the provider adapters memoize
        their own conversions on it."""
        if self._specs is None:
            self._specs = [t.spec() for t in self.all()]
        return self._specs

    def briefing(self):
        """The FAMILY-level facts that are true of a whole action space rather than of any one
        tool — units, the batching rule, how the screen is shown. They cannot live
        in a function declaration (each one would have to repeat them), so they go in the system
        prompt; built from the registry so a family that is not enabled is never mentioned."""
        out = []
        for fam in self.families:
            if not any(t.family == fam for t in self._tools.values()):
                continue
            text = _FAMILY_BRIEF[fam]
            if fam == "gui" and coord_wording() == "norm1000":
                # The wording must match the frame the harness DECODES (GUI_COORD_FRAME): a
                # model that natively answers on a 0-1000 grid is told so, instead of being
                # asked for "screen pixels" it then only sometimes produces (muse-spark-1.1
                # flipped between the two frames within one run under the pixel wording).
                text = text.replace(_PIXEL_SENTENCE, _GRID_SENTENCE)
            out.append(text)
        return "\n\n".join(out)


_PIXEL_SENTENCE = "Every coordinate is a SCREEN PIXEL read off the latest screenshot."
_GRID_SENTENCE = ("Every coordinate is a point on a 0-1000 GRID laid over the latest screenshot: "
                  "x runs 0 (left edge) to 1000 (right edge), y runs 0 (top edge) to 1000 "
                  "(bottom edge), whatever the screenshot's pixel size.")


def coord_wording():
    """How the GUI tools DESCRIBE a coordinate to the model: "pixels" or "norm1000". It
    FOLLOWS the frame the harness decodes for this run's MODEL (`tools/gui/profile.py`), so a
    model is never asked for pixels and decoded as a grid; `GUI_COORD_WORDING` overrides."""
    from .gui import profile
    return profile.resolve()["wording"]


_FAMILY_BRIEF = {
    "gui": ("GUI TOOLS — the application's user interface (screen + mouse + keyboard).\n"
            + _PIXEL_SENTENCE + " Click a target "
            "with `mouse_click(x, y)` — ONE call moves there and clicks (`mouse_move_to` is "
            "only for hover-positioning, e.g. before `scroll`). To replace a "
            "field's content: click it, then `select_all`, then `type`. If a target is not "
            "visible, `scroll` it into view (move the cursor over that panel first) rather than "
            "guessing a coordinate. Lengths are TYPED as their raw millimetre number.\n"
            "BATCH your calls — this is the rule, not an option: a one-call turn spends a whole "
            "turn of your fixed budget on a single mouse twitch, and a run that clicks one turn "
            "at a time runs out of turns half-done. Issue the WHOLE gesture sequence you are "
            "already committed to (click, click, select_all, type, Enter, ...) as "
            "several tool calls in ONE turn: they execute in order with a short pause between, "
            "and a call rejected mid-batch truncates the rest, so nothing fires at a stale "
            "cursor. These are SEQUENTIAL steps of one gesture, not parallel actions — issuing "
            "them together is safe BECAUSE they run strictly in the given order.\n"
            "THE SCREEN IS SHOWN TO YOU, you never ask for it: a fresh screenshot is captured "
            "at the start of EVERY turn and arrives with the previous turn's one for "
            "comparison. A batch's outcome is therefore visible at the start of your NEXT "
            "turn, never inside the batch — end a batch where the very next coordinate "
            "depends on a screen you have not seen yet (an unfamiliar dialog, a menu that may "
            "or may not be open)."),
}


# ---------------------------------------------------------------- call validation

def normalize_call(call):
    """Accept the tool-call envelope in any of the shapes a model plausibly emits and return
    the canonical {"tool", "args", "id"}: the documented {"tool", "args"}, plus the legacy
    {"op", ...flat fields} and {"action", "params"} shapes. Format drift must cost a
    deterministic rewrite, not a wasted round."""
    if not isinstance(call, dict):
        return None
    name = call.get("tool") or call.get("op") or call.get("action") or call.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    args = call.get("args")
    if not isinstance(args, dict):
        args = call.get("params") if isinstance(call.get("params"), dict) else None
    if args is None:                       # flat form: everything that is not envelope metadata
        args = {k: v for k, v in call.items()
                if k not in ("tool", "op", "action", "name", "id", "args", "params",
                             "reasoning", "reason", "why")}
    args = dict(args)
    # Qwen's computer-use habit (probed 2026-09-12): the point arrives as ONE field —
    # `coordinate: [x, y]`, sometimes as the string "[x, y]" — whatever the declared schema
    # says. A deterministic split, so the click is not rejected for a missing `x`.
    if "x" not in args and "y" not in args:
        for k in ("coordinate", "coordinates", "point", "position"):
            v = args.get(k)
            if isinstance(v, str):
                m = re.match(r"^\s*[\[(]?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\])]?\s*$", v)
                v = [float(m.group(1)), float(m.group(2))] if m else None
            if isinstance(v, (list, tuple)) and len(v) >= 2 \
                    and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in v[:2]):
                args.pop(k)
                args["x"], args["y"] = v[0], v[1]
                break
    # The other Qwen shape (measured 2026-09-14 on qwen3.7-plus, 70 of 424 clicks in the
    # post-decode Atomic runs and 6/6 in an in-condition probe): the declared `x`/`y` ints
    # arrive as LISTS — `x: [383, 70], y: [70]` or `x: [46, 69], y: [69, 69]` — the point
    # jammed into `x` and `y` echoing its own value. The validator rightly refused a list
    # where an int is declared, so every such click was dropped and the turn wasted. A
    # deterministic unjam: a 2-list in `x` IS the point; a 1-list is that field's value.
    def _unlist(v, second):
        if isinstance(v, (list, tuple)) and v and \
                all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in v[:2]):
            return (v[1] if second and len(v) >= 2 else v[0]), True
        return v, False
    if isinstance(args.get("x"), (list, tuple)):
        x2, ok = _unlist(args["x"], False)
        if ok:
            if len(args["x"]) >= 2:
                args["x"], args["y"] = args["x"][0], args["x"][1]
            else:
                args["x"] = x2
    if isinstance(args.get("y"), (list, tuple)):
        y2, ok = _unlist(args["y"], True)
        if ok:
            args["y"] = y2
    out = {"tool": name.strip(), "args": args}
    if call.get("id"):
        out["id"] = str(call["id"])
    return out


def _num(v):
    """A finite real number (NaN/inf must fail: json.loads accepts NaN, and NaN survives every
    min/max clamp straight into the backend)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_point(v):
    if isinstance(v, dict):
        return _num(v.get("x")) and _num(v.get("y"))
    return isinstance(v, (list, tuple)) and len(v) >= 2 and _num(v[0]) and _num(v[1])


def _coerce(kind, v):
    """Accept numbers (and booleans) that arrive as STRINGS — `x="183"` for a declared int —
    which some models emit in tool-call arguments; rejecting them would fail every click of
    such a model on a formality. Deterministic and lossless (only a string that parses as a number / true / false is touched); anything
    else is returned unchanged for `_shape_ok` to judge."""
    def num(s):
        if isinstance(s, str):
            t = s.strip()
            try:
                f = float(t)
            except ValueError:
                # the other observed shape: BOTH coordinates jammed into the first field
                # (x="222, 42", y=42) — the first number is the value of this field
                m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*-?\d+(?:\.\d+)?\s*$", t)
                if not m:
                    return s
                t = m.group(1)
                f = float(t)
            if not math.isfinite(f):
                return s
            return int(f) if f.is_integer() and "." not in t and "e" not in t.lower() else f
        return s

    if kind in ("int", "number"):
        return num(v)
    if kind == "bool" and isinstance(v, str):
        return {"true": True, "false": False}.get(v.strip().lower(), v)
    if kind == "point":
        if isinstance(v, dict):
            return {k: num(x) for k, x in v.items()}
        return [num(x) for x in v] if isinstance(v, (list, tuple)) else v
    if kind in ("points", "segments") and isinstance(v, (list, tuple)):
        return [([num(x) for x in p] if isinstance(p, (list, tuple))
                 else {k: num(x) for k, x in p.items()} if isinstance(p, dict) else p)
                for p in v]
    return v


def _shape_ok(kind, v):
    """Does the value match the param's declared shape? Deliberately permissive — this rejects
    what would CRASH or silently corrupt, not every type imperfection."""
    if kind in ("int", "number"):
        return _num(v)
    if kind == "string":
        return isinstance(v, str) or _num(v)          # a number where a string is wanted is fine
    if kind == "bool":
        return isinstance(v, bool)
    if kind == "point":
        return _is_point(v)
    if kind == "points":
        return isinstance(v, (list, tuple)) and len(v) >= 2 and all(_is_point(p) for p in v)
    if kind == "segments":
        return (isinstance(v, (list, tuple)) and bool(v)
                and all(isinstance(s, (list, tuple)) and len(s) >= 4
                        and all(_num(x) for x in s[:4]) for s in v))
    if kind == "keys":                                # hotkey: a STRING would iterate as chars
        return (isinstance(v, list) and bool(v)
                and all(isinstance(k, (str, int)) and not isinstance(k, bool) for k in v))
    if kind == "list":
        return isinstance(v, (list, tuple))
    if kind == "object":
        return isinstance(v, dict)
    return True


_REF_PREFIX = "$"          # "$<id>.<field>" — resolved by the backend batch runner


def validate_call(call, registry):
    """Validate ONE normalized call against the registry.

    Returns (checked_call, error). `error` is a human-readable string when the call cannot run
    at all (unknown tool, missing required param, unusable param shape) — the caller drops it.
    Unknown extra params are STRIPPED (an LLM habitually carries plan fields through; passing
    them on would TypeError the backend method) and reported in `checked_call["_dropped"]`.
    A "$id.field" cross-reference passes any shape check — its real value only exists at
    execution time."""
    tool = registry.get(call["tool"])
    if tool is None:
        return None, f"unknown tool {call['tool']!r}"
    args, dropped = {}, []
    for k, v in (call.get("args") or {}).items():
        if k in tool.params:
            args[k] = v
        else:
            dropped.append(k)
    for name in tool.required():
        if args.get(name) is None:
            return None, f"{tool.name}: missing required param {name!r}"
    for name, v in list(args.items()):
        if isinstance(v, str) and v.startswith(_REF_PREFIX):
            continue                                   # cross-reference, resolved at execution
        if v is None:                                  # an explicit null = "leave it out"
            continue
        v = args[name] = _coerce(tool.params[name].type, v)
        if not _shape_ok(tool.params[name].type, v):
            return None, (f"{tool.name}: param {name!r} should be "
                          f"{tool.params[name].type}, got {v!r}")
    out = {"tool": tool.name, "args": args}
    if call.get("id"):
        out["id"] = call["id"]
    if dropped:
        out["_dropped"] = dropped
    return out, None
