"""Build the vendored OFFICIAL Revit help corpus (`knowledge/revit2027_help/`).

Offline tooling, run once (network required); what ships is the generated corpus — the
Revit twin of `archicad29_help/` (same page format: one Markdown file per help page with a
`> Source:` line and local `images/` screenshot references), which the GUI family's
`documentation_retrieval` tool retrieves from via `knowledge/archicad_help.py`.

Source: the official Revit 2027 help (help.autodesk.com/view/RVT/2027/ENU — the year matches
the installed Revit, like AC29 matches the installed Archicad). The viewer is an SPA, but the
content is static:

  - The FULL table of contents is one JSON: `view/RVT/<year>/ENU/data/toctree.json`
    (every page's title + its `cloudhelp/<year>/ENU/<book>/files/GUID-*.htm` path).
  - Each page is clean TRIDION XHTML: `<div class="head-text"><h1>` title,
    `<div class="body ...">` content, figures as `<img class="image">` (16px ribbon-button
    icons carry the same class and are told apart by their width/height attributes),
    menu-path arrows as `ac.menuaro.gif` glyphs (rendered here as " > ").
  - Images live beside the page at `cloudhelp/<year>/ENU/<book>/images/`.

The corpus is a CURATED subset (`_SECTIONS`): the UI-operation and element-authoring chapters
a GUI-driving agent needs — UI basics/selection, levels, sketching, editing, compound
structure, families, materials, and the Architectural Design element chapters (walls, doors,
windows, components, floors, stairs, rooms, openings). "Video: ..." pages are skipped (an
embedded video carries nothing a text+screenshot corpus can serve). Official pages only —
same rule as the API-doc corpora: nothing derived from our own backend/tooling code.

Run from the project root:

    python -m authoring_framework.knowledge.fetch_revit_help            # build the corpus
    python -m authoring_framework.knowledge.fetch_revit_help --list     # plan only, no fetch

A rebuild DELETES the corpus' pages and re-fetches them (images are re-downloaded only as
referenced), so rebuild only deliberately: a finished benchmark arm was measured against the
corpus as it stood.
"""
import io
import os
import re
import json
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REVIT_YEAR = "2027"                     # matches the installed Revit (like AC29 <-> Archicad 29)
HELP_HOST = "https://help.autodesk.com"
TOC_URL = f"{HELP_HOST}/view/RVT/{REVIT_YEAR}/ENU/data/toctree.json"

# where the loader looks first: $APP_HELP_DIR, else this package's directory (git-ignored)
OUT = Path(os.environ.get("APP_HELP_DIR") or Path(__file__).resolve().parent) / f"revit{REVIT_YEAR}_help"

_ICON_MAX = 40                          # px: an <img> declared this small is an inline icon
_MAX_IMG_PER_PAGE = 6                   # figure downloads per page (the lookup attaches 2)
_MAX_EDGE = 1568                        # px: what the vision providers keep anyway (MAX_IMG_EDGE)
_SLEEP = 0.1                            # politeness between requests

# The curated sections: (slug prefix, TOC path from a book's title down, skip-title set).
# A page whose title is in the skip set — or whose SUBTREE root is — is left out entirely.
_SECTIONS = [
    ("010", ("Get Started", "User Interface"),
     {"Revit Product Feedback", "Revit My Insights", "Revit Home", "New Revit Home",
      "Search", "Dockable Windows", "InfoCenter", "Background Processes", "Online Help"}),
    ("015", ("Model the Design", "Model Layout", "Levels"), set()),
    ("020", ("Model the Design", "Tools and Techniques", "Sketching"), set()),
    ("021", ("Model the Design", "Tools and Techniques", "Editing Elements"), set()),
    ("022", ("Model the Design", "Tools and Techniques", "Compound Structure"), set()),
    ("025", ("Model the Design", "Revit Families"), set()),
    # Materials: the dialog/apply/organize pages; the rendering side (appearance assets,
    # textures) teaches nothing a modelling agent does.
    ("030", ("Customize Revit", "Project Settings", "Materials"),
     {"Change the Appearance of a Material", "About Material Properties and Assets",
      "Working with Physical and Thermal Assets"}),
    ("040", ("Architectural Design", "Walls"), set()),
    ("041", ("Architectural Design", "Doors"), set()),
    ("042", ("Architectural Design", "Windows"), set()),
    ("043", ("Architectural Design", "Components"), set()),
    ("044", ("Architectural Design", "Floors"), set()),
    ("045", ("Architectural Design", "Stairs"), set()),
    ("046", ("Architectural Design", "Rooms"), set()),
    ("047", ("Architectural Design", "Openings"), set()),
]

_SECTION_TITLES = {p[0]: " / ".join(p[1]) for p in _SECTIONS}


def _fetch(url, tries=3, binary=False):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return data if binary else data.decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


# ---------------------------------------------------------------- TOC

def _toc_roots(tree):
    """The toctree's books come in two shapes: children = [one root node holding the whole
    subtree] or children = [bare title node, ...section subtrees]. Normalize both to one
    {title: root-with-children} map."""
    roots = {}
    for book in tree.get("books", []):
        kids = [k for k in (book.get("children") or []) if isinstance(k, dict)]
        if not kids:
            continue
        title = (kids[0].get("ttl") or "").strip()
        if kids[0].get("children"):
            roots[title] = kids[0]
        else:
            roots[title] = {"ttl": title, "children": kids[1:], "ln": kids[0].get("ln")}
    return roots


def _resolve_path(roots, path):
    node = roots.get(path[0])
    for want in path[1:]:
        node = next((c for c in (node.get("children") or [])
                     if (c.get("ttl") or "").strip() == want), None) if node else None
    return node


def _collect_pages(node, skips, acc):
    """TOC-order (title, ln) list of the subtree's pages; skipped titles drop their subtree."""
    title = (node.get("ttl") or "").strip()
    if title in skips or title.startswith("Video:"):
        return acc
    if node.get("ln"):
        acc.append((title, node["ln"]))
    for c in node.get("children") or []:
        _collect_pages(c, skips, acc)
    return acc


# ---------------------------------------------------------------- page HTML -> Markdown

class _Page(HTMLParser):
    """TRIDION help page -> Markdown. Figures (`<img class="image">` above icon size) are
    recorded for download and referenced as `images/<name>`; declared-small images are inline
    ribbon icons and are dropped (the surrounding text names the button); `ac.menuaro.gif`
    glyphs are the ribbon menu-path arrows and become " > "."""

    def __init__(self):
        super().__init__()
        self.out = io.StringIO()
        self.images = []
        self._skip = 0
        self._pre = 0

    @staticmethod
    def _small(attrs):
        try:
            w, h = attrs.get("width"), attrs.get("height")
            return w is not None and h is not None \
                and int(w) <= _ICON_MAX and int(h) <= _ICON_MAX
        except ValueError:
            return False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("h1", "h2", "h3", "h4"):
            self.out.write("\n\n" + "#" * (int(tag[1]) + 1) + " ")
        elif tag == "li":
            self.out.write("\n- ")
        elif tag in ("p", "div", "tr", "br", "table"):
            self.out.write("\n")
        elif tag in ("td", "th"):
            self.out.write(" | ")
        elif tag == "pre":
            self._pre += 1
            self.out.write("\n```\n")
        elif tag == "img":
            src = a.get("src") or ""
            name = src.rsplit("/", 1)[-1]
            if name == "ac.menuaro.gif":
                self.out.write(" > ")
            elif self._small(a) or not re.search(r"\.(png|gif|jpe?g)$", name, re.I):
                pass                                   # inline icon / non-raster: drop
            else:
                # Every figure ships re-encoded as PNG (see _shrink), whatever the source was.
                name = re.sub(r"\.(png|gif|jpe?g)$", ".png", name, flags=re.I)
                if src not in [s for s, _ in self.images] \
                        and len(self.images) < _MAX_IMG_PER_PAGE:
                    self.images.append((src, name))
                self.out.write(f"\n![](images/{name})\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "pre":
            self._pre = max(0, self._pre - 1)
            self.out.write("\n```\n")
        elif tag in ("h1", "h2", "h3", "h4", "p"):
            self.out.write("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self.out.write(data if self._pre else re.sub(r"\s+", " ", data))

    def text(self):
        t = self.out.getvalue()
        t = re.sub(r"[ \t]+\n", "\n", t)
        return re.sub(r"\n{3,}", "\n\n", t).strip()


def _shrink(data):
    """Re-encode one downloaded figure as a lean PNG: first frame only (the source GIFs are
    multi-megabyte ANIMATIONS a vision model reads exactly one frame of) and the long edge
    capped at _MAX_EDGE (what the providers keep anyway — a bigger send is resized server-side
    and only wastes repo space)."""
    from io import BytesIO
    from PIL import Image
    im = Image.open(BytesIO(data))
    im.seek(0)                                      # animated GIF -> first frame
    if im.mode not in ("RGB", "RGBA", "L", "P"):
        im = im.convert("RGB")
    if max(im.size) > _MAX_EDGE:
        im.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.LANCZOS)
    buf = BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _convert(raw):
    """(title, markdown body, [(img src, img name)]) from one help page's XHTML. The body is
    parsed from the content div on (the head block repeats the title; links are kept as their
    text — the corpus is retrieved by keyword, a dangling href is noise)."""
    mt = re.search(r'<div class="head-text">\s*<h1[^>]*>(.*?)</h1>', raw, re.S)
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", mt.group(1))).strip() if mt else None
    start = raw.find('<div class="body')
    body_html = raw[start:] if start >= 0 else raw
    p = _Page()
    p.feed(body_html)
    return title, p.text(), p.images


# ---------------------------------------------------------------- main

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    plan_only = argv == ["--list"]
    if argv and not plan_only:
        raise SystemExit("usage: fetch_revit_help [--list]")

    log = io.StringIO()
    log.write(f"fetch_revit_help: {TOC_URL}\n")
    roots = _toc_roots(json.loads(_fetch(TOC_URL)))

    plan, seen_guids, skipped = [], set(), 0     # (slug, title, ln)
    for prefix, path, skips in _SECTIONS:
        node = _resolve_path(roots, path)
        if node is None:
            log.write(f"  [MISS section]  {' / '.join(path)}\n")
            print(f"MISS section: {' / '.join(path)}", file=sys.stderr)
            continue
        pages, n = _collect_pages(node, skips, []), 0
        for title, ln in pages:
            guid = ln.rsplit("/", 1)[-1].removesuffix(".htm")
            if guid in seen_guids:              # the TOC lists some pages in several places
                skipped += 1
                continue
            seen_guids.add(guid)
            n += 1
            plan.append((f"{prefix}-{n:03d}", title, ln))
        log.write(f"  [section]       {' / '.join(path)}: {n} pages\n")

    if plan_only:
        for slug, title, ln in plan:
            print(f"{slug}  {title}  {ln}")
        print(f"total {len(plan)} pages")
        return

    OUT.mkdir(exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    for old in OUT.glob("*.md"):
        old.unlink()
    for old in (OUT / "images").iterdir():
        old.unlink()

    kept, images_done, failed = [], set(), 0
    for slug, toc_title, ln in plan:
        url = HELP_HOST + ln
        try:
            title, text, images = _convert(_fetch(url))
        except Exception as e:
            failed += 1
            log.write(f"  [MISS page]     {toc_title}: {type(e).__name__}: {e}\n")
            continue
        title = title or toc_title
        for src, name in images:
            if name in images_done:
                continue
            img_url = urllib.parse.urljoin(url, src)
            try:
                (OUT / "images" / name).write_bytes(_shrink(_fetch(img_url, binary=True)))
                images_done.add(name)
            except Exception as e:
                log.write(f"  [MISS image]    {name} ({toc_title}): {type(e).__name__}\n")
                text = text.replace(f"![](images/{name})\n", "")
            time.sleep(_SLEEP)
        section = _SECTION_TITLES[slug.split("-")[0]]
        page = f"# {title}\n\n> Source: {url}\n> Section: {section}\n\n{text}\n"
        (OUT / f"{slug}.md").write_text(page, encoding="utf-8")
        kept.append((slug, title, url))
        log.write(f"  [{slug}] {title}\n")
        print(f"[{slug}] {title}")
        time.sleep(_SLEEP)

    index = [f"# Revit {REVIT_YEAR} Help — local backup (official docs, Markdown)", "",
             f"Downloaded from {HELP_HOST}/view/RVT/{REVIT_YEAR}/ENU as an offline reference "
             f"for the GUI agent. {len(kept)} pages, {len(images_done)} images. Generated by "
             f"`knowledge/fetch_revit_help.py` — do not hand-edit.", ""]
    section = None
    for slug, title, url in kept:
        sect = _SECTION_TITLES[slug.split("-")[0]]
        if sect != section:
            index += ["", f"## {sect}", ""]
            section = sect
        index.append(f"- [{title}]({slug}.md) — [source]({url})")
    (OUT / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    # The fetch log is PRINTED, never written into the corpus: a log file inside a versioned
    # directory would carry this machine's absolute path into the repo.
    log.write(f"\nDONE kept={len(kept)} failed={failed} dup_toc_refs={skipped} "
              f"images={len(images_done)}\n")
    print(log.getvalue())
    print(f"wrote {len(kept)} pages, {len(images_done)} images -> {OUT.name}/")


if __name__ == "__main__":
    main()
