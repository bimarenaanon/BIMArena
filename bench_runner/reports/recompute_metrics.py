"""Backfill PCS and CFR onto results graded before the C/P split existed.

Why this is a pure post-process. A grading report records every checkpoint with
its id and its pass/fail, and the class split is a function of the checkpoint id
plus the case's own start state -- neither depends on the agent. So the metrics
can be recomputed from the stored reports: no agent re-run, no project reopened,
no authoring application needed.

Per case the trivially-satisfied set T is obtained the way `rerun_cases` obtains
it live, by grading the case's baseline against itself. Checkpoints in T are
restated preservation duties, so they move from C into P; PCS is then scored over
C alone and CFR over the widened P.

    python bench_runner/reports/recompute_metrics.py <results-root> [--write]
    python bench_runner/reports/recompute_metrics.py results/gpt-5.6 --write

Without --write nothing is modified: the run prints the per-arm summary only.
With --write each score_<phase>.json gains the pcs/cfr fields (the file's other
fields, `score` included, are left exactly as they were, so older tooling keeps
working) and its EVAL.md is re-rendered.

A report that predates the split stores no `klass` on its checkpoints; one graded
after it does, and is left alone unless --force is given.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench_runner"))

import case_io                                                    # noqa: E402
from verifier.grade import grade, normalize_composites, trivial_from_report, _klass  # noqa: E402
from reports import case_eval_md                                  # noqa: E402
from verifier import trivial_probe                                # noqa: E402

BENCH_CASES = ROOT / "bench_cases"
TRACKS = ("atomic_tasks", "reasoning_tasks", "long-seq_tasks")
_TRIVIAL: dict[tuple, set] = {}

# "| pass | walls.0.geom | ..." and the post-split "| pass | C | walls.0.geom | ..."
_CP_ROW = re.compile(r"\|\s*(pass|\*\*FAIL\*\*|unchecked|·|—|-)?\s*\|"
                     r"(?:\s*(C|P\*?)\s*\|)?\s*([A-Za-z_][\w.\-]*)\s*\|")


def trivial_for(track: str, app: str, case_id: str) -> set:
    """T for one case, cached. An unreadable case yields the empty set, which
    leaves its PCS un-normalised rather than wrong."""
    key = (track, app, case_id)
    if key in _TRIVIAL:
        return _TRIVIAL[key]
    # the live probe, when the case has been through it: its snapshot carries
    # wall facing and opening swing, which the stored baseline does not
    live = trivial_probe.load_trivial(track, app, case_id)
    if live is not None:
        _TRIVIAL[key] = live
        return live
    ids: set = set()
    try:
        root = BENCH_CASES / track
        expected = case_io.read_spec(root, app, case_id).get("expected_result")
        bj = case_io.env_dir(root, app, case_id) / "start" / "baseline.json"
        base = json.loads(bj.read_text(encoding="utf-8")) if bj.exists() else {}
        snap = base.get("snapshot") or {}
        if expected:
            probe = grade(expected, snap, snap, normalize_composites([]),
                          anchor=(app == "revit"), answer="",
                          composites_final=base.get("composites"))
            ids = trivial_from_report(probe)
    except Exception as e:
        print(f"  [warn] no T for {track}/{app}/{case_id}: {e}")
    _TRIVIAL[key] = ids
    return ids


def checkpoints_of(case_dir: Path, app: str) -> tuple[list, Path | None]:
    """(checkpoints, score-json path). The score json is authoritative; where a
    batch kept only the rendered EVAL.md, its All-checkpoints table carries the
    same ids and verdicts and is parsed instead."""
    for p in sorted(case_dir.glob("score_*.json")):
        try:
            rep = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if rep.get("checkpoints"):
            return rep["checkpoints"], p
    ev = case_dir / "EVAL.md"
    if not ev.exists():
        return [], None
    txt = ev.read_text(encoding="utf-8", errors="replace")
    if "## All checkpoints" not in txt:
        return [], None
    cps = []
    for line in txt.split("## All checkpoints", 1)[1].split("\n## ", 1)[0].splitlines():
        m = _CP_ROW.match(line)
        if not m or m.group(3) == "checkpoint":
            continue
        mark = m.group(1) or ""
        score = (1.0 if mark.startswith("pass")
                 else 0.0 if "FAIL" in mark else None)
        cps.append({"id": m.group(3), "score": score})
    return cps, None


def metrics(checkpoints: list, trivial: set) -> dict:
    """The same arithmetic `grade` now does, over an already-scored report."""
    goal = keep = goal_ok = keep_ok = triv_n = 0
    for c in checkpoints:
        if c.get("score") is None:
            continue
        is_triv = c["id"] in trivial and _klass(c["id"]) == "C"
        triv_n += is_triv
        if is_triv or _klass(c["id"]) == "P":
            keep += 1
            keep_ok += c["score"] >= 1.0
        else:
            goal += 1
            goal_ok += c["score"] >= 1.0
    return {"pcs": round(goal_ok / goal, 4) if goal else None,
            "pcs_passed": goal_ok, "pcs_total": goal,
            "cfr": 1.0 if keep_ok == keep else 0.0,
            "cfr_passed": keep_ok, "cfr_total": keep,
            "trivial_total": triv_n}


def walk(results: Path):
    """Yield (track, arm, app, case_id, case_dir) for every graded run under a
    results root, whatever depth the arm sits at."""
    for ev in results.rglob("EVAL.md"):
        parts = ev.relative_to(results).parts
        if len(parts) < 4 or parts[-2] not in ("archicad", "revit"):
            continue
        # Archived and quarantined subtrees sit inside the model trees
        # (any `_`-prefixed dir, <app>_PRE-SAVEFIX_<date>, …). They
        # hold superseded runs of cases that were re-run, so counting them would
        # double a case and mix pre-fix numbers into a post-fix arm.
        if any(p.startswith("_") or "PRE-" in p or "discard" in p for p in parts):
            continue
        track = next((p for p in parts if p in TRACKS), None)
        if track is None:
            continue
        # .../<track>/<arm...>/<app>/<case>/<app>/EVAL.md — the app appears twice,
        # so the arm is everything between the track and the outer app dir
        i = parts.index(track)
        yield track, "/".join(parts[i + 1:-4]) or "-", parts[-2], parts[-3], ev.parent


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path, help="a results tree (or the results root)")
    ap.add_argument("--write", action="store_true",
                    help="patch the score json files and re-render their EVAL.md")
    ap.add_argument("--force", action="store_true",
                    help="recompute reports that already carry the split")
    ap.add_argument("--out", type=Path,
                    help="write every run's metrics as one CSV. Unlike --write this "
                         "covers the runs whose batch kept only an EVAL.md, so it is "
                         "the complete record to aggregate the paper's tables from.")
    a = ap.parse_args(argv)
    root = a.results if a.results.is_absolute() else ROOT / a.results
    if not root.exists():
        ap.error(f"no such results tree: {root}")

    agg = collections.defaultdict(list)
    n_seen = n_written = n_skipped = 0
    for track, arm, app, cid, cdir in walk(root):
        cps, sj = checkpoints_of(cdir, app)
        if not cps:
            n_skipped += 1
            continue
        # A report that already carries the split is re-written only under
        # --force, but it is always re-counted: the summary and --out must
        # cover every run, not just the ones this invocation happens to patch.
        already = sj is not None and any("klass" in c for c in cps)
        n_seen += 1
        m = metrics(cps, trivial_for(track, app, cid))
        scored = [c for c in cps if c.get("score") is not None]
        m["sr"] = bool(scored) and all(c["score"] >= 1.0 for c in scored)
        m.update({"model": root.name, "track": track, "arm": arm,
                  "app": app, "case": cid})
        agg[(root.name, track, arm, app)].append(m)
        if already and not a.force:
            n_skipped += 1
        elif a.write and sj is not None:
            rep = json.loads(sj.read_text(encoding="utf-8", errors="replace"))
            rep.update({k: v for k, v in m.items() if k != "sr"})
            triv = trivial_for(track, app, cid)
            for c in rep.get("checkpoints") or []:
                c["trivial"] = bool(c["id"] in triv and _klass(c["id"]) == "C")
                c["klass"] = "P" if (c["trivial"] or _klass(c["id"]) == "P") else "C"
            sj.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
            try:
                case_eval_md.write(cdir, rep.get("phase") or sj.stem[len("score_"):])
            except Exception as e:
                print(f"  [warn] EVAL.md not re-rendered for {cid}: {e}")
            n_written += 1

    if a.out:
        import csv
        cols = ["model", "track", "arm", "app", "case", "sr", "pcs", "cfr",
                "pcs_passed", "pcs_total", "cfr_passed", "cfr_total", "trivial_total"]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        new = not a.out.exists()
        with a.out.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            if new:
                w.writeheader()
            for s in agg.values():
                w.writerows(s)
        print(f"  metrics appended to {a.out}")

    print(f"\n{n_seen} runs recomputed, {n_written} written, {n_skipped} skipped\n")
    print(f"{'track':16}{'arm':26}{'app':10}{'n':>5}{'SR':>8}{'PCS':>8}{'CFR':>8}")
    for k in sorted(agg):
        s = agg[k]
        pv = [x["pcs"] for x in s if x["pcs"] is not None]
        print(f"{k[1]:16}{k[2][:25]:26}{k[3]:10}{len(s):>5}"
              f"{100 * sum(x['sr'] for x in s) / len(s):>7.1f}%"
              f"{(100 * sum(pv) / len(pv)) if pv else float('nan'):>7.1f}%"
              f"{100 * sum(x['cfr'] for x in s) / len(s):>7.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
