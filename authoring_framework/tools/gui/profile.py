"""The per-MODEL screen/coordinate profile — ONE place that decides, for the model this run
drives, everything that stands between "the pixel the model means" and "the point the mouse
lands on":

  frame        the coordinate frame the model ANSWERS in — "pixels" (read off the screenshot
               it was sent) or "norm1000" (a 0-1000 grid per axis, whatever the image size);
  wording      how the tool declarations DESCRIBE a coordinate to the model — follows the
               frame, so a model is never asked for pixels and decoded as a grid or vice versa;
  img_edge /   the client-side caps on the screenshot that is sent. A pixels-frame model is
  img_pixels   only correct if the image reaches it UNRESIZED: a provider that
               shrinks it server-side silently rescales the space the model reads, and every
               click lands short in proportion to its distance from the origin. A norm1000
               model is immune — its answer does not depend on the image's pixel size.

WHY PER MODEL, NOT PER PROVIDER. The frame is a property of how the MODEL was trained, so the
model id decides; the provider is only the fallback for an id no rule knows (keying on the
model keeps it right for a vendor that serves several model families).

RESOLUTION ORDER, per field: an explicit environment override > the model-id rule > the
provider default. One exception, `caps_locked`: for a model whose provider is KNOWN to resize
server-side (Claude), an environment value may only TIGHTEN the caps, never loosen them — a
shared .env that says "no cap" for another channel must not be able to break this one.

Every run records the resolved profile (`mem["gui_profile"]`, and `stats["gui"]` with the
sent-image size and scale), so a result can always be traced back to the exact frame and image
size it was produced under. A model no rule matches still runs — on its provider's default —
but the profile says so (`matched: None`) and the run prints a warning: verify it once with

    python -m authoring_framework.tools.gui.calibrate -p <provider> -m <model>

which measures the frame (and any server-side resize) empirically, then add a rule below.
"""
import os
import re

# The screenshot is sent at the screen's REAL pixels (the benchmark's fixed 1920x1080; 0 = no
# cap) for every model EXCEPT one whose provider resizes over-threshold images server-side.
# Anthropic shrinks anything over ~1568 px on an edge or ~1.15 MP, and Claude answers in the
# pixels of the image it actually sees — so an uncapped 1920x1080 frame comes back in a
# ~1568x882 coordinate space and every click lands ~22% short. The Claude rule therefore caps
# the SENT image client-side at 1344 px / 1.1 MP (1344x756 = 1.02 MP, measured pixel-exact on
# the direct endpoint), and `_SCALE` maps its answers back onto the 1920x1080 screen. Those
# caps are LOCKED: the environment may tighten them, never loosen them.
DEFAULT_IMG_EDGE = 0
DEFAULT_IMG_PIXELS = 0
CLAUDE_CAPS = {"img_edge": 1344, "img_pixels": 1_100_000, "caps_locked": True}

# Model-id rules, FIRST MATCH WINS (matched against the lowercased id, vendor prefix included,
# so a vendor-prefixed id matches too). Evidence is noted per rule.
_MODEL_RULES = [
    # Claude answers in true pixels of the image it was sent.
    (r"claude", {"frame": "pixels", "server_resizes": True, **CLAUDE_CAPS}),
    # Gemini / Qwen / Meta vision grounding is trained on a 0-1000 frame per axis and no
    # wording moves them off it (probed 2026-09-12 at 1568x882 and 1920x1080: x*1000/W,
    # y*1000/H with ~1 px residual).
    (r"gemini", {"frame": "norm1000"}),
    (r"qwen|qvq", {"frame": "norm1000"}),
    (r"muse|llama", {"frame": "norm1000"}),
    # EvoCUA / OpenCUA: `--coordinate_type relative`, a 0..999 grid (providers/evocua.py rescales
    # by 1000/999 so the shared norm1000 decode reproduces the upstream harness exactly).
    (r"evocua|opencua", {"frame": "norm1000"}),
    # GPT / o-series: pixel-exact on the same probe (2026-09-12).
    (r"gpt|(^|/)o\d", {"frame": "pixels"}),
]

# Fallback when no model rule matches: the provider's own family.
_PROVIDER_DEFAULT = {
    "openai": {"frame": "pixels"},
    "anthropic": {"frame": "pixels", "server_resizes": True, **CLAUDE_CAPS},
    "gemini": {"frame": "norm1000"},
    "qwen": {"frame": "norm1000"},
    "meta": {"frame": "norm1000"},
    "evocua": {"frame": "norm1000"},
    "opencua": {"frame": "norm1000"},
}

_FRAMES = ("pixels", "norm1000")
_memo = {}


def _identity():
    """(provider, model id) of the run — the same resolution the loop's chat calls use:
    --model / $LLM_MODEL_REACT / $LLM_MODEL / the provider's default."""
    try:
        from ... import config as _cfg              # lazy: may load before .env does
        prov = _cfg.current_provider()
        model = (os.getenv("LLM_MODEL_REACT") or _cfg.current_model())
    except Exception:
        prov = (os.getenv("LLM_PROVIDER") or "openai").lower()
        model = os.getenv("LLM_MODEL_REACT") or os.getenv("LLM_MODEL") or ""
    return prov, (model or "")


def _env_int(name):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _cap(name, env_val, base, locked):
    """One image cap and where it came from. 0 means "no cap"."""
    if env_val is None:
        return base, "model"
    if not locked:
        return env_val, f"env ${name}"
    # locked: the environment may only tighten. 0 ("no cap") or a looser value is refused.
    if env_val and (not base or env_val < base):
        return env_val, f"env ${name} (tighter than the model's cap)"
    return base, f"model (LOCKED — ${name}={env_val} would loosen it and was ignored)"


def resolve(provider=None, model=None):
    """The profile for this run (or for an explicit provider/model): a dict with `frame`,
    `wording`, `img_edge`, `img_pixels`, plus `provider`, `model`, `matched` (the rule that
    decided, None when only the provider default applied) and `sources` (field -> origin)."""
    if provider is None or model is None:
        p, m = _identity()
        provider, model = provider or p, (m if model is None else model)
    env = (os.getenv("GUI_COORD_FRAME", ""), os.getenv("GUI_COORD_WORDING", ""),
           os.getenv("GUI_MAX_IMG_EDGE", ""), os.getenv("MAX_IMG_PIXELS", ""))
    key = (provider, model, env)
    if key in _memo:
        return _memo[key]

    mid = (model or "").lower()
    matched, base = None, None
    for pat, prof in _MODEL_RULES:
        if re.search(pat, mid):
            matched, base = pat, prof
            break
    if base is None:
        base = _PROVIDER_DEFAULT.get(provider, {"frame": "pixels"})
    origin = f"model rule /{matched}/" if matched else f"provider default ({provider})"
    locked = bool(base.get("caps_locked"))
    sources = {}

    frame = (env[0] or "").strip().lower()
    if frame in _FRAMES:
        sources["frame"] = "env $GUI_COORD_FRAME"
    else:
        frame, sources["frame"] = base["frame"], origin

    w = (env[1] or "").strip().lower()
    if w in ("norm1000", "norm", "grid"):
        wording, sources["wording"] = "norm1000", "env $GUI_COORD_WORDING"
    elif w in ("pixels", "pixel", "px"):
        wording, sources["wording"] = "pixels", "env $GUI_COORD_WORDING"
    else:
        wording, sources["wording"] = frame, "follows the frame"

    edge, sources["img_edge"] = _cap("GUI_MAX_IMG_EDGE", _env_int("GUI_MAX_IMG_EDGE"),
                                     base.get("img_edge", DEFAULT_IMG_EDGE), locked)
    pixels, sources["img_pixels"] = _cap("MAX_IMG_PIXELS", _env_int("MAX_IMG_PIXELS"),
                                         base.get("img_pixels", DEFAULT_IMG_PIXELS), locked)
    for k in ("img_edge", "img_pixels"):
        if sources[k] == "model":
            sources[k] = origin

    out = {"provider": provider, "model": model, "matched": matched,
           "server_resizes": bool(base.get("server_resizes")),
           "frame": frame, "wording": wording, "img_edge": edge, "img_pixels": pixels,
           "caps_locked": locked, "sources": sources}
    _memo[key] = out
    return out


def warnings(prof=None):
    """Human-readable cautions about a resolved profile (printed at run start)."""
    prof = prof or resolve()
    out = []
    if prof["matched"] is None:
        out.append(f"no coordinate rule knows model {prof['model']!r}: running on the "
                   f"{prof['provider']} provider default (frame={prof['frame']}). Verify it "
                   f"once:  python -m authoring_framework.tools.gui.calibrate "
                   f"-p {prof['provider']} -m {prof['model']}")
    if prof["wording"] != prof["frame"]:
        out.append(f"coordinates are DESCRIBED as {prof['wording']} but DECODED as "
                   f"{prof['frame']} — an env override split them; clicks will be wrong "
                   f"unless that is deliberate")
    if prof.get("server_resizes") and not (prof["img_edge"] or prof["img_pixels"]):
        out.append("this provider is known to resize large images server-side (~1568 px / "
                   "~1.15 MP), which shifts a pixels-frame model's clicks, yet the screenshot "
                   "goes out uncapped — set $GUI_MAX_IMG_EDGE / $MAX_IMG_PIXELS (Claude: "
                   "1344 / 1100000) or confirm with `calibrate`")
    for k in ("img_edge", "img_pixels"):
        if "LOCKED" in prof["sources"][k]:
            out.append(f"{k}: {prof['sources'][k]}")
    return out


def describe(prof=None):
    prof = prof or resolve()
    cap = lambda v: "none" if not v else str(v)          # noqa: E731
    return (f"frame={prof['frame']} wording={prof['wording']} "
            f"img_edge<={cap(prof['img_edge'])} img_pixels<={cap(prof['img_pixels'])} "
            f"[{prof['sources']['frame']}]")
