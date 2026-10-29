"""The language model seam lives in csa_portal.ai.model; the old path hands out the same objects for one release."""


def test_the_old_seam_path_is_the_same_seam():
    from csa_portal import language_model
    from csa_portal.ai import model

    for name in ("Completion", "LanguageModel", "LmStudioModel", "ModelError", "ScriptedModel", "Tool", "ToolCall"):
        assert getattr(language_model, name) is getattr(model, name), name


def test_lm_studio_token_counts_come_from_the_response_usage():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from csa_portal.ai.model import LmStudioModel

    replies = [
        {"choices": [{"message": {"content": "Answer"}}], "usage": {"prompt_tokens": 312, "completion_tokens": 41}},
        {"choices": [{"message": {"content": "Answer"}}]},
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps(replies.pop(0)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        model = LmStudioModel(f"http://127.0.0.1:{server.server_port}", "qwen-test", timeout=2)
        with_usage = model.complete([{"role": "user", "content": "Q"}])
        without_usage = model.complete([{"role": "user", "content": "Q"}])
    finally:
        server.shutdown()

    assert (with_usage.input_tokens, with_usage.output_tokens) == (312, 41)
    assert (without_usage.input_tokens, without_usage.output_tokens) == (None, None)


def test_lm_studio_sends_the_temperature_it_was_given():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from csa_portal.ai.model import LmStudioModel

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"choices": [{"message": {"content": "Answer"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        LmStudioModel(url, "judge", timeout=2, temperature=0).complete([{"role": "user", "content": "Q"}])
        LmStudioModel(url, "assistant", timeout=2).complete([{"role": "user", "content": "Q"}])
    finally:
        server.shutdown()

    assert [body["temperature"] for body in seen] == [0, 0.2]
