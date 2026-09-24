"""Measure which COORDINATE FRAME a model answers in — and whether the route resizes the image.

    python -m authoring_framework.tools.gui.calibrate -p <provider> -m <model>
    python -m authoring_framework.tools.gui.calibrate -p openai -m google/gemini-3.7-flash \\
           --size 1920x1080 --points 6

The probe is the run's own situation in miniature: the model is handed the REAL `mouse_click`
declaration (worded exactly as a run under this model's profile would word it) and a synthetic
screenshot of the size a run would send, with ONE red target on it, and is asked to click its
centre. Known target, returned (x, y) — so the frame is measured, not assumed:

  pixels      the answer is the target's pixel position on the image that was sent
  norm1000    the answer is x*1000/W, y*1000/H (the 0-1000 grid)
  resized     the answer is k * the pixel position with k != 1: the provider
              shrank the image server-side and the model read pixels off the smaller one —
              the failure the client-side caps exist to prevent; k is reported

The verdict is compared with what `profile.resolve()` would apply to this model: PASS when
they agree (and no resize was seen), FAIL otherwise — exit code 0 / 1. The full measurement is
written to `tools/gui/calibration/<provider>__<model>.json` so the evidence behind a profile
rule is versioned with the code. Needs no BIM application and no screen — only the LLM key.

(EvoCUA is not probed here: it does not take tool declarations — `providers/evocua.py` renders
its own prompt — and its 0..999 grid is fixed by its training harness.)
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "calibration"
TOL_PX = 12          # a hit: within this many sent-image pixels of the target centre
RADIUS = 14


def make_image(w, h, target, seed):
    """A busy-but-unambiguous fake screen: grey UI-like rectangles, one RED disc."""
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), (244, 244, 246))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 36], fill=(225, 226, 230))                   # a "toolbar"
    d.rectangle([0, 36, 220, h], fill=(234, 235, 238))                 # a "side panel"
    for _ in range(28):
        x, y = rnd.randrange(w), rnd.randrange(h)
        ww, hh = rnd.randrange(30, 220), rnd.randrange(14, 90)
        g = rnd.randrange(170, 235)
        d.rectangle([x, y, x + ww, y + hh], outline=(g - 40,) * 3, fill=(g, g, g + 4))
    tx, ty = target
    d.ellipse([tx - RADIUS, ty - RADIUS, tx + RADIUS, ty + RADIUS], fill=(225, 20, 25),
              outline=(120, 0, 0), width=2)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def targets(w, h, n, seed=7):
    """Spread over the image INCLUDING far corners — that is where a frame or resize error
    is largest (it grows with the distance from the origin)."""
    m = 60
    fixed = [(w - m, h - m), (m + 200, m + 40), (w - m, m + 40), (m + 200, h - m),
             (w // 2, h // 2)]
    rnd = random.Random(seed)
    pts = fixed[:n]
    while len(pts) < n:
        pts.append((rnd.randrange(m + 220, w - m), rnd.randrange(m + 40, h - m)))
    return pts


def analyse(size, samples):
    """samples = [((tx, ty), (x, y)), ...] -> the verdict dict. Pure (unit-testable)."""
    w, h = size
    dist = lambda a, b: ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5     # noqa: E731
    err_px = [dist(t, a) for t, a in samples]
    err_norm = [dist(t, (a[0] * w / 1000.0, a[1] * h / 1000.0)) for t, a in samples]
    # least-squares uniform scale k with  answer ~= k * target  (a server-side resize)
    num = sum(a[0] * t[0] + a[1] * t[1] for t, a in samples)
    den = sum(t[0] ** 2 + t[1] ** 2 for t, _ in samples) or 1.0
    k = num / den
    err_k = [dist(a, (k * t[0], k * t[1])) for t, a in samples]
    med = statistics.median
    out = {"median_err_pixels": round(med(err_px), 1),
           "median_err_norm1000": round(med(err_norm), 1),
           "resize_factor_k": round(k, 4), "median_err_resized": round(med(err_k), 1)}
    if med(err_px) <= TOL_PX:
        out["frame"], out["resized"] = "pixels", False
    elif med(err_norm) <= TOL_PX:
        out["frame"], out["resized"] = "norm1000", False
    elif med(err_k) <= TOL_PX and abs(k - 1.0) > 0.02 and abs(k - 1000.0 / w) > 0.02:
        out["frame"], out["resized"] = "pixels", True
    else:
        out["frame"], out["resized"] = None, None
    return out


def _click_spec(wording):
    grid = wording == "norm1000"
    where = "on the 0-1000 grid over the current screenshot" if grid else "in screen pixels"
    return {"name": "mouse_click",
            "description": "click the left mouse button at a point",
            "parameters": {"type": "object", "required": ["x", "y"], "properties": {
                "x": {"type": "number",
                      "description": f"target's x {where}, read off the current screenshot"},
                "y": {"type": "number",
                      "description": f"target's y {where} (y grows DOWNWARD)"}}}}


def probe(provider, model, size, n, wording):
    from ... import config
    from ...providers.llm import chat
    from ..base import _GRID_SENTENCE, _PIXEL_SENTENCE
    config.set_llm_override(provider, model)
    w, h = size
    system = ("You operate a computer through its screen. "
              + (_GRID_SENTENCE if wording == "norm1000" else _PIXEL_SENTENCE)
              + " Answer ONLY by calling the tool.")
    samples, raw = [], []
    for i, t in enumerate(targets(w, h, n)):
        png = make_image(w, h, t, seed=100 + i)
        msg = [{"role": "user", "content": [
            {"text": "This is the current screenshot. Click the exact CENTRE of the red disc."},
            {"png": png}]}]
        reply = chat(msg, system=system, tools=[_click_spec(wording)], role="calibrate") or {}
        call = next((c for c in reply.get("calls") or [] if c.get("name") == "mouse_click"), None)
        args = (call or {}).get("args") or {}
        try:
            ans = (float(args["x"]), float(args["y"]))
        except (KeyError, TypeError, ValueError):
            nums = re.findall(r"-?\d+(?:\.\d+)?", reply.get("text") or "")
            ans = (float(nums[0]), float(nums[1])) if len(nums) >= 2 else None
        raw.append({"target": list(t), "answer": list(ans) if ans else None})
        print(f"  target {t} -> answer {ans}")
        if ans:
            samples.append((t, ans))
    return samples, raw


def sent_size_for(screen, prof):
    """The image size a run would SEND for a screen of this size under this profile — the
    same two-cap downscale as `ComputerController.screenshot`."""
    w, h = screen
    edge, pixels = prof["img_edge"], prof["img_pixels"]
    k = min(1.0, edge / max(w, h) if edge else 1.0,
            (pixels / (w * h)) ** 0.5 if pixels else 1.0)
    return (round(w * k), round(h * k)) if k < 1.0 else (w, h)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--provider", required=True)
    ap.add_argument("-m", "--model", required=True)
    ap.add_argument("--size", default="1920x1080", metavar="WxH",
                    help="the SCREEN size of the bench box (default 1920x1080); the probe "
                         "image is what a run would send for it under this model's caps")
    ap.add_argument("--points", type=int, default=5)
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args(argv)

    from . import profile
    prof = profile.resolve(a.provider.lower(), a.model)
    screen = tuple(int(v) for v in a.size.lower().split("x"))
    size = sent_size_for(screen, prof)
    print(f"[profile] {a.provider}:{a.model} -> {profile.describe(prof)}")
    for wmsg in profile.warnings(prof):
        print(f"[profile] WARNING: {wmsg}")
    print(f"[probe]   screen {screen[0]}x{screen[1]} -> sent image {size[0]}x{size[1]}, "
          f"{a.points} target(s)")

    samples, raw = probe(a.provider.lower(), a.model, size, a.points, prof["wording"])
    if len(samples) < max(3, a.points // 2):
        print("[result]  FAIL — too few usable answers (the model did not call the tool)")
        return 1
    res = analyse(size, samples)
    ok = res["frame"] == prof["frame"] and res["resized"] is False
    print(f"[result]  measured frame={res['frame']} resized={res['resized']} "
          f"(median error: pixels {res['median_err_pixels']} px, norm1000 "
          f"{res['median_err_norm1000']} px, k={res['resize_factor_k']})")
    print(f"[result]  {'PASS' if ok else 'FAIL'} — the profile applies frame={prof['frame']}")
    if not ok and res["resized"]:
        print(f"          the route RESIZES this image (x{res['resize_factor_k']}): tighten "
              f"the caps for this model in tools/gui/profile.py (img_edge / img_pixels)")
    elif not ok and res["frame"]:
        print(f"          add/adjust a rule in tools/gui/profile.py: frame={res['frame']!r}")
    if not a.no_save:
        OUT_DIR.mkdir(exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{a.provider}__{a.model}")
        rec = {"provider": a.provider, "model": a.model, "at": time.strftime("%Y-%m-%d %H:%M"),
               "screen": list(screen), "sent_size": list(size), "profile": prof,
               "measured": res, "pass": ok, "samples": raw}
        (OUT_DIR / f"{name}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"[saved]   {OUT_DIR / (name + '.json')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
