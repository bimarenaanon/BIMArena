"""Drawing input -> raster bytes for the vision models.

Handles both a PDF (first page rasterized) and a plain raster image, via PyMuPDF.
"""
import base64
import io
from pathlib import Path

import fitz
from PIL import Image


_CACHE = {}       # (resolved path, mtime, dpi, page) -> PNG bytes
_CACHE_MAX = 8    # a MULTI-VIEW case reads several drawings per planner/verifier call — a
                  # single-entry cache made every call past the first a miss, re-rasterizing
                  # every PDF once per verify loop. Bounded, evicting oldest-inserted.

# Long-edge cap for the DRAWING sent to the vision models. Drawings are never clicked, so
# there is no coordinate contract to preserve; providers reject huge images outright
# (Anthropic hard-fails > 8000 px) or downscale them server-side anyway. 2000 px keeps more
# detail than the providers' own resize thresholds while staying well under every limit.
MAX_DRAWING_EDGE = 2000


def to_png_bytes(path, dpi=300, page=0):
    """Render `path` (PDF or image) to PNG bytes. Only a PDF is rasterized at `dpi`; a raster
    input keeps its REAL pixels 1:1 — rendering it through a fitz page would rescale it by its
    embedded dpi metadata (e.g. ~4.17x at dpi=300), blowing past provider image-size limits.

    Memoized per (file, mtime, dpi, page): the planner and EVERY verify loop re-read the same
    drawing, so it is converted once per run instead of once per LLM call."""
    p = Path(path)
    key = (str(p.resolve()), p.stat().st_mtime, dpi, page)
    data = _CACHE.get(key)
    if data is None:
        data = _convert(p, dpi, page)
        while len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))           # evict oldest-inserted — bounds memory
        _CACHE[key] = data
    return data


def _convert(p, dpi, page):
    with fitz.open(p) as doc:                        # close the doc so the file handle isn't leaked
        if doc.is_pdf:
            return _cap_long_edge(doc[page].get_pixmap(dpi=dpi).tobytes("png"))
    if p.suffix.lower() == ".png":
        return _cap_long_edge(p.read_bytes())        # already a PNG — pass through (size-capped)
    return _cap_long_edge(fitz.Pixmap(str(p)).tobytes("png"))   # other raster -> PNG 1:1


def _cap_long_edge(data, cap=MAX_DRAWING_EDGE):
    """Downscale PNG bytes so the long edge is <= cap (LANCZOS); unchanged when already under.
    A large-format sheet (an A1/A2 PDF at 300 dpi is ~9900 px) would otherwise be REJECTED by
    Anthropic's 8000 px hard limit and bloat every other provider's vision tokens."""
    img = Image.open(io.BytesIO(data))
    k = cap / max(img.size)
    if k >= 1.0:
        return data
    img = img.resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def to_b64(data):
    """Base64-encode raw bytes to an ASCII string."""
    return base64.b64encode(data).decode()
