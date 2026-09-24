"""Pack / unpack the main tracks' start projects, which are distributed as release assets.

The 286 `.pln` / `.rvt` start projects of `reasoning_tasks` and `long-seq_tasks` weigh
~2.9 GB together — far beyond what a source repository should carry — so the repository
tracks everything else (task.json, drawings, baseline.json, the atomic templates) and the
projects travel as two zip archives attached to a release:

    python bench_runner/dataset/projects.py pack   --out <dir>          # -> archicad_projects.zip, revit_projects.zip
    python bench_runner/dataset/projects.py unpack --release <base-url> # download both and extract into bench_cases/
    python bench_runner/dataset/projects.py unpack --from <zip> [--from <zip>]   # from local archives
    python bench_runner/dataset/projects.py check                       # which start projects are missing

`pack` archives every `<track>/<tool>/<case>/env/start/<project>` path relative to the repo
root, one archive per application, so `unpack` restores the exact tree the cases expect.
`<base-url>` is the release's download prefix (for GitHub:
`https://github.com/<owner>/<repo>/releases/download/<tag>`).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "bench_cases"
TRACKS = ("reasoning_tasks", "long-seq_tasks")
PROJECT = {"archicad": "archicad.pln", "revit": "revit.rvt"}
ARCHIVE = {tool: f"{tool}_projects.zip" for tool in PROJECT}


def project_paths(tool: str) -> list[Path]:
    """Every start project the two main tracks expect for `tool`, existing or not."""
    out = []
    for track in TRACKS:
        tool_dir = CASES / track / tool
        if not tool_dir.is_dir():
            continue
        for case in sorted(p for p in tool_dir.iterdir() if p.is_dir()):
            if (case / "task.json").is_file():
                out.append(case / "env" / "start" / PROJECT[tool])
    return out


def pack(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for tool, name in ARCHIVE.items():
        paths = [p for p in project_paths(tool) if p.is_file()]
        missing = [p for p in project_paths(tool) if not p.is_file()]
        if missing:
            print(f"{tool}: {len(missing)} start project(s) missing — pack aborted:\n  "
                  + "\n  ".join(str(p.relative_to(ROOT)) for p in missing[:10]))
            return 1
        dest = out_dir / name
        size = 0
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                zf.write(p, p.relative_to(ROOT).as_posix())
                size += p.stat().st_size
        print(f"{dest}: {len(paths)} files, {size / 2**30:.2f} GB raw -> "
              f"{dest.stat().st_size / 2**30:.2f} GB")
    return 0


def _fetch(url: str, dest: Path) -> None:
    print(f"downloading {url}")
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 2**20:7.0f} / {total / 2**20:.0f} MB", end="", flush=True)
        print()


def unpack(archives: list[Path]) -> int:
    n = 0
    for a in archives:
        with zipfile.ZipFile(a) as zf:
            for m in zf.namelist():
                rel = Path(m)
                if rel.is_absolute() or ".." in rel.parts or rel.parts[0] != "bench_cases":
                    print(f"{a.name}: refusing unexpected member {m}")
                    return 1
            zf.extractall(ROOT)
            n += len(zf.namelist())
        print(f"{a.name}: {len(zf.namelist())} files extracted")
    print(f"{n} start project(s) in place")
    return check()


def check() -> int:
    missing = [p for tool in PROJECT for p in project_paths(tool) if not p.is_file()]
    present = sum(len(project_paths(t)) for t in PROJECT) - len(missing)
    print(f"start projects: {present} present, {len(missing)} missing")
    for p in missing[:20]:
        print("  missing:", p.relative_to(ROOT))
    if len(missing) > 20:
        print(f"  ... and {len(missing) - 20} more")
    return 1 if missing else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pack", help="write the two release archives")
    s.add_argument("--out", type=Path, required=True, help="directory for the archives (outside the repo)")
    s = sub.add_parser("unpack", help="download / extract the archives into bench_cases/")
    s.add_argument("--release", help="download prefix, e.g. https://github.com/<owner>/<repo>/releases/download/<tag>")
    s.add_argument("--from", dest="local", type=Path, action="append", default=[],
                   help="a local archive (repeatable)")
    sub.add_parser("check", help="list missing start projects")
    a = ap.parse_args(argv)
    if a.cmd == "pack":
        return pack(a.out)
    if a.cmd == "check":
        return check()
    if a.local:
        return unpack(a.local)
    if not a.release:
        ap.error("unpack needs --release <base-url> or --from <zip>")
    with tempfile.TemporaryDirectory() as td:
        got = []
        for name in ARCHIVE.values():
            dest = Path(td) / name
            _fetch(a.release.rstrip("/") + "/" + name, dest)
            got.append(dest)
        return unpack(got)


if __name__ == "__main__":
    sys.exit(main())
