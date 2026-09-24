"""The LLM primitive — a multi-turn conversation with NATIVE TOOL CALLING.

One entry point, `chat()`: a list of messages plus the tool declarations in, the model's reply
(text and/or tool calls) out. Every provider is reached through the same neutral shapes, so the
ReAct loop in `react.py` never learns which provider it is on.

    messages = [
      {"role": "user",      "content": [{"text": str} | {"png": bytes}, ...]},
      {"role": "assistant", "text": str|None, "calls": [...], "raw": <provider-native>},
      {"role": "tool",      "results": [{"id", "name", "content": str, "error": bool}, ...]},
    ]
    tools    = [{"name", "description", "parameters": <JSON Schema>}, ...]
                 (exactly what `ToolRegistry.tool_specs()` returns)
    ->         {"text": str|None, "calls": [{"id", "name", "args": dict}, ...],
                "raw": <provider-native assistant turn>, "stop": str|None}

REPLAYING THE ASSISTANT TURN. Each reply carries `raw`, the provider's own representation of
that turn, and the adapters send THAT back rather than a reconstruction. It is the only way to
be faithful about what a provider requires to be echoed verbatim — Anthropic's extended
thinking blocks must survive the round trip for the next tool turn to be accepted at all, and
a rebuilt-from-neutral-fields turn silently drops them.

Cross-cutting behaviour, all in one place:
- PER-ROLE model / reasoning effort: $LLM_MODEL_<ROLE> and $LLM_EFFORT_<ROLE> / $LLM_EFFORT
  beat the session model and `config.REASONING_EFFORT`.
- USAGE ACCOUNTING per role, snapshotted into the run's stats.
- TRANSIENT RETRY with exponential backoff: one dropped connection or 503 must not kill a run
  that is twenty tool calls deep.
- STALL GUARD: a hard per-attempt timeout (`config.LLM_TIMEOUT`, default 240 s) on every
  provider's HTTP client, with the SDKs' own silent retries DISABLED (max_retries=0): an
  endpoint sometimes accepts a request and never answers, and the SDK defaults (600 s × 3
  attempts) would freeze a run for tens of minutes per stall. A tripped timeout
  tears the connection down and re-enters the transient loop on a FRESH client immediately
  (no backoff — a stall is not a rate limit, and the wait was already paid).
- OUTPUT CAP: an explicit generous max-tokens on every provider.
- PROVIDER QUIRKS, memoized so each is probed once per process rather than once per call:
  OpenAI kwargs are stripped on rejection; Anthropic degrades thinking/temperature in a fixed
  order; Gemini drops a schema construct its validator refuses.
"""
import json
import os
import re
import time

from ..ults.images import to_b64

# A run is a long sequence of calls; a single transient blip (DNS hiccup, dropped TCP, rate
# limit, 5xx) must NOT abort it. Retry these with exponential backoff.
# 2026-08-31, user decision after a 26-minute run died on a network blip: ride out
# transient errors HARD. A flat 30 s wait x 10 retries (~5+ min of pure outage riding on
# top of the per-attempt timeouts) before giving the run up — the harness re-runs a dead
# case from scratch, so giving up costs the WHOLE run, not one call. $LLM_RETRIES /
# $LLM_RETRY_WAIT tune it.
_RETRIES = int(os.getenv("LLM_RETRIES") or "10")
_RETRY_WAIT_S = float(os.getenv("LLM_RETRY_WAIT") or "30")
_TRANSIENT_MARKERS = ("connection", "timeout", "getaddrinfo", "temporarily", "overloaded",
                      "rate limit")
# HTTP status codes must match as standalone numbers — a bare substring check makes "500"
# match inside a token count ("prompt is too long: 215000 tokens"), giving a PERMANENT
# error the full transient retry/backoff treatment (4 wasted calls re-uploading every image).
_TRANSIENT_CODES = re.compile(r"(?<!\d)(?:429|500|502|503|504)(?!\d)")
_TRANSIENT_TYPES = ("APIConnectionError", "APITimeoutError", "RateLimitError",
                    "InternalServerError", "ConnectError", "ConnectTimeout", "ReadTimeout",
                    "RemoteProtocolError", "TimeoutException", "DeadlineExceeded",
                    "EmptyReply")


class EmptyReply(Exception):
    """The endpoint answered with neither text nor a tool call. The ReAct loop reads "no tool
    calls" as THE AGENT IS FINISHED, so such a turn must never be returned: it is raised as a
    TRANSIENT error and `chat()` simply re-sends the turn."""


# The maximum response length of every call (the paper's setting). $LLM_MAX_OUTPUT_TOKENS
# overrides. NOTE: on the reasoning models this cap INCLUDES the reasoning tokens (OpenAI
# `max_output_tokens`, Anthropic `max_tokens` with thinking on), so a turn that reasons long
# can be cut short — such turns are counted in `stats["truncated_turns"]`.
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS") or 8192)

# EVERY call goes to the VENDOR'S OWN endpoint. The endpoints are passed to the SDKs EXPLICITLY: with
# base_url=None each SDK reads its own environment variable ($OPENAI_BASE_URL,
# $ANTHROPIC_BASE_URL, $GOOGLE_GEMINI_BASE_URL), so a stray one in a shell or .env would
# silently re-route a run.
OPENAI_ENDPOINT = "https://api.openai.com/v1"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com"


def _is_transient(e):
    s = str(e).lower()
    return (e.__class__.__name__ in _TRANSIENT_TYPES
            or any(m in s for m in _TRANSIENT_MARKERS)
            or bool(_TRANSIENT_CODES.search(s)))


_TIMEOUT_TYPES = ("APITimeoutError", "ReadTimeout", "ConnectTimeout", "TimeoutException",
                  "DeadlineExceeded")

# A CONFIGURATION error, never an outage: a rejected key, a forbidden or unknown model. The
# provider answered — it is the run's setup that is wrong, and every retry (and every
# further case of a batch) would fail the same way, so the agent must stop at once with a
# plain message rather than exit as "provider down".
_CONFIG_TYPES = ("AuthenticationError", "PermissionDeniedError", "NotFoundError")
_CONFIG_CODES = re.compile(r"(?<!\d)(?:401|403|404)(?!\d)")
_CONFIG_MARKERS = ("invalid x-api-key", "invalid api key", "incorrect api key", "api key not valid",
                   "unauthorized", "authentication", "permission denied", "model not found",
                   "does not exist or you do not have access", "not_found_error")


def is_config_error(e):
    s = str(e).lower()
    return (e.__class__.__name__ in _CONFIG_TYPES
            or any(m in s for m in _CONFIG_MARKERS)
            or bool(_CONFIG_CODES.search(s)))


def _is_stall(e):
    """A per-attempt timeout — the stall guard tripped (or the transport timed out on its
    own). Retried WITHOUT backoff: the wait was already paid inside the dead attempt, and
    each attempt reconnects on a fresh client anyway."""
    return (e.__class__.__name__ in _TIMEOUT_TYPES
            or "timed out" in str(e).lower() or "timeout" in str(e).lower())


def _args_of(raw_json, name):
    """A tool call's arguments dict from the provider's JSON string. A model occasionally emits
    malformed JSON here; returning the failure rather than raising lets the loop answer that
    ONE call with an error result (which the model can correct) instead of losing the turn."""
    if isinstance(raw_json, dict):
        return raw_json, None
    try:
        args = json.loads(raw_json or "{}")
    except (TypeError, ValueError) as e:
        return {}, f"{name}: arguments were not valid JSON ({e})"
    return (args, None) if isinstance(args, dict) else ({}, f"{name}: arguments were not an object")


class LLM:
    """One framework's binding of the LLM primitive to its config module."""

    def __init__(self, settings):
        self.settings = settings
        self._usage = {}
    # ------------------------------------------------------------- usage accounting
    def _tally(self, role, model, usage):
        u = self._usage.setdefault(role or "other",
                                   {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                    "cache_read_tokens": 0, "cache_write_tokens": 0,
                                    "model": model})
        u["calls"] += 1
        u["input_tokens"] += int(usage.get("input") or 0)
        u["output_tokens"] += int(usage.get("output") or 0)
        u["cache_read_tokens"] += int(usage.get("cache_read") or 0)
        u["cache_write_tokens"] = u.get("cache_write_tokens", 0) + int(usage.get("cache_write") or 0)
        u["model"] = model

    def usage_snapshot(self):
        """Cumulative LLM usage this process: {"by_role": {...}, "total": {...}}."""
        total = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                 "cache_write_tokens": 0}
        for u in self._usage.values():
            for k in total:
                total[k] += u.get(k, 0)
        out = {"by_role": {k: dict(v) for k, v in self._usage.items()}, "total": total}
        return out

    # ------------------------------------------------------------- per-role resolution
    def _model_for(self, cfg, role):
        """$LLM_MODEL_<ROLE> > the session model."""
        if role:
            m = os.getenv(f"LLM_MODEL_{role.upper()}")
            if m:
                return m
        return cfg["model"]

    def _effort_for(self, cfg, role):
        """Reasoning effort (none|low|medium|high|xhigh|max), or None to send nothing:
        $LLM_EFFORT_<ROLE> > $LLM_EFFORT > config.REASONING_EFFORT. OpenAI-family only."""
        e = (role and os.getenv(f"LLM_EFFORT_{role.upper()}")) or os.getenv("LLM_EFFORT")
        if e:
            return e
        return getattr(self.settings, "REASONING_EFFORT", None)

    def model_for(self, role=None):
        """The model id this role would run on right now (what the run banner prints)."""
        return self._model_for(self.settings.provider_config(), role)

    # ------------------------------------------------------------- the entry points
    def chat(self, messages, system=None, tools=None, role=None, temperature=None):
        """One turn of the conversation. See the module docstring for the message shapes."""
        cfg = self.settings.provider_config()
        model = self._model_for(cfg, role)
        if not cfg["key"]:
            raise SystemExit(f"no API key for {cfg['provider']} "
                             f"(set one of {cfg['key_envs']} in .env)")
        temp = self.settings.TEMPERATURE if temperature is None else temperature
        effort = self._effort_for(cfg, role)
        for attempt in range(_RETRIES + 1):
            started = time.monotonic()
            try:
                out, usage = self._dispatch(cfg, model, messages, system, tools, temp, effort)
                self._tally(role, model, usage)
                out["usage"] = dict(usage)      # per-call figures for the run trace
                return out
            except Exception as e:
                if attempt == _RETRIES or not _is_transient(e) or is_config_error(e):
                    raise
                elapsed = time.monotonic() - started
                if _is_stall(e):
                    # The stall guard tripped: the attempt sat dead for `elapsed` seconds.
                    # Reconnect and re-send NOW — every attempt builds a fresh client, so
                    # the retry cannot reuse the wedged connection.
                    print(f"[llm] attempt stalled {elapsed:.0f}s ({e.__class__.__name__}); "
                          f"reconnect + retry {attempt + 1}/{_RETRIES}")
                    continue
                wait = _RETRY_WAIT_S
                print(f"[llm] transient {e.__class__.__name__} ({str(e)[:120]}) after {elapsed:.0f}s; "
                      f"retry {attempt + 1}/{_RETRIES} in {wait}s")
                time.sleep(wait)

    def complete(self, text, images=None, system=None, role=None):
        """One text-only exchange (no tools) — the convenience wrapper over `chat`."""
        content = [{"text": text}] + [{"png": img} for img in (images or [])]
        return (self.chat([{"role": "user", "content": content}], system=system,
                          role=role) or {}).get("text")

    def _dispatch(self, cfg, model, messages, system, tools, temp, effort):
        p = cfg["provider"]
        if p == "openai":
            # The vendor's own endpoint speaks the Responses API: /v1/chat/completions rejects
            # function tools + reasoning_effort outright on the reasoning models.
            return _openai_responses(model, cfg["key"], messages, system, tools, temp, effort)
        if p in ("qwen", "meta"):
            # Both vendors serve an OpenAI-COMPATIBLE Chat Completions dialect on THEIR OWN
            # endpoint (DashScope / api.meta.ai) — that is the vendor API.
            base = self.settings.QWEN_BASE_URL if p == "qwen" else self.settings.META_BASE_URL
            return _openai_chat(model, cfg["key"], messages, system, tools, temp, effort, base)
        if p == "anthropic":
            return _anthropic_chat(model, cfg["key"], messages, system, tools, temp, effort)
        if p == "gemini":
            return _gemini_chat(model, cfg["key"], messages, system, tools, temp)
        if p == "evocua":
            # A computer-use fine-tune: its own prompt format in, its computer_use call
            # translated back to the framework's GUI tools (providers/evocua.py).
            from . import evocua
            return evocua.chat(model, cfg["key"], messages, system, tools, temp,
                            cfg.get("base_url"), _config.LLM_TIMEOUT)
        if p == "opencua":
            # Same idea for OpenCUA: its OSWorld prompt format in, its PyAutoGUI code
            # translated back to the framework's GUI tools (providers/opencua.py).
            from . import opencua
            return opencua.chat(model, cfg["key"], messages, system, tools, temp,
                                cfg.get("base_url"), _config.LLM_TIMEOUT)
        raise SystemExit(f"unknown LLM provider {p!r}")


from .. import config as _config          # noqa: E402  (the class above must exist first)

# THE binding the framework imports. One instance per process, so `usage_snapshot()` covers
# the whole run.
_impl = LLM(_config)
chat = _impl.chat
complete = _impl.complete
usage_snapshot = _impl.usage_snapshot
model_for = _impl.model_for


def _system_text(system):
    """A list-of-blocks system prompt joined for providers without per-block caching."""
    if isinstance(system, (list, tuple)):
        return "\n\n".join(s for s in system if s) or None
    return system


# ==================================================================== OpenAI / Qwen

# Kwarg adjustments an endpoint needed ("rename_max", "drop:<kwarg>"), memoized per
# (base_url, model) and re-applied up front — without this a model that rejects e.g.
# `temperature` pays one failed round-trip on EVERY call.
_OPENAI_KW_MEMO = {}


def _openai_messages(messages, system):
    """Neutral messages -> the Chat Completions `messages` array."""
    out = []
    sys_text = _system_text(system)
    if sys_text:
        out.append({"role": "system", "content": sys_text})
    for m in messages:
        if m["role"] == "user":
            content = []
            for part in m["content"]:
                if "text" in part:
                    content.append({"type": "text", "text": part["text"]})
                else:
                    url = f"data:image/png;base64,{to_b64(part['png'])}"
                    content.append({"type": "image_url", "image_url": {"url": url}})
            out.append({"role": "user", "content": content})
        elif m["role"] == "assistant":
            out.append(m["raw"])
        else:                                   # tool results: ONE message per call, by id
            for r in m["results"]:
                out.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
    return out


def _openai_chat(model, key, messages, system, tools, temp, effort, base_url):
    from openai import OpenAI
    # Stall guard: explicit per-request timeout, SDK-internal retries OFF — retry policy
    # (including the reconnect-on-stall) lives in chat()'s loop, in one place.
    client = OpenAI(api_key=key, base_url=base_url,        # the vendor's own endpoint (qwen / meta)
                    timeout=_config.LLM_TIMEOUT, max_retries=0)
    kwargs = {"temperature": temp, "max_completion_tokens": MAX_OUTPUT_TOKENS}
    if effort:
        kwargs["reasoning_effort"] = effort
    if tools:
        kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
    applied = list(_OPENAI_KW_MEMO.get((base_url, model), ()))
    for adj in applied:                          # re-apply what this endpoint needed before
        if adj == "rename_max" and "max_completion_tokens" in kwargs:
            kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
        elif adj.startswith("drop:"):
            kwargs.pop(adj[5:], None)
    msgs = _openai_messages(messages, system)
    if "strip_reasoning" in applied:             # this endpoint rejected replayed reasoning
        _strip_reasoning(msgs)
    resp, last_e = None, None
    for _ in range(6):                           # strip whichever kwarg this endpoint rejects
        try:
            resp = client.chat.completions.create(model=model, messages=msgs, **kwargs)
            if applied:
                _OPENAI_KW_MEMO[(base_url, model)] = tuple(applied)
            break
        except Exception as e:
            s = str(e).lower()
            bad = next((k for k in ("max_completion_tokens", "max_tokens", "reasoning_effort",
                                    "temperature") if k in s and k in kwargs), None)
            if bad is None:
                raise
            last_e = e
            if bad == "max_completion_tokens":   # older param name on compatible endpoints
                kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
                applied.append("rename_max")
            else:
                kwargs.pop(bad)
                applied.append(f"drop:{bad}")
    if resp is None:
        raise RuntimeError(f"OpenAI call failed after stripping unsupported params "
                           f"(last error: {last_e})") from last_e
    msg = resp.choices[0].message
    # Rebuild the assistant turn EXPLICITLY rather than model_dump()-ing it: the SDK object
    # carries fields (refusal, annotations, audio) that some compatible endpoints reject when
    # echoed back.
    raw = {"role": "assistant"}
    if msg.content:
        raw["content"] = msg.content
    calls = []
    for tc in (msg.tool_calls or []):
        args, err = _args_of(tc.function.arguments, tc.function.name)
        calls.append({"id": tc.id, "name": tc.function.name, "args": args, "bad_args": err})
    if msg.tool_calls:
        raw["tool_calls"] = [{"id": tc.id, "type": "function",
                              "function": {"name": tc.function.name,
                                           "arguments": tc.function.arguments}}
                             for tc in msg.tool_calls]
    u = getattr(resp, "usage", None)
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    usage = {"input": getattr(u, "prompt_tokens", 0),
             "output": getattr(u, "completion_tokens", 0), "cache_read": cached}
    return {"text": msg.content, "calls": calls, "raw": raw,
            "stop": resp.choices[0].finish_reason}, usage


# ------------------------------------------------------------------- Responses API (direct)

def _responses_input(messages):
    """Neutral messages -> the Responses API `input` array. An assistant turn's `raw` is the
    response's own output-item LIST (reasoning + message + function_call items) and is replayed
    verbatim — the run is STATELESS (store=False), so the encrypted reasoning content must
    survive the round trip exactly like Anthropic's thinking blocks. Tool results become
    `function_call_output` items referencing the call ids."""
    out = []
    for m in messages:
        if m["role"] == "user":
            content = []
            for part in m["content"]:
                if "text" in part:
                    content.append({"type": "input_text", "text": part["text"]})
                else:
                    content.append({"type": "input_image",
                                    "image_url": f"data:image/png;base64,{to_b64(part['png'])}"})
            out.append({"role": "user", "content": content})
        elif m["role"] == "assistant":
            out.extend(m["raw"])
        else:                                   # tool results: ONE item per call, by call id
            for r in m["results"]:
                out.append({"type": "function_call_output", "call_id": r["id"],
                            "output": r["content"]})
    return out


def _openai_responses(model, key, messages, system, tools, temp, effort):
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=OPENAI_ENDPOINT,
                    timeout=_config.LLM_TIMEOUT, max_retries=0)             # stall guard
    kwargs = {"temperature": temp, "max_output_tokens": MAX_OUTPUT_TOKENS,
              # stateless: nothing retained server-side, so the reasoning items come back
              # encrypted and are replayed by us (see _responses_input)
              "store": False, "include": ["reasoning.encrypted_content"]}
    if effort:
        kwargs["reasoning"] = {"effort": effort}
    if tools:
        kwargs["tools"] = [{"type": "function", "name": t["name"],
                            "description": t["description"], "parameters": t["parameters"]}
                           for t in tools]
    sys_text = _system_text(system)
    if sys_text:
        kwargs["instructions"] = sys_text
    applied = list(_OPENAI_KW_MEMO.get(("responses", model), ()))
    for adj in applied:                          # re-apply what this model needed before
        kwargs.pop(adj[5:], None)
    inp = _responses_input(messages)
    resp, last_e = None, None
    for _ in range(5):                           # strip whichever kwarg the model rejects
        try:
            resp = client.responses.create(model=model, input=inp, **kwargs)
            if applied:
                _OPENAI_KW_MEMO[("responses", model)] = tuple(applied)
            break
        except Exception as e:
            s = str(e).lower()
            bad = next((k for k in ("temperature", "max_output_tokens", "reasoning",
                                    "include", "store") if k in s and k in kwargs), None)
            if bad is None:
                raise
            last_e = e
            kwargs.pop(bad)
            applied.append(f"drop:{bad}")
    if resp is None:
        raise RuntimeError(f"OpenAI Responses call failed after stripping unsupported params "
                           f"(last error: {last_e})") from last_e

    text_parts, calls, raw = [], [], []
    for item in resp.output or []:
        raw.append(item.model_dump(exclude_none=True))
        if item.type == "message":
            for part in item.content or []:
                if getattr(part, "type", "") == "output_text" and part.text:
                    text_parts.append(part.text)
        elif item.type == "function_call":
            args, err = _args_of(item.arguments, item.name)
            calls.append({"id": item.call_id, "name": item.name, "args": args,
                          "bad_args": err})
    text = "\n".join(text_parts) or None
    u = getattr(resp, "usage", None)
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    usage = {"input": getattr(u, "input_tokens", 0),
             "output": getattr(u, "output_tokens", 0), "cache_read": cached}
    stop = getattr(getattr(resp, "incomplete_details", None), "reason", None) or resp.status
    return {"text": text, "calls": calls, "raw": raw, "stop": stop}, usage


# ==================================================================== Anthropic

# Which attempt shape worked for a given model — memoized so a model that rejects e.g.
# thinking doesn't pay a failed round-trip on EVERY call.
_ANTHROPIC_ATTEMPT = {}


def _anthropic_messages(messages):
    """Neutral messages -> the Messages API `messages` array. Tool results are USER turns.

    The LAST message's last block carries a cache breakpoint: system + tools alone stop the
    cached prefix before the conversation, so every turn re-billed the ENTIRE history at full
    input price — on a long run that is the dominant cost. With the marker here, each turn
    reads the previous turn's prefix from cache and pays only the delta. (3 of the 4 allowed
    breakpoints are in use: system, tools, and this one.)"""
    out = []
    for m in messages:
        if m["role"] == "user":
            content = []
            for part in m["content"]:
                if "text" in part:
                    content.append({"type": "text", "text": part["text"]})
                else:
                    content.append({"type": "image", "source": {
                        "type": "base64", "media_type": "image/png",
                        "data": to_b64(part["png"])}})
            out.append({"role": "user", "content": content, "_ephemeral": bool(m.get("ephemeral"))})
        elif m["role"] == "assistant":
            out.append({"role": "assistant", "content": m["raw"]})
        else:
            blocks = []
            for r in m["results"]:
                b = {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                if r.get("error"):
                    b["is_error"] = True
                blocks.append(b)
            out.append({"role": "user", "content": blocks})
    for m in reversed(out):
        # mark the newest PERSISTENT user message (assistant raw is replayed verbatim — do not
        # touch it; an ephemeral tail — the per-call screenshot message — is rebuilt every
        # turn and must stay OUTSIDE the cached prefix, so it is skipped)
        if m["role"] == "user" and not m.get("_ephemeral") and isinstance(m["content"], list) and m["content"]:
            last = m["content"][-1]
            if isinstance(last, dict):
                m["content"][-1] = {**last, "cache_control": {"type": "ephemeral"}}
            break
    for m in out:
        m.pop("_ephemeral", None)          # never reaches the wire
    return out


_ANTHROPIC_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _anthropic_chat(model, key, messages, system, tools, temp, effort=None):
    import anthropic
    parts = system if isinstance(system, (list, tuple)) else ([system] if system else [])
    parts = [s for s in parts if s]
    # The system prompt is static for the whole run and resent every turn — cache it. Same for
    # the tool declarations (~40k characters here), marked on the LAST tool, which caches the
    # whole block. `config.LLM_CACHE=0` sends both UNCACHED (a cost ablation) — the payload the
    # model sees is identical either way.
    cache = {"cache_control": {"type": "ephemeral"}} if _config.LLM_CACHE else {}
    # ONE breakpoint on the LAST system block (a breakpoint caches the whole prefix before
    # it, so marking every block buys nothing) + one on the last tool = 2 of the API's
    # maximum of 4 cache_control blocks (marking every system part exceeds it: 400 "A maximum
    # of 4 blocks with cache_control").
    sys_blocks = ([{"type": "text", "text": s, **(cache if i == len(parts) - 1 else {})}
                   for i, s in enumerate(parts)]
                  if parts else anthropic.NOT_GIVEN)
    tool_kw = {}
    if tools:
        decls = [{"name": t["name"], "description": t["description"],
                  "input_schema": t["parameters"]} for t in tools]
        if cache:
            decls[-1] = {**decls[-1], **cache}
        tool_kw = {"tools": decls}
    # Ordered degradation, richest first: adaptive thinking (vision + spatial reasoning benefit
    # from it, and the raw-replay above keeps its blocks intact across tool turns); then a
    # plain call with temperature (older models); then bare. Degrade ONLY on a parameter
    # rejection — a transport error must reach chat()'s retry.
    # EFFORT (Claude 4.6+ / Opus 5): `output_config.effort` is the ONLY depth control for
    # adaptive thinking (budget_tokens is rejected on Opus 5). Sent when $LLM_EFFORT /
    # config.REASONING_EFFORT names a valid level; the framework default "high" equals the
    # API default, so setting nothing changes nothing — `medium`/`low` are the cost levers
    # (opus-5 GUI runs measured ~1.5k hidden thinking tokens per turn at high, 2026-09-03).
    eff = {"output_config": {"effort": effort}} if effort in _ANTHROPIC_EFFORTS else {}
    attempts = [{"thinking": {"type": "adaptive"}, **eff},
                {"thinking": {"type": "adaptive"}},          # an endpoint that rejects output_config
                {"temperature": temp}, {}]
    # EXPLICIT base_url: with None the SDK would read $ANTHROPIC_BASE_URL from the environment
    # — every call must go to the vendor's own endpoint, whatever a stray env var says.
    client = anthropic.Anthropic(api_key=key, base_url=ANTHROPIC_ENDPOINT,
                                 timeout=_config.LLM_TIMEOUT,
                                 max_retries=0)                              # stall guard
    kw = dict(model=model, max_tokens=MAX_OUTPUT_TOKENS, system=sys_blocks,
              messages=_anthropic_messages(messages), **tool_kw)
    resp = None
    for i in range(_ANTHROPIC_ATTEMPT.get(model, 0), len(attempts)):
        try:
            resp = client.messages.create(**kw, **attempts[i])
            _ANTHROPIC_ATTEMPT[model] = i
            break
        except Exception as e:
            s = str(e).lower()
            if i == len(attempts) - 1 or not any(m in s for m in ("thinking", "temperature",
                                                                   "output_config", "effort")):
                raise
    blocks = [b.model_dump(exclude_none=True) for b in resp.content]
    calls, text = [], None
    for b in blocks:
        if b.get("type") == "tool_use":
            args, err = _args_of(b.get("input"), b.get("name"))
            calls.append({"id": b["id"], "name": b["name"], "args": args, "bad_args": err})
        elif b.get("type") == "text" and text is None:
            text = b.get("text")
    # EMPTY REPLY: neither text nor a tool call. The ReAct loop reads "no tool calls" as
    # THE AGENT IS FINISHED, so an empty turn silently ends the case 30 seconds in and it
    # gets graded on whatever existed — a false failure indistinguishable from a real one
    # (live-hit 2026-08-27: create_slab_opening1 ended at turn 2 with 1561 output tokens
    # that carried no text and no tool_use — thinking blocks only). A finished agent ALWAYS
    # writes its summary, so an empty reply is never a legitimate ending: retry the turn.
    if not calls and not (text or "").strip():
        kinds = [b.get("type") for b in blocks]
        raise EmptyReply(f"empty reply — no text, no tool calls (blocks={kinds}, "
                            f"stop={getattr(resp, 'stop_reason', None)}, "
                            f"out_tokens={getattr(getattr(resp, 'usage', None), 'output_tokens', '?')})")
    u = getattr(resp, "usage", None)
    usage = {"input": getattr(u, "input_tokens", 0), "output": getattr(u, "output_tokens", 0),
             "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
             "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
    return {"text": text, "calls": calls, "raw": blocks,
            "stop": getattr(resp, "stop_reason", None)}, usage


# ==================================================================== Gemini

# Models whose endpoint rejected our function declarations (Gemini validates them against its
# own OpenAPI subset) — the tools are sent unsanitized once, then sanitized thereafter.
_GEMINI_DECL_BAD = set()


def _gemini_clean(schema):
    """A JSON Schema reduced to Gemini's accepted subset: it rejects the validation keywords
    we use for documentation (minItems, enum on a non-string, ...) on some model versions."""
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items()
           if k in ("type", "description", "properties", "items", "required", "enum")}
    if "properties" in out:
        out["properties"] = {k: _gemini_clean(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _gemini_clean(out["items"])
    return out


def _gemini_contents(messages, types):
    """Neutral messages -> the genai `contents` list."""
    out = []
    for m in messages:
        if m["role"] == "user":
            parts = []
            for part in m["content"]:
                if "text" in part:
                    parts.append(types.Part.from_text(text=part["text"]))
                else:
                    parts.append(types.Part.from_bytes(data=part["png"],
                                                       mime_type="image/png"))
            out.append(types.Content(role="user", parts=parts))
        elif m["role"] == "assistant":
            out.append(types.Content(role="model", parts=m["raw"]))
        else:
            # Gemini matches a function response to its call by NAME, not by id.
            out.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=r["name"],
                                                  response={"result": r["content"]})
                for r in m["results"]]))
    return out


def _gemini_chat(model, key, messages, system, tools, temp):
    from google import genai
    from google.genai import types

    def _cfg(clean):
        kw = dict(temperature=temp, system_instruction=_system_text(system) or None,
                  max_output_tokens=MAX_OUTPUT_TOKENS)
        if tools:
            decls = [{"name": t["name"], "description": t["description"],
                      "parameters": _gemini_clean(t["parameters"]) if clean
                      else t["parameters"]}
                     for t in tools]
            kw["tools"] = [types.Tool(function_declarations=decls)]
        return types.GenerateContentConfig(**kw)

    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        base_url=GEMINI_ENDPOINT,                       # pinned — see OPENAI_ENDPOINT
        timeout=int(_config.LLM_TIMEOUT * 1000)))       # stall guard (genai wants ms)
    contents = _gemini_contents(messages, types)
    clean = model in _GEMINI_DECL_BAD
    try:
        resp = client.models.generate_content(model=model, contents=contents, config=_cfg(clean))
    except Exception as e:
        # A construct the validator refuses rejects the whole REQUEST — sanitize, remember, retry.
        if clean or not any(w in str(e).lower() for w in ("schema", "function", "declaration")):
            raise
        _GEMINI_DECL_BAD.add(model)
        resp = client.models.generate_content(model=model, contents=contents, config=_cfg(True))
    cand = (resp.candidates or [None])[0]
    parts = list(getattr(getattr(cand, "content", None), "parts", None) or [])
    calls, text = [], None
    for i, p in enumerate(parts):
        fc = getattr(p, "function_call", None)
        if fc is not None:
            args, err = _args_of(dict(fc.args or {}), fc.name)
            # Gemini issues no call ids; synthesize a stable one for THIS turn (the function
            # response is matched back by name, so the id is only for our own bookkeeping).
            calls.append({"id": f"{fc.name}-{i}", "name": fc.name, "args": args,
                          "bad_args": err})
        elif getattr(p, "text", None) and text is None:
            text = p.text
    um = getattr(resp, "usage_metadata", None)
    usage = {"input": getattr(um, "prompt_token_count", 0) or 0,
             "output": getattr(um, "candidates_token_count", 0) or 0,
             "cache_read": getattr(um, "cached_content_token_count", 0) or 0}
    return {"text": text, "calls": calls, "raw": parts,
            "stop": getattr(cand, "finish_reason", None)}, usage
