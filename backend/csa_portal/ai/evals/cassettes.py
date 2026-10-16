"""Cassettes: a case's model turns recorded in a live run and replayed in recorded runs.

Replaying the model's own turns, tool calls included, means a recorded run executes the real tools, the real agent
loop and the real scorers; only the model is played back. That is what the CI gate runs, since CI has no model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..model import Completion, ModelError, ToolCall
from .datasets import DATASETS_DIR

CASSETTES_DIR = DATASETS_DIR / "cassettes"


def cassette_path(dataset: str, case_id: str, directory: Path = CASSETTES_DIR) -> Path:
    return directory / dataset / f"{case_id}.json"


def save_cassette(path: Path, turns: list[Completion]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        {
            "text": turn.text,
            "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in turn.tool_calls],
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
        }
        for turn in turns
    ]
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def load_cassette(path: Path) -> list[Completion]:
    return [
        Completion(
            text=turn["text"],
            tool_calls=[ToolCall(c["id"], c["name"], c["arguments"]) for c in turn["tool_calls"]],
            input_tokens=turn["input_tokens"],
            output_tokens=turn["output_tokens"],
        )
        for turn in json.loads(path.read_text(encoding="utf-8"))
    ]


class RecordingModel:
    """Passes every call to the real model and keeps each reply, so a live run can be saved as cassettes."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.turns: list[Completion] = []

    def start(self) -> None:
        self.turns = []

    def complete(self, messages: list[dict[str, Any]], tools: Any = None, output: Any = None) -> Completion:
        reply = (
            self.inner.complete(messages, tools=tools)
            if output is None
            else self.inner.complete(messages, tools=tools, output=output)
        )
        self.turns.append(reply)
        return reply

    def chat(self, messages: list[dict[str, Any]]) -> str:
        return self.inner.chat(messages)


class CassetteModel:
    """Plays one case's recorded turns back, in order."""

    def __init__(self) -> None:
        self._turns: list[Completion] | None = None

    def load(self, turns: list[Completion] | None) -> None:
        self._turns = None if turns is None else list(turns)

    def complete(self, messages: list[dict[str, Any]], tools: Any = None, output: Any = None) -> Completion:
        if self._turns is None:
            raise ModelError(502, "no-cassette", "This case has no recorded cassette; record it with a live run")
        if not self._turns:
            raise ModelError(502, "cassette-exhausted", "The case asked the model more often than was recorded")
        return self._turns.pop(0)

    def chat(self, messages: list[dict[str, Any]]) -> str:
        text = self.complete(messages).text
        if not text:
            raise ModelError(502, "bad-model-response", "The recorded turn has no text")
        return text
