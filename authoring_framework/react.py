"""The agent: a ReAct loop over the GUI (computer-use) action space.

One model, one conversation, one loop:

    see the screen -> reason -> act (mouse / keyboard / lookups) -> see the screen -> ... -> answer

There are no roles, no plan, no per-step supervision and no verify pass. The model is handed
the task, the action space as native tool declarations, and a fresh screenshot every turn;
what used to be framework behaviour is the agent's own decision — when to consult the manual,
when it is finished.

What the framework still owns lives in the TOOL LAYER rather than here:
  - `tools.plan_batch` validates every call against the tool's declared params (a GUI batch
    is TRUNCATED at the first unusable call — the rest would act at a stale cursor position);
  - `tools.run_batch` executes them, pacing the calls;
  - the turn cap (MAX_TURNS) stops a run that is going nowhere.

IMAGES. The loop captures the screen at the start of every turn and shows the current + the
previous capture (`_capture_screen` / `_screen_tail`) — there is no tool for it. A lookup's
page images are parked on the ToolContext and attached as real images after its result; only
the most recent lookup's pages are kept in the history.
"""
import io
import os
import itertools
import json
import re
import sys
import time
import traceback
from pathlib import Path

from .config import (COMPACT_CHARS, COMPACT_KEEP_MSGS, MAX_TURNS,
                     bim_targets, gui_learning, provider_config, tool_families, tool_mode)
from .memory import session
from .providers.llm import chat, complete, is_config_error as llm_is_config_error, model_for, usage_snapshot
from .ults.images import to_png_bytes
from .ults.runs import new_run, screenshot_path, trace_event
from . import tools as toolkit

SYSTEM = (Path(__file__).resolve().parent / "prompt" / "react.prompt").read_text(
    encoding="utf-8")
ROLE = "react"           # the usage-accounting / per-role-override tag for every call

# Cap on ONE tool result's serialized payload. An unfiltered whole-model dump is tens of
# kilobytes and would crowd out the rest of the conversation; the read tools' own descriptions
# tell the model to narrow the ask, and the truncation note says so again when it does not.
RESULT_CHARS = 6000

# LOOKUP results (the External Support group: operational_skill_retrieval, documentation_retrieval,
# the knowledge tools) are EXEMPT from RESULT_CHARS and get this backstop
# instead. A retrieved recipe/article IS the payload — the whole operational-support mechanism is that the
# document lands in the conversation and stays there. Until 2026-08-19 these went through the
# generic 6000 cap, and a skill bundle (primitives + recipe, 20k+ chars) was cut BEFORE the
# recipe's first step: the agent "consulted the manual" and got a truncated primitives dump
# plus a note to ask narrower — which is why runs read skills and then visibly did not follow
# them. 60k (~15k tokens) is above every current bundle; it exists to stop a pathological
# document chain, not to shape normal lookups.
LOOKUP_RESULT_CHARS = 60_000

# THE SCREEN IS SHOWN, NOT ASKED FOR (2026-09-21, user decision). There is no `observation`
# tool in the GUI action space any more: on a run that drives the UI the loop captures the
# screen at the START of EVERY turn and sends the KEEP_IMAGES newest captures — by default the
# CURRENT screen plus the one the previous turn started from — as ONE ephemeral user message
# appended to the request AFTER the history. The captures are never stored in the history
# (rebuilt per call, outside the cache breakpoint), so the cached prefix is never rewritten;
# the price is re-sending those images every turn at the plain input rate.
# LOOKUP PAGE IMAGES (help articles, knowledge pages — tagged "kind": "lookup" by
# _attach_images) are the only images that live IN the history: the most recent lookup's
# pages ALL survive, however many that lookup attached — a retrieved article is one unit —
# and pages from OLDER lookups are dropped (re-running the lookup brings them back).
KEEP_IMAGES = int(os.getenv("AGENT_KEEP_IMAGES") or "2")   # the evocua provider raises this
# to EVOCUA_HISTORY + 1 in run() (its step history pairs each response with a frame)

# A reply with NO tool call ends the run, and the prompt's FINISHING protocol makes a real
# finish announce itself with a "RESULT:" line. A call-less reply WITHOUT that line is not a
# finish: runs have ended at turn 3 on the text "I clicked the floor tool. Now I need to
# observe what happened" (stop=end_turn, no tool_use block — the call the model announced
# never arrived). The agent is told and asked to
# continue, at most this many times per run; a third such reply is accepted as the answer.
NUDGE_MAX = int(os.getenv("AGENT_NUDGE_MAX") or "2")

_C = {"agent": "\033[36m", "tools": "\033[33m", "result": "\033[90m", "warn": "\033[31m"}
_RESET, _BOLD = "\033[0m", "\033[1m"

# Exit code for "the LLM provider stayed down through llm.py's retries". A provider outage is
# NOT a model result: the bench runner keys on this (plus mem["aborted"]="llm_failure") to
# discard the half-run and retry the case instead of grading a half-modified project.
EXIT_LLM_FAILURE = 13


# ---------------------------------------------------------------- history hygiene

def _prune_images(messages):
    """Drop stale LOOKUP page images from the conversation, in place.

    Lookup pages (parts tagged "kind": "lookup") are the only images stored in the history —
    screen captures ride the ephemeral tail (`_screen_tail`). The most recent lookup-carrying
    message keeps ALL its pages — an article's pages are one unit — while older lookups' pages
    are dropped (the lookup can be re-run).

    Replaced by a one-line placeholder rather than removed, so the model can see that it once
    had a picture there. Mutating in place matters: the bytes are gone for every later turn
    too, not just this one.

    THE OPENING MESSAGE IS EXEMPT: it carries the task drawings, which are the REQUIREMENT —
    no tool can re-fetch them, so pruning them would leave the agent building the rest of the
    model from memory of an image it saw once (`_maybe_compact` spares it for the same
    reason)."""
    lookup_kept = False        # the newest lookup-carrying message has been passed already
    for m in reversed(messages[1:]):
        if m.get("role") != "user":
            continue
        parts = m.get("content") or []
        has_lookup = any("png" in p and p.get("kind") == "lookup" for p in parts)
        if has_lookup and lookup_kept:
            m["content"] = [
                {"text": "[a page image from an older lookup was dropped from this history "
                         "to keep it small — re-run the lookup if you still need it]"}
                if "png" in part and part.get("kind") == "lookup" else part
                for part in parts]
        if has_lookup:
            lookup_kept = True


# ---------------------------------------------------------------- history compaction

_COMPACT_SYSTEM = (
    "You compress the working history of an agent that is authoring a BIM model mid-run. "
    "Write the briefing its NEXT turn will rely on INSTEAD of the full log. Preserve, in "
    "terse bullets: (1) every element BUILT or MODIFIED so far — its id/guid, kind, host, "
    "storey and the key numbers; (2) numeric facts read from the drawing or the model that "
    "are still needed; (3) decisions and substitutions made, with their stated reasons; "
    "(4) every FAILURE seen and its cause, so it is not repeated; (5) what remains to be "
    "done. Copy identifiers and numbers EXACTLY — never invent, merge or round them. Drop "
    "pleasantries and dead ends that resolved without consequence.")


def _history_chars(messages):
    """The conversation's replayed TEXT weight. Image bytes are excluded — they are budgeted
    separately by KEEP_IMAGES and would swamp this count. An assistant turn counts its RAW
    payload too: on the reasoning-replay routes (Responses API encrypted items, Anthropic's
    thinking blocks) that is what actually rides the wire, and it can be several times the
    visible text — ignoring it made compaction trigger long after the real request size."""
    n = 0
    for m in messages:
        if m.get("role") == "assistant":
            raw = m.get("raw")
            n += (len(str(raw)) if raw is not None
                  else len(m.get("text") or "")
                  + len(json.dumps(m.get("calls") or [], ensure_ascii=False, default=str)))
        elif m.get("role") == "tool":
            n += sum(len(r.get("content") or "") for r in m.get("results") or [])
        else:
            n += sum(len(p.get("text") or "") for p in (m.get("content") or []) if "text" in p)
    return n


def _render_for_summary(messages):
    """The stretch of history to be compacted, rendered as plain text for the summary call."""
    lines = []
    for m in messages:
        if m.get("role") == "assistant":
            if m.get("text"):
                lines.append("AGENT: " + m["text"])
            for c in m.get("calls") or []:
                lines.append("  CALL " + _fmt_call(c))
        elif m.get("role") == "tool":
            for r in m.get("results") or []:
                lines.append(f"  RESULT[{r.get('name')}]: {(r.get('content') or '')[:1500]}")
        else:
            for p in m.get("content") or []:
                lines.append(("USER: " + p["text"]) if "text" in p else "USER: [an image]")
    return "\n".join(lines)


def _maybe_compact(messages):
    """When the replayed history passes COMPACT_CHARS, spend ONE LLM call folding everything
    between the opening task message and the last COMPACT_KEEP_MSGS messages into a written
    briefing that replaces those turns in place.

    Invariants: the OPENING message (the task text + the drawings) always survives verbatim —
    compacting the requirement away would be fatal; the cut lands just BEFORE an assistant
    message, so no tool result is ever orphaned from the call that produced it (providers
    reject that); a failed summary call changes nothing (the history is kept over the risk of
    losing it). Returns True when a compaction happened."""
    if COMPACT_CHARS <= 0 or len(messages) <= COMPACT_KEEP_MSGS + 1:
        return False
    if _history_chars(messages) < COMPACT_CHARS:
        return False
    cut = next((i for i in range(max(1, len(messages) - COMPACT_KEEP_MSGS), len(messages))
                if messages[i].get("role") == "assistant"), None)
    if cut is None or cut <= 1:
        return False
    middle = messages[1:cut]
    try:
        summary = complete("THE LOG TO COMPRESS:\n\n" + _render_for_summary(middle),
                           system=_COMPACT_SYSTEM, role="compact")
    except Exception as e:
        print(f"{_C['tools']}[compact]{_RESET} summary call failed ({e}) - history kept")
        return False
    if not summary or not summary.strip():
        return False
    note = ("[EARLIER HISTORY COMPACTED to keep this conversation small. The briefing below "
            "replaces those turns. The live model is still the ground truth - observe again "
            "when in doubt.]\n\n" + summary.strip())
    messages[1:cut] = [{"role": "user", "content": [{"text": note}]}]
    trace_event("compact", dropped_msgs=len(middle), summary_chars=len(summary))
    print(f"{_C['tools']}[compact]{_RESET} folded {len(middle)} message(s) into a "
          f"{len(summary)}-char briefing")
    return True


def _result_text(rec, cap=RESULT_CHARS):
    """One tool result as the string the model reads. A failure leads with its error (that is
    the actionable part); a success carries its payload, capped at `cap` (RESULT_CHARS for
    ordinary tools, LOOKUP_RESULT_CHARS for the External Support group — see the constants)."""
    if not rec.get("ok"):
        return json.dumps({"ok": False, "error": str(rec.get("error"))[:1500]},
                          ensure_ascii=False)
    blob = json.dumps({"ok": True, "result": rec.get("result")}, ensure_ascii=False,
                      default=str)
    if len(blob) <= cap:
        return blob
    return (blob[:cap]
            + f"\n... TRUNCATED at {cap} of {len(blob)} characters. Ask a narrower "
              f"question (e.g. one element kind, one storey) to see the rest.")


def _retrieved_docs(res):
    """The document names a LOOKUP result carries — console log only, so a log reader sees
    WHICH file/page a retrieval served without scrolling the payload. Skill bundles name
    their files in '# SKILL:' headers; help/api-doc results carry page
    titles (the corpora's page identity — what a re-query takes verbatim)."""
    texts, names = [], []
    if isinstance(res, dict):
        if isinstance(res.get("recipe"), str):
            texts.append(res["recipe"])
        if isinstance(res.get("recipes"), dict):
            texts += [t for t in res["recipes"].values() if isinstance(t, str)]
        names += [a["title"] for k in ("articles", "pages")
                  for a in (res.get(k) or []) if isinstance(a, dict) and a.get("title")]
    elif isinstance(res, str):
        texts.append(res)
    for t in texts:
        names += re.findall(r"^# SKILL: (\S+\.md)", t, re.M)
    return names


def _fmt_call(c):
    """One-line render of a tool call for the console."""
    args = c.get("args") or {}
    parts = []
    for k, v in args.items():
        s = json.dumps(v, ensure_ascii=False, default=str)
        if isinstance(v, list) and len(v) > 4:
            s = f"[{len(v)} items]"
        parts.append(f"{k}={s if len(s) <= 60 else s[:57] + '...'}")
    return f"{c['name']}(" + ", ".join(parts) + ")"


# ---------------------------------------------------------------- the loop

def run(pdf=None, instruction=None):
    """Drive the task to completion. `pdf` is a drawing path, a LIST of paths for a multi-view
    case, or None for a text-only run; `instruction` is the whole task."""
    cfg = provider_config()
    cfg_provider = cfg["provider"]
    targets, families = bim_targets(), tool_families()
    t0 = time.time()
    global KEEP_IMAGES
    if not os.getenv("AGENT_KEEP_IMAGES"):
        # The open computer-use agents' released visual-history settings: EvoCUA pairs each
        # of its last EVOCUA_HISTORY responses with the frame it answered, plus the current
        # frame (4 + 1 = five screenshots); OpenCUA keeps OPENCUA_MAX_IMAGE_HISTORY (3).
        if cfg["provider"] == "evocua":
            from .providers import evocua
            KEEP_IMAGES = evocua.HISTORY + 1
        elif cfg["provider"] == "opencua":
            from .providers import opencua
            KEEP_IMAGES = opencua.MAX_IMAGE_HISTORY
    # Console output stays ASCII: `python -m authoring_framework` reconfigures stdout to UTF-8,
    # but a caller that imports run() directly does not, and a log line must never be the thing
    # that kills a run on a cp1252 console.
    print(f"[target] applications: {', '.join(targets)} - which one is live is the agent's to work out")
    print(f"[tools]  {tool_mode()} -> {', '.join(families)}")
    print(f"[llm]    {cfg['provider']}:{model_for(ROLE)}")

    if not instruction:
        raise SystemExit("nothing to do: pass an --instruction")
    paths = [Path(p) for p in (pdf if isinstance(pdf, (list, tuple)) else [pdf] if pdf else [])]
    for p in paths:
        if not p.exists():
            raise SystemExit(f"input drawing not found: {p}")
    drawings = [to_png_bytes(p) for p in paths]
    print(f"[input]  drawing     = {[str(p) for p in paths] if paths else '(none - text-only)'}")
    print(f"[input]  instruction = {instruction!r}")

    run_dir = new_run()
    print(f"[run]    {run_dir}")
    mem = session()
    mem.update({"pdf": [str(p) for p in paths] or None, "instruction": instruction,
                "tools": tool_mode(), "agent": "react"})

    ctx = toolkit.ToolContext(
        toolkit.build_registry(families, targets=targets, gui_learning=gui_learning()),
        mem=mem, targets=targets)
    # The per-MODEL screen/coordinate profile (frame, wording, screenshot caps) — resolved
    # once, printed, and written into the run record: a result must be traceable to the exact
    # frame and image size it was produced under.
    from .tools.gui import profile as gui_profile
    prof = gui_profile.resolve(cfg["provider"], model_for(ROLE))
    print(f"[gui]    {gui_profile.describe(prof)}")
    for w in gui_profile.warnings(prof):
        print(f"{_C['warn']}[gui]    WARNING: {w}{_RESET}")
    mem["gui_profile"] = prof
    specs = ctx.registry.tool_specs()
    batching = ("\n\nTOOL CALLS: a turn may carry MANY tool calls; they run in the given "
                "order and each returns its own result. DEFAULT TO BATCHING: decide the whole "
                "next sequence, then issue it as ONE turn. A turn carrying a single mechanical "
                "call is a WASTED turn — your turn budget is the run's only limit. Split into "
                "separate turns ONLY where you must read a result or a fresh screenshot before "
                "you can choose the next call's values.")
    handed = specs
    system = [SYSTEM, ctx.registry.briefing() + batching]
    print(f"[tools]  {len(specs)} tool(s)")

    opening = "The TASK:\n" + instruction
    if len(drawings) == 1:
        opening += "\n\nThe drawing is the attached image — it is the requirement, read it."
    elif drawings:
        opening += (f"\n\nThe {len(drawings)} drawings are the attached images, in order: "
                    f"SEVERAL VIEWS of ONE requirement. Read them together.")
    else:
        opening += "\n\nNo drawing was provided: the task text above is the whole requirement."
    messages = [{"role": "user",
                 "content": [{"text": opening}] + [{"png": d} for d in drawings]}]

    turns = spent = 0
    tally = {"by_tool": {}, "by_family": {}, "failed": 0, "writes": 0}
    reasoning_log = []      # the agent's written per-turn rationale — part of the run record
    try:
        # MAX_TURNS <= 0 = NO turn cap at all — only sane under a harness with its own
        # timeout (there is no other run limiter).
        turn_cap = str(MAX_TURNS) if MAX_TURNS > 0 else "∞"
        nudges = 0
        for turn in (range(1, MAX_TURNS + 1) if MAX_TURNS > 0 else itertools.count(1)):
            turns = turn
            ctx.current_turn = turn
            _capture_screen(ctx)
            _prune_images(messages)
            _maybe_compact(messages)
            print(f"\n{_BOLD}=== turn {turn}/{turn_cap} ==={_RESET}  "
                  f"({spent} tool calls used)")
            try:
                reply = chat(messages + _screen_tail(ctx), system=system, tools=handed,
                             role=ROLE) or {}
            except Exception as e:
                # llm.py already retried transient 5xx/timeouts with backoff; an exception
                # reaching here means the provider STAYED down. That is an outage, not a
                # model result — mark it, record honest stats, and exit with the dedicated
                # code so a harness discards this half-run rather than grading it.
                if "repetitive tool calls" in str(e).lower():
                    # DashScope refuses the CONVERSATION once the same tool call repeats
                    # too often ("<400> InternalError.Algo.InvalidParameter: Repetitive
                    # tool calls detected", 2026-09-12, qwen3.7-plus clicking one point 30
                    # times). The provider is up; it is the agent's own loop that ended the
                    # run — a model result, so the run is SAVED and GRADED like a turn-cap
                    # abort, not discarded as an outage.
                    print(f"\n{_BOLD}[stop] the provider refused to continue a repetitive "
                          f"conversation — graded as the agent's own dead loop: "
                          f"{str(e)[:200]}{_RESET}")
                    mem["aborted"] = "provider_refused_repetition"
                    trace_event("provider_refusal", turn=turn, error=str(e)[:500])
                    _settle(ctx)
                    break
                if llm_is_config_error(e):
                    # The provider ANSWERED — with a rejected key, a forbidden or unknown
                    # model. Nothing to retry and nothing to grade: a configuration error,
                    # reported plainly and exited with a plain code (1, not the outage code)
                    # so a harness stops its batch instead of waiting for a recovery.
                    _settle(ctx)
                    _record_stats(mem, t0, turns, spent, tally)
                    raise SystemExit(
                        f"[stop] configuration error — the provider rejected the request: "
                        f"{type(e).__name__}: {str(e)[:300]}\n"
                        f"       check the API key / model in .env or -p/-m (provider "
                        f"{cfg_provider!r}, model {model_for(ROLE)!r})")
                mem["aborted"] = "llm_failure"
                print(f"\n{_BOLD}[stop] LLM provider failed after retries: "
                      f"{type(e).__name__}: {str(e)[:300]}{_RESET}")
                trace_event("llm_failure", turn=turn,
                            error=f"{type(e).__name__}: {str(e)[:500]}")
                _settle(ctx)
                _record_stats(mem, t0, turns, spent, tally)
                raise SystemExit(EXIT_LLM_FAILURE)
            text, calls = reply.get("text"), reply.get("calls") or []
            # TRUNCATION: a reply cut off at MAX_OUTPUT_TOKENS comes back with the provider's
            # length stop reason. It is not an error — the turn still carries whatever the
            # model managed to emit — but a run full of them means the cap is too tight for
            # the task, so count them and make each one visible in the trace.
            if str(reply.get("stop") or "").lower() in ("max_tokens", "length"):
                tally["truncated"] = tally.get("truncated", 0) + 1
                print(f"{_C['warn']}[warn]{_RESET} reply TRUNCATED at the output-token cap "
                      f"(turn {turn}; {tally['truncated']} so far this run)")
            if text:
                print(f"{_C['agent']}[agent]{_RESET} {text.strip()}")
            trace_event("turn", turn=turn, text=text, stop=reply.get("stop"),
                        usage=reply.get("usage"),
                        calls=[{"name": c["name"], "args": c.get("args")} for c in calls])
            if calls and text:
                # The prompt requires a written rationale before every tool batch; keep it in
                # the run record.
                reasoning_log.append({"turn": turn, "text": text.strip()})
                mem["reasoning"] = reasoning_log

            if not calls and reply.get("continue"):
                # A provider adapter's call-less step that is NOT a finish (a computer-use
                # model's `wait`, a reply it could not parse): keep it and go again — the
                # next turn shows the fresh screen.
                messages.append({"role": "assistant", "text": text, "calls": [],
                                 "raw": reply.get("raw")})
                continue
            if not calls and nudges < NUDGE_MAX and not re.search(r"^\s*RESULT:", text or "", re.I | re.M):
                # Not a finish (see NUDGE_MAX): keep the reply in the history, tell the agent,
                # and go again. Costs one turn; a dropped call otherwise costs the run.
                nudges += 1
                tally["nudged_finishes"] = nudges
                messages.append({"role": "assistant", "text": text, "calls": [],
                                 "raw": reply.get("raw")})
                note = ("[transport] Your previous reply reached this conversation with NO tool "
                        "call and no RESULT: line, so nothing was executed. If the work is not "
                        "finished, continue by calling tools now; if it is finished, reply with "
                        "the RESULT: line as instructed.")
                messages.append({"role": "user", "content": [{"text": note}]})
                print(f"\n{_C['warn']}[nudge] turn {turn}: call-less reply without a RESULT: "
                      f"line — asking the agent to continue ({nudges}/{NUDGE_MAX}){_RESET}")
                trace_event("nudged_finish", turn=turn, text=(text or "")[:300])
                continue
            if not calls:
                mem["answer"] = text
                # The prompt's WHEN TO GIVE UP protocol: a final reply opening with
                # "RESULT: abandoned" is the agent's own verdict that the requirement
                # cannot be completed. Recorded so the harness can tell a deliberate stop
                # from a finished build (both are saved and graded the same way).
                m = re.search(r"^\s*RESULT:\s*abandoned\b\s*[—–:-]?\s*(.*)", text or "", re.I | re.M)
                if m:
                    mem["gave_up"] = (m.group(1).strip().splitlines() or [""])[0][:300]
                    print(f"\n{_BOLD}[done] the agent GAVE UP after {turn} turn(s): "
                          f"{mem['gave_up']}{_RESET}")
                else:
                    print(f"\n{_BOLD}[done] the agent finished after {turn} turn(s){_RESET}")
                break

            messages.append({"role": "assistant", "text": text, "calls": calls,
                             "raw": reply.get("raw")})
            results, spent = _execute(ctx, calls, spent, tally)
            messages.append({"role": "tool", "results": results})
            _attach_images(ctx, messages)
        else:
            print(f"\n{_BOLD}[stop] reached the turn limit{_RESET}")
            mem["aborted"] = "turn_budget_exceeded"
            # The run may have stopped MID-GESTURE (a dialog open, a tool armed) — settle the
            # UI before the harness drives its keyboard Save-As into whatever is focused.
            _settle(ctx)
    except Exception:
        _settle(ctx)                       # leave the application usable, then let it surface
        _record_stats(mem, t0, turns, spent, tally)
        raise
    finally:
        ctx.close()

    _record_stats(mem, t0, turns, spent, tally)


def _execute(ctx, calls, spent, tally):
    """Run one turn's tool calls and return (results, spent).

    EVERY call the model made gets a result, whatever happened to it — a provider rejects the
    next turn outright if a tool call goes unanswered, and "your call was dropped because X" is
    better feedback than silence anyway. Two things can intervene between the model's call
    and the application: malformed arguments and the validation gate.
    """
    out, runnable = [], []
    truncate_rest = False
    for c in calls:
        if truncate_rest:
            out.append({"id": c["id"], "name": c["name"], "error": True,
                        "content": "NOT RUN: the batch was truncated at an earlier malformed "
                                   "call — GUI ops carry positional dependencies, so running "
                                   "the remainder would act at a stale cursor position."})
            continue
        if c.get("bad_args"):
            out.append({"id": c["id"], "name": c["name"], "error": True,
                        "content": f"REJECTED: {c['bad_args']}"})
            # same positional-dependency rule plan_batch applies to unusable calls: on a run
            # that HAS GUI tools, a malformed call mid-sequence must take the tail with it
            # (filtering it out silently would let a later click land at the wrong spot).
            if ctx.registry.has_family("gui"):
                truncate_rest = True
            continue
        runnable.append({"tool": c["name"], "args": c.get("args") or {}, "id": c["id"]})

    batch, dropped = toolkit.plan_batch(runnable, ctx)
    dropped_why = {c.get("id"): why for c, why in dropped if isinstance(c, dict)}
    if dropped:
        print(f"{_C['tools']}[tools]{_RESET} dropped {len(dropped)} unusable call(s)")
    if batch:
        print(f"{_C['tools']}[tools]{_RESET} " + ", ".join(
            _fmt_call({"name": c["tool"], "args": c.get("args")}) for c in batch))
    records = toolkit.run_batch(batch, ctx) if batch else []
    spent += len(records)
    for r in records:
        tally["by_tool"][r["tool"]] = tally["by_tool"].get(r["tool"], 0) + 1
        tally["by_family"][r["family"]] = tally["by_family"].get(r["family"], 0) + 1
        tally["failed"] += 0 if r.get("ok") else 1
        tally["writes"] = tally.get("writes", 0) + (1 if r.get("writes") else 0)
    by_id = {r["id"]: r for r in records if r.get("id")}

    for c in runnable:
        cid = c["id"]
        rec = by_id.get(cid)
        if rec is not None:
            ok = rec.get("ok")
            print(f"{_C['result']}    {'ok  ' if ok else 'FAIL'} {rec['tool']}"
                  f"{'' if ok else ' - ' + str(rec.get('error'))[:160]}{_RESET}")
            # Lookup results carry a retrieved DOCUMENT as their payload — exempt from the
            # generic cap (see LOOKUP_RESULT_CHARS: a capped recipe is a recipe the agent
            # never read).
            tool = ctx.registry.get(rec["tool"])
            cap = (LOOKUP_RESULT_CHARS
                   if tool and str(tool.group or "").startswith("External Support")
                   else RESULT_CHARS)
            if ok and cap == LOOKUP_RESULT_CHARS:
                docs = _retrieved_docs(rec.get("result"))
                if docs:
                    print(f"{_C['result']}         retrieved: "
                          f"{', '.join(docs[:8])}{_RESET}")
            out.append({"id": cid, "name": c["tool"], "error": not ok,
                        "content": _result_text(rec, cap)})
        elif cid in dropped_why:
            out.append({"id": cid, "name": c["tool"], "error": True,
                        "content": f"REJECTED before execution: {dropped_why[cid]}"})
        elif not any(o["id"] == cid for o in out):
            # Folded into another call by a deterministic backstop (the storey stack is the
            # only one that does this today). Say so, or the model reads the silence as a
            # failure and re-issues it.
            out.append({"id": cid, "name": c["tool"], "error": False,
                        "content": "This call was merged into another call of the same turn by "
                                   "the harness (a whole-stack write takes one call); its "
                                   "effect is included in that call's result."})
    order = {c["id"]: i for i, c in enumerate(calls)}
    out.sort(key=lambda r: order.get(r["id"], 0))
    trace_event("tools", results=[{"tool": r["name"], "ok": not r["error"]} for r in out])
    return out, spent


_PNG_SIG = b"\x89PNG\r\n\x1a\n"
LOOKUP_IMG_EDGE = 2000     # the API's per-image limit once a request carries many images


def _as_png(data):
    """Lookup page images come straight from the help corpora as whatever the page shipped
    (GIF included) and are declared image/png on the wire; the direct API checks the real
    format and rejects the request (400 "appears to be a image/gif"). Re-encode anything that is not a PNG, and cap the long edge."""
    try:
        if data[:8] == _PNG_SIG:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as im:
                if max(im.size) <= LOOKUP_IMG_EDGE:
                    return data
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            if max(im.size) > LOOKUP_IMG_EDGE:
                k = LOOKUP_IMG_EDGE / max(im.size)
                im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))))
            buf = io.BytesIO(); im.save(buf, "PNG")
            return buf.getvalue()
    except Exception:
        return data          # unreadable bytes go through as they are; the API will say why


def _capture_screen(ctx):
    """Capture the screen for this turn (UI-driving runs only) into ctx.recent_screens, which
    `_screen_tail` serves. NOTHING else shows the agent the screen — there is no tool for it.
    Runs after a short settle pause so the last action of the previous batch has painted. A
    failed capture is reported to the agent in the tail rather than killing the run."""
    if not ctx.has("gui"):
        return
    shots = getattr(ctx, "recent_screens", None)
    if shots is None:
        shots = ctx.recent_screens = []
    turn = getattr(ctx, "current_turn", 0)
    try:
        if turn > 1:
            time.sleep(toolkit.GUI_OP_DELAY_S)
        png = ctx.controller.screenshot()
        path = screenshot_path()
        path.write_bytes(png)
        ctx.screen_error = None
    except Exception as e:                       # noqa: BLE001 — reported, never fatal
        ctx.screen_error = f"{type(e).__name__}: {e}"
        print(f"{_C['warn']}[screen] capture failed: {ctx.screen_error}{_RESET}")
        return
    shots.append((png, turn))
    del shots[:-max(1, KEEP_IMAGES)]


def _screen_tail(ctx):
    """The ephemeral screenshot message: the KEEP_IMAGES newest per-turn captures, oldest
    first, as one user message that is appended to the request and never kept."""
    shots = getattr(ctx, "recent_screens", None)
    if not ctx.has("gui"):
        return []
    err = getattr(ctx, "screen_error", None)
    if not shots:
        return [{"role": "user", "ephemeral": True, "content": [
            {"text": f"[the screen could not be captured this turn: {err}]"}]}] if err else []
    content = [{"text": "THE SCREEN. It is captured for you automatically at the start of every "
                        "turn — there is nothing to call. The LAST image below is the screen "
                        "as it is RIGHT NOW; any image before it is the screen as it was at "
                        "the start of an earlier turn, for comparison. What a batch of calls "
                        "changed becomes visible at the start of your NEXT turn, never inside "
                        "the batch."
                        + (f" (This turn's capture FAILED — {err}; the newest image is older.)"
                           if err else "")}]
    for i, (png, at) in enumerate(shots):
        label = "the screen NOW" if i == len(shots) - 1 and not err else "earlier"
        content.append({"text": f"[{label} — captured at the start of turn {at}]"})
        content.append({"png": png})
    return [{"role": "user", "content": content, "ephemeral": True}]


def _attach_images(ctx, messages):
    """Pick up the page images the turn's lookups parked and add them as a real user message
    after the results. (Screen captures never come through here — see `_capture_screen`.)"""
    content = []
    for imgs, note in ctx.take_images():
        content.append({"text": f"Reference pages from your lookup ({note}) — read the "
                                f"diagrams, that is where the values are:"})
        # "kind" marks these as lookup pages for _prune_images — every provider adapter
        # renders parts by "text"/"png" alone, so the tag never reaches the wire.
        content += [{"png": _as_png(i), "kind": "lookup"} for i in imgs]
    if content:
        messages.append({"role": "user", "content": content})


def _settle(ctx):
    """On an abnormal stop, leave the application usable (GUI runs only): release a held
    Shift, close any half-open dialog. NEVER RAISES — it runs on failure paths where a
    secondary error would replace the real one (or skip the stats/exit-code contract the
    bench runner keys on). Skipped when the controller was never created: a run that never
    touched the UI has nothing to settle, and instantiating pyautogui here could itself
    fail."""
    try:
        if not ctx.has("gui") or ctx._controller is None:
            return
        cc = ctx.controller
        cc._release_shift()
        for press in (cc.press_enter, cc.press_esc):
            for _ in range(3):
                press()
                time.sleep(0.5)
    except Exception as e:
        print(f"[settle] skipped ({type(e).__name__}: {e})")


def _record_stats(mem, t0, turns, spent, tally):
    """Tally the run into mem["stats"] — the record the bench harness reads."""
    usage = usage_snapshot()
    stats = {"agent": "react", "tools": tool_mode(),
             "turns": turns, "tool_calls": spent,
             # write_calls = calls to tools with writes=True — the HANDS-ON count (clicks/
             # typing), as opposed to
             # observations and reference lookups, which spend budget but touch nothing.
             "write_calls": tally.get("writes", 0),
             "calls_by_family": tally["by_family"], "calls_failed": tally["failed"],
             "tool_breakdown": tally["by_tool"],
             "duration_s": round(time.time() - t0, 1),
             "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
             "ended_at": time.strftime("%Y-%m-%d %H:%M:%S"), "llm": usage}
    try:
        # what the model actually SAW: the sent-screenshot size and the sent-px-per-point scale
        from .tools.gui import controller as _ctl
        prof = mem.get("gui_profile") or {}
        stats["gui"] = {"frame": prof.get("frame"), "wording": prof.get("wording"),
                        "img_edge": prof.get("img_edge"), "img_pixels": prof.get("img_pixels"),
                        "sent_size": list(_ctl._SENT_SIZE) if _ctl._SENT_SIZE else None,
                        "scale": _ctl._SCALE}
    except Exception:
        pass
    if tally.get("truncated"):
        # Turns whose reply hit the output-token cap. A non-zero count is a warning about
        # MAX_OUTPUT_TOKENS, not about the model: the turn kept whatever was emitted.
        stats["truncated_turns"] = tally["truncated"]
    if mem.get("aborted"):
        stats["aborted"] = mem["aborted"]
    if mem.get("gave_up") is not None:
        stats["gave_up"] = mem["gave_up"] or True   # the agent's own "cannot complete" verdict
    mem["stats"] = stats
    tot = usage["total"]
    print(f"\n[stats] {turns} turn(s), {spent} tool call(s) ({tally['failed']} failed), "
          f"{stats['duration_s']}s | llm: {tot['calls']} call(s), {tot['input_tokens']} in / "
          f"{tot['output_tokens']} out tok ({tot['cache_read_tokens']} cached)")
    return stats
