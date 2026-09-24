"""Scrub an identifying string (a Windows user name) out of the dataset's project files.

    python bench_runner/dataset/anonymize_projects.py --find <name> --replace <same-length>
    python bench_runner/dataset/anonymize_projects.py --find <name> --check      # report only

A Revit project stores the author's paths in PLAIN TEXT metadata — BasicFileInfo ("Last Save
Path"), embedded XML (`<LastSavedAbsolutePath>`) and the file names inside an embedded zip —
as ASCII and as UTF-16LE, so `C:\\Users\\<name>\\...` survives into every released `.rvt`.
The replacement is SAME-LENGTH and in place, in both encodings: no stream changes size, so
the OLE compound file's sector chains and the zip's offsets stay valid (a zip CRC covers an
entry's content, not its name). Archicad `.pln` files and images are scanned too; they have
been clean so far.

Run it after authoring or re-saving any project on a personal machine, before committing.
Only files under `bench_cases/` are touched by default (`--root` to point elsewhere).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTS = {".rvt", ".pln", ".rfa", ".png", ".jpg", ".jpeg", ".pdf", ".json", ".md", ".txt", ".log"}


def variants(s: str) -> list[bytes]:
    out = []
    for v in {s, s.lower(), s.upper()}:
        out += [v.encode("ascii"), v.encode("utf-16le")]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--find", required=True, help="the identifying string (e.g. a user name)")
    ap.add_argument("--replace", default=None, help="SAME-LENGTH replacement (ASCII)")
    ap.add_argument("--check", action="store_true", help="report hits, change nothing")
    ap.add_argument("--root", type=Path, default=ROOT / "bench_cases")
    a = ap.parse_args(argv)
    if not a.check:
        if not a.replace or len(a.replace) != len(a.find) or not a.replace.isascii():
            sys.exit("--replace must be ASCII and EXACTLY as long as --find "
                     "(a same-length patch is what keeps the file structure valid)")
    pairs = []
    if not a.check:
        for f, r in ((a.find, a.replace), (a.find.lower(), a.replace.lower()),
                     (a.find.upper(), a.replace.upper())):
            pairs += [(f.encode("ascii"), r.encode("ascii")),
                      (f.encode("utf-16le"), r.encode("utf-16le"))]
    needles = variants(a.find)

    files = hits = changed = 0
    for p in sorted(a.root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        files += 1
        data = p.read_bytes()
        n = sum(data.count(x) for x in set(needles))
        if not n:
            continue
        hits += 1
        if a.check:
            print(f"  {n:3d} hit(s)  {p.relative_to(a.root)}")
            continue
        new = data
        for f, r in dict(pairs).items():
            new = new.replace(f, r)
        assert len(new) == len(data)
        p.write_bytes(new)
        changed += 1
    print(f"{files} file(s) scanned, {hits} with hits, {changed} rewritten")
    return 1 if (a.check and hits) else 0


if __name__ == "__main__":
    sys.exit(main())
