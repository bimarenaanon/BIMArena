"""RunFS — per-run working directories under <runs_dir>/<timestamp>-<uuid>/.

One RunFS is bound to the framework's `runs/` dir at the bottom of this module, so the rest of
the code just imports `new_run` / `current_run` / `screenshot_path` / `trace_event`. Each
invocation starts a new run (`new_run`); memory and any other outputs default into that
folder. The active run id is remembered in a pointer file, so any later stage — even a
separate process — resolves the same directory via `current_run`.
"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..config import RUNS_DIR


class RunFS:
    def __init__(self, runs_dir):
        self.runs_dir = Path(runs_dir)
        self._pointer = self.runs_dir / ".current"
        self._active = {}   # this process's resolved run dir — re-reading the pointer file per
                            # call would let ANOTHER process's new_run() silently redirect this
                            # run's memory/outputs

    def new_run(self):
        """Create a fresh <runs_dir>/<timestamp>-<uuid>/ directory and make it the current run."""
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        d = self.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        self._pointer.write_text(run_id)
        self._active["dir"] = d
        return d

    def current_run(self):
        """The current run directory: this process's own run once resolved (stable for the whole
        process, whatever other processes do to the pointer file); else the pointer file (so a
        separate later process finds the previous run); else a new run."""
        d = self._active.get("dir")
        if d is not None and d.is_dir():
            return d
        if self._pointer.exists():
            d = self.runs_dir / self._pointer.read_text().strip()
            if d.is_dir():
                self._active["dir"] = d
                return d
        return self.new_run()

    def screenshot_path(self):
        """A fresh <run>/screenshot/<uuid>.png path (the folder is created). The uuid name
        keeps successive screenshots from colliding."""
        d = self.current_run() / "screenshot"
        d.mkdir(parents=True, exist_ok=True)
        return d / (uuid.uuid4().hex + ".png")

    def trace_event(self, kind, **payload):
        """Append ONE event line to <run>/trace.jsonl (durable, O(1) per write).

        The JSONL stream is the durable per-event record (crash-analyzable line by line) —
        unlike memory.json, which REWRITES the whole growing file on every mutation. A trace
        write must never kill a run."""
        line = {"t": round(time.time(), 3), "event": kind, **payload}
        try:
            with open(self.current_run() / "trace.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"[trace] event write failed ({type(e).__name__}: {e})")


# THE binding the rest of the framework imports: one RunFS on the package's runs/ dir.
_FS = RunFS(RUNS_DIR)
new_run = _FS.new_run
current_run = _FS.current_run
screenshot_path = _FS.screenshot_path
trace_event = _FS.trace_event
