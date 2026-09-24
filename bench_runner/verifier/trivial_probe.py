"""Decide, from the LIVE model, which goal checkpoints a case starts out satisfying.

`grade` splits checkpoints into the goal class C and the preservation class P by
asking what a no-operation run already achieves (see `grade.trivial_from_report`).
Answering that offline, from the stored `baseline.json`, is approximate: those
snapshots were captured before the schema carried wall facing and opening swing,
so the checkpoints that read those fields come back undecided and stay in C by
default. The consequence is that a no-operation run is not *provably* scored
PCS 0 -- an undecided checkpoint it happens to satisfy still counts as a goal.

This probe removes the approximation. It opens each case's own start project in
the authoring application, takes a snapshot through the same code path that
grades a finished run, and grades the case against that snapshot as both the
baseline and the answer. Whatever passes is what no action was required to
achieve.

Two properties make this cheap. The start project is opened once per DISTINCT
FILE, not once per case: the Reasoning and Long-Sequence tracks ship byte-identical
projects, so one snapshot serves both. And the snapshots are cached to disk, so
the trivial sets can be recomputed for free whenever an answer key changes --
only a change to a start project needs the application again.

`baseline.json` is never written. The probe is additive: its output is a separate
file, and every consumer falls back to the offline approximation when it is absent.

    # capture (needs the application running with its add-in answering)
    python bench_runner/verifier/trivial_probe.py capture --target archicad
    python bench_runner/verifier/trivial_probe.py capture --target revit

    # recompute the trivial sets from the cache (no application needed)
    python bench_runner/verifier/trivial_probe.py resolve
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "bench_runner"))
sys.path.insert(0, str(ROOT))

import case_io                                                      # noqa: E402
from verifier.grade import grade, normalize_composites, trivial_from_report  # noqa: E402

BENCH_CASES = ROOT / "bench_cases"
TRACKS = ("reasoning_tasks", "long-seq_tasks", "atomic_tasks")
EXT = {"archicad": ".pln", "revit": ".rvt"}
CACHE = HERE / ".cache" / "start_snapshots.json"
OUT = HERE / "trivial_sets.json"


def _hash(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cases(target: str):
    """(track, case_id, start-project path) for every case of one application."""
    for track in TRACKS:
        root = BENCH_CASES / track
        if not root.exists():
            continue
        try:
            ids = case_io.case_ids(root, target)
        except Exception:
            continue
        for cid in ids:
            start = case_io.env_dir(root, target, cid) / "start"
            hits = sorted(start.glob("*" + EXT[target]))
            if hits:
                yield track, cid, hits[0]


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ capture

def capture(target: str, only=None, redo: bool = False,
            open_wait: float = 15.0) -> int:
    """Open every distinct start project once and cache its live snapshot."""
    from bench_runner.backend import Toolbox
    from bench_runner.backend.snapshot import model_snapshot
    if target == "archicad":
        from drivers import archicad_io as io
        from bench_runner.backend.archicad.inventory import list_composites
    else:
        from drivers import revit_io as io
        list_composites = None

    cache = _load(CACHE, {})
    # one entry per distinct file: the tracks share start projects byte for byte
    todo: dict[str, tuple[Path, list[str]]] = {}
    for track, cid, pln in cases(target):
        if only and cid not in only:
            continue
        key = _hash(pln)
        todo.setdefault(key, (pln, []))[1].append(f"{track}/{cid}")
    pending = {k: v for k, v in todo.items() if redo or k not in cache}
    print(f"{target}: {len(todo)} distinct start projects "
          f"({sum(len(v[1]) for v in todo.values())} cases), {len(pending)} to capture")

    done = fail = 0
    for i, (key, (pln, used_by)) in enumerate(sorted(pending.items(),
                                                     key=lambda kv: kv[1][0].name), 1):
        label = used_by[0] if len(used_by) == 1 else f"{used_by[0]} (+{len(used_by) - 1})"
        print(f"  [{i}/{len(pending)}] {label}: {pln.name}", flush=True)
        try:
            io.open_project(pln, mode="gui", open_wait=open_wait)
            tb = Toolbox.connect(target)
            snap = model_snapshot(tb)
            comps = (list_composites(tb.client) if list_composites
                     else tb.remote_composites())
            cache[key] = {"target": target, "project": pln.name,
                          "used_by": used_by, "snapshot": snap, "composites": comps}
            _save(CACHE, cache)            # checkpoint after each, a batch can resume
            done += 1
        except Exception as e:
            print(f"      [fail] {type(e).__name__}: {e}", flush=True)
            fail += 1
    print(f"{target}: captured {done}, failed {fail}, cached total {len(cache)}")
    return fail


# ------------------------------------------------------------------ resolve

def resolve(verbose: bool = False) -> dict:
    """Grade every case against its cached start snapshot and record what passes."""
    cache = _load(CACHE, {})
    if not cache:
        print(f"no snapshot cache at {CACHE} — run `capture` first")
        return {}
    out = _load(OUT, {})
    n_live = n_miss = n_bad = 0
    nonzero = []
    for target in ("archicad", "revit"):
        for track, cid, pln in cases(target):
            key = f"{track}/{target}/{cid}"
            entry = cache.get(_hash(pln))
            if entry is None:
                n_miss += 1
                continue
            try:
                expected = case_io.read_spec(BENCH_CASES / track, target,
                                             cid).get("expected_result")
                if not expected:
                    continue
                snap = entry["snapshot"]
                comps = entry.get("composites")
                probe = grade(expected, snap, snap, normalize_composites([]),
                              anchor=(target == "revit"), answer="",
                              composites_final=comps)
                T = trivial_from_report(probe)
                # the check the whole probe exists for: with T applied, the
                # start project must score PCS 0 and CFR 1 on its own case
                check = grade(expected, snap, snap, normalize_composites([]),
                              anchor=(target == "revit"), answer="",
                              composites_final=comps, trivial=T)
                if check["pcs"] not in (None, 0.0) or check["cfr"] != 1.0:
                    nonzero.append((key, check["pcs"], check["cfr"]))
                out[key] = sorted(T)
                n_live += 1
            except Exception as e:
                n_bad += 1
                if verbose:
                    traceback.print_exc()
                else:
                    print(f"  [warn] {key}: {type(e).__name__}: {e}")
    _save(OUT, out)
    print(f"\nresolved {n_live} cases from the live cache, {n_miss} not captured, "
          f"{n_bad} errored")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(out)} cases)")
    if nonzero:
        print(f"[!] {len(nonzero)} cases do NOT score PCS 0 / CFR 1 on their own "
              f"start project — the split is not airtight for them:")
        for k, p, c in nonzero[:20]:
            print(f"    {k}: PCS={p} CFR={c}")
    else:
        print("every captured case scores PCS 0 and CFR 1 on its own start "
              "project — the no-operation floor is provably zero")
    return out


def load_trivial(track: str, target: str, case_id: str) -> set | None:
    """The live-probed trivial set for one case, or None if it was never probed."""
    ids = _load(OUT, {}).get(f"{track}/{target}/{case_id}")
    return set(ids) if ids is not None else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture", help="open the start projects and cache their snapshots")
    c.add_argument("--target", choices=("archicad", "revit"), required=True)
    c.add_argument("--only", nargs="*", help="limit to these case ids")
    c.add_argument("--redo", action="store_true", help="re-capture already cached projects")
    c.add_argument("--open-wait", type=float, default=15.0)
    r = sub.add_parser("resolve", help="recompute the trivial sets from the cache")
    r.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "capture":
        return 1 if capture(a.target, only=a.only, redo=a.redo,
                            open_wait=a.open_wait) else 0
    resolve(verbose=a.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
