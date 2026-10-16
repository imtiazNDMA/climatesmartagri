"""One agent loop for every AI feature: the model may call tools for a bounded number of rounds, then answers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..facts import Fact
from .model import ModelError
from .tools import ToolRegistry

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class AgentPolicy:
    # Times the model is asked. Tools are offered in all but the last, so by then it must answer.
    max_rounds: int = 4


@dataclass(frozen=True)
class AgentStep:
    """One tool call: what was asked, the error if it failed, and how many facts it returned."""

    tool: str
    arguments: dict[str, Any]
    error: str | None
    facts: int


@dataclass(frozen=True)
class AgentResult:
    answer: str
    facts: list[Fact] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)


class Agent:
    """A system prompt, the tools it may use, the model it runs on and how long it may take.

    One agent serves every request: `run` keeps everything about a conversation in local variables.
    """

    def __init__(
        self, name: str, system_prompt: str, registry: ToolRegistry, model: Any, policy: AgentPolicy = AgentPolicy()
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.registry = registry
        self.model = model
        self.policy = policy

    def run(self, messages: list[dict[str, Any]]) -> AgentResult:
        """Answer the conversation in `messages`; the system prompt is added here and `messages` is left as it was."""
        conversation: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}, *messages]
        if not hasattr(self.model, "complete"):
            # A model that can only chat answers without tools.
            return AgentResult(self.model.chat(conversation))
        facts: list[Fact] = []
        steps: list[AgentStep] = []
        last = self.policy.max_rounds - 1
        for round_number in range(self.policy.max_rounds):
            reply = self.model.complete(conversation, tools=self.registry.tools if round_number < last else None)
            if reply.text:
                return AgentResult(reply.text, facts, steps)
            if not reply.tool_calls:
                raise ModelError(502, "bad-model-response", "The AI model returned neither an answer nor a tool call")
            if round_number == last:
                break
            conversation.append({
                "role": "assistant", "content": "", "tool_calls": [
                    {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}
                    for call in reply.tool_calls
                ],
            })
            for call in reply.tool_calls:
                output = self.registry.run(call)
                facts.extend(output.facts)
                steps.append(AgentStep(call.name, dict(call.arguments), output.result.get("error"), len(output.facts)))
                logger.info(
                    "%s fact tool %s argument_names=%s returned=%d facts",
                    self.name.capitalize(), call.name, sorted(call.arguments), len(output.facts),
                )
                conversation.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(output.result, ensure_ascii=True)}
                )
        raise ModelError(502, "tool-limit", f"The AI model did not answer within {self.policy.max_rounds} tool rounds")
