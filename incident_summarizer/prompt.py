"""Prompt construction. Keeping this separate makes prompt changes easy to review."""
from __future__ import annotations

import json

SYSTEM_PROMPT = """You are an experienced Site Reliability Engineer helping an on-call engineer \
write a first-draft incident summary.

Rules:
- Use ONLY the evidence provided. Do not invent metrics, timestamps, services or causes.
- Separate facts (what the data shows) from hypotheses (what might explain it).
- If the data does not support a conclusion, say so and put it under open_questions.
- Give a confidence level (low, medium, high) for every probable cause.
- Recommended actions must be concrete and safe to review (no destructive commands).
- Respond with a single JSON object and nothing else."""

OUTPUT_SCHEMA = {
    "summary": "2-3 sentence plain-language summary of what happened",
    "impact": "who or what was affected, based only on the evidence",
    "timeline": [{"time": "ISO timestamp or 'unknown'", "event": "what happened"}],
    "probable_causes": [
        {"cause": "hypothesis", "evidence": ["supporting facts from the data"], "confidence": "low|medium|high"}
    ],
    "recommended_actions": ["concrete next steps"],
    "open_questions": ["what is still unknown"],
}


def build_user_prompt(ctx: dict) -> str:
    return (
        "Incident data (pre-processed; repeated log lines are grouped with counts):\n\n"
        f"{json.dumps(ctx, indent=2, default=str)}\n\n"
        "Return JSON matching this schema exactly:\n"
        f"{json.dumps(OUTPUT_SCHEMA, indent=2)}"
    )
