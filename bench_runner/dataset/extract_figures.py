"""Materialize the input drawings that are FIGURES OF A COPYRIGHTED BOOK from your own copy.

    python bench_runner/dataset/extract_figures.py --pdf /path/to/Neufert-4th-edition.pdf
    python bench_runner/dataset/extract_figures.py            # $NEUFERT_PDF / the default path
    python bench_runner/dataset/extract_figures.py --check    # report what is missing, write nothing

Some cases take a figure from Neufert, "Architects' Data" (4th ed.) as their input drawing.
The figure itself is not distributed with the dataset: the case's `task.json` carries a
REFERENCE instead —

    "input": {"drawing": ["drawing.png"],
              "source": {"drawing.png": {"document": "...", "pdf_page": 91, "printed_page": 78,
                                         "bbox": [x0, y0, x1, y1], "page_size": [w, h],
                                         "anchor": "<words of the figure's caption>"}}}

— and this script cuts the figure out of the PDF and writes it next to the `task.json` under
the name the case expects, so the harness finds it exactly where a shipped drawing would be.

`bbox` is in PDF points, origin TOP-LEFT (PyMuPDF's convention), on a page of `page_size`;
it is rescaled if your PDF's page size differs. `pdf_page` is the 1-based page of the full
4th-edition PDF. Because PDF copies differ (front matter, excerpts), the page is CONFIRMED by
the caption `anchor`: the script tries `pdf_page` (1-based, then 0-based) and, if the caption
is not there, searches the document for the page whose clip region carries it. A figure whose
caption cannot be found anywhere is reported and NOT written — a wrong crop would silently
change the task.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DPI = 250           # ~3.5 px per PDF point: the scale the original hand-cut figures had
PAD = 14.0          # pt of slack around the bbox when LOOKING for the caption (never when cropping)


def find_pdf(arg: str | None) -> Path | None:
    for cand in (arg, os.environ.get("NEUFERT_PDF"),
                 ROOT / "authoring_framework" / "knowledge" / "Neufert-4th-edition.pdf",
                 ROOT / "Neufert-4th-edition.pdf"):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def references(root: Path):
    """(task.json path, drawing name, reference dict) for every sourced drawing under `root`."""
    for tj in sorted(root.rglob("task.json")):
        try:
            spec = json.loads(tj.read_text(encoding="utf-8"))
        except Exception:
            continue
        for name, ref in ((spec.get("input") or {}).get("source") or {}).items():
            yield tj, name, ref


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def locate(doc, ref):
    """The 0-based page index carrying this figure, or None."""
    import fitz
    anchor = _norm(ref.get("anchor") or "")
    x0, y0, x1, y1 = ref["bbox"]

    def has_anchor(i: int) -> bool:
        if not (0 <= i < len(doc)):
            return False
        if not anchor:
            return True
        page = doc[i]
        sx, sy = _scale(page, ref)
        clip = fitz.Rect((x0 - PAD) * sx, (y0 - PAD) * sy, (x1 + PAD) * sx, (y1 + 3 * PAD) * sy)
        return anchor in _norm(page.get_text(clip=clip))

    given = int(ref["pdf_page"])
    for i in (given - 1, given):                    # 1-based as documented, then 0-based
        if has_anchor(i):
            return i
    if anchor:                                      # another edition / an excerpt: search
        for i in range(len(doc)):
            if has_anchor(i):
                return i
    return None


def _scale(page, ref):
    w, h = ref.get("page_size") or (page.rect.width, page.rect.height)
    return page.rect.width / float(w), page.rect.height / float(h)


def crop(doc, index: int, ref, dpi: int = DPI) -> bytes:
    import fitz
    page = doc[index]
    sx, sy = _scale(page, ref)
    x0, y0, x1, y1 = ref["bbox"]
    pix = page.get_pixmap(clip=fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy), dpi=dpi)
    return pix.tobytes("png")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", default=None, help="your copy of the book (default: $NEUFERT_PDF, "
                    "then authoring_framework/knowledge/Neufert-4th-edition.pdf)")
    ap.add_argument("--root", type=Path, default=ROOT / "bench_cases")
    ap.add_argument("--check", action="store_true", help="list sourced drawings and whether "
                    "they exist; write nothing")
    ap.add_argument("--force", action="store_true", help="re-cut figures that already exist")
    a = ap.parse_args(argv)

    refs = list(references(a.root))
    if not refs:
        print("no sourced drawings under", a.root)
        return 0
    if a.check:
        missing = 0
        for tj, name, ref in refs:
            ok = (tj.parent / name).is_file()
            missing += not ok
            print(f"  {'ok     ' if ok else 'MISSING'} {tj.parent.relative_to(a.root)}/{name}  "
                  f"<- p.{ref.get('printed_page')} of {ref.get('document')}")
        print(f"{len(refs)} sourced drawing(s), {missing} missing")
        return 1 if missing else 0

    pdf = find_pdf(a.pdf)
    if pdf is None:
        sys.exit("no PDF: pass --pdf <your copy of the book> or set $NEUFERT_PDF")
    import fitz
    doc = fitz.open(pdf)
    print(f"[pdf] {pdf.name}: {len(doc)} page(s)")
    wrote = failed = 0
    for tj, name, ref in refs:
        out = tj.parent / name
        rel = out.relative_to(a.root)
        if out.is_file() and not a.force:
            print(f"  kept    {rel}")
            continue
        i = locate(doc, ref)
        if i is None:
            failed += 1
            print(f"  FAILED  {rel}: caption {ref.get('anchor')!r} not found near the bbox on "
                  f"PDF page {ref.get('pdf_page')} (printed p.{ref.get('printed_page')}) — "
                  f"not written")
            continue
        out.write_bytes(crop(doc, i, ref))
        wrote += 1
        print(f"  wrote   {rel}  <- PDF page {i + 1} (printed p.{ref.get('printed_page')})")
    print(f"{wrote} written, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
