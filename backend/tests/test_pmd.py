"""The PMD client, against a small stand-in server that behaves the way PMD's does."""

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from csa_portal.pmd import PmdClient, PmdError, PmdFile


class Pmd(BaseHTTPRequestHandler):
    logins = 0
    expire_next = False
    password = "secret"

    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type="application/json", cookie=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/user/login" and sent == {"username": "PMD", "password": Pmd.password}:
            Pmd.logins += 1
            self._send(200, {"success": "true"}, cookie=f"ews_jwt=token{Pmd.logins}; Path=/")
        else:
            self._send(200, {"success": "false"})

    def do_GET(self):
        if Pmd.expire_next or f"ews_jwt=token{Pmd.logins}" not in self.headers.get("Cookie", ""):
            Pmd.expire_next = False
            return self._send(401, {"detail": "no"})
        url = urlparse(self.path)
        query = {name: values[0] for name, values in parse_qs(url.query).items()}
        if url.path == "/api/modelTimeList":
            return self._send(200, {"data": [{"data_time": "20261008120000"}, {"data_time": "20261009000000"}]})
        if url.path == "/api/model":
            assert query == {"data_type": "SRC", "element": "TEM", "level": "850", "date_time": "20261009000000",
                             "suffix": "tif"}
            return self._send(200, {"count": 2, "ds": [
                {"file_path": "/static/b.tif", "forecast_time_utc": "2026-10-09T06:00:00"},
                {"file_path": "/static/a.tif", "forecast_time_utc": "2026-10-09T00:00:00"},
                {"file_path": "/static/lines.json", "forecast_time_utc": "2026-10-09T00:00:00"},
            ]})
        if url.path == "/static/a.tif":
            return self._send(200, b"tiff-bytes", "image/tiff")
        if url.path == "/api/broken":
            return self._send(200, b"<html>", "text/html")
        return self._send(404, {"detail": "missing"})


@pytest.fixture
def base_url():
    Pmd.logins, Pmd.expire_next = 0, False
    server = ThreadingHTTPServer(("127.0.0.1", 0), Pmd)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_runs_come_newest_first_after_signing_in_once(base_url):
    client = PmdClient(base_url, "PMD", "secret")
    assert client.runs("SRC", "TEM") == [datetime(2026, 10, 9, 0), datetime(2026, 10, 8, 12)]
    client.runs("SRC", "TEM")
    assert Pmd.logins == 1


def test_files_are_the_rasters_of_a_run_earliest_first(base_url):
    run = datetime(2026, 10, 9, 0)
    assert PmdClient(base_url, "PMD", "secret").files("SRC", "TEM", 850, run) == [
        PmdFile(run=run, valid=datetime(2026, 10, 9, 0), path="/static/a.tif"),
        PmdFile(run=run, valid=datetime(2026, 10, 9, 6), path="/static/b.tif"),
    ]


def test_download_returns_the_file(base_url):
    assert PmdClient(base_url, "PMD", "secret").download("/static/a.tif") == b"tiff-bytes"


def test_an_ended_session_is_signed_in_again(base_url):
    client = PmdClient(base_url, "PMD", "secret")
    client.runs("SRC", "TEM")
    Pmd.expire_next = True
    assert client.download("/static/a.tif") == b"tiff-bytes"
    assert Pmd.logins == 2


def test_a_refused_sign_in_a_missing_file_and_a_bad_answer_are_errors(base_url):
    with pytest.raises(PmdError, match="refused"):
        PmdClient(base_url, "PMD", "wrong").runs("SRC", "TEM")
    client = PmdClient(base_url, "PMD", "secret")
    with pytest.raises(PmdError, match="404"):
        client.download("/static/absent.tif")
    with pytest.raises(PmdError, match="not JSON"):
        client._json("/api/broken", {})


def test_a_server_that_is_not_there_is_an_error():
    with pytest.raises(PmdError, match="could not be reached"):
        PmdClient("http://127.0.0.1:9", "PMD", "secret", timeout=2, attempts=1).runs("SRC", "TEM")
