"""Executing tool calls: the context they run in, the validation gate, and the runner.

The agent emits a small BATCH of tool calls per round. `plan_batch` turns that raw model
output into calls that are safe to run (envelope normalization, validation against the
registry); `run_batch` executes them in order and returns one result record each.
"""
import time

from . import base
from .base import ToolRegistry, normalize_call, validate_call

# Pause between consecutive GUI ops so the application can react to each before the next
# (a heavyweight BIM UI drops input otherwise).
GUI_OP_DELAY_S = 0.5


class ToolContext:
    """Everything the tools need at execution time. One per run."""

    def __init__(self, registry, mem=None, targets=None):
        self.registry = registry
        self.mem = mem                 # the run's MemoryStore
        self.targets = tuple(targets or ())   # the applications a recipe lookup may serve
        self._controller = None
        self._pending = []             # (images, note) parked by a lookup, for the next message

    @property
    def controller(self):
        """The GUI controller (lazily — importing pyautogui touches the display)."""
        if self._controller is None:
            from .gui import ComputerController
            self._controller = ComputerController()
        return self._controller

    def has(self, family):
        return self.registry.has_family(family)

    # ---- images a tool produced, handed to the caller that can SHOW them ----
    # A tool RESULT is JSON and cannot carry image bytes, so the tools that produce images park
    # them here and the agent loop attaches them as real images alongside that result.
    # (The SCREEN does not come through here: the loop captures it itself at the start of
    # every turn — `react._capture_screen`.)
    def attach_images(self, images, note=""):
        """A lookup parks its page images here: the excerpt TEXT is the tool result,
        but these sources carry their real content in dimensioned diagrams."""
        images = [i for i in (images or []) if i]
        if images:
            self._pending.append((images, note))

    def take_images(self):
        """Pop the parked lookup images: [(png_bytes, ...), note]. Consumed — the excerpt text
        stays in the conversation, so the pictures need attaching only once."""
        out, self._pending = self._pending, []
        return out

    def close(self):
        """Release anything held across the run (a Shift left down by a hover)."""
        if self._controller is not None:
            try:
                self._controller._release_shift()
            except Exception:
                pass


# ---------------------------------------------------------------- family hooks

def _family_module(family):
    if family == "gui":
        from . import gui
        return gui
    raise ValueError(f"unknown tool family {family!r}")


# ---------------------------------------------------------------- validation gate

def plan_batch(calls, ctx):
    """Validate + prepare one raw batch of model-emitted tool calls.

    Returns (batch, dropped): `batch` is ready to execute, `dropped` is [(call, reason)] for
    logging. GUI ops carry POSITIONAL dependencies (move -> click -> type), so on the first
    unusable op the rest of the sequence is TRUNCATED — running it would click or type at a
    stale cursor position, which on a live UI can start a wall, commit a dialog or delete a
    selection. (A batch of lookups alone carries no such dependency: an unusable one is
    dropped and the rest still run.)
    """
    raw = [normalize_call(c) for c in (calls or [])]
    reg = ctx.registry

    def _maybe_gui(r):
        """Does this call carry a positional dependency? A GUI tool does, and so might an
        UNKNOWN name on a run that has GUI tools."""
        if not r:
            return False
        tool = reg.get(r["tool"])
        return tool.family == "gui" if tool is not None else reg.has_family("gui")

    gui_in_batch = any(_maybe_gui(r) for r in raw)
    batch, dropped = [], []
    pairs = list(zip(calls or [], raw))
    for i, (original, call) in enumerate(pairs):
        err = None
        checked = None
        if call is None:
            err = "not a tool call"
        else:
            checked, err = validate_call(call, reg)
        if err:
            dropped.append((original, err))
            if gui_in_batch:
                # positional dependency — do not run the remainder, and say so: the tail is
                # dropped too, which a "dropped 1 call" line would hide.
                dropped += [(o, "not run — the batch was truncated at an earlier unusable call")
                            for o, _ in pairs[i + 1:]]
                break
            continue
        checked.pop("_dropped", None)        # unknown args are stripped silently
        batch.append(checked)
    return batch, dropped


# ---------------------------------------------------------------- runner

def run_batch(batch, ctx, ran=None):
    """Execute a prepared batch IN ORDER; return one result record per call:
    {tool, id?, family, ok, result | error}.

    `ran` (optional list) is appended with each call AS IT COMPLETES, so a mid-batch crash
    still tells the caller how many calls actually reached the application.

    A GUI WRITE op that raises PROPAGATES (a broken input device or a fail-safe abort must stop
    the run, not be swallowed into a "failed" record); a failed lookup comes back as a record
    with ok=False.
    """
    out = []
    prev_family = None
    for call in batch:
        tool = ctx.registry.get(call["tool"])
        if tool is None:                     # cannot happen after plan_batch — belt and braces
            out.append({"tool": call["tool"], "family": "?", "ok": False,
                        "error": "unknown tool"})
            continue
        if prev_family is not None:
            # pace EVERY call in a multi-call batch (2026-08-20; it used to apply only
            # around GUI ops): the previous call's effect gets 0.5 s to land before the
            # next call reads or acts on the application.
            time.sleep(GUI_OP_DELAY_S)
        args = call.get("args") or {}
        rec = {"tool": tool.name, "family": tool.family, "writes": bool(tool.writes)}
        if call.get("id"):
            rec["id"] = call["id"]
        if tool.family == "gui" and tool.writes:
            # A WRITE op that raises propagates: a broken input device must stop the run
            # (running on would click/type blind). A READ-ONLY gui tool (the
            # Reference lookups) failing is just a failed lookup — report it and run on.
            rec["result"] = tool.handler(ctx, **args)
            rec["ok"] = True
        elif tool.family == "gui":
            try:
                rec["result"] = tool.handler(ctx, **args)
                rec["ok"] = True
            except Exception as e:
                rec["ok"] = False
                rec["error"] = f"{type(e).__name__}: {e}"
        else:
            try:
                res = tool.handler(ctx, **args)
                rec["ok"] = not (isinstance(res, dict) and res.get("ok") is False)
                if rec["ok"]:
                    rec["result"] = res
                else:
                    rec["error"] = res.get("error", "failed")
            except (Exception, SystemExit) as e:
                rec["ok"] = False
                rec["error"] = f"{type(e).__name__}: {e}"
        prev_family = tool.family
        out.append(rec)
        if ran is not None:
            ran.append(call)
    return out


# ---------------------------------------------------------------- registry building

def build_registry(families=("gui",), targets=None, gui_learning=None):
    """Build the registry for this run.

    `gui_learning` is the mode's retrieval channel: None (no retrieval tool — gui-raw), "help"
    (`documentation_retrieval` — gui-docs) or "skills" (`operational_skill_retrieval` on top of
    it — gui-support).

    `targets` NARROWS which applications' procedures the skill lookup serves. The default is
    every application: the harness does not decide which one the agent is driving — the agent
    identifies it from the screen."""
    families = tuple(f for f in base.FAMILIES if f in set(families))
    if not families:
        raise SystemExit("no tool families enabled (check the --tools mode)")
    env = {"targets": tuple(targets) if targets else None, "families": families,
           "gui_learning": gui_learning}
    reg = ToolRegistry(families)
    for fam in families:
        for tool in _family_module(fam).tools(env):
            reg.add(tool)
    return reg
