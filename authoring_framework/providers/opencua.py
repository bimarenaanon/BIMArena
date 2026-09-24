"""OpenCUA (xlang-ai, the open computer-use foundation model) as an LLM provider.

Like EvoCUA (`evocua.py`), OpenCUA does not speak the framework's native tool-calling contract:
it was trained to answer a screenshot with a `## Thought / ## Action / ## Code` block whose
code is PyAutoGUI, and its OSWorld harness re-renders the whole episode every step. This
module is the provider-native representation of that contract, so `react.py` — the loop,
the tool layer, the grading — stays exactly what every other model runs under.

The configuration is OpenCUA-32B's released OSWorld-Verified one
(`run_multienv_opencua.py --use_old_sys_prompt --cot_level l2 --history_type action_history
--coordinate_type qwen25 --max_image_history_length 3`):

  * the model gets ITS OWN system prompt (`opencua_prompts.py`, verbatim), never
    react.prompt or the tool declarations;
  * the framework's neutral history is re-rendered into OpenCUA's shape each call — the
    task text as the Task Instruction, every earlier step as `# Step n: ## Action:` text,
    the last `OPENCUA_MAX_IMAGE_HISTORY - 1` (2) of them WITH the frame they answered, and
    the current screenshot: three screenshots per request, as in its OSWorld runs;
  * its PyAutoGUI code is translated into the framework's GUI tools; the fresh screenshot
    its loop expects after every step is the loop's own per-turn capture;
  * COORDINATES (`qwen25`): the model answers in the pixels of the Qwen2.5-VL
    smart-resized image (factor 28: a 1920x1080 screen becomes 1932x1092). The adapter
    computes that size from the frame it actually sent and rescales the answer onto the
    framework's norm1000 grid, which the GUI controller decodes back onto the screen — the
    click lands where OpenCUA's own harness would put it;
  * a reply its harness could not parse is re-requested (up to `OPENCUA_MAX_RETRY` times,
    at its retry temperature); when every retry fails the harness FAILS the episode, and so
    does this adapter (a call-less `RESULT: abandoned` reply);
  * `computer.terminate` becomes the call-less reply carrying the RESULT: line the loop
    ends on (`answer` passed through verbatim — the read atoms are graded off that text).

Nothing here teaches the model about the application: it sees the task text and the screen,
the same two things every other model on the GUI arms sees.
"""
from __future__ import annotations

import ast
import io
import math
import os
import re
import time

from ..ults.images import to_b64
from . import opencua_prompts as P
from .evocua import _clean_keys, _key_calls, _plain, _type_calls

_SYSTEM = P.SYSTEM_PROMPT_V1_L2

MAX_IMAGE_HISTORY = int(os.getenv("OPENCUA_MAX_IMAGE_HISTORY") or "3")  # screenshots/request
MAX_TOKENS = int(os.getenv("OPENCUA_MAX_TOKENS") or "2048")     # run_multienv_opencua default
TOP_P = float(os.getenv("OPENCUA_TOP_P") or "0.9")
MAX_RETRY = int(os.getenv("OPENCUA_MAX_RETRY") or "5")           # unparsable-reply re-requests
RETRY_TEMP = 0.2                                                # the harness's retry temperature
WAIT_S = float(os.getenv("OPENCUA_WAIT_S") or "5")              # computer.wait / time.sleep cap
SCROLL_CAP = 30                                                 # wheel steps per scroll call
PRESS_CAP = 20                                                  # pyautogui.press(presses=N) cap

# Qwen2.5-VL smart_resize, the model's input geometry (the `qwen25` coordinate type).
_FACTOR, _MIN_PIXELS, _MAX_PIXELS = 28, 3136, 12845056

# Per-process state (one run per process): a Shift held by keyDown turns the next click
# into the framework's shift_click.
_STATE = {"shift": False, "step": 0}


# ------------------------------------------------------------------ the provider entry
def chat(model, key, messages, system, tools, temp, base_url, timeout):
    """One OpenCUA step. Returns (reply, usage) in llm.py's neutral shape."""
    from openai import OpenAI
    client = OpenAI(api_key=key or "EMPTY", base_url=base_url, timeout=timeout, max_retries=0)
    if not tools:
        # Text-only use (the liveness probe, history compaction): a plain completion.
        return _plain(client, model, messages, system, temp)
    view, frame_size = _render(messages)
    if view is None:
        # No screenshot reached this call (the loop's capture failed): the model cannot act
        # blind — spend the turn and let the next one bring a frame.
        _STATE["step"] += 1
        return ({"text": None, "calls": [], "raw": None, "stop": "no_screen",
                 "continue": True},
                {"input": 0, "output": 0, "cache_read": 0})
    usage = {"input": 0, "output": 0, "cache_read": 0}
    content, parsed, stop = "", None, None
    for attempt in range(MAX_RETRY):
        # The harness re-requests an unparsable reply at max(0.2, T) — same here.
        t = temp if attempt == 0 else max(RETRY_TEMP, temp)
        resp = client.chat.completions.create(
            model=model, messages=view, max_tokens=MAX_TOKENS, temperature=t, top_p=TOP_P)
        content = resp.choices[0].message.content or ""
        stop = resp.choices[0].finish_reason
        u = getattr(resp, "usage", None)
        usage["input"] += getattr(u, "prompt_tokens", 0) or 0
        usage["output"] += getattr(u, "completion_tokens", 0) or 0
        parsed = parse(content)
        if parsed["ok"]:
            break
    _STATE["step"] += 1
    reply = translate(parsed, frame_size)
    # The Action section is what the model's history is rendered from (action_history).
    reply["raw"] = {"role": "assistant", "content": content, "action": parsed.get("action", "")}
    reply["stop"] = stop
    return reply, usage


# ------------------------------------------------------------------ history -> OpenCUA view
def _render(messages):
    """The framework's neutral history as OpenCUA's request plus the current frame's pixel
    size, or (None, None) when there is no current screenshot to act on.

    The opening message is the task (its text = the Task Instruction, its images = the
    drawings). After it, the run alternates screen captures and model responses: the loop
    captures the screen at the start of every turn, so captures and responses pair 1:1 and
    the pairing is done FROM THE END — the newest capture is the current screen, the one
    before it is the frame the newest response answered, and so on. The captures ride the
    loop's ephemeral tail message (the loop keeps MAX_IMAGE_HISTORY frames for this
    provider). The step layout is the OSWorld agent's `predict()` verbatim: every earlier
    step is `# Step n:` + `## Action:` text; the last MAX_IMAGE_HISTORY - 1 steps are each
    preceded by their frame as a user message, the older ones are joined into ONE assistant
    message placed before them; the current frame + instruction close the request."""
    opening = messages[0]
    instruction = "\n".join(p["text"] for p in opening["content"] if "text" in p).strip()
    drawings = [p["png"] for p in opening["content"] if "png" in p]

    frames, steps = [], []                      # steps = the Action text of every response
    for m in messages[1:]:
        role = m.get("role")
        if role == "assistant":
            raw = m.get("raw")
            if isinstance(raw, dict) and raw.get("content"):   # a no-screen turn has none
                steps.append(raw.get("action") or _action_of(raw["content"]))
        elif role == "user" and m.get("ephemeral"):
            frames += [p["png"] for p in m.get("content") or [] if "png" in p]
    if not frames:
        return None, None

    current = frames[-1]
    n_imaged = min(MAX_IMAGE_HISTORY - 1, len(frames) - 1, len(steps))
    imaged = list(zip(reversed(frames[:-1]), reversed(steps)))[:n_imaged]
    imaged.reverse()                            # oldest first
    n = len(steps)
    first_imaged = n - n_imaged                 # index of the first step that keeps its frame

    def image(png):
        return {"type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{to_b64(png)}"}}

    def step_text(i):
        return (P.STEP_TEMPLATE.format(step_num=i + 1)
                + P.ACTION_HISTORY_TEMPLATE.format(action=steps[i]))

    drawing_parts = []
    if drawings:
        # The drawings, when the case has any, go in front of the first frame the model
        # sees: OpenCUA's format has no other slot for a requirement image.
        drawing_parts = [{"type": "text", "text": "The task's drawing(s), before the screenshot:"}]
        drawing_parts += [image(d) for d in drawings]

    out = [{"role": "system", "content": _SYSTEM}]
    older = [step_text(i) for i in range(first_imaged)]
    if older:
        out.append({"role": "assistant", "content": "\n".join(older)})
    for k, (png, _) in enumerate(imaged):
        parts = (drawing_parts if k == 0 else []) + [image(png)]
        out.append({"role": "user", "content": parts})
        out.append({"role": "assistant", "content": step_text(first_imaged + k)})
    parts = (drawing_parts if not imaged else []) + [image(current)]
    parts.append({"type": "text",
                  "text": P.INSTRUTION_TEMPLATE.format(instruction=instruction)})
    out.append({"role": "user", "content": parts})
    return out, _png_size(current)


def _png_size(png):
    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        return im.size                          # (width, height)


def _action_of(content):
    return parse(content).get("action", "")


# ------------------------------------------------------------------ response -> sections
_OBS_RE = re.compile(r"^##\s*Observation\s*:?[\n\r]+(.*?)(?=^##\s*Thought:|^##\s*Action:|^##|\Z)",
                     re.DOTALL | re.MULTILINE)
_THOUGHT_RE = re.compile(r"^##\s*Thought\s*:?[\n\r]+(.*?)(?=^##\s*Action:|^##|\Z)",
                         re.DOTALL | re.MULTILINE)
_ACTION_RE = re.compile(r"^##\s*Action\s*:?[\n\r]+(.*?)(?=^##|\Z)", re.DOTALL | re.MULTILINE)
_CODE_RE = re.compile(r"```(?:code|python)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def parse(response):
    """OpenCUA's reply -> {"ok", "action", "thought", "kind", "code", "status", "answer"} —
    the OSWorld harness's `parse_response_to_cot_and_action` rules: the section headings,
    the LAST code block, `computer.wait` / `computer.terminate` special-cased, anything
    else is PyAutoGUI code. `ok` is False where the harness would re-request the reply."""
    text = response or ""
    out = {"ok": False, "action": "", "thought": "", "kind": None, "code": "",
           "status": None, "answer": ""}
    m = _THOUGHT_RE.search(text)
    if m:
        out["thought"] = m.group(1).strip()
    m = _ACTION_RE.search(text)
    if m:
        out["action"] = m.group(1).strip()
    blocks = _CODE_RE.findall(text)
    if not blocks:
        return out                              # "no code blocks found" -> retry
    code = blocks[-1].strip()
    out["code"] = code
    low = code.lower()
    if "computer.wait" in low:
        out.update(kind="wait", ok=True)
        return out
    if "computer.terminate" in low:
        if "failure" in low or "fail" in low:
            out.update(kind="terminate", status="failure", ok=True)
        elif "success" in low:
            out.update(kind="terminate", status="success", ok=True)
        else:
            return out                          # terminate without a status -> retry
        m = re.search(r"answer\s*=\s*(?:'''(.*?)'''|\"\"\"(.*?)\"\"\"|'([^']*)'|\"([^\"]*)\")",
                      code, re.DOTALL)
        if m:
            out["answer"] = next(g for g in m.groups() if g is not None).strip()
        return out
    if not out["action"]:
        return out                              # "missing required action section" -> retry
    out.update(kind="code", ok=True)
    return out


# ------------------------------------------------------------------ sections -> tool calls
def translate(parsed, frame_size):
    """The parsed reply as the loop's neutral reply: `text` (the whole response — the
    Thought/Action prose is the run's reasoning record), `calls` on the framework's GUI
    tools, or a call-less RESULT: reply on terminate / an unrecoverable parse failure. A
    step with nothing to execute (a wait, a code block with no supported call) is flagged
    `continue` so the loop goes on to the next turn — and its fresh screenshot — instead
    of reading the call-less reply as a finish."""
    text = _render_text(parsed)
    if not parsed["ok"]:
        # The harness returns FAIL after MAX_RETRY unparsable replies: the episode ends.
        return {"text": text + f"\n\nRESULT: abandoned — {MAX_RETRY} consecutive replies "
                "could not be parsed", "calls": []}
    if parsed["kind"] == "terminate":
        tail = f"\n{parsed['answer']}" if parsed["answer"] else ""
        if parsed["status"] == "failure":
            return {"text": "RESULT: abandoned — the agent reported failure" + tail, "calls": []}
        return {"text": "RESULT: completed" + tail, "calls": []}
    if parsed["kind"] == "wait":
        time.sleep(WAIT_S)
        return {"text": text, "calls": [], "continue": True}
    calls = _map_code(parsed["code"], frame_size)
    return {"text": text, "calls": calls, "continue": not calls}


def _render_text(parsed):
    parts = []
    if parsed.get("thought"):
        parts.append("## Thought:\n" + parsed["thought"])
    if parsed.get("action"):
        parts.append("## Action:\n" + parsed["action"])
    if parsed.get("code"):
        parts.append("## Code:\n" + parsed["code"])
    return "\n\n".join(parts)


def _map_code(code, frame_size):
    """A PyAutoGUI code block -> the framework's GUI calls, statement by statement."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    calls = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        name = _dotted(node.value.func)
        try:
            args = [ast.literal_eval(a) for a in node.value.args]
            kw = {k.arg: ast.literal_eval(k.value) for k in node.value.keywords if k.arg}
        except (ValueError, SyntaxError):
            continue
        calls += _map_call(name, args, kw, frame_size)
    return calls


def _dotted(func):
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _map_call(name, args, kw, frame_size):
    base = name.split(".")[-1]
    xy = _xy(args, kw, frame_size)
    if name.startswith("pyautogui."):
        if base == "click":
            button = str(kw.get("button", "left")).lower()
            if button not in ("left", "primary"):
                return []                        # right/middle clicks: not in the action space
            if int(kw.get("clicks", 1) or 1) >= 2:
                return [_call("mouse_double_click", xy or {})]
            if xy and _STATE["shift"]:
                return [_call("shift_click", xy)]
            return [_call("mouse_click", xy or {})]
        if base in ("doubleClick", "tripleClick"):
            return [_call("mouse_double_click", xy or {})]
        if base == "moveTo":
            return [_call("mouse_move_to", xy)] if xy else []
        if base in ("rightClick", "middleClick", "dragTo", "dragRel", "moveRel",
                    "mouseDown", "mouseUp"):
            return []
        if base in ("write", "typewrite"):
            text = kw.get("message", args[0] if args else "")
            return _type_calls(str(text))
        if base == "press":
            keys = kw.get("keys", args[0] if args else [])
            keys = _clean_keys(keys if isinstance(keys, list) else [keys])
            presses = min(PRESS_CAP, max(1, int(kw.get("presses", args[1] if len(args) > 1 else 1))))
            out = []
            for k in keys:
                out += _key_calls([k]) * presses
            return out
        if base == "hotkey":
            keys = kw.get("keys", list(args))
            return _key_calls(_clean_keys(keys if isinstance(keys, list) else [keys]))
        if base == "keyDown":
            if args and str(args[0]).lower() == "shift":
                _STATE["shift"] = True
            return []
        if base == "keyUp":
            if not args or str(args[0]).lower() == "shift":
                _STATE["shift"] = False
            return []
        if base in ("scroll", "hscroll"):
            n = kw.get("clicks", args[0] if args else 0)
            try:
                n = int(round(float(n)))
            except (TypeError, ValueError):
                return []
            n = max(-SCROLL_CAP, min(SCROLL_CAP, n))
            return [_call("scroll", {"dx": n} if base == "hscroll" else {"dy": n})]
        if base == "sleep":
            return _sleep(args)
        return []
    if name == "computer.triple_click":
        return [_call("mouse_double_click", xy or {})]
    if name in ("time.sleep", "sleep"):
        return _sleep(args)
    return []


def _sleep(args):
    try:
        time.sleep(min(float(args[0]) if args else WAIT_S, WAIT_S))
    except (TypeError, ValueError):
        pass
    return []


def smart_resize(height, width, factor=_FACTOR, min_pixels=_MIN_PIXELS, max_pixels=_MAX_PIXELS):
    """Qwen2.5-VL's input geometry (qwen_vl_utils.smart_resize, verbatim): both sides
    rounded to a multiple of `factor`, the pixel count kept within [min, max]."""
    h_bar = max(1, round(height / factor)) * factor
    w_bar = max(1, round(width / factor)) * factor
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = max(1, math.floor(height / beta / factor)) * factor
        w_bar = max(1, math.floor(width / beta / factor)) * factor
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


def _xy(args, kw, frame_size):
    """The call's (x, y) -> the framework's norm1000 point, or None. The model answers in
    the pixels of the smart-resized frame (`qwen25`); the harness projects
    `x / resized_w * screen_w`, which on the norm1000 grid is `x / resized_w * 1000`. A
    value already in 0..1 is taken as a fraction of the screen."""
    x = kw.get("x", args[0] if len(args) > 0 else None)
    y = kw.get("y", args[1] if len(args) > 1 else None)
    if x is None or y is None or not frame_size:
        return None
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        return None
    w, h = frame_size
    h_bar, w_bar = smart_resize(h, w)
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
        return {"x": int(round(x * 1000.0)), "y": int(round(y * 1000.0))}
    return {"x": int(round(x / w_bar * 1000.0)), "y": int(round(y / h_bar * 1000.0))}


_SEQ = [0]


def _call(name, args):
    _SEQ[0] += 1
    return {"id": f"opencua-{_STATE['step']}-{_SEQ[0]}", "name": name, "args": dict(args)}
