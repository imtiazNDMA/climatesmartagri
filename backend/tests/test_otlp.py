import json
import logging
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from csa_portal.ai.otlp import OtlpExporter, otlp_body
from csa_portal.ai.store import SpanRecord, TraceRecord

START = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TRACE = TraceRecord(
    id="a" * 32, source="live", agent="assistant", model="qwen", started_at=START, duration_ms=1000.0, status="error",
    error_reason="tool-limit", input_tokens=300, output_tokens=20, question_hash="f" * 64, question_text=None,
    answer_text=None,
    spans=[
        SpanRecord("1" * 16, "a" * 32, None, "agent", "assistant", START, 1000.0, "error", {"gen_ai.agent.name": "assistant"}),
        SpanRecord("2" * 16, "a" * 32, "1" * 16, "llm", "chat qwen", START, 250.5, "ok",
                   {"gen_ai.usage.input_tokens": 300, "csa.ratio": 0.5, "csa.cached": False}),
    ],
)


def test_a_trace_becomes_an_otlp_json_request_with_one_span_per_record():
    body = otlp_body(TRACE)

    resource = body["resourceSpans"][0]
    assert resource["resource"]["attributes"] == [{"key": "service.name", "value": {"stringValue": "csa-portal"}}]
    agent, llm = resource["scopeSpans"][0]["spans"]
    assert (agent["traceId"], agent["spanId"], agent["name"], agent["kind"]) == ("a" * 32, "1" * 16, "assistant", 1)
    assert "parentSpanId" not in agent
    assert agent["status"] == {"code": 2}
    assert (llm["parentSpanId"], llm["kind"], llm["status"]) == ("1" * 16, 3, {"code": 1})
    start = int(START.timestamp() * 1_000_000_000)
    assert (llm["startTimeUnixNano"], llm["endTimeUnixNano"]) == (str(start), str(start + 250_500_000))
    assert {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "300"}} in llm["attributes"]
    assert {"key": "csa.ratio", "value": {"doubleValue": 0.5}} in llm["attributes"]
    assert {"key": "csa.cached", "value": {"boolValue": False}} in llm["attributes"]
    assert {"key": "csa.span.kind", "value": {"stringValue": "llm"}} in llm["attributes"]


def test_a_trace_is_posted_to_the_collector():
    received = {}

    class Collector(BaseHTTPRequestHandler):
        def do_POST(self):
            received["path"] = self.path
            received["type"] = self.headers["Content-Type"]
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        OtlpExporter(f"http://127.0.0.1:{server.server_port}/").send(TRACE)
    finally:
        server.shutdown()

    assert (received["path"], received["type"]) == ("/v1/traces", "application/json")
    assert received["body"] == otlp_body(TRACE)


def test_an_unreachable_collector_is_logged_and_does_not_raise(caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        OtlpExporter("http://127.0.0.1:1", timeout=0.2).send(TRACE)

    assert any("could not be exported" in record.getMessage() for record in caplog.records)
