"""GUI TOOL FAMILY — the computer-use action space (screen + mouse + keyboard).

Every tool here is one low-level operation on the BIM application's user interface, executed
through `ComputerController` (pyautogui). The ops are application-AGNOSTIC: which button to
click, how a wall segment is committed, how many Enters an opening takes — none of that is
in the specs. What the agent may LOOK UP is the run's `--tools` MODE (`env["gui_learning"]`):

  None     (gui-raw)      no retrieval tool at all — the screen is the only source.
  "help"   (gui-docs)     `documentation_retrieval` — retrieval over the applications' OFFICIAL
           help corpora (text + dialog screenshots, `knowledge/archicad_help.py` — AC29 +
           Revit 2027, indexed together; the other application's pages are misses). This is
           what a human operator would read.
  "skills" (gui-support)  the documentation PLUS `operational_skill_retrieval` — the
           hand-written per-capability procedures under `software_skills/` (the authors'
           operational support). A procedure walks through exactly the operations the
           benchmark tests, which is why it exists only in gui-support.

The docs on each tool ARE its spec: `ToolRegistry.tool_specs()` turns them into the function
declarations the model is given.
"""
import os

from ..base import Param, Tool, coord_wording
from .controller import ComputerController

FAMILY = "gui"

_PX = "px"


# Save shortcuts are REFUSED. Saving is the harness's job — it does a Save As
# into the run's own result file after the agent stops. An agent that "tidies up" with
# Ctrl+S instead writes its half-finished model straight into the case's START PROJECT
# (`bench_cases/<subset>/<tool>/<case>/env/start/…`), silently corrupting the environment
# every later run of that case begins from. Rare but destructive: 5 of 625 runs did it,
# and five long-seq_tasks templates had to be restored from git. Refusing costs the agent
# nothing — its work is saved for it either way.
_SAVE_KEYS = {"s"}
_SAVE_MODS = {"mod", "ctrl", "cmd", "command"}


def _is_save_combo(keys):
    ks = {str(k).strip().lower() for k in (keys or [])}
    return bool(ks & _SAVE_MODS) and bool(ks & _SAVE_KEYS)


def _apply(name):
    """Handler for one op: hand it to the controller's dispatcher (which also enforces the
    shift-release safety rule between ops)."""
    def run(ctx, **args):
        if name == "hotkey" and _is_save_combo(args.get("keys")):
            return {"ok": False,
                    "error": "save shortcuts are disabled: the harness saves the project for "
                             "you after you finish, and saving here would overwrite the case's "
                             "start file. Nothing is lost — carry on with the task."}
        return ctx.controller.apply({"op": name, **args})
    return run


def _t(name, group, summary, params=None, notes="", writes=True):
    return Tool(name=name, family=FAMILY, group=group, summary=summary,
                params=params or {}, handler=_apply(name), writes=writes, notes=notes)


def _skill_menu(env):
    """The gesture recipes on offer, as a one-line-per-topic menu carried in the
    `operational_skill_retrieval` tool's own description. Without it the agent has to GUESS topic
    words; with it, it asks for recipes that actually exist. Application names are neutralised
    out (see `providers.skills.available_topics`) — the menu must not announce which
    application this run is driving."""
    from ...providers import skills
    topics = skills.available_topics((env or {}).get("targets"))
    if not topics:
        return ""
    return ("\nTOPICS ON OFFER (ask for one of these):\n"
            + "\n".join(f"  - {n}: {d}" if d else f"  - {n}" for n, d in topics))


def tools(env=None):
    """Every GUI tool, in catalog order.

    The Reference tools are picked by `env["gui_learning"]` (set by the `--tools` mode — see
    the module docstring): None (gui-raw) serves no lookup at all, "help" (gui-docs) serves
    `documentation_retrieval`, and "skills" (gui-support) ADDS `operational_skill_retrieval`
    on top."""
    # The coordinate wording follows this run's MODEL profile (tools/gui/profile.py via
    # base.coord_wording): "pixels", or "norm1000" — the same params described as a 0-1000
    # grid over the screenshot — for models that answer (and are decoded) in that frame.
    grid = coord_wording() == "norm1000"
    frame = "on the 0-1000 grid over the current screenshot" if grid else "in screen pixels"
    unit = None if grid else _PX
    xy = {"x": Param("int", f"target's x {frame}, read off the current screenshot",
                     required=True, unit=unit),
          "y": Param("int", f"target's y {frame} (y grows DOWNWARD)",
                     required=True, unit=unit)}
    xy_opt = {"x": Param("int", f"target's x {frame} — give x AND y to MOVE there "
                                "and click in ONE call (the preferred form); omit both to "
                                "click at the current cursor position", unit=unit),
              "y": Param("int", f"target's y {frame} (y grows DOWNWARD)",
                         unit=unit)}
    out = [
        # ---- pointer ----
        _t("mouse_move_to", "Mouse Interaction",
           ("move the cursor to a point on the 0-1000 screenshot grid WITHOUT clicking" if grid
            else "move the cursor to an absolute screen pixel WITHOUT clicking"),
           dict(xy),
           notes="Only for hover-positioning (before `scroll`, or to read a tracker/tooltip). "
                 "To CLICK a target, call mouse_click(x, y) directly — a separate move first "
                 "buys nothing."),
        _t("mouse_click", "Mouse Interaction",
           "left-click — with (x, y) it moves there and clicks in ONE call; without, it "
           "clicks at the current cursor position", dict(xy_opt)),
        _t("mouse_double_click", "Mouse Interaction",
           "double-click — with (x, y) it moves there and double-clicks in ONE call; "
           "without, at the current cursor position", dict(xy_opt),
           notes="Use where the application ends a multi-point input this way (e.g. finishing a "
                 "polyline/baseline), as the application's help describes."),
        _t("mouse_press_hold", "Mouse Interaction",
           "press the left button and HOLD it for `seconds` before releasing — with (x, y) "
           "it moves there first in the same call",
           {**dict(xy_opt),
            "seconds": Param("number", "how long to keep the button down before releasing "
                                       "(default 1.0; a flyout usually needs about 1 s)")},
           notes="For controls whose VARIANTS pop out on a press-and-hold (a toolbar/Info Box "
                 "icon hiding sibling modes behind a flyout). Hold, read the NEXT screenshot "
                 "to see the flyout, then mouse_click the wanted variant. A plain mouse_click "
                 "does not open a flyout — it only re-fires the icon's current mode."),
        _t("shift_hover", "Mouse Interaction",
           "hold Shift and move to (x, y) WITHOUT clicking, so the element there PRE-HIGHLIGHTS",
           dict(xy),
           notes="How a DOOR/WINDOW is selected: hover on its marker, let the NEXT screenshot "
                 "show whether the OPENING (not the host wall) is highlighted, and only THEN "
                 "`commit_select`. Shift stays held across rounds. Do this as its OWN round — "
                 "do not also click in the same batch."),
        _t("commit_select", "Mouse Interaction",
           "click where shift_hover parked the cursor (on the highlighted element) and release Shift",
           notes="Only once a screenshot has confirmed the intended element is the highlighted one."),
        _t("shift_click", "Mouse Interaction",
           "one-shot Shift+click at (x, y) — the atomic shift_hover + commit_select", dict(xy),
           notes="For when the element's exact pixel is trusted without a highlight check."),
        # ---- keyboard ----
        _t("type", "Keyboard Interaction", "type the given characters on the keyboard",
           {"text": Param("string", "the characters to type — a length is typed as its raw mm "
                                    "number, never converted", required=True)}),
        _t("select_all", "Keyboard Interaction", "select all text in the focused field (Ctrl/Cmd+A)",
           notes="ONLY immediately after clicking INTO a text/number field. With the canvas "
                 "focused this selects ALL ELEMENTS of the active tool, and a following "
                 "type/delete would corrupt the model."),
        _t("press_enter", "Keyboard Interaction", "press the Enter / Return key"),
        _t("press_esc", "Keyboard Interaction", "press the Escape key (also releases a held Shift)"),
        _t("press_tab", "Keyboard Interaction",
           "press the Tab key — move focus / cycle the active input field, where the "
           "application's help calls for it"),
        _t("delete_selected", "Keyboard Interaction",
           "delete the CURRENTLY SELECTED element(s) (the Delete key)",
           notes="You MUST select first — mouse_move_to the element on the canvas + mouse_click "
                 "(or shift_click for an opening) — THEN delete_selected. With nothing selected "
                 "it is a no-op."),
        _t("hotkey", "Keyboard Interaction",
           "press a keyboard SHORTCUT (the listed keys are held together)",
           {"keys": Param("keys", "modifier(s) + final key, e.g. the story-up/story-down or "
                                  "view-switch combos the application's help names. Use the token "
                                  "\"mod\" for the primary modifier so the same combo works on "
                                  "both OSes (Command on macOS, Ctrl elsewhere). Other usable "
                                  "keys: arrows up/down/left/right, digits, f1-f12, shift, alt, "
                                  "delete, space, home/end, pageup/pagedown",
                          required=True)}),
        # ---- view ----
        _t("scroll", "Navigation",
           "scroll the mouse wheel at the CURRENT cursor position",
           {"dy": Param("int", "vertical wheel steps; >0 scrolls UP/away, <0 DOWN/toward"),
            "dx": Param("int", "horizontal wheel steps (right > 0)")},
           notes="Over a LIST / DROPDOWN / DIALOG it scrolls to reveal off-screen rows; OVER THE "
                 "WHITE CANVAS the wheel ZOOMS (dy<0 = zoom out, dy>0 = zoom in). Always "
                 "mouse_move_to the target panel first — it acts where the cursor is."),
    ]
    # The retrieval tools follow the MODE, and nothing else: gui-raw serves none, gui-docs the
    # official documentation, gui-support the documentation AND the operational skills. A mode
    # that promises the documentation refuses to run without the corpus — silently dropping
    # the tool would turn a "with documentation" arm into a "without" one.
    ref = []
    learning = (env or {}).get("gui_learning")
    if learning in ("help", "skills"):
        from ... import knowledge as corpora
        if not corpora.archicad_help.available():
            raise SystemExit(
                "this --tools mode serves documentation_retrieval, but the official help "
                "corpus is not built. Run:\n"
                "  python -m authoring_framework.knowledge.fetch_archicad_help\n"
                "  python -m authoring_framework.knowledge.fetch_revit_help")
        ref.append(_app_help_tool())
    if learning == "skills":
        ref.append(_skill_tool(env))
    out += ref
    return out


def _app_help_tool():
    """The GUI route's learning channel: retrieval over the application's OFFICIAL help.

    The query guidance in the spec is what makes it work — the corpus titles are the
    application's own task names, so a query in the UI's vocabulary lands and an invented
    paraphrase misses. Nothing here names the application: the help is simply 'this
    application's', and a corpus for another application is a lookup that returns nothing."""
    return Tool(
        name="documentation_retrieval", family=FAMILY, group="External Support", writes=False,
        summary="LOOK IT UP: search the application's official help for how an operation is "
                "done in this user interface",
        handler=_documentation_retrieval,
        params={"query": Param("string",
                               "2-6 words in the application's OWN vocabulary: the element or "
                               "tool noun plus ONE operation verb (create / place / edit / "
                               "move / stretch / delete / settings), or the EXACT label you "
                               "can read on a menu, dialog or tool in the screenshot",
                               required=True),
                "max_pages": Param("int", "how many help articles to return (default 3)")},
        notes="The AUTHORITATIVE reference for this application's UI: exact tool/menu/dialog "
              "labels, option names, where a setting lives, and the click/commit sequence an "
              "operation takes. Look an operation up BEFORE performing it for the first time, "
              "and again whenever a gesture keeps failing — one lookup is cheaper than three "
              "wrong clicks. HOW TO QUERY: ONE operation per query (split 'draw walls and "
              "place a door' into two lookups); prefer the words the UI itself shows — read "
              "them off the current screenshot; on a miss, retry with the exact on-screen "
              "label or another word the application might use. The result's "
              "`related_articles` are REAL page titles — re-query one verbatim to open it. "
              "The matching help pages' screenshots are attached as images alongside the "
              "result: the dialog pictures usually carry the labels the text refers to.")


def _documentation_retrieval(ctx, query, max_pages=3):
    """Search the official-help corpus and RETURN the best articles as this call's result (the
    text lands in the conversation and stays there); the pages' screenshots are PARKED on the
    context and the loop attaches them as real images right after the results."""
    from ... import knowledge as corpora
    found = corpora.archicad_help.lookup([str(query or "")], max_pages=int(max_pages or 3))
    if not found:
        return {"ok": True, "found": False, "query": query,
                "note": "no help article matched — re-query with the exact words the UI shows "
                        "(a tool name, dialog title or option label read off the screenshot), "
                        "one operation per query"}
    ctx.attach_images(found["images"], f"application-help screenshots (for {query!r})")
    out = {"ok": True, "found": True,
           "articles": [{"title": e["title"], "text": e["text"]} for e in found["excerpts"]],
           "note": "the matching help-page screenshots are attached alongside this result — "
                   "the dialog pictures usually carry the labels the text refers to"}
    if found.get("more"):
        out["related_articles"] = found["more"]
        out["note"] += ("; related_articles lists further matching page titles — re-query one "
                        "VERBATIM to open it")
    return out


def _skill_tool(env):
    """The hand-written gesture recipes — the *-skills modes' learning channel. Pre-packaged
    knowledge (a recipe walks through exactly the operations the benchmark tests), which is
    why the raw modes serve the official help instead and never this."""
    return Tool(
        name="operational_skill_retrieval", family=FAMILY, group="External Support", writes=False,
        summary="LOOK IT UP FIRST: read this application's written recipe for an operation "
                "you are unsure how to perform — the PREFERRED lookup over documentation_retrieval",
        handler=_operational_skill_retrieval,
        params={"topic": Param("string", "2-6 words naming the element kind and the "
                                         "operation you need the gesture for",
                               required=True),
                "application": Param("string", "which application's recipe you want — the "
                                               "one you have worked out you are working "
                                               "in. Gestures differ per application, so "
                                               "naming it gets you the right recipe "
                                               "instead of every application's at once")},
        notes="The recipe comes back as this call's RESULT: the exact controls, keys and "
              "click/commit sequence this application takes, plus the traps (which "
              "highlight really means the element is the target, which control opens the "
              "WRONG dialog, the reliable fallback when a pick keeps missing). Read it "
              "BEFORE inventing a gesture or repeating one that failed — the gestures are "
              "application-specific and are NOT in your prompt. When the operation is on "
              "the menu below, this recipe beats a documentation_retrieval lookup: consult it "
              "FIRST and fall back to the official help only for what no recipe covers."
              + _skill_menu(env))


def _operational_skill_retrieval(ctx, topic, application=None):
    """Look a gesture recipe up and RETURN it. The framework owns the corpus (retrieval, the
    shared interaction primitives, the pruning); the tool result carries the text, so it lands
    in the conversation exactly where it is needed and stays there for the rest of the run.

    The application is the AGENT's own statement of where it thinks it is — nothing in the
    harness picks between the applications. Naming none serves every application's variant side
    by side rather than choosing for it."""
    from ...providers import skills
    topic = str(topic or "").strip()
    # The agent states the application in its OWN words ("Autodesk Revit 2027.1") — resolve
    # that onto the recipe suffixes by substring. An unrecognized name must fall back to
    # serving every application's variant, never filter the corpus down to nothing.
    want = str(application or "").strip().lower() or None
    if want:
        want = next((sw for sw in skills._SOFTWARE if sw in want), None)
    serve = [want] if want else list(getattr(ctx, "targets", ()) or [None])
    blocks = []
    for app in serve:
        lead = skills.topic_hint(topic, app)       # "move wall"/... beats keyword noise;
        text = skills.retrieve(f"{topic} {lead}", target=app, lead=lead)   # target-aware
        if text:
            blocks.append((app, text))
    if not blocks:
        return {"ok": True, "found": False, "topic": topic,
                "note": "nothing is written up for this topic — work from what is on screen; "
                        "do not repeat a gesture that already failed. The topics on offer are "
                        "listed in this tool's description."}
    if len(blocks) == 1:
        return {"ok": True, "found": True, "topic": topic,
                "application": blocks[0][0], "recipe": blocks[0][1]}
    # No application named: serve every variant side by side rather than picking one.
    return {"ok": True, "found": True, "topic": topic,
            "note": "you did not say which application, so every application's version "
                    "follows — use the one for the application you are actually in, and name "
                    "it next time to get only that one",
            "recipes": {app: text for app, text in blocks}}


__all__ = ["FAMILY", "tools", "ComputerController"]
