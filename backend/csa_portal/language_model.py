"""The one seam every AI feature reaches a language model through (ADR 0001).

Callers send messages and get back a plain answer, tool calls, an object of a given shape, or text pieces as
they are written. They never see HTTP or a provider's formats. The LM Studio adapter is the default; a hosted
model can be added as another adapter without touching callers.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from collections.abc import Iterator
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

Shape = TypeVar("Shape", bound=BaseModel)


class ModelError(Exception):
    """A model request failed. `reason` is a short code callers and the frontend act on."""

    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Tool:
    """Something the model may ask the caller to do, described by a JSON schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Completion:
    """What the model gave back: words, tool calls to run before it can answer, or an object of the asked shape."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    data: Any = None


class LanguageModel(Protocol):
    def chat(self, messages: list[dict[str, Any]]) -> str: ...

    def complete(
        self, messages: list[dict[str, Any]], tools: list[Tool] | None = None, output: type[BaseModel] | None = None
    ) -> Completion: ...

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[str]: ...


class LmStudioModel:
    """LM Studio's OpenAI-compatible chat completions endpoint."""

    def __init__(self, base_url: str, model: str, timeout: float = 60, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.api_key = api_key

    def chat(self, messages: list[dict[str, Any]]) -> str:
        text = self.complete(messages).text
        if not text:
            raise ModelError(502, "bad-model-response", "The local AI model returned an empty answer")
        return text

    def complete(
        self, messages: list[dict[str, Any]], tools: list[Tool] | None = None, output: type[BaseModel] | None = None
    ) -> Completion:
        """Words or tool calls; or, with `output`, an object of that shape in `data`. A reply that does not fit
        the shape is asked for once more, then given up as `bad-model-response`."""
        if output is not None:
            return Completion(data=self._shaped(messages, output))
        payload = self._payload(messages)
        if tools:
            payload["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
        message = self._message(self._post(payload))
        calls = [_tool_call(call) for call in message.get("tool_calls") or []]
        content = message.get("content")
        text = content.strip() if isinstance(content, str) and content.strip() else None
        return Completion(text=text, tool_calls=calls)

    def _shaped(self, messages: list[dict[str, Any]], output: type[Shape]) -> Shape:
        payload = self._payload(messages)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": output.__name__, "strict": True, "schema": output.model_json_schema()},
        }
        for _attempt in range(2):
            message = self._message(self._post(payload))
            # A thinking model's schema-bound reply can be filed as reasoning with the content left empty
            # (LM Studio with Qwen3); the reply is still the object asked for.
            content = message.get("content") or message.get("reasoning_content")
            try:
                return output.model_validate_json(content or "")
            except ValidationError:
                continue
        raise ModelError(502, "bad-model-response", f"The local AI model did not answer in the {output.__name__} shape")

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        """The answer in pieces as the model writes it. Closing the iterator lets the connection go, which stops
        the model writing. A stream that ends before the model says it is done raises `assistant-unavailable`."""
        payload = self._payload(messages)
        payload["stream"] = True
        response = self._open(payload)
        try:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    return
                try:
                    piece = json.loads(data)["choices"][0]["delta"].get("content")
                except (ValueError, KeyError, IndexError, TypeError, AttributeError) as err:
                    raise ModelError(502, "bad-model-response", "The local AI model sent a piece it cannot read") from err
                if piece:
                    yield piece
        except OSError as err:
            raise ModelError(503, "assistant-unavailable", "The local AI model stopped answering") from err
        finally:
            response.close()
        raise ModelError(503, "assistant-unavailable", "The local AI model stopped before finishing its answer")

    def _payload(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"model": self.model, "messages": messages, "temperature": 0.2, "max_tokens": 700, "stream": False}

    def _post(self, payload: dict[str, Any]) -> Any:
        response = self._open(payload)
        try:
            return json.loads(response.read())
        except (ValueError, TypeError) as err:
            raise ModelError(502, "bad-model-response", "The local AI model returned invalid JSON") from err
        except OSError as err:
            raise ModelError(503, "assistant-unavailable", "The local AI model stopped answering") from err
        finally:
            response.close()

    def _open(self, payload: dict[str, Any]) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as err:
            if err.code in {400, 401, 403, 404}:
                raise ModelError(
                    502, "assistant-misconfigured",
                    f"LM Studio rejected the configured model or credentials (HTTP {err.code})",
                ) from err
            raise ModelError(503, "assistant-unavailable", f"The AI model answered with HTTP {err.code}") from err
        except (OSError, TimeoutError) as err:
            raise ModelError(503, "assistant-unavailable", "The local AI model could not be reached") from err

    @staticmethod
    def _message(body: Any) -> dict[str, Any]:
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as err:
            raise ModelError(502, "bad-model-response", "The local AI model returned an unexpected response") from err
        if not isinstance(message, dict):
            raise ModelError(502, "bad-model-response", "The local AI model returned an unexpected response")
        return message


def _tool_call(call: Any) -> ToolCall:
    try:
        arguments = json.loads(call["function"]["arguments"] or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("arguments are not an object")
        return ToolCall(str(call["id"]), str(call["function"]["name"]), arguments)
    except (KeyError, TypeError, ValueError) as err:
        raise ModelError(502, "bad-model-response", "The local AI model asked for a tool in a form it cannot use") from err


class ScriptedModel:
    """A model that plays back scripted turns in order, for tests and recorded evaluations.

    Each turn is a `Completion` (for `chat` and `complete`) or a list of text pieces (for `stream`). It keeps the
    messages and tools it was sent, and fails loudly when a caller asks for more turns than were scripted.
    """

    def __init__(self, turns: list[Completion | list[str]]) -> None:
        self.turns = list(turns)
        self.sent: list[list[dict[str, Any]]] = []
        self.tools: list[list[Tool] | None] = []

    def chat(self, messages: list[dict[str, Any]]) -> str:
        text = self.complete(messages).text
        if not text:
            raise ModelError(502, "bad-model-response", "The scripted turn has no text")
        return text

    def complete(
        self, messages: list[dict[str, Any]], tools: list[Tool] | None = None, output: type[BaseModel] | None = None
    ) -> Completion:
        turn = self._next(messages, tools)
        assert isinstance(turn, Completion), "the next scripted turn is a stream, not a completion"
        return turn

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        turn = self._next(messages, None)
        assert isinstance(turn, list), "the next scripted turn is a completion, not a stream"
        yield from turn

    def _next(self, messages: list[dict[str, Any]], tools: list[Tool] | None) -> Completion | list[str]:
        assert self.turns, "the model was asked for more than it has: no more scripted turns"
        self.sent.append(list(messages))
        self.tools.append(tools)
        return self.turns.pop(0)
