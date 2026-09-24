"""Regenerate results/<run>/EVAL_RESULTS.md from the per-case score_<phase>.json files.

Reads every `<results>/<CASE_ID>/<tool>/score_<phase>.json`, plus (optional) a BASELINE
results tree to show a per-case Δscore, and writes the summary document: the per-case table,
overall totals, and the by-category breakdown.

Cases with no score file are listed with the `--missing-note` status and counted as FAIL —
the denominator never silently shrinks.

Usage (repo root):
    python bench_runner/reports/gen_eval_results.py bench_runner/results/archicad_bycase_api \
        --baseline bench_runner/results/archicad_bycase_api_baseline_e5b0410 \
        --header-file header.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # bench_runner/ (for case_io)
import case_io                                   # noqa: E402  (path set just above)

ROOT = Path(__file__).resolve().parents[2]
BENCH_CASES = ROOT / "bench_cases" / "reasoning_tasks"


def _natkey(s: str):
    return [int(t) if t.isdigit() else t for t in re.findall(r"\d+|\D+", s)]


# The phases were RENAMED on 2026-08-11 (api->api-priors, code->api-raw, gui->gui-raw,
# hybrid->hybrid-priors) and the result trees were renamed with them — but the score files
# inside a batch that RAN under an old name keep that name (`score_code.json` in a tree now
# called `..._api_raw`). Looking only for `score_<phase>.json` made those trees regenerate as
# "0 graded + N counted-as-fail", i.e. a blank scoreboard over a complete batch. So a phase
# also accepts the legacy spellings it was renamed FROM.
_PHASE_FILE_ALIASES = {
    "api-priors": ("api", "api-tools"),
    "api-raw": ("code",),
    "gui-raw": ("gui",),
    "gui-support": ("gui-priors", "gui-skills"),
    "hybrid-priors": ("hybrid", "hybrid-tools"),
    "hybrid-raw": (),
}


def _score(results: Path, case_id: str, tool: str, phase: str) -> dict | None:
    d = results / case_id / tool
    for name in (phase, *_PHASE_FILE_ALIASES.get(phase, ())):
        p = d / f"score_{name}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


# On the GUI arms "support use" is the share of DOC LOOKUPS that went to the operational
# support: numerator = `open_software_skill` calls (the hand-written procedures, gui-support only),
# denominator = those PLUS `search_app_help` calls (the official application help, every GUI
# arm) — i.e. of everything the run looked up, how much came from the authors' recipes
# rather than the vendor's docs. The score file's run block carries only the pre-aggregated
# `prior_actions`, so the per-tool counts come from the collected run's memory.json; a case
# collected without one falls back to prior_actions over total ops (the old reading).
def _lookup_pair(results: Path, case_id: str, tool: str,
                 phase: str) -> tuple[int, int] | None:
    d = results / case_id / tool
    for name in (phase, *_PHASE_FILE_ALIASES.get(phase, ())):
        mj = d / name / "agent_run" / "memory.json"
        if mj.is_file():
            try:
                st = json.loads(mj.read_text(encoding="utf-8")).get("stats") or {}
            except Exception:
                return None
            tb = st.get("tool_breakdown") or {}
            # the two lookups were renamed 2026-09-21; older runs carry the old names
            skill = int(tb.get("operational_skill_retrieval") or tb.get("open_software_skill") or 0)
            help_ = int(tb.get("documentation_retrieval") or tb.get("search_app_help") or 0)
            return skill, skill + help_
    return None


def _fails(sc: dict) -> list[str]:
    return [c["id"] for c in (sc.get("checkpoints") or [])
            if c.get("score") is not None and c["score"] < 1.0]


def _row(case_id: str, sc: dict | None, base: dict | None, missing_note: str,
         is_rerun: bool) -> str:
    if sc is None:
        return (f"| {case_id} | {missing_note} "
                f"| | | | | | | | | | | | | | |")
    run = sc.get("run") or {}
    rw = (f"{sc['reward']} ({sc['units_passed']}/{sc['units_total']})"
          if sc.get("reward") is not None else f"None ({sc.get('units_passed', 0)}/"
                                               f"{sc.get('units_total', 0)})")
    cp = f"{sc.get('checkpoints_passed')}/{sc.get('checkpoints_total')}"
    secs = run.get("agent_seconds") or 0
    tin, tout = run.get("tokens_in") or 0, run.get("tokens_out") or 0
    # Δ only means something for a case that was actually RE-RUN; a row carried over from the
    # baseline gets a blank (it is the same measurement, not a measured zero change).
    delta = ""
    if is_rerun and base is not None and base.get("score") is not None \
            and sc.get("score") is not None:
        d = round(sc["score"] - base["score"], 4)
        delta = "0" if abs(d) < 1e-9 else f"{d:+.4f}".rstrip("0").rstrip(".")
    fails = _fails(sc)
    ops = run.get("actions")
    ops_cell = "" if ops is None else (f"{ops} ({run['exec_failures']} failed)"
                                       if run.get("exec_failures") else str(ops))
    # hands-on = calls to writes=True tools only (clicks/typing on the GUI route, authoring
    # calls on the API route) — observations and reference lookups spend ops but touch nothing.
    hands = run.get("write_actions")
    # support use = the share of ops that went through the OPERATIONAL SUPPORT (legacy: packaged API
    # tools + open_software_skill); the rest is the raw/neutral channel (run_code,
    # search_api_doc, GUI ops, search_app_help, observations). Older run blocks lack
    # prior_actions — fall back to by_family["api"], which is exact for the api arms
    # (open_software_skill is a gui-family tool, absent there) and a lower bound elsewhere.
    support_cell = ""
    pair = run.get("lookup_pair")
    if pair is not None:                 # GUI arms: skill lookups / all doc lookups
        pn, pd = pair
        support_cell = f"{pn}/{pd} ({round(100 * pn / pd)}%)" if pd else "0/0"
    else:
        prior = run.get("support_actions", run.get("prior_actions"))   # older scores: prior_actions
        if prior is None and isinstance(run.get("by_family"), dict):
            prior = run["by_family"].get("api")
        if prior is not None and ops:
            support_cell = f"{prior}/{ops} ({round(100 * prior / ops)}%)"
    # PCS over the goal class, CFR over the preservation class; SR is the PASS cell.
    pcs = ("" if sc.get("pcs") is None
           else f"{sc['pcs']} ({sc.get('pcs_passed', 0)}/{sc.get('pcs_total', 0)})")
    cfr = ("" if sc.get("cfr") is None
           else f"{'yes' if sc['cfr'] >= 1.0 else 'NO'} "
                f"({sc.get('cfr_passed', 0)}/{sc.get('cfr_total', 0)})")
    return (f"| {case_id} | {sc.get('status')} | {rw} | {cp} | "
            f"{pcs} | {cfr} | "
            f"{sc.get('score')} | {delta} | {'PASS' if sc.get('passed') else 'fail'} | "
            f"{(secs / 60):.1f}m | {round(tin / 1000)}k/{round(tout / 1000)}k | "
            f"{run.get('turns', run.get('loops', run.get('rounds', '')))} | {ops_cell} | "
            f"{'' if hands is None else hands} | {support_cell} | "
            f"{', '.join(fails[:4])}{' …' if len(fails) > 4 else ''} |")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("results", type=Path)
    p.add_argument("--baseline", type=Path, default=None,
                   help="earlier results tree, for the Δscore column")
    p.add_argument("--tool", default="archicad")
    p.add_argument("--bench-root", type=Path, default=None,
                   help="dataset tree the case ids/complexities come from (default "
                        "bench_cases/reasoning_tasks); pass bench_cases/atomic_tasks for the atomic "
                        "tree or bench_cases/long-seq_tasks")
    p.add_argument("--phase", default="gui-support")
    p.add_argument("--header-file", type=Path, default=None,
                   help="markdown file whose content replaces the generated header block")
    p.add_argument("--missing-note", default="not run (counted as FAIL)")
    a = p.parse_args(argv)
    if a.bench_root:
        global BENCH_CASES
        BENCH_CASES = a.bench_root.resolve()

    # UNION of result dirs and ALL bench cases that exist for this tool: a case that was
    # never run (e.g. the end-to-end set) still gets a row with the missing-note — dropping
    # it would silently shrink the denominator.
    all_ids = set(case_io.case_ids(BENCH_CASES, a.tool))
    ids = {d.name for d in a.results.iterdir() if d.is_dir() and d.name in all_ids}
    ids |= all_ids
    case_ids = sorted(ids, key=_natkey)
    # GUI arms: support use = skill lookups over ALL doc lookups (see _lookup_pair); the pair
    # is stashed on the run block so the row, the totals line and the per-category table
    # all read the same numbers through the one _support_of path.
    lookup_mode = a.phase.startswith("gui")
    rows, graded, reruns = [], [], []
    for cid in case_ids:
        sc = _score(a.results, cid, a.tool, a.phase)
        if sc is not None and lookup_mode:
            pair = _lookup_pair(a.results, cid, a.tool, a.phase)
            if pair is not None:
                sc.setdefault("run", {})["lookup_pair"] = pair
        base = _score(a.baseline, cid, a.tool, a.phase) if a.baseline else None
        # a case counts as RE-RUN when its live grading timestamp moved vs the baseline tree
        is_rerun = bool(sc and base
                        and (sc.get("graded_at") or "") != (base.get("graded_at") or ""))
        rows.append(_row(cid, sc, base, a.missing_note, is_rerun))
        if sc is not None:
            graded.append(sc)
            if is_rerun:
                reruns.append((cid, base, sc))

    header = (a.header_file.read_text(encoding="utf-8").rstrip()
              if a.header_file else f"# Bench results ({a.tool} / {a.phase})")
    out = [header, "",
           "| case | status | reward (units) | checkpoints | PCS | CFR | score | Δ "
           "| passed | time | tokens in/out | turns | ops | hands-on | support use "
           "| failing checkpoints |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|", *rows, ""]

    npass = sum(1 for s in graded if s.get("passed"))
    n_missing = sum(1 for r in rows if a.missing_note in r)
    rewarded = [s for s in graded if s.get("reward") is not None]
    mean_rw_all = (sum(s["reward"] for s in rewarded) / (len(rewarded) + n_missing)
                   if (rewarded or n_missing) else 0.0)
    mean_sc = sum(s["score"] for s in graded) / len(graded) if graded else 0.0
    mins = sum((s.get("run") or {}).get("agent_seconds") or 0 for s in graded) / 3600
    tin = sum((s.get("run") or {}).get("tokens_in") or 0 for s in graded)
    tout = sum((s.get("run") or {}).get("tokens_out") or 0 for s in graded)

    def _support_of(run):
        """(numerator, denominator) for one run block: the GUI arms' lookup pair when it was
        stashed, else prior_actions over total ops with the by_family fallback _row uses."""
        pair = run.get("lookup_pair")
        if pair is not None:
            return pair
        p = run.get("support_actions", run.get("prior_actions"))
        if p is None and isinstance(run.get("by_family"), dict):
            p = run["by_family"].get("api")
        return p, run.get("actions")

    support_pairs = [(_p, _o) for _p, _o in
                   (_support_of(s.get("run") or {}) for s in graded)
                   if _p is not None and _o]
    support_txt = ""
    if support_pairs:
        tot_p, tot_o = sum(p for p, _ in support_pairs), sum(o for _, o in support_pairs)
        mean_ratio = sum(p / o for p, o in support_pairs) / len(support_pairs)
        denom_word = "doc lookups" if lookup_mode else "all ops"
        support_txt = (f"; support use {100 * tot_p / tot_o:.0f}% of {denom_word} "
                     f"(per-case mean {100 * mean_ratio:.0f}%, "
                     f"{len(support_pairs)}/{len(graded)} cases reporting)")
    # The two headline metrics. SR counts an ungraded case as a failure (it has the
    # full case set as its denominator); PCS and CFR are defined over graded runs only,
    # and PCS additionally skips a case whose key the start state already satisfies.
    pcs_vals = [s["pcs"] for s in graded if s.get("pcs") is not None]
    cfr_vals = [s["cfr"] for s in graded if s.get("cfr") is not None]
    metric_txt = ""
    if pcs_vals or cfr_vals:
        metric_txt = (f"SR {100 * npass / (len(graded) + n_missing):.1f}%"
                      + (f", PCS {100 * sum(pcs_vals) / len(pcs_vals):.1f}% "
                         f"({len(pcs_vals)} cases)" if pcs_vals else "")
                      + (f", CFR {100 * sum(cfr_vals) / len(cfr_vals):.1f}%"
                         if cfr_vals else "") + "; ")
    out += [f"**{len(graded)} graded + {n_missing} counted-as-fail — {metric_txt}"
            f"{npass}/{len(graded) + n_missing} passed, mean reward {mean_rw_all:.2f} "
            f"(fails included), mean checkpoint score {mean_sc:.2f} (graded only); "
            f"total agent time {mins:.1f} h, total tokens {tin / 1e6:.2f}M in / "
            f"{tout / 1e6:.2f}M out{support_txt}**", ""]

    if reruns:
        up = [(c, b, s) for c, b, s in reruns if s["score"] > b["score"] + 1e-9]
        down = [(c, b, s) for c, b, s in reruns if s["score"] < b["score"] - 1e-9]
        same = len(reruns) - len(up) - len(down)
        np_new = sum(1 for _, _, s in reruns if s.get("passed"))
        np_old = sum(1 for _, b, _ in reruns if b.get("passed"))
        out += ["## Re-run outcome (vs the baseline tree)", "",
                f"- {len(reruns)} case(s) re-run: **{len(up)} improved, {len(down)} regressed, "
                f"{same} unchanged**",
                f"- passes among them: **{np_old} → {np_new}**",
                f"- mean score among them: "
                f"**{sum(b['score'] for _, b, _ in reruns) / len(reruns):.4f} → "
                f"{sum(s['score'] for _, _, s in reruns) / len(reruns):.4f}**", ""]
        if up:
            out += ["improved: " + ", ".join(f"{c} ({b['score']}→{s['score']})"
                                             for c, b, s in up), ""]
        if down:
            out += ["regressed: " + ", ".join(f"{c} ({b['score']}→{s['score']})"
                                              for c, b, s in down), ""]

    by_cat = {}
    for s in graded:
        by_cat.setdefault(s["case"].split("_")[0], []).append(s)
    # the not-run rows still count as failures in the per-category tally
    missing_cats = {}
    for r, cid in zip(rows, case_ids):
        if a.missing_note in r:
            cat = cid.split("_")[0]
            missing_cats[cat] = missing_cats.get(cat, 0) + 1

    out += ["| category | passed | mean reward | mean time | support use |",
            "|---|---|---|---|---|"]
    for cat in sorted(set(by_cat) | set(missing_cats)):
        g = by_cat.get(cat, [])
        nmiss = missing_cats.get(cat, 0)
        rw = [s["reward"] for s in g if s.get("reward") is not None]
        mean = (sum(rw) / (len(rw) + nmiss)) if (rw or nmiss) else 0.0
        t = [((s.get("run") or {}).get("agent_seconds") or 0) / 60 for s in g]
        tcol = f"{(sum(t) / len(t)):.1f}m" if t else "-"
        pp = [(_p, _o) for _p, _o in (_support_of(s.get("run") or {}) for s in g)
              if _p is not None and _o]
        pcol = (f"{100 * sum(p for p, _ in pp) / sum(o for _, o in pp):.0f}%"
                if pp else "-")
        out.append(f"| {cat} | {sum(1 for s in g if s.get('passed'))}/{len(g) + nmiss} | "
                   f"{mean:.2f} | {tcol} | {pcol} |")
    out += [""]


    dest = a.results / "EVAL_RESULTS.md"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({len(graded)} graded, {len(reruns)} re-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
