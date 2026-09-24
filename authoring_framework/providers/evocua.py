"""EvoCUA (an OpenCUA-style computer-use fine-tune) as an LLM provider.

A CUA fine-tune does not speak the framework's native tool-calling contract: it was trained
on ONE `computer_use` function embedded in its own system prompt, answers with an `Action:`
line plus a `<tool_call>` JSON block, and expects a fresh screenshot after every step. This
module is the provider-native representation of that contract, so `react.py` — the loop,
the tool layer, the grading — stays exactly what every other model runs under:

  * the model gets ITS OWN system prompt (`evocua_prompts.py`, verbatim from the EvoCUA repo),
    never react.prompt or the tool declarations: that prompt + a 20-tool catalog is
    out-of-distribution for a CUA fine-tune, and a run on it would measure prompt mismatch
    rather than the model;
  * the framework's neutral history is re-rendered into EvoCUA's shape each call — the task
    text as the Instruction, the last `EVOCUA_HISTORY` (4, its harness default)
    (screenshot, response) pairs, the current screenshot, older steps as "Previous actions";
  * its `computer_use` call is translated into the framework's GUI tools; the fresh
    screenshot EvoCUA's loop expects after every action is the loop's own per-turn capture
    (`react._capture_screen`), so each step's response pairs with the frame it answered;
  * COORDINATES: EvoCUA's harness runs `--coordinate_type relative` — the prompt tells the
    model the screen is 1000x1000, it answers on a 0..999 grid, and the harness scales by
    `original / 999`. The GUI controller's norm1000 decode divides by 1000, so the adapter
    rescales by 1000/999 first: a click lands where EvoCUA's own harness would put it;
  * `terminate` becomes the call-less reply carrying the RESULT: line the loop ends on
    (`answer` is passed through verbatim — the read atoms are graded off that text).

Nothing here teaches the model about the application: it sees the task text and the screen,
the same two things every other model on the GUI arms sees.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time

from ..ults.images import to_b64
from . import evocua_prompts as P

# The one tool EvoCUA knows. Its prompt names the screen as 1000x1000 in relative mode; the
# tools XML is json.dumps of the schema, exactly as the upstream agent builds it.
_RESOLUTION_LINE = "* The screen's resolution is 1000x1000."
_SYSTEM = P.S2_SYSTEM_PROMPT.format(tools_xml=json.dumps(P.build_s2_tools_def(
    P.S2_DESCRIPTION_PROMPT_TEMPLATE.format(resolution_info=_RESOLUTION_LINE))))
_INSTRUCTION_TMPL = ("\nPlease generate the next move according to the UI screenshot, "
                     "instruction and previous actions.\n\nInstruction: {instruction}\n\n"
                     "Previous actions:\n{previous}")

HISTORY = int(os.getenv("EVOCUA_HISTORY") or "4")          # (screenshot, response) pairs kept
MAX_TOKENS = int(os.getenv("EVOCUA_MAX_TOKENS") or "4096")  # a step is a few hundred tokens
TOP_P = float(os.getenv("EVOCUA_TOP_P") or "0.9")            # the upstream agent's default
MAX_UNPARSED = int(os.getenv("EVOCUA_MAX_UNPARSED") or "5")  # consecutive action-less replies
GRID = 999.0                                                 # EvoCUA's relative frame is 0..999
SCROLL_CAP = 30                                              # wheel steps per scroll call

# Per-process state (one run per process): a Shift held by `key_down` turns the next click
# into the framework's shift_click; the unparsed streak ends a run that never acts.
_STATE = {"shift": False, "unparsed": 0, "step": 0}


# ------------------------------------------------------------------ the provider entry
def chat(model, key, messages, system, tools, temp, base_url, timeout):
    """One EvoCUA step. Returns (reply, usage) in llm.py's neutral shape."""
    from openai import OpenAI
    client = OpenAI(api_key=key or "EMPTY", base_url=base_url, timeout=timeout, max_retries=0)
    if not tools:
        # Text-only use (the liveness probe, history compaction): a plain completion.
        return _plain(client, model, messages, system, temp)
    view = _render(messages)
    if view is None:
        # No screenshot reached this call (the loop's capture failed): the model cannot act
        # blind — spend the turn and let the next one bring a frame.
        _STATE["step"] += 1
        return ({"text": None, "calls": [], "raw": None, "stop": "no_screen",
                 "continue": True},
                {"input": 0, "output": 0, "cache_read": 0})
    resp = client.chat.completions.create(
        model=model, messages=view, max_tokens=MAX_TOKENS, temperature=temp, top_p=TOP_P)
    content = resp.choices[0].message.content or ""
    u = getattr(resp, "usage", None)
    usage = {"input": getattr(u, "prompt_tokens", 0) or 0,
             "output": getattr(u, "completion_tokens", 0) or 0, "cache_read": 0}
    _STATE["step"] += 1
    reply = translate(content)
    reply["raw"] = {"role": "assistant", "content": content}
    reply["stop"] = resp.choices[0].finish_reason
    return reply, usage


def _plain(client, model, messages, system, temp):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": _text_of(system)})
    for m in messages:
        if m["role"] == "user":
            msgs.append({"role": "user", "content": _parts(m["content"])})
        elif m["role"] == "assistant" and (m.get("raw") or {}).get("content"):
            msgs.append({"role": "assistant", "content": m["raw"]["content"]})
    resp = client.chat.completions.create(model=model, messages=msgs, max_tokens=MAX_TOKENS,
                                          temperature=temp, top_p=TOP_P)
    u = getattr(resp, "usage", None)
    return ({"text": resp.choices[0].message.content, "calls": [], "raw": None,
             "stop": resp.choices[0].finish_reason},
            {"input": getattr(u, "prompt_tokens", 0) or 0,
             "output": getattr(u, "completion_tokens", 0) or 0, "cache_read": 0})


def _text_of(system):
    if isinstance(system, (list, tuple)):
        return "\n\n".join(s for s in system if s)
    return system or ""


def _parts(content):
    out = []
    for p in content:
        if "text" in p:
            out.append({"type": "text", "text": p["text"]})
        elif "png" in p:
            out.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{to_b64(p['png'])}"}})
    return out


# ------------------------------------------------------------------ history -> EvoCUA view
def _render(messages):
    """The framework's neutral history as EvoCUA's request, or None when there is no
    current screenshot to act on.

    The opening message is the task (its text = the Instruction, its images = the drawings).
    After it, the run alternates screen captures and model responses: the loop captures the
    screen at the start of every turn, so captures and responses pair 1:1 and the pairing is
    done FROM THE END — the newest capture is the current screen, the one before it is the
    frame the newest response answered, and so on. The captures ride the loop's ephemeral
    tail message (the newest KEEP_IMAGES frames — run EvoCUA with AGENT_KEEP_IMAGES =
    EVOCUA_HISTORY + 1)."""
    opening = messages[0]
    instruction = "\n".join(p["text"] for p in opening["content"] if "text" in p).strip()
    drawings = [p["png"] for p in opening["content"] if "png" in p]

    frames, responses = [], []
    for m in messages[1:]:
        role = m.get("role")
        if role == "assistant":
            raw = m.get("raw")
            content = raw.get("content") if isinstance(raw, dict) else None
            if content:                         # a synthetic no-screen turn has none
                responses.append(content)
        elif role == "user" and m.get("ephemeral"):
            frames += [p["png"] for p in m.get("content") or [] if "png" in p]
    if not frames:
        return None

    current = frames[-1]
    pairs = list(zip(reversed(frames[:-1]), reversed(responses)))[:HISTORY]
    pairs.reverse()                              # oldest first
    earlier = responses[:len(responses) - len(pairs)]
    previous = "\n".join(f"Step {i + 1}: {_action_line(r)}"
                         for i, r in enumerate(earlier)) or "None"
    instr_text = _INSTRUCTION_TMPL.format(instruction=instruction, previous=previous)

    def image(png):
        return {"type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{to_b64(png)}"}}

    def first_user(png):
        # The drawings, when the case has any, go in front of the first frame: EvoCUA's
        # format has no other slot for a requirement image.
        parts = []
        if drawings:
            parts.append({"type": "text",
                          "text": "The task's drawing(s), before the screenshot:"})
            parts += [image(d) for d in drawings]
        parts.append(image(png))
        parts.append({"type": "text", "text": instr_text})
        return {"role": "user", "content": parts}

    out = [{"role": "system", "content": [{"type": "text", "text": _SYSTEM}]}]
    for i, (png, resp) in enumerate(pairs):
        out.append(first_user(png) if i == 0 else {"role": "user", "content": [image(png)]})
        out.append({"role": "assistant", "content": [{"type": "text", "text": resp}]})
    out.append(first_user(current) if not pairs
               else {"role": "user", "content": [image(current)]})
    return out


def _action_line(response):
    for line in response.splitlines():
        s = line.strip()
        if s.lower().startswith("action:"):
            return s.split(":", 1)[1].strip()
    return "(no action line)"


# ------------------------------------------------------------------ response -> tool calls
def parse(response):
    """EvoCUA's reply -> (action_line, [tool-call dicts]) — the upstream parser's rules:
    `<tool_call>...</tool_call>` blocks, and bare `{...}` lines carrying name+arguments."""
    action, calls = "", []
    inside, buf = False, []
    for line in (response or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("action:"):
            if not action:
                action = line.split(":", 1)[1].strip()
            continue
        if line.startswith("<tool_call>"):
            inside, buf = True, []
            rest = line[len("<tool_call>"):].strip()
            if rest.endswith("</tool_call>"):
                rest = rest[:-len("</tool_call>")].strip()
                inside = False
                _add(calls, rest)
            elif rest:
                buf.append(rest)
            continue
        if line.startswith("</tool_call>"):
            if buf:
                _add(calls, "\n".join(buf))
            inside, buf = False, []
            continue
        if inside:
            if line.endswith("</tool_call>"):     # the closing tag glued to the JSON's last line
                buf.append(line[:-len("</tool_call>")].strip())
                _add(calls, "\n".join(buf))
                inside, buf = False, []
            else:
                buf.append(line)
            continue
        if line.startswith("{") and line.endswith("}"):
            _add(calls, line)
    if buf:
        _add(calls, "\n".join(buf))
    return action, calls


def _add(calls, raw):
    try:
        # strict=False: a model that puts a literal newline inside a JSON string (a typed
        # text ending in Enter) still parses, where the upstream parser would drop the step.
        obj = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        try:
            obj = ast.literal_eval(raw)
        except Exception:
            return
    if isinstance(obj, dict) and "name" in obj and isinstance(obj.get("arguments"), dict):
        calls.append(obj)


def translate(response):
    """The model's reply as the loop's neutral reply: `text` (the whole response — the
    Thought/Action prose is the run's reasoning record), `calls` on the framework's GUI
    tools, or a call-less RESULT: reply on terminate. A step with nothing to execute (a
    `wait`, an unparsed reply) is flagged `continue` so the loop goes on to the next turn —
    and its fresh screenshot — instead of reading the call-less reply as a finish."""
    action, tool_calls = parse(response)
    calls, final = [], None
    for tc in tool_calls:
        if tc.get("name") != "computer_use":
            continue
        mapped, done = _map(tc["arguments"])
        calls += mapped
        if done:
            final = done
            break
    if final:
        _STATE["unparsed"] = 0
        return {"text": final, "calls": []}
    if not tool_calls:
        _STATE["unparsed"] += 1
        if _STATE["unparsed"] >= MAX_UNPARSED:
            return {"text": (response or "") + f"\n\nRESULT: abandoned — {MAX_UNPARSED} "
                    "consecutive replies carried no computer_use call", "calls": []}
    else:
        _STATE["unparsed"] = 0
    return {"text": response, "calls": calls, "continue": not calls}


_KEY_ALIAS = {"return": "enter", "escape": "esc", "back_space": "backspace",
              "page_up": "pageup", "page_down": "pagedown", "super": "win", "cmd": "win",
              "control": "ctrl", "del": "delete", "minus": "-", "plus": "+", "equal": "=",
              "period": ".", "comma": ",", "spacebar": "space"}


def _map(args):
    """One computer_use call -> ([framework calls], final_text_or_None)."""
    act = str(args.get("action") or "").lower()
    xy = _coord(args.get("coordinate"))
    if act in ("left_click", "click"):
        if xy and _STATE["shift"]:
            return [_call("shift_click", xy)], None
        return [_call("mouse_click", xy or {})], None
    if act in ("double_click", "triple_click"):
        return [_call("mouse_double_click", xy or {})], None
    if act == "mouse_move":
        return ([_call("mouse_move_to", xy)] if xy else []), None
    if act in ("right_click", "middle_click", "left_click_drag"):
        return [], None                      # not in the benchmark's GUI action space
    if act == "type":
        return _type_calls(args.get("text", "")), None
    if act == "key":
        return _key_calls(_clean_keys(args.get("keys", []))), None
    if act == "key_down":
        keys = [k.lower() for k in _clean_keys(args.get("keys", []))]
        if "shift" in keys:
            _STATE["shift"] = True
        return [], None
    if act == "key_up":
        keys = [k.lower() for k in _clean_keys(args.get("keys", []))]
        if "shift" in keys or not keys:
            _STATE["shift"] = False
        return [], None
    if act in ("scroll", "hscroll"):
        n = _num(args.get("pixels", 0))
        n = max(-SCROLL_CAP, min(SCROLL_CAP, int(round(n))))
        return [_call("scroll", {"dx": n} if act == "hscroll" else {"dy": n})], None
    if act == "wait":
        time.sleep(min(float(_num(args.get("time", 2))), 5.0))
        return [], None
    if act == "terminate":
        status = str(args.get("status", "success")).lower()
        answer = str(args.get("answer") or "").strip()
        tail = f"\n{answer}" if answer else ""
        if status == "failure":
            return [], "RESULT: abandoned — the agent reported failure" + tail
        return [], "RESULT: completed" + tail
    if act == "answer":
        answer = str(args.get("answer") or args.get("text") or "").strip()
        return [], "RESULT: completed" + (f"\n{answer}" if answer else "")
    return [], None


def _type_calls(text):
    """EvoCUA types character by character with a newline as Enter; the framework's `type`
    tool types a string, so the text is split at newlines with press_enter in between. The
    upstream agent also un-escapes literal backslash sequences first — same here."""
    text = str(text)
    try:
        text = text.encode("latin-1", "backslashreplace").decode("unicode_escape")
    except Exception:
        pass
    out = []
    segs = text.split("\n")
    for i, seg in enumerate(segs):
        if seg:
            out.append(_call("type", {"text": seg}))
        if i < len(segs) - 1:
            out.append(_call("press_enter", {}))
    return out


def _key_calls(keys):
    keys = [_KEY_ALIAS.get(str(k).strip().lower(), str(k).strip().lower())
            for k in keys if str(k).strip()]
    if not keys:
        return []
    if len(keys) == 1:
        k = keys[0]
        if k == "enter":
            return [_call("press_enter", {})]
        if k == "esc":
            return [_call("press_esc", {})]
        if k == "tab":
            return [_call("press_tab", {})]
        if k == "delete":
            return [_call("delete_selected", {})]
    return [_call("hotkey", {"keys": keys})]


def _clean_keys(raw):
    """The upstream agent's tolerance for keys arriving as "keys=['ctrl','s']" strings."""
    keys = raw if isinstance(raw, list) else [raw]
    out = []
    for k in keys:
        if isinstance(k, str):
            if k.startswith("keys=["):
                k = k[6:]
            if k.endswith("]"):
                k = k[:-1]
            if k.startswith("['") or k.startswith('["'):
                k = k[2:] if len(k) > 2 else k
            if k.endswith("']") or k.endswith('"]'):
                k = k[:-2] if len(k) > 2 else k
            pieces = re.split(r"[,+]", k) if ("," in k or "+" in k) else [k]
            for piece in pieces:
                piece = piece.strip().strip("'\"")
                if piece:
                    out.append(piece)
        else:
            out.append(str(k))
    return out


def _coord(v):
    """EvoCUA's 0..999 grid point -> the framework's norm1000 frame (x * 1000/999), as
    ints. Accepts the list the schema declares and the "[x, y]" string Qwen-family models
    sometimes emit."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            nums = re.findall(r"-?\d+(?:\.\d+)?", v)
            v = [float(n) for n in nums[:2]]
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        return None
    try:
        x, y = float(v[0]), float(v[1])
    except (TypeError, ValueError):
        return None
    return {"x": int(round(x * 1000.0 / GRID)), "y": int(round(y * 1000.0 / GRID))}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


_SEQ = [0]


def _call(name, args):
    _SEQ[0] += 1
    return {"id": f"cua-{_STATE['step']}-{_SEQ[0]}", "name": name, "args": dict(args)}
