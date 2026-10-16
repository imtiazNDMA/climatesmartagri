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
