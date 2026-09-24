"""Build the local Archicad 29 Help corpus that `documentation_retrieval` searches.

    python -m authoring_framework.knowledge.fetch_archicad_help            # the whole subset
    python -m authoring_framework.knowledge.fetch_archicad_help --limit 5  # a smoke test

The vendor's help is NOT distributed with this repo. What is versioned is
`archicad29_help_manifest.json` — the curated subset as TITLES + LINKS only (236 pages in
five sections: elements, interaction, attributes, tool settings, views). This script fetches
each listed page from help.graphisoft.com, converts it to Markdown and downloads its
screenshots into `<out>/archicad29_help/` in the layout `knowledge/archicad_help.py` indexes:

    NNN-MMM.md      "# <title>", "> Source: <url>", "> Section: <section>", then the body;
                    images as ![alt](images/<book>_<file>)
    images/         the page screenshots
    index.md        the table of contents, by section

`<out>` defaults to where the loader looks first (`$APP_HELP_DIR`, else this package's
directory, which is git-ignored for the two corpora). Standard library only.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "archicad29_help_manifest.json"
NAME = "archicad29_help"
UA = "Mozilla/5.0 (help-corpus builder; research use)"
_BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
_SKIP_IDS = {"header", "footer"}


def get(url: str, tries: int = 3) -> bytes:
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:                      # noqa: BLE001 — retried, then raised
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


class _Page(HTMLParser):
    """The help page's body as Markdown blocks: one paragraph per FrameMaker <p>, links kept
    as [text](href), images as ![alt](images/<book>_<file>); the breadcrumb header, the
    copyright footer and scripts are dropped."""

    def __init__(self, book: str):
        super().__init__(convert_charrefs=True)
        self.book = book
        self.blocks: list[str] = []
        self.images: list[tuple[str, str]] = []     # (remote file name, local file name)
        self._buf: list[str] = []
        self._skip = 0                              # depth inside a skipped container
        self._skip_stack: list[bool] = []
        self._in_body = False
        self._mute = 0                              # inside <script>/<style>
        self._href: str | None = None
        self._link: list[str] = []

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        text = re.sub(r"^•\s*", "- ", text)
        self._buf = []
        if text and text != "-":
            self.blocks.append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "body":
            self._in_body = True
            return
        if not self._in_body:
            return
        if tag in ("script", "style"):
            self._mute += 1
            return
        if tag == "div":
            skip = a.get("id") in _SKIP_IDS or bool(self._skip)
            self._skip_stack.append(skip)
            self._skip += 1 if skip else 0
        if self._skip or self._mute:
            return
        if tag in _BLOCK:
            self._flush()
        elif tag == "br":
            self._buf.append(" ")
        elif tag == "a" and a.get("href"):
            self._href, self._link = a["href"], []
        elif tag == "img" and a.get("src"):
            remote = a["src"]
            local = f"{self.book}_{Path(urllib.parse.unquote(remote)).name}"
            self.images.append((remote, local))
            self._flush()
            self.blocks.append(f"![{a.get('alt') or Path(remote).name}](images/{local})")

    def handle_endtag(self, tag):
        if not self._in_body:
            return
        if tag in ("script", "style"):
            self._mute = max(0, self._mute - 1)
            return
        if tag == "div" and self._skip_stack:
            if self._skip_stack.pop():
                self._skip -= 1
            return
        if self._skip or self._mute:
            return
        if tag == "a" and self._href is not None:
            label = re.sub(r"\s+", " ", "".join(self._link)).strip()
            if label:
                self._buf.append(f"[{label}]({self._href})")
            self._href = None
        elif tag in _BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._in_body or self._skip or self._mute:
            return
        (self._link if self._href is not None else self._buf).append(data)

    def close(self):
        super().close()
        self._flush()


def convert(raw: bytes, page: dict) -> tuple[str, list[tuple[str, str]]]:
    book = page["slug"].split("-")[0]
    p = _Page(book)
    p.feed(raw.decode("utf-8", "replace"))
    p.close()
    title = page["title"]
    body = "\n\n".join(html.unescape(b) for b in p.blocks)
    md = (f"# {title}\n\n> Source: {page['url']}\n> Section: {page['section']}\n\n"
          f"{title}\n\n{body}\n")
    return md, p.images


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="directory that will hold archicad29_help/ (default: $APP_HELP_DIR, "
                         "else this package's directory)")
    ap.add_argument("--limit", type=int, default=0, help="fetch only the first N pages")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    a = ap.parse_args(argv)

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = a.out or Path(os.environ.get("APP_HELP_DIR") or HERE)
    out = base / NAME
    (out / "images").mkdir(parents=True, exist_ok=True)
    pages = man["pages"][: a.limit] if a.limit else man["pages"]
    done = failed = n_img = 0
    for i, page in enumerate(pages, 1):
        try:
            md, images = convert(get(page["url"]), page)
        except Exception as e:                      # noqa: BLE001 — reported, run continues
            failed += 1
            print(f"  FAILED {page['slug']} {page['url']}: {type(e).__name__}: {e}")
            continue
        (out / f"{page['slug']}.md").write_text(md, encoding="utf-8")
        for remote, local in images:
            dst = out / "images" / local
            if dst.exists():
                continue
            try:
                dst.write_bytes(get(urllib.parse.urljoin(page["url"], remote)))
                n_img += 1
            except Exception as e:                  # noqa: BLE001
                print(f"    image failed {remote}: {type(e).__name__}")
        done += 1
        if i % 25 == 0 or i == len(pages):
            print(f"  {i}/{len(pages)} pages, {n_img} images")
        time.sleep(a.delay)

    index = [f"# Archicad 29 Help — local copy (official docs, Markdown)", "",
             f"Downloaded from {man['source']} by `knowledge/fetch_archicad_help.py` — do not "
             f"hand-edit. {done} pages.", ""]
    for sec in man["sections"]:
        index += ["", f"## {sec}", ""]
        index += [f"- [{p['title']}]({p['slug']}.md) — [source]({p['url']})"
                  for p in pages if p["section"] == sec]
    (out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"wrote {done} pages ({failed} failed), {n_img} new images -> {out.name}/")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
