import os
import unittest

from incident_summarizer.llm import heuristic_analysis, parse_json_response
from incident_summarizer.preprocess import build_context, build_timeline, cluster_logs, load_bundle, normalize

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "sample_data", "incident_oomkilled.json")


class PreprocessTests(unittest.TestCase):
    def test_normalize_strips_volatile_tokens(self):
        a = normalize("timeout after 3001ms calling 10.0.1.12:8443 at 2026-03-12T10:04:01Z")
        b = normalize("timeout after 3002ms calling 10.0.7.99:8443 at 2026-03-12T10:04:02Z")
        self.assertEqual(a, b)

    def test_normalize_pod_suffix(self):
        self.assertIn("-<pod>", normalize("pod checkout-api-7d9f8b6c5d-x2k4p restarted"))

    def test_normalize_keeps_ordinary_hyphenated_words(self):
        self.assertIn("failed-start", normalize("failed-start detected"))

    def test_cluster_counts_and_order(self):
        logs = ["error 1", "error 2", "error 3", "other thing"]
        clusters = cluster_logs(logs)
        self.assertEqual(clusters[0]["count"], 3)
        self.assertEqual(clusters[1]["count"], 1)

    def test_timeline_is_chronological_and_includes_resolution(self):
        alerts = [{"name": "A", "severity": "critical", "starts_at": "2026-03-12T10:05:00Z", "resolved_at": "2026-03-12T10:20:00Z"}]
        events = [{"time": "2026-03-12T10:01:00Z", "type": "Warning", "reason": "OOMKilled", "object": "pod/x", "message": "m"}]
        tl = build_timeline(alerts, events)
        self.assertEqual([t["source"] for t in tl], ["k8s", "alert", "alert"])
        self.assertTrue(tl[-1]["text"].startswith("RESOLVED"))

    def test_timeline_unparseable_time_sorts_last(self):
        events = [{"time": "garbage", "reason": "X"}, {"time": "2026-03-12T10:01:00Z", "reason": "Y"}]
        tl = build_timeline([], events)
        self.assertIn("Y", tl[0]["text"])

    def test_sample_bundle_compresses_logs(self):
        ctx = build_context(load_bundle(SAMPLE))
        self.assertEqual(ctx["raw_counts"]["log_lines"], 171)
        self.assertLess(len(ctx["log_clusters"]), 10)


class LlmHelperTests(unittest.TestCase):
    def test_parse_json_with_code_fence(self):
        self.assertEqual(parse_json_response('```json\n{"summary": "ok"}\n```'), {"summary": "ok"})

    def test_parse_json_with_surrounding_prose(self):
        self.assertEqual(parse_json_response('Here you go: {"a": 1} Thanks!'), {"a": 1})

    def test_parse_json_raises_without_object(self):
        with self.assertRaises(ValueError):
            parse_json_response("no json here")

    def test_heuristic_detects_oomkilled_on_sample(self):
        ctx = build_context(load_bundle(SAMPLE))
        causes = " ".join(c["cause"] for c in heuristic_analysis(ctx)["probable_causes"])
        self.assertIn("OOMKilled", causes)


if __name__ == "__main__":
    unittest.main()
