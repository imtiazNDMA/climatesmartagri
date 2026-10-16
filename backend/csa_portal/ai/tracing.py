"""Tracing: every AI answer leaves a trace of spans (agent, llm, tool, workflow) named after OpenTelemetry GenAI.

`span()` can be called from anywhere. It records into the trace the current request is answering, and does
nothing when there is none, so code that opens spans also runs untraced (tests, the evaluation script).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from .store import SpanRecord, TraceRecord

logger = logging.getLogger("uvicorn.error")

SpanKind = Literal["agent", "llm", "tool", "workflow"]
_TOKEN_ATTRIBUTES = ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens")


class TraceSink(Protocol):
    def write_trace(self, trace: TraceRecord) -> None: ...


class Span:
    """A span being recorded. `set` adds attributes; `fail` marks it as an error."""

    def __init__(self, trace_id: str, parent_id: str | None, kind: SpanKind, name: str, attributes: dict[str, Any]) -> None:
        self.id = secrets.token_hex(8)
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.kind = kind
        self.name = name
        self.attributes = dict(attributes)
        self.status = "ok"
        self.started_at = datetime.now(UTC)
        self.duration_ms = 0.0
        self._started = time.perf_counter()

    def set(self, **attributes: Any) -> None:
        self.attributes.update(attributes)

    def fail(self) -> None:
        self.status = "error"

    def finish(self) -> None:
        self.duration_ms = (time.perf_counter() - self._started) * 1000

    def record(self) -> SpanRecord:
        return SpanRecord(
            self.id, self.trace_id, self.parent_id, self.kind, self.name, self.started_at, self.duration_ms,
            self.status, dict(self.attributes),
        )


class NoSpan:
    """What `span` gives when no trace is being recorded: it accepts everything and keeps nothing."""

    id = None

    def set(self, **attributes: Any) -> None:
        pass

    def fail(self) -> None:
        pass


_NO_SPAN = NoSpan()


class ActiveTrace:
    """The trace one request is recording."""

    def __init__(self, agent: str, model: str, question: str, source: str, eval_run_id: str | None) -> None:
        self.id = secrets.token_hex(16)
        self.agent = agent
        self.model = model
        self.question = question
        self.source = source
        self.eval_run_id = eval_run_id
        self.answer: str | None = None
        self.status = "ok"
        self.error_reason: str | None = None
        self.spans: list[Span] = []
        self.started_at = datetime.now(UTC)
        self._started = time.perf_counter()

    def answered(self, text: str) -> None:
        self.answer = text

    def record(self, capture_content: bool) -> TraceRecord:
        llm = [s for s in self.spans if s.kind == "llm"]
        tokens = [_total(llm, name) for name in _TOKEN_ATTRIBUTES]
        return TraceRecord(
            id=self.id, source=self.source, agent=self.agent, model=self.model, started_at=self.started_at,
            duration_ms=(time.perf_counter() - self._started) * 1000, status=self.status,
            error_reason=self.error_reason, input_tokens=tokens[0], output_tokens=tokens[1],
            question_hash=hashlib.sha256(self.question.encode("utf-8")).hexdigest(),
            question_text=self.question if capture_content else None,
            answer_text=self.answer if capture_content else None,
            eval_run_id=self.eval_run_id, spans=[s.record() for s in self.spans],
        )


_trace: ContextVar[ActiveTrace | None] = ContextVar("csa_trace", default=None)
_span: ContextVar[Span | None] = ContextVar("csa_span", default=None)


@contextmanager
def span(kind: SpanKind, name: str, **attributes: Any) -> Iterator[Span | NoSpan]:
    active = _trace.get()
    if active is None:
        yield _NO_SPAN
        return
    parent = _span.get()
    current = Span(active.id, parent.id if parent else None, kind, name, attributes)
    active.spans.append(current)
    token = _span.set(current)
    try:
        yield current
    except BaseException:
        current.fail()
        raise
    finally:
        _span.reset(token)
        current.finish()


class Tracer:
    """Starts traces and hands each finished one to the store and the exporter.

    A store that cannot write never fails an answer: the failure is logged and counted, and `status` turns
    `degraded`. `unavailable` says why there is no store at all when one was configured.
    """

    def __init__(
        self,
        sink: TraceSink | None = None,
        *,
        capture_content: bool = False,
        exporter: TraceSink | None = None,
        unavailable: str | None = None,
    ) -> None:
        self.sink = sink
        self.capture_content = capture_content
        self.exporter = exporter
        self.unavailable = unavailable
        self.failures = 0
        self._lock = threading.Lock()

    @property
    def status(self) -> str:
        if self.unavailable or self.failures:
            return "degraded"
        return "off" if self.sink is None else "ok"

    @contextmanager
    def trace(
        self, agent: str, *, model: str, question: str, source: str = "live", eval_run_id: str | None = None
    ) -> Iterator[ActiveTrace]:
        active = ActiveTrace(agent, model, question, source, eval_run_id)
        trace_token = _trace.set(active)
        span_token = _span.set(None)
        try:
            yield active
        except BaseException as error:
            active.status = "error"
            active.error_reason = getattr(error, "reason", None) or type(error).__name__
            raise
        finally:
            _span.reset(span_token)
            _trace.reset(trace_token)
            self._finish(active.record(self.capture_content))

    def _finish(self, record: TraceRecord) -> None:
        if self.sink is not None:
            try:
                self.sink.write_trace(record)
            except Exception:
                with self._lock:
                    self.failures += 1
                logger.warning("Trace %s could not be stored", record.id, exc_info=True)
        if self.exporter is not None:
            try:
                self.exporter.write_trace(record)
            except Exception:
                with self._lock:
                    self.failures += 1
                logger.warning("Trace %s could not be exported", record.id, exc_info=True)


def _total(spans: list[Span], attribute: str) -> int | None:
    values = [s.attributes[attribute] for s in spans if isinstance(s.attributes.get(attribute), int)]
    return sum(values) if values else None


class _TracedChat:
    """A model that can only chat, with each call an `llm` span."""

    def __init__(self, inner: Any, model_name: str) -> None:
        self.inner = inner
        self.model_name = model_name

    def _attributes(self) -> dict[str, Any]:
        return {"gen_ai.operation.name": "chat", "gen_ai.request.model": self.model_name}

    def chat(self, messages: list[dict[str, Any]]) -> str:
        with span("llm", f"chat {self.model_name}", **self._attributes()):
            return self.inner.chat(messages)


class TracedModel(_TracedChat):
    """A language model whose every `complete` and `chat` call is an `llm` span with request and usage attributes."""

    def complete(self, messages: list[dict[str, Any]], tools: Any = None, output: Any = None) -> Any:
        with span("llm", f"chat {self.model_name}", **self._attributes()) as current:
            reply = (
                self.inner.complete(messages, tools=tools)
                if output is None
                else self.inner.complete(messages, tools=tools, output=output)
            )
            usage = {"gen_ai.usage.input_tokens": reply.input_tokens, "gen_ai.usage.output_tokens": reply.output_tokens}
            current.set(**{name: value for name, value in usage.items() if value is not None})
            current.set(**{"csa.tool_calls": len(reply.tool_calls)})
            return reply

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        # Streaming is traced with #6; a span cannot safely stay open across a generator's yields here.
        return self.inner.stream(messages)


def traced(model: Any, model_name: str) -> Any:
    """`model` with its calls traced. A chat-only model stays chat-only, so callers can still tell."""
    return TracedModel(model, model_name) if hasattr(model, "complete") else _TracedChat(model, model_name)
