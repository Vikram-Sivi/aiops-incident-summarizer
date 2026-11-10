"""LLM call plus an offline heuristic used for --dry-run and as a test double."""
from __future__ import annotations

import json
import os

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")


def parse_json_response(text: str) -> dict:
    """Extract the JSON object from a model reply, tolerating code fences or stray prose."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


def call_llm(system: str, user: str, model: str = DEFAULT_MODEL, max_tokens: int = 2000) -> dict:
    """Call the Anthropic Messages API and return the parsed analysis."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Use --dry-run to run without an API key.")
    import anthropic  # imported lazily so --dry-run and tests need no dependency

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    return parse_json_response(text)


# --- Offline heuristic -------------------------------------------------------

_SIGNATURES = [
    ("OOMKilled", "Container exceeded its memory limit and was killed (OOMKilled).",
     "Review memory requests/limits and recent memory growth; check for leaks or traffic spikes."),
    ("CrashLoopBackOff", "Pod is repeatedly crashing and restarting (CrashLoopBackOff).",
     "Inspect previous container logs (kubectl logs --previous) and recent config or image changes."),
    ("ImagePullBackOff", "Image could not be pulled.",
     "Verify image tag, registry credentials and registry availability."),
    ("FailedScheduling", "Pods could not be scheduled.",
     "Check node capacity, taints/tolerations and resource requests."),
    ("connection refused", "Dependency refused connections.",
     "Check the health and endpoints of the downstream service."),
    ("timeout", "Requests or dependencies timed out.",
     "Check latency of downstream dependencies and connection pool settings."),
]


def heuristic_analysis(ctx: dict) -> dict:
    """Keyword-based draft so the pipeline can be exercised without an LLM."""
    haystack = " ".join(
        [t["text"] for t in ctx["timeline"]] + [c["pattern"] for c in ctx["log_clusters"]]
    ).lower()
    causes, actions = [], []
    for needle, cause, action in _SIGNATURES:
        if needle.lower() in haystack:
            causes.append({"cause": cause, "evidence": [f"'{needle}' appears in alerts, events or logs"], "confidence": "low"})
            actions.append(action)
    first = ctx["timeline"][0]["text"] if ctx["timeline"] else "no alerts or events"
    return {
        "summary": f"Heuristic (no LLM) summary for {ctx['service']} in {ctx['environment']}. First signal: {first}.",
        "impact": "Not determined without LLM analysis.",
        "timeline": [{"time": t["time"] or "unknown", "event": t["text"]} for t in ctx["timeline"]],
        "probable_causes": causes,
        "recommended_actions": actions or ["Review the timeline and top log patterns manually."],
        "open_questions": ["Run without --dry-run for an LLM-generated analysis."],
    }
