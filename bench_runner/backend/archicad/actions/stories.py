"""Story (floor) actions: read / set the project's story structure + elevations.

The official archicad package only reads navigator items; story elevations are
driven through Tapir's GetStories / SetStories (v1.1.5+).

Schema (Tapir):
  GetStories -> {firstStory, lastStory, actStory, skipNullFloor,
                 stories: [{index, floorId, dispOnSections, level, name}]}
  SetStories <- {stories: [{name, level, dispOnSections}]}   # whole ordered stack

`level` is the story elevation in meters. SetStories replaces the ENTIRE story stack.

CHANGING THE ACTIVE STORY is a different mechanism and took a while to find: Tapir has no
"SetActiveStory" (12 candidate names were probed and none is registered), because the active
story is not a property you set — it is WHICH WINDOW IS OPEN, exactly as in the UI. So it is
`ChangeWindow` (Tapir >= 1.3.1) pointed at the story's Project Map navigator item, whose guid
comes from the OFFICIAL `API.GetNavigatorItemTree`. See `set_active_story` below.
"""
from ..client import exec_error


def get_stories(client):
    """Return the project's story structure (indices + each story's level/name)."""
    try:
        resp = client.tap("GetStories")
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    return {"ok": True, **resp}


def story_level(client, floor_index):
    """Elevation (m) of the storey at `floor_index`, or None when unresolvable.

    Used by the delete+recreate modifies (stair/object) to keep a replaced element at its
    OLD storey's level when the caller gives no explicit z — without it a corrective
    "widen the stair" on an upper floor would silently rebuild the stair at z=0."""
    if floor_index is None:
        return None
    st = get_stories(client)
    if not st.get("ok"):
        return None
    return next((s.get("level") for s in st.get("stories") or []
                 if s.get("index") == floor_index), None)


def set_stories(client, stories):
    """Set the WHOLE story stack (ordered).

    stories : [{"name", "level", "dispOnSections"?}] bottom->top. `level` in meters.
              dispOnSections defaults to True when omitted.
    """
    if not stories:
        return {"ok": False, "error": "stories list required"}
    payload = [{"name": str(s.get("name", f"Story {i}")),
                "level": float(s["level"]),
                "dispOnSections": bool(s.get("dispOnSections", True))}
               for i, s in enumerate(stories)]
    try:
        resp = client.tap("SetStories", {"stories": payload})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    # SetStories is a Tapir write like the modifies: failure may arrive via executionResults
    # with no exception — a silently-rejected storey stack must not report ok.
    err = exec_error(resp, "SetStories failed")
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "stories": payload}


def _story_items(client):
    """[{name, prefix, guid}] for every story in the Project Map, top -> bottom as the
    navigator lists them. OFFICIAL command (`GetNavigatorItemTree`) — the read needs no
    Tapir; only the ChangeWindow that follows does. The typed response is walked as a plain
    dict so the shape of the tree (folders, nesting depth) does not have to be hard-coded."""
    tree = client.acc.GetNavigatorItemTree(
        client.act.NavigatorTreeId("ProjectMap")).to_dict()
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "StoryItem":
                found.append({"name": node.get("name"),
                              "prefix": str(node.get("prefix") or "").rstrip("."),
                              "guid": (node.get("navigatorItemId") or {}).get("guid")})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(tree)
    return [s for s in found if s.get("guid")]


def set_active_story(client, story):
    """Open a story's floor plan, making it the ACTIVE story.

    `story` is the story's NAME or its bottom-up INDEX (int or digit string) as `GetStories`
    reports it. Resolution order: exact name, then index. The navigator's own `prefix` is NOT
    used as the index — it is the story's display number, which a renumbered project can shift
    away from the index the rest of the tool layer speaks.

    Returns {"ok": True, "story": {...}, "active": <index>} or {"ok": False, "error"}.
    """
    if story is None or (isinstance(story, str) and not story.strip()):
        return {"ok": False, "error": "story (name or index) required"}
    st = get_stories(client)
    if not st.get("ok"):
        return st
    stories = st.get("stories") or []

    want = None
    key = str(story).strip()
    by_name = {str(s.get("name") or "").strip().lower(): s for s in stories}
    if key.lower() in by_name and key.lower():
        want = by_name[key.lower()]
    else:
        try:
            idx = int(float(key))
        except (TypeError, ValueError):
            idx = None
        if idx is not None:
            want = next((s for s in stories if s.get("index") == idx), None)
    if want is None:
        names = [f"{s.get('index')}:{s.get('name')!r}" for s in stories]
        return {"ok": False,
                "error": f"no storey named or indexed {story!r} — the project has {names}"}

    try:
        items = _story_items(client)
    except Exception as e:
        return {"ok": False, "error": f"cannot read the Project Map: {e}"}
    # Match the navigator item by NAME. An unnamed storey has none to match on, so fall back
    # to the navigator's own ordering, which is top -> bottom (index descending).
    target = next((it for it in items
                   if str(it.get("name") or "").strip() == str(want.get("name") or "").strip()
                   and str(want.get("name") or "").strip()), None)
    if target is None and len(items) == len(stories):
        target = items[len(stories) - 1 - int(want.get("index") or 0)]
    if target is None:
        return {"ok": False,
                "error": f"storey {want.get('name')!r} has no Project Map item to open"}

    try:
        resp = client.tap("ChangeWindow", {"navigatorItemId": {"guid": target["guid"]}})
    except Exception as e:
        return {"ok": False, "error": f"Archicad/Tapir error: {e}"}
    err = exec_error(resp, "ChangeWindow failed")
    if err:
        return {"ok": False, "error": err}

    # Confirm, rather than trust: ChangeWindow reports success for opening ANY window, so a
    # wrong navigator item would come back ok with the active storey unchanged. A FAILED
    # confirm read is a failure too — reporting unverified success is exactly the
    # trust-ChangeWindow trap this check exists for.
    after = get_stories(client)
    act = after.get("actStory") if after.get("ok") else None
    if act is None:
        return {"ok": False,
                "error": "ChangeWindow returned, but the active storey could not be "
                         "confirmed (the follow-up GetStories failed) — retry, then check "
                         "with an observation"}
    if act != want.get("index"):
        return {"ok": False,
                "error": f"ChangeWindow succeeded but the active storey is {act}, "
                         f"not {want.get('index')} ({want.get('name')!r})"}
    return {"ok": True, "story": {"index": want.get("index"), "name": want.get("name"),
                                  "level": want.get("level")}, "active": act}
