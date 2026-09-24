"""CLI entry: `python -m authoring_framework [<drawing>...] -i "<instruction>"`."""
import argparse
import sys

from .react import run
from .config import (BIM_TARGETS, LLM_PROVIDERS, TOOL_MODES, TOOL_MODE_ALIASES,
                     set_llm_override, set_target_override, set_tools_override)


def main(argv=None):
    # On Windows the console defaults to cp1252, which cannot encode the arrows/bullets the
    # agent prints and would crash the run. Force UTF-8.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(
        prog="authoring_framework",
        description="BIM authoring agent (Archicad or Revit) — a computer-use ReAct loop "
                    "over the application's GUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="The instruction is the WHOLE task: the agent reads any drawing, works out which "
               "application it is in, and drives it with the tools it is given.")
    p.add_argument("pdf", nargs="*", default=None,
                   help="drawing PDF/image path(s) (optional; pass SEVERAL for a multi-view "
                        "case — all are attached in the given order; OMIT for a text-only run)")
    p.add_argument("-i", "--instruction", default=None,
                   help="the task, as free text — the ONLY task input there is (required)")
    p.add_argument("--tools", choices=list(TOOL_MODES) + list(TOOL_MODE_ALIASES),
                   default=None,
                   help="the support setting: gui-raw (no retrieval tool — w/o support), "
                        "gui-docs (documentation_retrieval, the vendors' official help) or "
                        "gui-support (default — the documentation PLUS "
                        "operational_skill_retrieval, the hand-written per-capability "
                        "procedures). $AGENT_TOOLS sets the default.")
    p.add_argument("-p", "--provider", choices=LLM_PROVIDERS, default=None,
                   help="LLM provider (default: openai, or $LLM_PROVIDER)")
    p.add_argument("-m", "--model", default=None,
                   help="override the LLM model id (default: the provider's model in config)")
    p.add_argument("--target", default=None,
                   help="NARROW which application's operational skills are served (%s), "
                        "comma-separated for several. Default: every application's — the agent "
                        "works out from the screen which one is actually running."
                        % ", ".join(BIM_TARGETS))
    args = p.parse_args(argv)
    set_llm_override(args.provider, args.model)
    set_target_override(args.target)
    set_tools_override(args.tools)
    run(pdf=args.pdf, instruction=args.instruction)


if __name__ == "__main__":
    main()
