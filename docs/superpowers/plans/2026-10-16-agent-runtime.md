# Agent Runtime Implementation Plan (#28)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the assistant's built-in tool loop into a reusable `ToolRegistry` and `Agent` in a new `csa_portal/ai/` package, with no change in behaviour.

**Architecture:** The language model seam moves to `ai/model.py`. `ai/tools.py` holds a registry whose tools take one pydantic argument model each; it makes the JSON schema, checks arguments, and turns failures into `{"error": ...}` results. `ai/agent.py` holds the bounded tool loop that is in `AssistantService._tool_answer` today. The assistant moves to `ai/agents/assistant.py` and is rebuilt on both. The old module paths stay as re-exports for one release.

**Tech Stack:** Python 3.13, FastAPI, pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-16-ai-platform-core-design.md` (Architecture: Tool registry, Agent loop; Rollout step 1)

## Global Constraints

- Pure refactor: `POST /api/assistant/chat` responses, status codes and reason codes (`bad-model-response`, `tool-limit`, `assistant-busy`, `bad-view`) do not change.
- Existing tests in `backend/tests/test_assistant.py` and `backend/tests/test_language_model.py` pass **without edits**.
- The recorded evaluation (`uv run python backend/scripts/evaluate_assistant.py --mode recorded`) gives the same pass/fail per case before and after.
- `csa_portal/language_model.py` and `csa_portal/assistant.py` re-export their public names for one release.
- Tools are offered in the order `find_place`, `get_section_facts`, `get_district_risk`, `get_crop_calendar`.
- At most 4 rounds (`AgentPolicy.max_rounds = 4`); no tools offered in the last round.
- Tool calls are logged to the `uvicorn.error` logger with argument **names** only, in a line containing `Assistant fact tool`.
- No new dependencies. Run Python through `uv run`. On this machine, scripts that import `rasterio` need `use_bundled_proj()` first (the scripts already do this).

## Review Focus

1. **The model sends a number where a string is expected** (e.g. `place_id: 101`). Today's code applied `str()` to these and carried on. Expect the same: argument models coerce numbers to strings. Test in Task 2.
2. **A tool fails with an unexpected exception** (a bug, not a `FactsError`). Expect the conversation to continue: the model gets `{"error": "The tool failed"}`, and the exception is logged with its traceback. Test in Task 2.
3. **The model replies with both text and tool calls.** Expect the text to be the answer and the tools not to run, as today. Test in Task 3.
4. **Several tool calls in one reply.** Expect each to run in order, each to be its own step, and each to get its own `tool` message. Test in Task 3.
5. **One `Agent` serves every request.** Expect nothing to carry over from one run to the next (facts, steps, messages). Test in Task 3.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `backend/csa_portal/ai/__init__.py` | Package marker with a one-line docstring |
| `backend/csa_portal/ai/model.py` | The language model seam (moved unchanged from `language_model.py`) |
| `backend/csa_portal/language_model.py` | Re-export shim for one release |
| `backend/csa_portal/ai/tools.py` | `ToolArguments`, `ToolOutput`, `ToolRegistry` |
| `backend/csa_portal/ai/agent.py` | `AgentPolicy`, `AgentStep`, `AgentResult`, `Agent` |
| `backend/csa_portal/ai/agents/__init__.py` | Package marker |
| `backend/csa_portal/ai/agents/assistant.py` | The assistant: request models, prompt, `assistant_tools(facts)`, `AssistantService`, routes |
| `backend/csa_portal/assistant.py` | Re-export shim for one release |
| `backend/tests/test_ai_model.py` | The old seam path is the same objects |
| `backend/tests/test_tools.py` | Registry tests |
| `backend/tests/test_agent.py` | Agent loop tests |

---

### Task 0: Branch and the before-picture

**Files:** none changed.

- [ ] **Step 1: Branch from the merged base**

PR #34 (#7) and PR #26 (spec and this plan) must be merged first.

```bash
git fetch origin
git switch -c feat/28-agent-runtime origin/feat/portal-data
```

- [ ] **Step 2: Record the recorded-evaluation result before any change**

The output prints a latency per case; strip it so the before and after files can be compared.

```bash
uv run python backend/scripts/evaluate_assistant.py --mode recorded | sed -E 's/ \([0-9.]+s\)$//' > ../eval-before.txt || true
tail -1 ../eval-before.txt
```

Expected: the last line reads `Passed N/44` for some N. Keep the file outside the repo.

- [ ] **Step 3: Confirm the suite is green before starting**

Run: `uv run pytest -q`
Expected: all pass (300 at the time of writing).

---

### Task 1: Move the language model seam into `ai/model.py`

**Files:**
- Create: `backend/csa_portal/ai/__init__.py`
- Move: `backend/csa_portal/language_model.py` → `backend/csa_portal/ai/model.py`
- Create: `backend/csa_portal/language_model.py` (shim)
- Test: `backend/tests/test_ai_model.py`

**Interfaces:**
- Produces: `csa_portal.ai.model` with `Completion`, `LanguageModel`, `LmStudioModel`, `ModelError`, `ScriptedModel`, `Shape`, `Tool`, `ToolCall`, all unchanged.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_ai_model.py`:

```python
"""The language model seam lives in csa_portal.ai.model; the old path hands out the same objects for one release."""


def test_the_old_seam_path_is_the_same_seam():
    from csa_portal import language_model
    from csa_portal.ai import model

    for name in ("Completion", "LanguageModel", "LmStudioModel", "ModelError", "ScriptedModel", "Tool", "ToolCall"):
        assert getattr(language_model, name) is getattr(model, name), name
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest backend/tests/test_ai_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'model' from 'csa_portal.ai'` (or `ModuleNotFoundError: No module named 'csa_portal.ai'`).

- [ ] **Step 3: Move the module and add the shim**

```bash
mkdir -p backend/csa_portal/ai
git mv backend/csa_portal/language_model.py backend/csa_portal/ai/model.py
```

`backend/csa_portal/ai/__init__.py`:

```python
"""The AI platform: the language model seam, tools, the agent loop, and the agents built on them."""
```

`backend/csa_portal/language_model.py`:

```python
"""Kept for one release: the language model seam now lives in csa_portal.ai.model."""

from .ai.model import Completion, LanguageModel, LmStudioModel, ModelError, ScriptedModel, Shape, Tool, ToolCall

__all__ = ["Completion", "LanguageModel", "LmStudioModel", "ModelError", "ScriptedModel", "Shape", "Tool", "ToolCall"]
```

`ai/model.py` has no relative imports, so it needs no edits.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q backend/tests/test_ai_model.py backend/tests/test_language_model.py backend/tests/test_assistant.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/ai backend/csa_portal/language_model.py backend/tests/test_ai_model.py
git commit -m "refactor: move the language model seam into csa_portal.ai.model (#28)"
```

---

### Task 2: Tool registry

**Files:**
- Create: `backend/csa_portal/ai/tools.py`
- Test: `backend/tests/test_tools.py`

**Interfaces:**
- Consumes: `Tool(name, description, parameters)` and `ToolCall(id, name, arguments)` from `csa_portal.ai.model`; `Fact` and `FactsError` (with `.message`) from `csa_portal.facts`.
- Produces:
  - `class ToolArguments(BaseModel)`: base for every tool's argument model; coerces numbers to strings.
  - `@dataclass(frozen=True) class ToolOutput: result: dict[str, Any]; facts: list[Fact] = []`
  - `class ToolRegistry` with `register(name: str, description: str, arguments: type[ToolArguments], run: Callable[[Any], ToolOutput]) -> None`, `tools -> list[Tool]` (property, in registration order), and `run(call: ToolCall) -> ToolOutput` (never raises).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_tools.py`:

```python
import logging

import pytest

from csa_portal.ai.model import ToolCall
from csa_portal.ai.tools import ToolArguments, ToolOutput, ToolRegistry
from csa_portal.facts import Fact, FactsError


class LookupArgs(ToolArguments):
    place_id: str
    year: int | None = None


class TitledArgs(ToolArguments):
    title: str


def lookup(args: LookupArgs) -> ToolOutput:
    fact = Fact("Example", 175, "units", args.place_id, str(args.year) if args.year else None, "Alpha / Pakistan")
    return ToolOutput({"place_id": args.place_id, "year": args.year}, [fact])


def registry_with(*entries) -> ToolRegistry:
    registry = ToolRegistry()
    for name, arguments, run in entries:
        registry.register(name, f"{name} description", arguments, run)
    return registry


def test_tools_are_listed_in_registration_order_with_schemas_from_their_argument_models():
    registry = registry_with(("lookup", LookupArgs, lookup), ("titled", TitledArgs, lambda args: ToolOutput({})))

    lookup_tool, titled_tool = registry.tools

    assert (lookup_tool.name, lookup_tool.description) == ("lookup", "lookup description")
    assert lookup_tool.parameters == {
        "type": "object",
        "properties": {
            "place_id": {"type": "string"},
            "year": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
        },
        "required": ["place_id"],
    }
    # Pydantic's schema titles are dropped, but an argument that is itself called "title" is kept.
    assert titled_tool.parameters["properties"] == {"title": {"type": "string"}}


def test_a_tool_runs_with_its_checked_arguments_and_returns_its_facts():
    output = registry_with(("lookup", LookupArgs, lookup)).run(ToolCall("1", "lookup", {"place_id": "PK101", "year": 2005}))

    assert output.result == {"place_id": "PK101", "year": 2005}
    assert [fact.value for fact in output.facts] == [175]


def test_numbers_sent_for_string_arguments_are_taken_as_strings():
    output = registry_with(("lookup", LookupArgs, lookup)).run(ToolCall("1", "lookup", {"place_id": 101}))

    assert output.result == {"place_id": "101", "year": None}


def test_bad_arguments_unknown_tools_and_missing_facts_come_back_as_errors_for_the_model():
    def no_data(args: LookupArgs) -> ToolOutput:
        raise FactsError("no-data", "Alpha has no figures yet")

    registry = registry_with(("lookup", LookupArgs, lookup), ("empty", LookupArgs, no_data))

    assert registry.run(ToolCall("1", "lookup", {})).result == {"error": "Invalid arguments for lookup"}
    assert registry.run(ToolCall("2", "lookup", {"place_id": "PK", "year": "soon"})).result == {
        "error": "Invalid arguments for lookup"
    }
    assert registry.run(ToolCall("3", "nowhere", {})).result == {"error": "Unknown tool 'nowhere'"}
    assert registry.run(ToolCall("4", "empty", {"place_id": "PK"})) == ToolOutput({"error": "Alpha has no figures yet"})


def test_a_tool_that_breaks_tells_the_model_and_logs_the_traceback(caplog):
    def broken(args: LookupArgs) -> ToolOutput:
        raise KeyError("figures")

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        output = registry_with(("broken", LookupArgs, broken)).run(ToolCall("1", "broken", {"place_id": "PK"}))

    assert output == ToolOutput({"error": "The tool failed"})
    record = next(record for record in caplog.records if "broken" in record.getMessage())
    assert record.exc_info is not None


def test_a_name_can_only_be_registered_once():
    registry = registry_with(("lookup", LookupArgs, lookup))

    with pytest.raises(ValueError, match="already registered"):
        registry.register("lookup", "again", LookupArgs, lookup)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.ai.tools'`.

- [ ] **Step 3: Write the registry**

`backend/csa_portal/ai/tools.py`:

```python
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
        return {key: _without_titles(value) for key, value in node.items() if not (key == "title" and isinstance(value, str))}
    if isinstance(node, list):
        return [_without_titles(item) for item in node]
    return node
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/test_tools.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/ai/tools.py backend/tests/test_tools.py
git commit -m "feat: tool registry with checked arguments and errors returned to the model (#28)"
```

---

### Task 3: Agent loop

**Files:**
- Create: `backend/csa_portal/ai/agent.py`
- Test: `backend/tests/test_agent.py`

**Interfaces:**
- Consumes: `ToolRegistry.tools`, `ToolRegistry.run(call) -> ToolOutput` (Task 2); `Completion`, `ModelError`, `ScriptedModel`, `ToolCall` from `csa_portal.ai.model`.
- Produces:
  - `@dataclass(frozen=True) class AgentPolicy: max_rounds: int = 4`
  - `@dataclass(frozen=True) class AgentStep: tool: str; arguments: dict[str, Any]; error: str | None; facts: int`
  - `@dataclass(frozen=True) class AgentResult: answer: str; facts: list[Fact] = []; steps: list[AgentStep] = []`
  - `class Agent(name: str, system_prompt: str, registry: ToolRegistry, model: Any, policy: AgentPolicy = AgentPolicy())` with attribute `registry` and `run(messages: list[dict[str, Any]]) -> AgentResult`. `run` adds the system prompt itself and does not change the list it is given. It raises `ModelError(502, "bad-model-response", ...)` when a reply has neither text nor tool calls, and `ModelError(502, "tool-limit", ...)` when no answer comes within `max_rounds`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent.py`:

```python
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
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `uv run pytest backend/tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.ai.agent'`.

- [ ] **Step 3: Write the agent**

`backend/csa_portal/ai/agent.py`:

```python
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
                conversation.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(output.result, ensure_ascii=True)})
        raise ModelError(502, "tool-limit", f"The AI model did not answer within {self.policy.max_rounds} tool rounds")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/test_agent.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/csa_portal/ai/agent.py backend/tests/test_agent.py
git commit -m "feat: reusable agent loop with bounded tool rounds (#28)"
```

---

### Task 4: Move the assistant onto the registry and the agent

**Files:**
- Move: `backend/csa_portal/assistant.py` → `backend/csa_portal/ai/agents/assistant.py`
- Create: `backend/csa_portal/ai/agents/__init__.py`
- Create: `backend/csa_portal/assistant.py` (shim)
- Modify: `backend/csa_portal/main.py:25,28` (imports)
- Modify: `backend/scripts/evaluate_assistant.py:17,24,25` (imports)
- Test: `backend/tests/test_assistant.py` (unchanged; it must pass as it is), plus one new test in `backend/tests/test_agent.py`

**Interfaces:**
- Consumes: `ToolArguments`, `ToolOutput`, `ToolRegistry` (Task 2); `Agent`, `AgentPolicy` (Task 3); `Facts.find_place(name)`, `Facts.section(section_id, place_id, year)`, `Facts.district_risk(hazard, model, time, run, level)` from `csa_portal.facts`.
- Produces: `assistant_tools(facts: Facts) -> ToolRegistry` and, unchanged, `AssistantService`, `AssistantChatRequest`, `AssistantView`, `AssistantClient`, `AssistantError`, `LmStudioClient`, `MAX_TOOL_ROUNDS`, `add_assistant_routes`, all importable from both `csa_portal.ai.agents.assistant` and `csa_portal.assistant`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_agent.py`:

```python
def test_the_assistant_offers_its_four_fact_tools_in_order_with_checked_arguments():
    from csa_portal.ai.agents.assistant import assistant_tools

    class NoFacts:
        def find_place(self, name):
            return []

    registry = assistant_tools(NoFacts())

    assert [tool.name for tool in registry.tools] == [
        "find_place", "get_section_facts", "get_district_risk", "get_crop_calendar",
    ]
    section = next(tool for tool in registry.tools if tool.name == "get_section_facts")
    assert section.parameters["required"] == ["section_id", "place_id"]
    risk = next(tool for tool in registry.tools if tool.name == "get_district_risk")
    assert risk.parameters["required"] == ["hazard", "model", "time", "run"]
    assert registry.run(ToolCall("1", "find_place", {"name": "Lahore"})).result == {"places": []}
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest backend/tests/test_agent.py -k four_fact_tools -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'csa_portal.ai.agents'`.

- [ ] **Step 3: Move the module and fix its imports**

```bash
mkdir -p backend/csa_portal/ai/agents
git mv backend/csa_portal/assistant.py backend/csa_portal/ai/agents/assistant.py
```

`backend/csa_portal/ai/agents/__init__.py`:

```python
"""Agents built on the AI platform: each is a prompt, a tool registry and a policy on the shared agent loop."""
```

In `backend/csa_portal/ai/agents/assistant.py`, replace the import block (from `from .catalogue import Catalogue` down to `from .places import COUNTRY_ID, PlaceIndex`) with:

```python
from ...catalogue import Catalogue
from ...evaluation import score_grounding
from ...facts import Fact, Facts, SectionFacts
from ...places import COUNTRY_ID, PlaceIndex
from ..agent import Agent, AgentPolicy
from ..model import Completion, LmStudioModel, ModelError, Tool
from ..tools import ToolArguments, ToolOutput, ToolRegistry
```

Also remove `import logging` and the module's `logger = logging.getLogger("uvicorn.error")` line (logging now happens in the agent), and keep `import json` and `import threading`. `FactsError` is still used by `_view_facts` and `_context`, so import it too: `from ...facts import Fact, Facts, FactsError, SectionFacts`.

- [ ] **Step 4: Replace `TOOLS` and `MAX_TOOL_ROUNDS` with the registry**

Delete the `MAX_TOOL_ROUNDS = 4` line and the whole `TOOLS = [...]` list. Put this after `SYSTEM_PROMPT`:

```python
# Kept for callers and tests that read the limit from here.
MAX_TOOL_ROUNDS = AgentPolicy().max_rounds


class FindPlaceArgs(ToolArguments):
    name: str


class SectionFactsArgs(ToolArguments):
    section_id: str
    place_id: str
    year: int | None = None


class DistrictRiskArgs(ToolArguments):
    hazard: str
    model: str
    time: str
    run: str
    level: int = 0


class CropCalendarArgs(ToolArguments):
    place_id: str


def assistant_tools(facts: Facts) -> ToolRegistry:
    """The assistant's fact tools, in the order the model sees them."""

    def find_place(args: FindPlaceArgs) -> ToolOutput:
        return ToolOutput({"places": [place.as_dict() for place in facts.find_place(args.name)[:20]]})

    def section_facts(args: SectionFactsArgs) -> ToolOutput:
        answer = facts.section(args.section_id, args.place_id, args.year)
        return ToolOutput(_section_tool_result(answer), answer.facts)

    def district_risk(args: DistrictRiskArgs) -> ToolOutput:
        answer = facts.district_risk(args.hazard, args.model, args.time, args.run, args.level)
        return ToolOutput({
            "hazard": answer.title, "time": answer.time, "run": answer.run,
            "disclaimer": answer.disclaimer, "statistic": answer.statistic,
            "facts": [_fact_json(fact, answer.risk.get(fact.place)) for fact in answer.facts],
        }, answer.facts)

    def crop_calendar(args: CropCalendarArgs) -> ToolOutput:
        answer = facts.section("climate-calendar", args.place_id)
        return ToolOutput(_section_tool_result(answer), answer.facts)

    registry = ToolRegistry()
    registry.register("find_place", "Find portal places by name before asking for their facts.", FindPlaceArgs, find_place)
    registry.register(
        "get_section_facts", "Get every portal fact for one section, place id and optional year.",
        SectionFactsArgs, section_facts,
    )
    registry.register(
        "get_district_risk", "Get district risk facts for one hazard, model, valid time and run.",
        DistrictRiskArgs, district_risk,
    )
    registry.register("get_crop_calendar", "Get crop-calendar facts for a place id.", CropCalendarArgs, crop_calendar)
    return registry
```

The `AssistantClient` protocol keeps its `complete(messages, tools: list[Tool] | None = None) -> Completion` method, which is why `Completion` and `Tool` are still imported.

- [ ] **Step 5: Run the assistant through the agent**

In `AssistantService.__init__`, after `self.local_model = local_model`, add:

```python
        self._agent = Agent("assistant", SYSTEM_PROMPT, assistant_tools(facts), client)
```

In `AssistantService.answer`, change how the messages start and how the answer is made. Replace

```python
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
```

with

```python
        messages: list[dict[str, Any]] = []
```

and replace

```python
        try:
            answer, tool_facts, tool_calls = self._tool_answer(messages)
        finally:
            self._generation_lock.release()
        used_facts = [*context_facts, *tool_facts]
```

with

```python
        try:
            result = self._agent.run(messages)
        finally:
            self._generation_lock.release()
        answer = result.answer
        tool_calls = len(result.steps)
        used_facts = [*context_facts, *result.facts]
```

Delete the `_tool_answer` method entirely. Replace the `_run_tool` method with:

```python
    def _run_tool(self, call: ToolCall) -> tuple[dict[str, Any], list[Fact]]:
        """Run one fact tool by hand; the agent loop does this for the model."""
        output = self._agent.registry.run(call)
        return output.result, output.facts
```

and add `ToolCall` to the `..model` import: `from ..model import Completion, LmStudioModel, ModelError, Tool, ToolCall`.

- [ ] **Step 6: Add the shim and point internal imports at the new path**

`backend/csa_portal/assistant.py`:

```python
"""Kept for one release: the assistant now lives in csa_portal.ai.agents.assistant."""

from .ai.agents.assistant import (
    MAX_TOOL_ROUNDS,
    AssistantChatRequest,
    AssistantClient,
    AssistantError,
    AssistantService,
    AssistantView,
    LmStudioClient,
    add_assistant_routes,
)

__all__ = [
    "MAX_TOOL_ROUNDS", "AssistantChatRequest", "AssistantClient", "AssistantError", "AssistantService",
    "AssistantView", "LmStudioClient", "add_assistant_routes",
]
```

In `backend/csa_portal/main.py`, change

```python
from .assistant import AssistantClient, AssistantService, add_assistant_routes  # noqa: E402
```
to
```python
from .ai.agents.assistant import AssistantClient, AssistantService, add_assistant_routes  # noqa: E402
```
and
```python
from .language_model import LmStudioModel  # noqa: E402
```
to
```python
from .ai.model import LmStudioModel  # noqa: E402
```

In `backend/scripts/evaluate_assistant.py`, change the three imports to:

```python
from csa_portal.ai.agents.assistant import AssistantChatRequest, AssistantService, AssistantView  # noqa: E402
from csa_portal.ai.model import Completion, LmStudioModel, ModelError, ScriptedModel  # noqa: E402
```

(the two `csa_portal.language_model` lines become the one `csa_portal.ai.model` line).

- [ ] **Step 7: Run every backend test**

Run: `uv run pytest -q`
Expected: all PASS, including every test in `backend/tests/test_assistant.py` with no edits to that file. If `test_assistant_uses_fact_tools_and_returns_only_the_fact_sources` fails on the schema of `get_section_facts`, check that `year` is optional (`int | None = None`), not required.

- [ ] **Step 8: Check the recorded evaluation did not change**

```bash
uv run python backend/scripts/evaluate_assistant.py --mode recorded | sed -E 's/ \([0-9.]+s\)$//' > ../eval-after.txt || true
diff ../eval-before.txt ../eval-after.txt && echo "recorded evaluation unchanged"
```

Expected: `recorded evaluation unchanged`. Any difference means behaviour changed; find it before going on.

- [ ] **Step 9: Run the full check and the browser tests**

Run: `npm run check` then `npm run test:e2e`
Expected: lint clean, all backend, frontend and browser tests pass.

- [ ] **Step 10: Commit**

```bash
git add backend/csa_portal backend/scripts/evaluate_assistant.py backend/tests/test_agent.py
git commit -m "refactor: the assistant runs on the tool registry and agent loop (#28)"
```

---

### Task 5: Pull request

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin feat/28-agent-runtime
gh pr create --base feat/portal-data --title "refactor: agent runtime — tool registry and reusable agent loop" --body "Closes #28

- \`csa_portal/ai/\`: the language model seam (\`model.py\`), \`ToolRegistry\` (\`tools.py\`) and \`Agent\` (\`agent.py\`).
- The assistant moved to \`ai/agents/assistant.py\` and runs on them; the if/elif tool dispatch is gone.
- \`language_model.py\` and \`assistant.py\` re-export for one release.
- No behaviour change: existing assistant tests unchanged and passing; recorded evaluation identical before and after.
- Two deliberate differences, both for bad input: numbers sent for string arguments are taken as strings (as before, now by the argument model), and a tool that breaks returns \`{\"error\": \"The tool failed\"}\` to the model with the traceback logged, where before only KeyError, TypeError and ValueError were caught.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 2: Wait for CI**

Run: `gh pr checks --watch`
Expected: `quality` and `e2e` pass.
