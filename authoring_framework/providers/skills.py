"""Retrieval over the SOFTWARE SKILLS — the per-application GUI how-to recipes.

A light RAG over `software_skills/`: score each markdown doc against a query and return the
most relevant one(s), the detailed step-by-step operation guide for an application's UI.

It is reached ONLY through the `operational_skill_retrieval` TOOL: nothing here runs until the agent
asks for a recipe, and the recipe comes back as that tool's RESULT. Recipes are large and only
some operations need one, so keeping them out of the system prompt is worth a tool call when
one is genuinely needed — and it makes consulting the manual a visible, budgeted action
instead of a silent input.

Each doc carries SKILL.md-style YAML frontmatter (`name` = the canonical capability id,
`description` = one line of WHEN to use it, `software` = which application it documents).
Scoring (since 2026-08-19) is SEMANTIC first: each doc's retrieval surface is its frontmatter
name + description embedded as one string (the BODY is deliberately NOT embedded — bodies are
long gesture scripts full of shared UI vocabulary, and embedding them blurs the docs into each
other), the query is embedded live, and cosine similarity is the primary score. Two bounded
deterministic bonuses ride on top: the `topic_hint` LEAD (the routing decisions learned from
observed failures — e.g. revit's type-level opening sizes) and a full-name-coverage bonus
(breaks superset-name ties: "create slab" reaches create_slab, not create_slab_opening).
When embeddings are unavailable (no direct OpenAI key, offline, or the API failed once this
process) the old keyword scorer is the fallback — same signals, term-overlap arithmetic.
The frontmatter is stripped from the text handed to the model.
"""
import re
from pathlib import Path

from ..tools.target import BIM_TARGETS
from . import embeddings

SKILLS_DIR = Path(__file__).resolve().parent.parent / "software_skills"

# Per-software skills are named <base>.<software>.md (e.g. doors.revit.md). These are the
# recognized software suffixes; a doc with no suffix is treated as shared (used for any target).
_SOFTWARE = ("archicad", "revit")

# Docs that are not per-task how-to and must never win a retrieval on their filename.
# Both are RETIRED file families kept listed defensively, so a stray copy can never hijack
# a query: `existing_walls` (the per-case library dumps, retired 2026-08-11) and
# `primitives` (the shared interaction-vocabulary docs, deleted 2026-08-23 by user
# decision — the recipes stand alone now, no prepended vocabulary).
_NON_SKILL_BASES = {"existing_walls", "primitives"}

# Markdown link to another skill file, e.g. "[walls](walls.archicad.md)" -> "walls.archicad.md".
_LINK_RE = re.compile(r"\(([\w.\-]+\.md)\)")

# resolved path str -> (mtime, text). The docs are static within a run; cache so the dir isn't
# re-read on every lookup.
_FILE_CACHE = {}


def _read(p):
    """Read a skill/reference doc with an mtime-validated cache (utf-8, tolerant)."""
    key, mtime = str(p), p.stat().st_mtime
    hit = _FILE_CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    text = p.read_text(encoding="utf-8", errors="ignore")
    _FILE_CACHE[key] = (mtime, text)
    return text


# SKILL.md-style frontmatter: a leading `---` block with simple `key: value` lines
# (single-line values only — keeps the parser trivial, no yaml dependency).
_FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_doc(text):
    """Split a doc into (meta, body): meta = the frontmatter's key->value dict ({} when the doc
    has none), body = the text WITHOUT the frontmatter (what the model should see)."""
    m = _FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end():].lstrip("\n")


def _split_name(name):
    """'doors.revit.md' -> ('doors', 'revit'); 'stories.md' -> ('stories', None)."""
    stem = name[:-3] if name.lower().endswith(".md") else name
    for sw in _SOFTWARE:
        if stem.lower().endswith("." + sw):
            return stem[: -(len(sw) + 1)], sw
    return stem, None


# topic word -> the LEAD hint for `retrieve`. Since 2026-08-15 the recipes are PER CANONICAL
# CAPABILITY (`bench_cases/CAPABILITIES.md`: `<capability>.<app>.md`, e.g. move_element /
# flip_element / replace_type), so an EDIT verb maps straight onto its merged capability
# doc's full base — there is exactly ONE move/flip/replace/modify doc per application, and
# composing an element word (the old per-atom disambiguation) would hand lead points to that
# element's create/place doc instead. Order matters: the first matching entry wins, so the
# more specific phrases come first, and verbs beat element words (an EDIT topic must reach
# the edit capability, not the element's create recipe).
_TOPIC_WORDS = (
    # type-replacement phrasings — before the generic edit verbs
    ("change type", "replace type"), ("switch type", "replace type"),
    ("swap", "replace type"), ("replace", "replace type"), ("convert", "replace type"),
    # "place" AFTER the replace group on purpose: matching is substring, and "replace"
    # contains "place" — the earlier replace entries must win a replace topic first.
    ("place", "place"), ("insert", "place"),
    # delete verbs BEFORE the move group: matching is substring and "remove" CONTAINS
    # "move" — ("move", …) would claim every remove topic for move_element.
    ("delete", "delete element"), ("remove", "delete element"),
    # orientation verbs -> flip_element (hinge folded into it). "constrain" BEFORE "move":
    # a constrained-move topic contains both words and must reach move_with_constrain.
    ("hinge", "flip element"), ("flip", "flip element"), ("swing", "flip element"),
    ("mirror", "flip element"),
    ("constrain", "move constrain"), ("follow", "move constrain"),
    ("move", "move element"), ("reposition", "move element"),
    ("relocate", "move element"), ("drag", "move element"),
    ("stretch", "move element"), ("extend", "move element"), ("trim", "move element"),
    # read verbs BEFORE the library words: "list library door" must reach the list_library
    # browse doc, not the load recipe — ("library", "load library component") below would
    # otherwise claim every library topic for the load capability.
    ("list", "list"), ("browse", "list"), ("inventory", "list"),
    ("favorite", "list library"),
    ("observe", "observation"), ("inspect", "observation"),
    ("clash", "clash check"), ("collision", "clash check"), ("interference", "clash check"),
    ("overlap", "clash check"),
    # reading / setting the UI selection is part of the inspection capability
    ("selection", "observation"), ("select", "observation"),
    ("load", "load library component"), ("library", "load library component"),
    # generic edit verbs -> replace_type, which carries the settings edits (height, sill,
    # name, material). A slab/floor OUTLINE edit is special-cased in topic_hint (it lives
    # in move_element), as are door/window "resize" topics on revit (TYPE-level there:
    # create_opening_type)
    ("modify", "replace type"), ("resize", "replace type"),
    ("rename", "replace type"), ("straighten", "replace type"),
    ("reshape", "replace type"), ("update", "replace type"),
    ("subtract", "replace type"), ("change", "replace type"), ("edit", "replace type"),
    # view-navigation topics belong to set_active_story — and MUST match before "window",
    # or "open 3d window" would retrieve a window recipe
    ("3d", "active story"), ("floor plan", "active story"), ("floor-plan", "active story"),
    # room-separation lines are part of the create_room capability (its revit Part B)
    ("separation", "create room"), ("separator", "create room"),
    # a create-composite / create-type topic -> the type-authoring capabilities; the
    # element word composes below ("type wall" -> create_wall_type). A bare "composite"
    # match stays a trap: a BUILD flow's "select composite" must not retrieve the SETUP doc.
    ("create composite", "type"), ("create-composite", "type"), ("new composite", "type"),
    ("create type", "type"), ("new type", "type"), ("family type", "type"),
    # element words last — a bare element topic lands on that element's create/place doc
    # (zone/room emit BOTH tokens: the capability base is create_room, archicad docs say zone)
    ("door", "door"), ("window", "window"), ("slab", "slab"),
    ("zone", "zone room"), ("room", "zone room"), ("stair", "stair"),
    ("storey", "stories"), ("story", "stories"), ("level", "stories"),
    ("wall", "wall"))


# The element words, kept separate so `topic_hint` can compose "verb + element" for the
# leads that still span several docs (place_door vs place_window; create_wall_type vs
# create_slab_type). The element is picked by FIRST OCCURRENCE in the topic ("place the
# door ... beside the window" is a DOOR topic even though "window" appears later). The
# merged edit capabilities do NOT compose — their lead is already the full doc base.
_ELEMENT_WORDS = (("door", "door"), ("window", "window"), ("slab", "slab"),
                  ("floor", "slab"),
                  # the two vocabularies name the room element differently (archicad docs:
                  # zone, revit docs: room) — emit BOTH tokens so the lead matches either
                  ("zone", "zone room"), ("room", "zone room"), ("stair", "stair"),
                  ("storey", "stories"), ("story", "stories"), ("level", "stories"),
                  ("wall", "wall"))


def topic_hint(topic, target=None):
    """The routing hint for a free-text topic, or "" — the deterministic signal that beats
    keyword noise in `retrieve`. A multi-word verb entry IS the full lead (the merged edit
    capabilities have exactly one doc per application); the single-word leads that still
    span several docs ("place", "type") compose with the FIRST element word occurring in
    the topic ("place door", "type wall"), so the lead bonus (which counts matched name
    tokens) separates place_door from place_window instead of tying them.
    `target` refines application-specific routings (revit's type-level opening sizes)."""
    low = str(topic or "").lower()
    verb = next((base for word, base in _TOPIC_WORDS if word in low), "")
    if (any(w in low for w in ("storey", "story", "stories", "level")) and
            any(w in low for w in ("active", "switch", "go to", "current", "activate"))):
        # changing WHICH storey is worked on is set_active_story, not the storey-stack
        # setup — checked before the verb returns, since "switch"/"change storey" topics
        # would otherwise land on replace_type or set_stories
        return "active story"
    if (verb in ("", "replace type", "place", "stories", "slab")
            and re.search(r"\b(hole|shaft)\b", low) and "wall" not in low):
        # "cut a hole" / "shaft" topics are the slab-opening capability; word-boundary
        # match so "the whole wall" cannot trigger it, and a hole in a WALL stays with
        # the wall/opening docs. Stronger verbs (delete/move the hole...) keep their
        # lead; the weak noun leads ("shaft through the LEVELS", "hole in the SLAB")
        # do not.
        return "create slab opening"
    if (verb == "replace type" and any(w in low for w in ("slab", "floor"))
            and not any(w in low for w in ("type", "composite"))
            and any(w in low for w in ("outline", "boundary", "polygon", "reshape",
                                       "resize", "subtract", "level", "elevation"))):
        # a slab's outline / level edit lives in move_element; "change the floor type"
        # stays a type swap
        return "move element"
    if (verb == "replace type" and target == "revit" and "resize" in low
            and any(w in low for w in ("door", "window", "opening"))):
        # DOOR/WINDOW sizes are TYPE-level on revit — those resize topics must reach
        # create_opening_type; a wall resize stays a settings edit
        return "opening type"
    if verb in ("list",          # read verbs: composing the element word hands the lead
                "observation"):  # bonus to that element's EDIT docs ("list wall types"
        return verb              # must reach list_types, not replace_type)
    if " " in verb:
        return verb              # a merged-capability lead is already the full doc base
    if ("composite" in low and verb != "type"
            and any(w in low for w in ("create", "new", "author"))):
        # a create-composite topic phrased non-contiguously ("create a slab composite")
        # falls past the table's "create composite" entry to a bare element word — it is
        # still the type-authoring capability
        verb = "type"
    elem, pos = "", len(low) + 1
    for word, base in _ELEMENT_WORDS:
        i = low.find(word)
        if 0 <= i < pos:
            elem, pos = base, i
    if "type" in low and (
            verb in ("door", "window")
            or (verb == "type" and elem in ("door", "window"))):
        # a door/window TYPE topic is the type-authoring capability (create_opening_type:
        # a family type on revit, a saved favorite on archicad)
        return "opening type"
    if verb and elem and verb != elem:
        return f"{verb} {elem}"
    return verb or elem


_TOPICS_CACHE = {}     # target tuple -> [(name, description)] — the docs are static in a run

# Each recipe's frontmatter description names the application it documents ("... in <app>'s
# attribute library"). That is right in the doc, but the MENU is shown before the agent has
# worked out which application it is in — and the menu is deduplicated by topic, so whichever
# doc sorts first would silently announce the answer. So application names are neutralised out
# of the menu whenever more than one application is on offer.
# The optional leading "the " is part of the match so "the Archicad primitives" does not come
# out as "the the application primitives" — these descriptions are read by the model every turn.
_APP_WORDS = re.compile(r"\b(?:the\s+)?(?:archicad|revit|graphisoft|autodesk|tapir)\b('s)?",
                        re.I)


def _neutralize(text):
    """Replace application names in a menu description with a neutral reference."""
    return _APP_WORDS.sub(lambda m: "the application's" if m.group(1) else "the application",
                          text or "")


def available_topics(targets=None):
    """[(name, description)] of the gesture recipes on offer — the menu carried in the
    `operational_skill_retrieval` tool's own description. Without it the agent must GUESS topic words;
    with it, it asks for recipes that actually exist.

    The menu spans EVERY application whose recipes are on disk, deduplicated by base name — the
    topics are the same authoring operations whichever application you are in, so the listing
    names the work without giving away which application this is."""
    key = tuple(sorted(targets)) if targets else None
    hit = _TOPICS_CACHE.get(key)
    if hit is not None:
        return hit
    hide_app = len(targets or BIM_TARGETS) > 1   # more than one on offer -> do not name it
    out, seen = [], set()
    if SKILLS_DIR.exists():
        for p in sorted(SKILLS_DIR.glob("*.md")):
            base, soft = _split_name(p.name)
            if base in _NON_SKILL_BASES or base in seen:
                continue
            if soft and targets and soft not in targets:
                continue
            seen.add(base)
            meta, _ = _parse_doc(_read(p))
            desc = meta.get("description", "")
            out.append((meta.get("name") or base, _neutralize(desc) if hide_app else desc))
    _TOPICS_CACHE[key] = out
    return out


_RETRIEVE_CACHE = {}   # (query, k, target, lead) -> result


def _name_tokens(base, meta):
    """WHOLE-token name vocabulary (with naive plural stemming), not substrings: "all" must
    not score as a hit on base "walls" the way `"all" in "walls"` would."""
    return {w.rstrip("s") for w in re.findall(
        r"[a-z]+", (base + " " + (meta.get("name") or "")).lower())}


def _doc_embed_text(base, meta):
    """A doc's retrieval surface: the capability name + the author's one-line when-to-use
    description. The BODY is deliberately excluded — it is a gesture script full of shared
    UI vocabulary (click, dialog, OK) that blurs the docs into each other when embedded."""
    name = (meta.get("name") or base).replace("_", " ")
    desc = meta.get("description") or ""
    return f"{name}: {desc}" if desc else name


def _embedding_scores(query, docs, terms, lead_terms):
    """[(score, path, body)] by cosine similarity of the query against each doc's
    name+description embedding, or None when embeddings are unavailable (no key / API
    failure) — the caller then falls back to `_keyword_scores`. The doc vectors are
    disk-cached by content, so a lookup's marginal cost is embedding the query string.

    Two bounded additive bonuses keep the deterministic routing signals in charge of the
    close calls: the `topic_hint` LEAD (+0.10 per matched name token, capped at 2 — it
    encodes per-target decisions like revit's type-level opening sizes that similarity
    alone ties on) and full-name coverage (+0.08 — "create slab" must reach create_slab,
    not the superset-named create_slab_opening, when the cosines are near-equal)."""
    if not embeddings.available():
        return None
    vecs = embeddings.embed([_doc_embed_text(base, meta) for _, base, meta, _ in docs]
                            + [query])
    if not vecs:
        return None
    qv = vecs[-1]
    scored = []
    for (p, base, meta, body), dv in zip(docs, vecs):
        names = _name_tokens(base, meta)
        lead_hits = min(len(lead_terms & names), 2)
        covered = bool(names) and all(t in terms for t in names)
        score = (embeddings.cosine(qv, dv) + 0.10 * lead_hits + (0.08 if covered else 0.0))
        scored.append((score, p, body))
    return scored


def _keyword_scores(query, docs, terms, lead_terms):
    """The keyword fallback (the pre-2026-08-19 scorer, unchanged): NAME hits dominate, the
    DESCRIPTION is a secondary signal, term frequency over the BODY is a length-normalized
    tiebreaker, the `topic_hint` LEAD outweighs them all per matched token, and full-name
    coverage breaks superset-name ties."""
    scored = []
    for p, base, meta, body in docs:
        low = body.lower()
        name_tokens = _name_tokens(base, meta)
        desc_tokens = {w.rstrip("s") for w in re.findall(
            r"[a-z]+", (meta.get("description") or "").lower())}
        name_hits = sum(1 for t in terms if t in name_tokens)
        desc_hits = sum(1 for t in terms if t in desc_tokens)
        tf_density = sum(low.count(t) for t in terms) / (len(low) + 1)  # length-normalized
        lead_hits = len(lead_terms & name_tokens)      # router hint dominates, PER matched
        covered = 80 if name_tokens and name_hits >= len(name_tokens) else 0
        score = 150 * lead_hits + 100 * name_hits + 30 * desc_hits + covered + 1000 * tf_density
        if score:
            scored.append((score, p, body))
    return scored


def retrieve(query, k=1, target=None, lead=""):
    """The text of the top-k most relevant skill docs for `query`, concatenated with a header
    per file. Empty string if nothing matches. Memoized — the docs are static within a run.

    `target` (archicad|revit) scopes retrieval to that software's docs: a doc tagged for the
    OTHER software is skipped, so on a Revit lookup only the *.revit.md skills (and any
    untagged shared doc) can match.

    Scoring is SEMANTIC first — see `_embedding_scores` (cosine over each doc's frontmatter
    name+description, with the `topic_hint` lead and full-name coverage as bounded tiebreak
    bonuses) — with `_keyword_scores` as the deterministic fallback when embeddings are
    unavailable. Both paths read the same signals, so a doc reachable offline stays reachable.
    """
    cache_key = (query, k, target, lead)
    hit = _RETRIEVE_CACHE.get(cache_key)
    if hit is not None:
        return hit
    terms = {t.rstrip("s") for t in re.findall(r"[a-z]+", (query or "").lower())
             if len(t) > 2}
    lead_terms = {t.rstrip("s") for t in re.findall(r"[a-z]+", (lead or "").lower())
                  if len(t) > 2}
    if not terms or not SKILLS_DIR.exists():
        return ""
    # Top level ONLY (glob, not rglob): subdirectories hold source/reference material whose
    # same-name docs must never compete with (or leak into) the retrieved bundle.
    docs = []
    for p in SKILLS_DIR.glob("*.md"):
        base, sw = _split_name(p.name)
        if base in _NON_SKILL_BASES:                       # reference data, not a how-to
            continue
        if target and sw and sw != target:                 # the other software's doc
            continue
        meta, body = _parse_doc(_read(p))
        docs.append((p, base, meta, body))
    scored = _embedding_scores(query, docs, terms, lead_terms)
    if scored is None:
        scored = _keyword_scores(query, docs, terms, lead_terms)
    scored.sort(key=lambda x: -x[0])
    chosen = [(p, body) for _, p, body in scored[:k]]
    # Resolve ONE level of in-doc cross-references: a skill may delegate steps to another skill
    # ("follow Part A of walls.archicad.md verbatim"). RAG returns only top-k, so without this
    # the agent gets a dangling pointer and cannot act.
    included = {p.name for p, _ in chosen}
    for _, text in list(chosen):
        for fname in _LINK_RE.findall(text):
            if fname in included:
                continue
            ref = SKILLS_DIR / fname
            base, sw = _split_name(fname)
            if not ref.exists() or base in _NON_SKILL_BASES:
                continue
            if target and sw and sw != target:
                continue
            included.add(fname)
            chosen.append((ref, _parse_doc(_read(ref))[1]))
    result = "\n\n---\n\n".join(
        f"# SKILL: {p.relative_to(SKILLS_DIR)}\n\n{text}" for p, text in chosen)
    _RETRIEVE_CACHE[cache_key] = result
    return result
