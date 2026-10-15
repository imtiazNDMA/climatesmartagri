"""The language model seam: plain answers, tool calls, structured output and streaming, behind one interface."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import BaseModel

from csa_portal.language_model import LmStudioModel, ModelError, Tool


class FakeLmStudio:
    """A stand-in for LM Studio's OpenAI-compatible server: answers each request with the next scripted reply
    and keeps every request body it was sent."""

    def __init__(self):
        self.replies = []
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                fake.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                status, body, content_type = fake.replies.pop(0)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def stream(self, pieces, finish=True):
        events = [{"choices": [{"delta": {"content": piece}}]} for piece in pieces]
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        if finish:
            body += "data: [DONE]\n\n"
        self.replies.append((200, body.encode(), "text/event-stream"))

    def reply(self, message, status=200):
        body = json.dumps({"choices": [{"message": message}]}).encode()
        self.replies.append((status, body, "application/json"))


@pytest.fixture
def lm():
    fake = FakeLmStudio()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


FIND_PLACE = Tool(
    "find_place",
    "Find a place in Pakistan by name.",
    {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)


def test_the_model_can_ask_for_a_tool_and_is_offered_the_tools_it_may_use(lm):
    lm.reply({"content": None, "tool_calls": [
        {"id": "call-1", "type": "function", "function": {"name": "find_place", "arguments": '{"name": "Sindh"}'}},
    ]})
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)

    reply = model.complete([{"role": "user", "content": "Irrigated land in Sindh?"}], tools=[FIND_PLACE])

    assert reply.text is None
    assert [(call.id, call.name, call.arguments) for call in reply.tool_calls] == [("call-1", "find_place", {"name": "Sindh"})]
    sent = lm.requests[0]
    assert sent["model"] == "qwen-test"
    assert sent["tools"] == [{"type": "function", "function": {
        "name": "find_place", "description": "Find a place in Pakistan by name.", "parameters": FIND_PLACE.parameters,
    }}]


class Headline(BaseModel):
    headline: str
    figure: float


def test_an_answer_of_a_given_shape_comes_back_as_that_object(lm):
    lm.reply({"content": '{"headline": "Sindh irrigates most", "figure": 95.9}'})
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)

    reply = model.complete([{"role": "user", "content": "Sum it up"}], output=Headline)

    assert reply.data == Headline(headline="Sindh irrigates most", figure=95.9)
    schema = lm.requests[0]["response_format"]
    assert schema["type"] == "json_schema"
    assert schema["json_schema"]["schema"]["required"] == ["headline", "figure"]


def test_an_answer_that_does_not_fit_the_shape_is_asked_for_once_more_then_given_up(lm):
    lm.reply({"content": "Sindh irrigates most."})
    lm.reply({"content": '{"headline": "Sindh irrigates most", "figure": 95.9}'})
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)
    assert model.complete([{"role": "user", "content": "Sum it up"}], output=Headline).data.figure == 95.9
    assert len(lm.requests) == 2

    lm.reply({"content": "no"})
    lm.reply({"content": '{"headline": 3}'})
    with pytest.raises(ModelError) as error:
        model.complete([{"role": "user", "content": "Sum it up"}], output=Headline)
    assert error.value.reason == "bad-model-response"


def test_plain_answers_are_trimmed_and_unusable_replies_say_why(lm):
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)
    ask = [{"role": "user", "content": "Who irrigates most?"}]

    def reason(call):
        with pytest.raises(ModelError) as error:
            call()
        return error.value.reason

    lm.reply({"content": "  Sindh irrigates most.  "})
    assert model.chat(ask) == "Sindh irrigates most."

    lm.reply({"content": None, "tool_calls": [{"id": "c", "function": {"name": "find_place", "arguments": "{not json"}}]})
    assert reason(lambda: model.complete(ask, tools=[FIND_PLACE])) == "bad-model-response"
    lm.reply({"content": "   "})
    assert reason(lambda: model.chat(ask)) == "bad-model-response"
    lm.reply({"content": "x"}, status=404)
    assert reason(lambda: model.chat(ask)) == "assistant-misconfigured"
    lm.reply({"content": "x"}, status=500)
    assert reason(lambda: model.chat(ask)) == "assistant-unavailable"


def test_an_answer_can_be_read_in_pieces_as_it_is_written(lm):
    lm.stream(["Sindh ", "irrigates ", "most."])
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)

    pieces = list(model.stream([{"role": "user", "content": "Who irrigates most?"}]))

    assert pieces == ["Sindh ", "irrigates ", "most."]
    assert lm.requests[0]["stream"] is True


def test_a_stream_that_stops_before_it_is_finished_says_so(lm):
    lm.stream(["Sindh "], finish=False)
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)
    pieces = []
    with pytest.raises(ModelError) as error:
        for piece in model.stream([{"role": "user", "content": "?"}]):
            pieces.append(piece)
    assert (pieces, error.value.reason) == (["Sindh "], "assistant-unavailable")


def test_reading_can_stop_part_way(lm):
    lm.stream(["one ", "two ", "three"])
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)
    pieces = model.stream([{"role": "user", "content": "?"}])
    assert next(pieces) == "one "
    pieces.close()  # the reader pressed Stop; the connection is let go


def test_a_scripted_model_plays_back_its_turns_in_order_and_keeps_what_it_was_sent():
    from csa_portal.language_model import Completion, ScriptedModel, ToolCall

    model = ScriptedModel([
        Completion(tool_calls=[ToolCall("call-1", "find_place", {"name": "Sindh"})]),
        Completion(text="Sindh irrigates most."),
        Completion(data=Headline(headline="Sindh irrigates most", figure=95.9)),
        ["Sindh ", "irrigates most."],
    ])
    first = [{"role": "user", "content": "Irrigated land in Sindh?"}]

    assert model.complete(first, tools=[FIND_PLACE]).tool_calls[0].arguments == {"name": "Sindh"}
    assert model.chat(first + [{"role": "tool", "tool_call_id": "call-1", "content": "Sindh"}]) == "Sindh irrigates most."
    assert model.complete(first, output=Headline).data.figure == 95.9
    assert list(model.stream(first)) == ["Sindh ", "irrigates most."]
    assert model.sent[1][-1]["role"] == "tool"
    assert model.tools[0] == [FIND_PLACE]
    with pytest.raises(AssertionError, match="no more scripted turns"):
        model.chat(first)


def test_a_thinking_model_whose_shaped_answer_lands_in_its_reasoning_is_still_read(lm):
    # LM Studio files Qwen3's whole schema-bound reply as reasoning and leaves the content empty (seen live).
    lm.reply({"content": "", "reasoning_content": '{\n  "headline": "Sindh relies on surface water",\n  "figure": 95.9\n}\n'})
    model = LmStudioModel(lm.url, "qwen-test", timeout=2)

    assert model.complete([{"role": "user", "content": "Sum it up"}], output=Headline).data.figure == 95.9
