"""The TOOL LAYER — everything the agent can do.

    tools/gui/   the ACTION SPACE: the computer-use route — screen, mouse, keyboard — plus its
                 two retrieval lookups: `documentation_retrieval` (the vendors' official help,
                 both modes) and `operational_skill_retrieval` (the hand-written per-capability
                 procedures, gui-support only).

The applications' programming interfaces are NOT here: the harness-side backends the bench
grades through live in `bench_runner/backend/`.

Every tool implements ONE contract (`base.Tool`): a name, a one-line summary, typed params with
docs, and a handler. The registry renders them into the function declarations the agent is
handed and validates every call against the same specs, so a tool exists exactly once.
"""
from .base import (FAMILIES, Param, Tool,
                   ToolRegistry, normalize_call, validate_call)
from .runtime import GUI_OP_DELAY_S, ToolContext, build_registry, plan_batch, run_batch

__all__ = ["FAMILIES", "Param", "Tool",
           "ToolRegistry", "ToolContext", "build_registry", "plan_batch", "run_batch",
           "normalize_call", "validate_call", "GUI_OP_DELAY_S"]
