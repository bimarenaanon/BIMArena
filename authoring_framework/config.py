"""Centralised constants and environment for the framework.

Holds the LLM provider/model config, the tool-family selection, the run budgets and the run
paths. Loads `.env` from the project root.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from .tools.target import (BIM_TARGETS, REVIT_ROUTES_URL, bim_target, bim_targets,
                           set_target_override)

# authoring_framework/config.py -> parent == package dir; parents[1] == project root
PKG = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# --- LLM provider (switchable: openai | gemini | anthropic | qwen | meta | evocua | opencua) ---
# default model + accepted API-key env names per provider. Override the model with
# LLM_MODEL; pick the provider with LLM_PROVIDER (or --provider on the CLI).
# Every key here is the vendor's own, and llm.py pins each SDK to the vendor's own endpoint.
_PROVIDERS = {
    "openai":    {"model": "gpt-5.6-sol",     "keys": ["OA_OPENAI_KEY", "OPENAI_API_KEY"]},
    # A VISION model is mandatory: the agent reads screenshots, so a text-only default would
    # break the run outright. (`Gemini_KET` is the spelling actually present in this repo's
    # .env — do NOT remove it.)
    "gemini":    {"model": "gemini-3.7-flash",
                  "keys": ["Gemini_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "Gemini_KET"]},
    "anthropic": {"model": "claude-opus-5",
                  "keys": ["Anthropic_KEY", "ANTHROPIC_API_KEY"]},
    # Qwen (Alibaba DashScope) speaks the OpenAI-compatible chat API. Region via QWEN_BASE_URL.
    "qwen":      {"model": "qwen3.7-plus",    "keys": ["Qwen_KEY", "QWEN_API_KEY",
                                                       "DASHSCOPE_API_KEY"]},
    # Meta (dev.meta.ai). OpenAI-compatible chat API at $META_BASE_URL; probed 2026-08-26:
    # /v1/chat/completions with a Bearer key, native tool_calls, and image_url vision — all
    # three are required here (the GUI arms feed screenshots and drive multi-step tool loops).
    "meta":      {"model": "muse-spark-1.1",  "keys": ["Meta_KEY", "META_API_KEY",
                                                       "LLAMA_API_KEY"]},
    # EvoCUA (meituan, an OpenCUA-style computer-use fine-tune) served by vLLM as an
    # OpenAI-compatible endpoint at $EVOCUA_BASE_URL (`--served-model-name EvoCUA`). It does
    # NOT speak native tool calling — providers/evocua.py renders the run in its own prompt
    # format and translates its `computer_use` call back. vLLM needs no key ("EMPTY").
    "evocua":    {"model": "EvoCUA",          "keys": ["EVOCUA_KEY"]},
    # OpenCUA (xlang-ai) served the same way at $OPENCUA_BASE_URL; providers/opencua.py
    # renders its OSWorld prompt format and translates its PyAutoGUI code back.
    "opencua":   {"model": "OpenCUA-32B",     "keys": ["OPENCUA_KEY"]},
}
LLM_PROVIDERS = list(_PROVIDERS)        # valid --provider choices (kept in sync with _PROVIDERS)

# Qwen's OpenAI-compatible base URL. Default = mainland-China DashScope; override via env for the
# international (dashscope-intl) / US / HK endpoints.
QWEN_BASE_URL = (os.getenv("QWEN_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
                 or "https://dashscope.aliyuncs.com/compatible-mode/v1")

# Meta's OpenAI-compatible base URL (dev.meta.ai). $META_BASE_URL overrides.
META_BASE_URL = os.getenv("META_BASE_URL") or "https://api.meta.ai/v1"

# The EvoCUA vLLM endpoint. Default = the model's own `vllm serve --port 8080` on this
# machine (or an SSH tunnel to it); a guest VM points it at the host's VMnet address.
EVOCUA_BASE_URL = os.getenv("EVOCUA_BASE_URL") or "http://127.0.0.1:8080/v1"
OPENCUA_BASE_URL = os.getenv("OPENCUA_BASE_URL") or "http://127.0.0.1:8080/v1"
_override = {}


def set_llm_override(provider=None, model=None):
    """CLI hook: force a provider/model for this process (beats env)."""
    if provider:
        _override["provider"] = provider.lower()
    if model:
        _override["model"] = model


def current_provider():
    """The provider this process drives (--provider override > $LLM_PROVIDER > openai), for
    callers that need the provider's conventions without resolving a key — the GUI
    controller's coordinate-frame decode (Gemini/Qwen/Meta answer in a 0-1000 frame)."""
    return (_override.get("provider") or os.getenv("LLM_PROVIDER") or "openai").lower()


def current_model():
    """The model id this process drives (--model override > $LLM_MODEL > the provider's
    default), without resolving a key — the GUI coordinate profile keys on it."""
    spec = _PROVIDERS.get(current_provider()) or {}
    return _override.get("model") or os.getenv("LLM_MODEL") or spec.get("model") or ""


def provider_config(provider=None, model=None):
    """Resolve the active provider, model id, and API key (call-arg > --override > env > default)."""
    p = (provider or _override.get("provider") or os.getenv("LLM_PROVIDER") or "openai").lower()
    if p not in _PROVIDERS:
        raise SystemExit(f"Unknown LLM provider '{p}' (use: {', '.join(_PROVIDERS)})")
    spec = _PROVIDERS[p]
    explicit = model or _override.get("model") or os.getenv("LLM_MODEL")
    m = explicit or spec["model"]
    key_env = next((k for k in spec["keys"] if os.getenv(k)), None)
    key = os.getenv(key_env) if key_env else None
    cfg = {"provider": p, "model": m, "key": key, "key_envs": spec["keys"],
           "model_explicit": bool(explicit)}
    if p in ("evocua", "opencua"):
        # A self-hosted vLLM checks no key; llm.chat still insists on one being set.
        cfg["key"] = key or "EMPTY"
        cfg["base_url"] = EVOCUA_BASE_URL if p == "evocua" else OPENCUA_BASE_URL
    return cfg


# Reasoning effort for every call (none | low | medium | high | xhigh | max); $LLM_EFFORT
# overrides. Only sent to OpenAI-family models. The agent reads drawings and reasons about
# geometry, so the default is not the cheapest tier.
REASONING_EFFORT = os.getenv("LLM_EFFORT") or "high"

# Sampling temperature for all LLM calls: T = 1.0, the providers' default sampling
# configuration (the paper's setting). Some models only accept their default temperature;
# llm.py drops the parameter for those. $LLM_TEMPERATURE overrides.
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "1.0"))

# Hard per-ATTEMPT timeout (seconds) on every LLM HTTP request, $LLM_TIMEOUT overrides.
# An endpoint sometimes accepts a request and never answers; the
# SDK defaults (600 s, PLUS 2 silent SDK-internal retries) let one such stall freeze a run
# for tens of minutes. With this cap the stalled attempt is torn down and llm.py's transient
# retry re-sends it on a FRESH connection. Raise it before suspecting the mechanism if a
# provider's slowest LEGITIMATE calls (a high-effort reasoning turn over a late-run history
# with screenshots) start tripping it.
# 90 s leaves headroom for a slow legitimate turn over a long history and still cuts a true
# stall's cost to a fraction of the 600 s SDK default.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))

# PROMPT CACHING (Anthropic): the system blocks and the ~40k-character tool declarations are
# resent every turn, so they are marked `cache_control: ephemeral` by default. Set
# $LLM_CACHE=0 to send them uncached (a cost ablation). Costs tokens; changes nothing the model
# sees.
LLM_CACHE = (os.getenv("LLM_CACHE", "1").strip().lower() not in ("0", "false", "no"))


# --- TOOL MODES (what the agent may look up) ---
# The framework is a COMPUTER-USE agent: the one interface is the application's GUI (screen +
# mouse + keyboard). The mode is the SUPPORT axis — the paper's three settings:
#   gui-raw      w/o support    no retrieval tool at all;
#   gui-docs     w/ doc         `documentation_retrieval` (the vendors' official help);
#   gui-support  w/ doc+skill   the documentation PLUS `operational_skill_retrieval` (the
#                               benchmark authors' hand-written per-capability procedures).
_TOOL_MODES = {
    "gui-raw":     {"families": ("gui",), "gui_learning": None},
    "gui-docs":    {"families": ("gui",), "gui_learning": "help"},
    "gui-support": {"families": ("gui",), "gui_learning": "skills"},
}
TOOL_MODES = tuple(_TOOL_MODES)

# Earlier spellings, accepted wherever a mode is.
TOOL_MODE_ALIASES = {"gui-skills": "gui-support", "gui-priors": "gui-support"}
_tools_override = {}


def set_tools_override(mode=None):
    """CLI hook: force which tool mode this process runs (beats $AGENT_TOOLS)."""
    if mode:
        _tools_override["mode"] = mode.lower()


def tool_mode():
    mode = (_tools_override.get("mode") or os.getenv("AGENT_TOOLS") or "gui-support").lower()
    mode = TOOL_MODE_ALIASES.get(mode, mode)
    if mode not in _TOOL_MODES:
        raise SystemExit(f"unknown tool mode {mode!r} (use: {', '.join(TOOL_MODES)})")
    return mode


def tool_families():
    """The enabled tool families, as a tuple in canonical order."""
    return _TOOL_MODES[tool_mode()]["families"]


def gui_learning():
    """The mode's retrieval channel: None (gui-raw), "help" (gui-docs — the official help
    corpus) or "skills" (gui-support — the operational skills on top of it)."""
    return _TOOL_MODES[tool_mode()]["gui_learning"]


# --- run budget ---
# HARD CAP on model turns — the ONE run limiter. A turn is one LLM call, which may carry
# several tool calls; a reply with no tool calls ends the run before the cap. $AGENT_MAX_TURNS
# overrides; 0 (or negative) = NO cap at all — only use under a harness with its own timeout.
MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS") or 100)

# --- history compaction ---
# The conversation is replayed IN FULL every turn, so a long run's history only ever grows.
# When its TEXT weight (characters, images excluded — those are budgeted by KEEP_IMAGES)
# passes COMPACT_CHARS, the loop spends ONE extra LLM call folding everything between the
# opening task message and the most recent COMPACT_KEEP_MSGS messages into a single written
# briefing (built state, key numbers, failures seen, what remains). 0 disables compaction.
COMPACT_CHARS = int(os.getenv("AGENT_COMPACT_CHARS") or 300_000)
COMPACT_KEEP_MSGS = int(os.getenv("AGENT_COMPACT_KEEP") or 20)

# --- per-run working directories ---
# Each run gets runs/<id>/ (memory + outputs). $AGENT_RUNS_DIR relocates the whole runs
# tree — REQUIRED when several guests execute this package from ONE shared checkout (the
# VM bench): runs/.current is a single pointer file, and three agents writing it into the
# same shared runs/ made each guest's harness collect ANOTHER guest's run (2026-09-03).
RUNS_DIR = Path(os.getenv("AGENT_RUNS_DIR") or (PKG / "runs"))

__all__ = ["BIM_TARGETS", "REVIT_ROUTES_URL", "bim_target", "bim_targets",
           "set_target_override",
           "LLM_PROVIDERS", "TOOL_MODES", "TOOL_MODE_ALIASES", "MAX_TURNS",
           "COMPACT_CHARS", "COMPACT_KEEP_MSGS",
           "QWEN_BASE_URL", "META_BASE_URL", "REASONING_EFFORT", "TEMPERATURE",
           "LLM_TIMEOUT", "LLM_CACHE",
           "RUNS_DIR", "PKG", "ROOT", "provider_config", "set_llm_override",
           "set_tools_override", "tool_mode", "tool_families", "gui_learning"]
