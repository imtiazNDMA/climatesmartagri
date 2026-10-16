"""Tools an agent may call: checked arguments in, a result for the model and the facts behind it out."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ..facts import Fact, FactsError
from .model import Tool, ToolCall

logger = logging.getLogger("uvicorn.error")


class ToolArguments(BaseModel):
    """Base for a tool's arguments. Models often send ids as numbers; they are taken as the strings they stand for."""

    model_config = ConfigDict(coerce_numbers_to_str=True)


@dataclass(frozen=True)
class ToolOutput:
    """What a tool hands back to the model (`result`) and the facts that result holds, for grounding."""

    result: dict[str, Any]
    facts: list[Fact] = field(default_factory=list)


@dataclass(frozen=True)
class _Entry:
    tool: Tool
    arguments: type[ToolArguments]
    run: Callable[[Any], ToolOutput]


class ToolRegistry:
    """Tools in the order they were registered.

    A tool's JSON schema comes from its argument model, and the model's arguments are checked against it before the
    tool runs. Bad arguments, unknown tools, facts the portal does not hold and tools that break all come back as
    `{"error": ...}` results the model can read and act on; `run` never raises.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def register(
        self, name: str, description: str, arguments: type[ToolArguments], run: Callable[[Any], ToolOutput]
    ) -> None:
        if name in self._entries:
            raise ValueError(f"Tool '{name}' is already registered")
        self._entries[name] = _Entry(Tool(name, description, _schema(arguments)), arguments, run)

    @property
    def tools(self) -> list[Tool]:
        return [entry.tool for entry in self._entries.values()]

    def run(self, call: ToolCall) -> ToolOutput:
        entry = self._entries.get(call.name)
        if entry is None:
            return ToolOutput({"error": f"Unknown tool '{call.name}'"})
        try:
            arguments = entry.arguments.model_validate(call.arguments)
        except ValidationError:
            return ToolOutput({"error": f"Invalid arguments for {call.name}"})
        try:
            return entry.run(arguments)
        except FactsError as error:
            return ToolOutput({"error": error.message})
        except Exception:
            # A bug, not a question the portal cannot answer: keep the conversation going, keep the traceback.
            logger.exception("Tool %s failed", call.name)
            return ToolOutput({"error": "The tool failed"})


def _schema(arguments: type[ToolArguments]) -> dict[str, Any]:
    """The argument model's JSON schema without pydantic's titles, which only cost the model tokens."""
    return _without_titles(arguments.model_json_schema())


def _without_titles(node: Any) -> Any:
    if isinstance(node, dict):
        # A string "title" is pydantic's label; a dict under "title" is an argument of that name and stays.
        return {
            key: _without_titles(value) for key, value in node.items() if not (key == "title" and isinstance(value, str))
        }
    if isinstance(node, list):
        return [_without_titles(item) for item in node]
    return node
