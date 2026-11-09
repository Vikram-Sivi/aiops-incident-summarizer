# Incident Summarizer (AIOps)

Turns raw incident data (alerts, Kubernetes events, logs) into a structured **draft RCA** using an LLM.
Built from an SRE point of view: the engineer stays in the loop, and the tool is designed to be
evidence-bound rather than creative.

## Why
During a P1, on-call engineers lose time stitching together alerts, `kubectl` events and thousands of
repetitive log lines. This tool does the stitching: it builds a timeline, collapses noisy logs into
patterns with counts, and asks an LLM for a summary, probable causes (with evidence and confidence),
recommended actions and open questions.

## How it works
```
incident.json -> preprocess -> prompt -> LLM -> JSON analysis -> Markdown report
                 (timeline,      (evidence-only
                  log clustering) rules + schema)
```
- **Log clustering:** timestamps, IPs, UUIDs, pod suffixes and numbers are normalised, so 171 log lines
  in the sample collapse to 3 patterns with counts. This cuts tokens and keeps the signal visible.
- **Evidence-bound prompt:** the model may only use the supplied data, must separate facts from
  hypotheses, must give a confidence level per cause, and must list what is unknown.
- **Structured output:** the model returns JSON that is parsed and rendered to Markdown; responses
  with code fences or extra prose are handled.
- **Offline mode:** `--dry-run` uses a keyword heuristic, so the pipeline works without an API key
  (also useful in CI and for tests).

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...            # optional: only needed for LLM mode
# optional: export ANTHROPIC_MODEL=<model name>   (default set in incident_summarizer/llm.py)

python -m incident_summarizer sample_data/incident_oomkilled.json --dry-run   # no API call
python -m incident_summarizer sample_data/incident_oomkilled.json --out report.md   # LLM mode
python -m incident_summarizer sample_data/incident_oomkilled.json --show-prompt     # inspect the prompt
python -m unittest discover -s tests -t .                                           # run tests
```

## Input format
```json
{
  "service": "checkout-api", "environment": "prod",
  "window": {"start": "...", "end": "..."},
  "alerts": [{"name": "...", "severity": "...", "starts_at": "...", "resolved_at": "...", "summary": "..."}],
  "k8s_events": [{"time": "...", "type": "Warning", "reason": "OOMKilled", "object": "pod/...", "message": "..."}],
  "logs": [{"time": "...", "level": "ERROR", "message": "..."}]
}
```
The sample data is synthetic. Never commit real production logs or client data.

## Limitations
- Output is a draft; an engineer must verify it. Confidence labels come from the model, not from calibration.
- Input is a JSON bundle; there are no live integrations yet.
- No evaluation set yet, so quality has been checked only on the synthetic sample.

## Roadmap
- Ingest from Alertmanager/Prometheus and CloudWatch Logs directly
- Post the draft to Slack or the incident ticket
- Small eval set of past incidents to compare prompts and models
- Redact secrets and PII before logs leave the environment
