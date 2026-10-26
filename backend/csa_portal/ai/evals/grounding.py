"""What an answer may quote: every number the agent was shown, in its view's context or by the tools the case
expects it to call. The conversation history and the question are left out on purpose: a number a reader typed
is not a fact, which is exactly what the injection cases check."""

from __future__ import annotations

from typing import Any

from ...evaluation import answer_numbers
from ..agents.assistant import AssistantService, AssistantView
from ..model import ToolCall
from .datasets import EvalCase


def shown_numbers(service: AssistantService, case: EvalCase) -> list[float]:
    view = AssistantView(**case.view.model_dump())
    context, facts = service.view_context(view)
    numbers = set(_numbers(context))
    for fact in facts:
        if isinstance(fact.value, int | float) and not isinstance(fact.value, bool):
            numbers.add(float(fact.value))
        if fact.when and fact.when.isdigit():
            numbers.add(float(fact.when))
    for tool in case.expected_tools:
        numbers.update(_numbers(service.tools.run(ToolCall("expected", tool.name, tool.arguments)).result))
    return sorted(round(number, 6) for number in numbers)


def _numbers(node: Any) -> list[float]:
    if isinstance(node, bool) or node is None:
        return []
    if isinstance(node, int | float):
        return [float(node)]
    if isinstance(node, str):
        return list(answer_numbers(node))
    if isinstance(node, dict):
        return [number for value in node.values() for number in _numbers(value)]
    if isinstance(node, list | tuple):
        return [number for item in node for number in _numbers(item)]
    return []
