"""One agent loop for every AI feature: the model may call tools for a bounded number of rounds, then answers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..facts import Fact
from .model import ModelError
from .tools import ToolRegistry
from .tracing import span

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
    # Totals over the run's model replies, or None when no reply reported any.
    input_tokens: int | None = None
    output_tokens: int | None = None


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
        attributes = {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": self.name}
        with span("agent", self.name, **attributes) as agent_span:
            result = self._run(messages)
            agent_span.set(**{"csa.tool_calls": len(result.steps)})
            return result

    def _run(self, messages: list[dict[str, Any]]) -> AgentResult:
        conversation: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}, *messages]
        if not hasattr(self.model, "complete"):
            # A model that can only chat answers without tools.
            return AgentResult(self.model.chat(conversation))
        facts: list[Fact] = []
        steps: list[AgentStep] = []
        replies: list[Any] = []
        last = self.policy.max_rounds - 1
        for round_number in range(self.policy.max_rounds):
            reply = self.model.complete(conversation, tools=self.registry.tools if round_number < last else None)
            replies.append(reply)
            if reply.text:
                return AgentResult(
                    reply.text, facts, steps,
                    _total(r.input_tokens for r in replies), _total(r.output_tokens for r in replies),
                )
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
                with span("tool", call.name, **{
                    "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": call.name,
                    "gen_ai.tool.call.id": call.id, "csa.tool.argument_names": ",".join(sorted(call.arguments)),
                }) as tool_span:
                    output = self.registry.run(call)
                    tool_span.set(**{"csa.facts": len(output.facts)})
                    if "error" in output.result:
                        tool_span.fail()
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


def _total(counts: Any) -> int | None:
    known = [count for count in counts if isinstance(count, int)]
    return sum(known) if known else None
