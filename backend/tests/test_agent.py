import json
import logging

import pytest

from csa_portal.ai.agent import Agent, AgentPolicy, AgentStep
from csa_portal.ai.model import Completion, ModelError, ScriptedModel, ToolCall
from csa_portal.ai.tools import ToolArguments, ToolOutput, ToolRegistry
from csa_portal.facts import Fact


class LookupArgs(ToolArguments):
    place_id: str


def lookup(args: LookupArgs) -> ToolOutput:
    if args.place_id == "nowhere":
        return ToolOutput({"error": "Unknown place 'nowhere'"})
    return ToolOutput({"place_id": args.place_id}, [Fact("Example", 175, "units", args.place_id, None, "Alpha")])


def agent_for(model: ScriptedModel, policy: AgentPolicy = AgentPolicy()) -> Agent:
    registry = ToolRegistry()
    registry.register("lookup", "Look a place up.", LookupArgs, lookup)
    return Agent("assistant", "You are a test guide.", registry, model, policy)


QUESTION = [{"role": "user", "content": "What is the value?"}]


def test_an_answer_without_tools_comes_back_with_no_steps_and_the_system_prompt_first():
    model = ScriptedModel([Completion(text="It is 175.")])

    result = agent_for(model).run(QUESTION)

    assert (result.answer, result.facts, result.steps) == ("It is 175.", [], [])
    assert model.sent[0] == [{"role": "system", "content": "You are a test guide."}, *QUESTION]
    assert [tool.name for tool in model.tools[0]] == ["lookup"]


def test_tool_results_go_back_to_the_model_and_their_facts_and_steps_are_kept():
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {"place_id": "PK101"})]),
        Completion(text="District One has 175."),
    ])
    asked = list(QUESTION)

    result = agent_for(model).run(asked)

    assert result.answer == "District One has 175."
    assert [fact.value for fact in result.facts] == [175]
    assert result.steps == [AgentStep("lookup", {"place_id": "PK101"}, None, 1)]
    second = model.sent[1]
    assert second[-2]["tool_calls"][0]["function"] == {"name": "lookup", "arguments": json.dumps({"place_id": "PK101"})}
    assert second[-1] == {"role": "tool", "tool_call_id": "a", "content": json.dumps({"place_id": "PK101"})}
    assert asked == QUESTION  # the caller's list is not changed


def test_several_tool_calls_in_one_reply_each_run_in_order():
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {"place_id": "PK101"}), ToolCall("b", "lookup", {"place_id": "nowhere"})]),
        Completion(text="Only District One is known."),
    ])

    result = agent_for(model).run(QUESTION)

    assert result.steps == [
        AgentStep("lookup", {"place_id": "PK101"}, None, 1),
        AgentStep("lookup", {"place_id": "nowhere"}, "Unknown place 'nowhere'", 0),
    ]
    assert [message["tool_call_id"] for message in model.sent[1] if message["role"] == "tool"] == ["a", "b"]


def test_text_wins_when_a_reply_has_both_text_and_tool_calls():
    model = ScriptedModel([Completion(text="It is 175.", tool_calls=[ToolCall("a", "lookup", {"place_id": "PK101"})])])

    result = agent_for(model).run(QUESTION)

    assert (result.answer, result.steps) == ("It is 175.", [])


def test_no_tools_are_offered_in_the_last_round_and_a_model_that_still_asks_hits_the_limit():
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {"place_id": "PK101"})]),
        Completion(tool_calls=[ToolCall("b", "lookup", {"place_id": "PK101"})]),
    ])

    with pytest.raises(ModelError) as raised:
        agent_for(model, AgentPolicy(max_rounds=2)).run(QUESTION)

    assert (raised.value.status, raised.value.reason) == (502, "tool-limit")
    assert model.tools[1] is None
    assert len(model.sent) == 2


def test_a_reply_with_neither_text_nor_tool_calls_is_a_bad_model_response():
    with pytest.raises(ModelError) as raised:
        agent_for(ScriptedModel([Completion()])).run(QUESTION)

    assert (raised.value.status, raised.value.reason) == (502, "bad-model-response")


def test_a_chat_only_model_answers_without_tools():
    class ChatOnly:
        def chat(self, messages):
            self.messages = messages
            return "Plain answer."

    model = ChatOnly()
    result = Agent("assistant", "You are a test guide.", ToolRegistry(), model).run(QUESTION)

    assert (result.answer, result.steps) == ("Plain answer.", [])
    assert model.messages[0]["role"] == "system"


def test_nothing_carries_over_from_one_run_to_the_next():
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {"place_id": "PK101"})]),
        Completion(text="District One has 175."),
        Completion(text="Nothing to look up."),
    ])
    agent = agent_for(model)

    agent.run(QUESTION)
    second = agent.run(QUESTION)

    assert (second.facts, second.steps) == ([], [])
    assert model.sent[2] == [{"role": "system", "content": "You are a test guide."}, *QUESTION]


def test_each_tool_call_is_logged_with_argument_names_only(caplog):
    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("a", "lookup", {"place_id": "private-text"})]),
        Completion(text="Done."),
    ])

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        agent_for(model).run(QUESTION)

    message = next(record.getMessage() for record in caplog.records if "fact tool" in record.getMessage())
    assert message.startswith("Assistant fact tool lookup")
    assert "place_id" in message
    assert "private-text" not in message
