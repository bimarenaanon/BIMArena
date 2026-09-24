"""Official application Help (local Markdown backups) as a knowledge source — GUI agent only.

ONE corpus per application, INDEXED TOGETHER (the pool rule: nothing tells the agent which
application it is in, so the lookup serves every application's help side by side and the other
application's pages are simply misses — same pattern as `api_doc.py` for the two API corpora):
`archicad29_help/` (the official AC29 Help) and `revit2027_help/` (the official Revit 2027 help,
built by `fetch_revit_help.py`). Both are Markdown + local screenshots, downloaded offline, and
are the AUTHORITATIVE reference for HOW to operate the GUI: exact tool/menu/dialog labels,
reference-line / location-line option names, pet-palette / ribbon editing commands,
selection/marquee/tracker interaction, composite & compound-structure dialogs, Story / Level
settings. `lookup(queries)` scores the pages by keyword and returns a text excerpt per hit PLUS
the page's screenshots (PNG bytes) for the vision model — most of the value is in the dialog
screenshots.

It is reached through the GUI family's `documentation_retrieval` TOOL (`tools/gui/`): with the
hand-written software-skill recipes banned from the pool, this corpus is the GUI route's ONE
learning channel, so retrieval quality matters. What the scorer does and why:

  - WHOLE-TOKEN matching over a light STEM (plural/-ing/-ed folded, trailing e dropped, y->i),
    so "place"/"placing", "story"/"stories", "line"/"lines" all meet — substring matching would
    let "end" hit "ending" and "all" hit "walls".
  - IDF weighting with a strong TITLE boost: the corpus titles are the application's own task
    names ("Create a Chain of Walls", "Placing Doors or Windows"), so a title hit is the signal.
  - A BIGRAM boost for adjacent query terms found adjacent in the page ("reference line",
    "story settings") — the phrase is usually the concept.
  - A tiny ADDITIVE synonym map from agent vocabulary into the corpus' (storey/floor/level ->
    story, room -> zone, remove -> delete, hole <-> opening): the agent must not be told the
    application's vocabulary in any prompt (that would leak which application the run drives),
    so the mapping lives here, invisibly.
  - TOP-N pages per query (not one), and the RUNNER-UP titles are returned as `more` — real
    page titles the agent can re-query verbatim to drill in.

Degrades gracefully: no corpus on disk -> `available()` is False and the tool is not offered.
"""
import math
import re
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_NAMES = ("archicad29_help", "revit2027_help")                    # one dir per application


def _corpora():
    """The vendors' help is NOT versioned with the code (it is their copyrighted material):
    build it with `fetch_archicad_help.py` / `fetch_revit_help.py`. Each corpus is looked for
    in `$APP_HELP_DIR`, then in this package's directory (git-ignored there), then in the
    repo's private `0_docs/help_corpora/`; the first location that holds pages wins."""
    import os
    roots = [Path(p) for p in (os.environ.get("APP_HELP_DIR"),) if p]
    roots += [_HERE, _HERE.parents[1] / "0_docs" / "help_corpora"]
    out = []
    for name in _NAMES:
        hit = next((r / name for r in roots
                    if (r / name).is_dir() and any((r / name).glob("[0-9]*.md"))), None)
        out.append(hit or roots[0] / name)
    return out


CORPORA = _corpora()
_MAX_IMG_PER_PAGE = 2       # screenshots to attach per chosen page (dialogs are the value)
_MAX_IMG_TOTAL = 6          # cap the total images added to one vision call
_EXCERPT_CHARS = 1400       # text window around the strongest hit per page
_MORE_TITLES = 6            # runner-up page titles offered for a follow-up query

_MEM = None                 # in-process index: [{slug, title, text, images, tt, bt, ts, bs}]

_STOP = {"the", "and", "for", "with", "how", "what", "where", "when", "you", "your",
         "can", "not", "are", "this", "that", "into", "onto", "from"}

# Agent vocabulary -> the corpus' own vocabulary, in STEM space. ADDITIVE: a query term also
# matches its synonym's pages, it never stops matching its own. Kept here (not in any prompt or
# tool doc) so the vocabulary mapping never announces which application the run is driving.
_SYN = {"storei": "stori", "floor": "stori", "level": "stori",
        "room": "zone", "remov": "delet", "eras": "delet",
        "hole": "opening", "opening": "hole",
        "composit": "compound", "compound": "composit"}


def available():
    return any(c.exists() and any(c.glob("[0-9]*.md")) for c in CORPORA)


def _stem(w):
    """Light suffix folding — enough to meet plural/-ing/-ed and infinitive forms in the middle
    ("placing"=="place"=="plac", "stories"=="story"=="stori"). Applied identically to the corpus
    and the query, so only CONSISTENCY matters, not linguistic correctness."""
    while True:
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        else:
            break
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    if w.endswith("y"):
        w = w[:-1] + "i"
    return w


def _tokens(text):
    return [t for t in re.findall(r"[a-z]+", str(text).lower())
            if len(t) > 2 and t not in _STOP]


def _index():
    """Parse every page .md once: title / body text / referenced local images, plus the stemmed
    token counters and stem-strings the scorer works on."""
    global _MEM
    if _MEM is not None:
        return _MEM
    docs = []
    for corpus in CORPORA:
        if not corpus.exists():
            continue
        for p in sorted(corpus.glob("[0-9]*.md")):    # page files start with a digit; skips index.md
            raw = p.read_text(encoding="utf-8", errors="ignore")
            mt = re.search(r"^#\s+(.+)$", raw, re.M)
            title = mt.group(1).strip() if mt else p.stem
            body = re.sub(r"^> .*$", "", raw, flags=re.M)      # drop the > Source / > Section lines
            body = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.M).strip()   # and the H1 title
            images = re.findall(r"\]\((images/[^)]+\.(?:png|jpg|jpeg|gif))\)", raw)
            # The corpora reuse each other's numeric page prefixes, so the slug carries the
            # corpus dir (internal only — the model sees titles, never slugs).
            docs.append({"slug": f"{corpus.name}/{p.stem}", "dir": corpus,
                         "title": title, "text": body, "images": images,
                         "tt": Counter([_stem(t) for t in _tokens(title)]),
                         "bt": Counter([_stem(t) for t in _tokens(body)]),
                         "ts": " ".join(_stem(t) for t in _tokens(title)),
                         "bs": " ".join(_stem(t) for t in _tokens(body))})
    _MEM = docs
    return docs


def _rank(docs, terms):
    """Score every page against the stemmed query terms; return [(score, doc_index)] best-first."""
    n = len(docs)

    def _count(d, t):
        v = _SYN.get(t)
        ct = max(d["tt"].get(t, 0), d["tt"].get(v, 0) if v else 0)
        cb = max(d["bt"].get(t, 0), d["bt"].get(v, 0) if v else 0)
        return ct, cb

    df = {t: sum(1 for d in docs if any(_count(d, t))) for t in terms}
    terms = [t for t in terms if df[t] > 0]
    if not terms:
        return []
    idf = {t: math.log(n / df[t]) + 0.1 for t in terms}
    need = min(2, len(terms))
    ranked = []
    for i, d in enumerate(docs):
        matched, score = 0, 0.0
        for t in terms:
            ct, cb = _count(d, t)
            if not (ct or cb):
                continue
            matched += 1
            score += idf[t] * (min(cb, 8) + 10 * min(ct, 2))
        if matched < need:
            continue
        for a, b in zip(terms, terms[1:]):     # adjacent in the query AND in the page = the concept
            pair = f"{a} {b}"
            if pair in d["ts"]:
                score += 40
            elif pair in d["bs"]:
                score += 12
        score *= matched / len(terms)
        if score > 0:
            ranked.append((score, i))
    ranked.sort(key=lambda x: -x[0])
    return ranked


def _excerpt(text, raw_terms, stems):
    """A text window centred on the first hit of any query term (raw first, stem-prefix fallback)."""
    low = text.lower()
    hits = [low.find(t) for t in raw_terms if low.find(t) >= 0]
    pos = min(hits) if hits else -1
    if pos < 0:
        for t in stems:
            m = re.search(r"\b" + re.escape(t), low)
            if m:
                pos = m.start()
                break
    start = max(0, (pos if pos >= 0 else 0) - _EXCERPT_CHARS // 3)
    return re.sub(r"[ \t]+", " ", text[start:start + _EXCERPT_CHARS]).strip()


def _images_for(slugs):
    """PNG bytes for the given pages' screenshots (capped)."""
    by = {d["slug"]: d for d in _index()}
    out = []
    for s in slugs or []:
        d = by.get(s)
        if not d:
            continue
        for rel in d["images"][:_MAX_IMG_PER_PAGE]:
            fp = d["dir"] / rel
            if fp.exists():
                out.append(fp.read_bytes())
            if len(out) >= _MAX_IMG_TOTAL:
                return out
    return out


# alias so callers can re-render page images from stored slugs (parity with neufert.render_pages)
render = _images_for


def lookup(queries, max_pages=3):
    """Retrieve the best AC29 Help pages for the queries.

    Returns {"excerpts": [{"slug", "title", "query", "text"}], "slugs": [...],
    "images": [png bytes], "more": [runner-up titles]} — or None when nothing relevant was
    found. One query yields up to `max_pages` pages (the old scorer returned one page per
    query, which starved a single-query call); `more` carries the next-best page TITLES so
    the caller can re-query one verbatim to drill in.
    """
    if not available() or not queries:
        return None
    docs = _index()
    chosen, excerpts, more = [], [], []
    for q in queries:
        raw = _tokens(q)
        seen = set()
        stems = [s for s in (_stem(t) for t in raw) if not (s in seen or seen.add(s))]
        if not stems:
            continue
        for _, i in _rank(docs, stems):
            d = docs[i]
            if d["slug"] in chosen:
                continue
            if len(chosen) < int(max_pages):
                chosen.append(d["slug"])
                excerpts.append({"slug": d["slug"], "title": d["title"], "query": q,
                                 "text": _excerpt(d["text"], raw, stems)})
            elif d["title"] not in more:
                more.append(d["title"])
                if len(more) >= _MORE_TITLES:
                    break
        if len(chosen) >= int(max_pages):
            break
    if not excerpts:
        return None
    return {"excerpts": excerpts, "slugs": chosen, "images": _images_for(chosen), "more": more}
