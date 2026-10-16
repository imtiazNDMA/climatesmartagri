"""Sends finished traces to an OpenTelemetry collector as OTLP/HTTP JSON, when CSA_OTLP_ENDPOINT is set.

This lets Langfuse, Phoenix or any OTLP collector show the portal's traces without the portal depending on them.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from typing import Any

from .store import SpanRecord, TraceRecord

logger = logging.getLogger("uvicorn.error")

_SPAN_KIND_INTERNAL = 1
_SPAN_KIND_CLIENT = 3
_STATUS = {"ok": 1, "error": 2}


def otlp_body(trace: TraceRecord) -> dict[str, Any]:
    return {
        "resourceSpans": [{
            "resource": {"attributes": [_attribute("service.name", "csa-portal")]},
            "scopeSpans": [{"scope": {"name": "csa_portal.ai"}, "spans": [_span(span) for span in trace.spans]}],
        }],
    }


def _span(span: SpanRecord) -> dict[str, Any]:
    start = int(span.started_at.timestamp() * 1_000_000_000)
    body: dict[str, Any] = {
        "traceId": span.trace_id,
        "spanId": span.id,
        "name": span.name,
        "kind": _SPAN_KIND_CLIENT if span.kind == "llm" else _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + round(span.duration_ms * 1_000_000)),
        "attributes": [_attribute(key, value) for key, value in span.attributes.items()]
        + [_attribute("csa.span.kind", span.kind)],
        "status": {"code": _STATUS.get(span.status, 0)},
    }
    if span.parent_id:
        body["parentSpanId"] = span.parent_id
    return body


def _attribute(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        typed: dict[str, Any] = {"boolValue": value}
    elif isinstance(value, int):
        typed = {"intValue": str(value)}
    elif isinstance(value, float):
        typed = {"doubleValue": value}
    else:
        typed = {"stringValue": str(value)}
    return {"key": key, "value": typed}


class OtlpExporter:
    def __init__(self, endpoint: str, timeout: float = 2.0) -> None:
        self.url = endpoint.rstrip("/") + "/v1/traces"
        self.timeout = timeout

    def write_trace(self, trace: TraceRecord) -> None:
        # Sent out of the request's way: a slow or absent collector must not slow an answer.
        threading.Thread(target=self.send, args=(trace,), daemon=True).start()

    def send(self, trace: TraceRecord) -> None:
        request = urllib.request.Request(
            self.url, data=json.dumps(otlp_body(trace)).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except (OSError, ValueError):
            logger.warning("Trace %s could not be exported to %s", trace.id, self.url, exc_info=True)
