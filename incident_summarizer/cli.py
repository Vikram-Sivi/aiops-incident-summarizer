from __future__ import annotations

import argparse
import sys

from .llm import DEFAULT_MODEL, call_llm, heuristic_analysis
from .preprocess import build_context, load_bundle
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .report import render_markdown


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="incident_summarizer", description="Draft an RCA from alerts, events and logs.")
    p.add_argument("bundle", help="Path to incident JSON bundle")
    p.add_argument("--dry-run", action="store_true", help="No API call: use the offline heuristic")
    p.add_argument("--show-prompt", action="store_true", help="Print the prompt that would be sent to the model and exit")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", help="Write the Markdown report to this file")
    args = p.parse_args(argv)

    ctx = build_context(load_bundle(args.bundle))
    user_prompt = build_user_prompt(ctx)
    counts = ctx["raw_counts"]
    print(
        f"Loaded {counts['alerts']} alerts, {counts['k8s_events']} events, {counts['log_lines']} log lines "
        f"-> {len(ctx['log_clusters'])} log patterns, prompt ~{len(user_prompt)} chars",
        file=sys.stderr,
    )
    if args.show_prompt:
        print(SYSTEM_PROMPT + "\n\n" + user_prompt)
        return 0

    if args.dry_run:
        analysis, source = heuristic_analysis(ctx), "offline heuristic (no LLM)"
    else:
        analysis, source = call_llm(SYSTEM_PROMPT, user_prompt, args.model), f"LLM ({args.model})"

    report = render_markdown(analysis, ctx, source)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0
