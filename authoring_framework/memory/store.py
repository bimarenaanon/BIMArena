"""MemoryStore — a dict-like, JSON-persisted key/value store shared across stages.

Use it like a dict: ``mem["instruction"]``, ``mem["instruction"] = ...``,
``"pdf" in mem``, iteration. Add several keys at once with ``mem.update({...})``.

Several MemoryStore instances are alive at once within one run (agent.py keeps one while the
providers each open another via ``session()``). To keep them consistent
WITHOUT re-reading the JSON on every access (``reasoning`` and ``stats``
grow over a long run, so a reload-per-access is O(n^2)), all instances opened on
the SAME file path in this process **share one dict object** — a process-level registry. A
write by any instance is therefore immediately visible to every other instance, and there is
no stale snapshot to clobber another instance's keys. Writes also persist to disk (the file
is the durable record the bench harness collects; a separate process — e.g. the GUI agent's
``--no-plan`` reuse, or a later inspection — loads the file fresh on start).
"""
import json
import os
from pathlib import Path

# resolved-path str -> the shared data dict for that file (one per process).
_REGISTRY = {}


class MemoryStore:
    def __init__(self, path, autosave=True):
        self.path = Path(path)
        self.autosave = autosave
        key = str(self.path.resolve())
        data = _REGISTRY.get(key)
        if data is None:                              # first open of this file in this process
            data = {}
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    data.update(json.load(f))
            _REGISTRY[key] = data
        self.data = data                              # SHARED across all instances for this path

    # ---- reads (the shared dict is always current within the process) ----
    def get(self, key, default=None):
        return self.data.get(key, default)

    def all(self):
        """A shallow copy of the whole store as a plain dict."""
        return dict(self.data)

    # ---- writes (mutate the shared dict, then persist) ----
    def set(self, key, value):
        self.data[key] = value
        self._flush()
        return value

    def update(self, data):
        """Merge a dict into memory, e.g. mem.update({"instruction": ...})."""
        self.data.update(data)
        self._flush()
        return self.data

    def append(self, key, value):
        """Append to a list-valued key (created on first use)."""
        lst = self.data.setdefault(key, [])
        if not isinstance(lst, list):
            raise TypeError(f"memory key {key!r} is not a list")
        lst.append(value)
        self._flush()
        return lst

    def delete(self, key):
        self.data.pop(key, None)
        self._flush()

    def clear(self):
        self.data.clear()                             # clear IN PLACE so other holders keep the object
        self._flush()

    # ---- dict-style access ----
    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.set(key, value)

    def __delitem__(self, key):
        self.delete(key)

    def __contains__(self, key):
        return key in self.data

    def __iter__(self):
        return iter(dict(self.data))

    def __len__(self):
        return len(self.data)

    # ---- persistence ----
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # encoding="utf-8" — data can hold non-ASCII; the Windows default cp1252 would raise
        # UnicodeEncodeError with ensure_ascii=False. COMPACT separators: save() runs on every
        # mutation and the store grows to hundreds of KB (the per-turn reasoning record)
        # — a pretty-printed rewrite per write is the run's dominant disk cost (read the file
        # with `jq`). ATOMIC via temp + os.replace: save() truncate-rewrites hundreds of times
        # per run, and a process killed mid-write (Ctrl-C, harness timeout) would otherwise
        # leave a half-written memory.json — the run's entire durable state unreadable.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, self.path)

    def load(self):
        """Force a refresh of the shared dict from disk IN PLACE (rarely needed — reads already see
        every in-process write; useful only if an external process changed the file)."""
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                fresh = json.load(f)
            self.data.clear()
            self.data.update(fresh)
        return self.data

    def _flush(self):
        if self.autosave:
            self.save()
