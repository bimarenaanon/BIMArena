"""Render one case's score_<phase>.json as a per-case EVAL.md, next to the score file.

`rerun_cases._grade_saved` calls `write()` right after writing the score json, so every
freshly graded case gets a human-readable report the moment its grading lands. The CLI
covers the other two uses:

    python bench_runner/reports/case_eval_md.py <results_tree>                # one-shot: all cases
    python bench_runner/reports/case_eval_md.py <results_tree> --watch 20     # live: poll + regen

`--watch` polls the tree and (re)writes any EVAL.md older than its score json — the way to
get live per-case reports out of a batch that was ALREADY RUNNING when this module was
added (its rerun_cases process predates the hook and never calls it).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def _pct(x) -> str:
    return "-" if x is None else f"{x:g}"


def render(report: dict) -> str:
    """The markdown for one case's grading report (the score json, dict form)."""
    cid = report.get("case", "?")
    phase = report.get("phase", "api")
    verdict = "PASS" if report.get("passed") else "FAIL"
    head = [f"# {cid} — {phase} eval", ""]
    line = (f"**{verdict}** · score {_pct(report.get('score'))} · "
            f"reward {_pct(report.get('reward'))} "
            f"({report.get('units_passed', 0)}/{report.get('units_total', 0)} units) · "
            f"checkpoints {report.get('checkpoints_passed', 0)}"
            f"/{report.get('checkpoints_total', 0)}")
    if report.get("checkpoints_unchecked"):
        line += f" (+{report['checkpoints_unchecked']} unchecked)"
    head += [line, ""]
    # The two metrics, one per checkpoint class: PCS over C (what the task asks
    # to add or change), CFR over P (what had to survive). SR is their
    # conjunction, i.e. the PASS/FAIL above.
    if report.get("pcs_total") is not None or report.get("cfr_total") is not None:
        head += [f"PCS {_pct(report.get('pcs'))} "
                 f"({report.get('pcs_passed', 0)}/{report.get('pcs_total', 0)} goal) · "
                 f"CFR {_pct(report.get('cfr'))} "
                 f"({report.get('cfr_passed', 0)}/{report.get('cfr_total', 0)} preserved"
                 + (f", {report['trivial_total']} restated" if report.get("trivial_total")
                    else "") + ")", ""]
    meta = [f"status: {report.get('status')}", f"source: {report.get('source')}",
            f"graded: {report.get('graded_at')}"]
    if report.get("alternative") is not None:
        meta.append(f"alternative: {report['alternative']}")
    shift = report.get("alignment_shift_mm")
    if shift:
        meta.append(f"alignment shift: {shift} mm")
    head += [" · ".join(m for m in meta if not m.endswith("None")), ""]

    run = report.get("run") or {}
    if run:
        secs = run.get("agent_seconds") or 0
        tin, tout = run.get("tokens_in") or 0, run.get("tokens_out") or 0
        cached = run.get("tokens_cached") or 0
        hands = run.get("write_actions")
        head += ["## Run", "",
                 "| time | turns | tool calls | hands-on | failed | tokens in/out (cached) "
                 "| tools |",
                 "|---|---|---|---|---|---|---|",
                 f"| {secs / 60:.1f}m | {run.get('turns', '')} | {run.get('actions', '')} "
                 f"| {'' if hands is None else hands} | {run.get('exec_failures', '')} "
                 f"| {round(tin / 1000)}k/{round(tout / 1000)}k ({round(cached / 1000)}k) "
                 f"| {run.get('tools', '')} |", ""]
        if run.get("aborted"):
            head += [f"**aborted: {run['aborted']}**", ""]

    cps = report.get("checkpoints") or []
    if cps:
        fails = [c for c in cps if c.get("score") is not None and c["score"] < 1.0]
        if fails:
            head += ["## Failing checkpoints", "",
                     "| checkpoint | expected | built |", "|---|---|---|"]
            head += [f"| {c.get('id')} | {c.get('desc', '')} | {c.get('detail', '')} |"
                     for c in fails]
            head += [""]
        head += ["## All checkpoints", "",
                 "|  | class | checkpoint | expected | built |",
                 "|---|---|---|---|---|"]
        for c in cps:
            mark = ("·" if c.get("score") is None
                    else "pass" if c["score"] >= 1.0 else "**FAIL**")
            # P* = a goal checkpoint the start state already satisfied, graded
            # as a preservation duty rather than counted as progress
            kl = c.get("klass") or ""
            kl = "P*" if (kl == "P" and c.get("trivial")) else kl
            head.append(f"| {mark} | {kl} | {c.get('id')} | {c.get('desc', '')} "
                        f"| {c.get('detail', '')} |")
        head += [""]

    units = report.get("units") or []
    if units:
        head += ["## Reward units", "", "|  | unit | checkpoints |", "|---|---|---|"]
        head += [f"| {'pass' if u.get('passed') else '**FAIL**'} | {u.get('unit')} "
                 f"| {', '.join(u.get('checkpoints') or [])} |" for u in units]
        head += [""]
    return "\n".join(head)


def write(case_tool_dir: Path, phase: str = "api") -> Path | None:
    """Render `<case_tool_dir>/score_<phase>.json` into `<case_tool_dir>/EVAL.md`.
    Returns the written path, or None when there is no score file (a case that failed
    before grading has nothing to render). Never raises — a rendering problem must not
    break the grading loop that calls this."""
    case_tool_dir = Path(case_tool_dir)
    sp = case_tool_dir / f"score_{phase}.json"
    if not sp.is_file():
        return None
    try:
        report = json.loads(sp.read_text(encoding="utf-8"))
        dest = case_tool_dir / "EVAL.md"
        dest.write_text(render(report), encoding="utf-8")
        return dest
    except Exception as e:
        print(f"  [case-eval-md] {case_tool_dir.name}: {type(e).__name__}: {e}")
        return None


def sweep(results: Path, phase: str = "api", stale_only: bool = True) -> int:
    """(Re)write EVAL.md for every case in a results tree; with `stale_only`, only where
    the score json is newer than the existing EVAL.md. Returns how many were written."""
    n = 0
    for sp in Path(results).glob(f"*/*/score_{phase}.json"):
        dest = sp.parent / "EVAL.md"
        if (stale_only and dest.is_file()
                and dest.stat().st_mtime >= sp.stat().st_mtime):
            continue
        if write(sp.parent, phase):
            n += 1
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("results", type=Path, help="a results tree (results/<tool>_bycase_<phase>)")
    p.add_argument("--phase", default="gui-support")
    p.add_argument("--watch", type=float, default=None, metavar="SECONDS",
                   help="poll the tree at this interval and regenerate stale EVAL.md files "
                        "(run alongside a live batch); one-shot over the whole tree otherwise")
    p.add_argument("--for-hours", type=float, default=6.0,
                   help="stop a --watch after this many hours (default 6)")
    a = p.parse_args(argv)
    if a.watch is None:
        print(f"wrote {sweep(a.results, a.phase, stale_only=False)} EVAL.md file(s)")
        return 0
    deadline = time.time() + a.for_hours * 3600
    print(f"watching {a.results} every {a.watch:g}s (up to {a.for_hours:g}h)", flush=True)
    while time.time() < deadline:
        n = sweep(a.results, a.phase)
        if n:
            print(f"  [{time.strftime('%H:%M:%S')}] wrote {n} EVAL.md file(s)", flush=True)
        time.sleep(a.watch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
