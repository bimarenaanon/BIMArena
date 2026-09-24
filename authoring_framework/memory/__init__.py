"""Global shared memory for the framework.

`session()` opens the current run's memory store (runs/<uuid>/memory.json); any stage can
call it to read the run's pdf / instruction (and anything later stages write).
"""
from ..ults.runs import current_run
from .store import MemoryStore


def session():
    """Open the current run's memory store."""
    return MemoryStore(current_run() / "memory.json")


__all__ = ["MemoryStore", "session"]
