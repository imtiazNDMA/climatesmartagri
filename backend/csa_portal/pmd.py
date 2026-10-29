"""A read-only client for PMD's early warning platform, the source of the forecast rasters.

The platform lists a model's runs and each run's forecast files, and hands the files out as
GeoTIFFs. Every request needs the session cookie that signing in sets.
"""

from __future__ import annotations

import hashlib
import http.client
import http.cookiejar
import json
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

STAMP = "%Y%m%d%H%M%S"


class PmdError(Exception):
    """PMD could not be reached, refused the sign-in, or answered with something unexpected."""


@dataclass(frozen=True)
class PmdFile:
    """One forecast file: the run that produced it, the time it is for, and where it is."""

    run: datetime
    valid: datetime
    path: str


class _PinnedConnection(http.client.HTTPSConnection):
    """An HTTPS connection that goes ahead only if the server shows the one certificate expected."""

    def __init__(self, *args: Any, fingerprint: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._fingerprint = fingerprint

    def connect(self) -> None:
        super().connect()
        shown = hashlib.sha256(self.sock.getpeercert(binary_form=True) or b"").hexdigest()
        if shown != self._fingerprint:
            self.close()
            raise ssl.SSLError(f"PMD showed a certificate that is not the expected one ({shown})")


class _PinnedHandler(urllib.request.HTTPSHandler):
    def __init__(self, context: ssl.SSLContext, fingerprint: str) -> None:
        super().__init__(context=context)
        self._pinned_context = context
        self._fingerprint = fingerprint

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        def connect(host: str, **kwargs: Any) -> _PinnedConnection:
            return _PinnedConnection(host, fingerprint=self._fingerprint, **kwargs)

        return self.do_open(connect, req, context=self._pinned_context)


class PmdClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        cert_sha256: str = "",
        timeout: float = 45,
        attempts: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._attempts = attempts
        self._signed_in = False
        self._lock = threading.Lock()
        handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
        fingerprint = cert_sha256.replace(":", "").strip().lower()
        if self._base.startswith("https://") and fingerprint:
            # PMD's certificate is self-signed, so the usual check against trusted authorities cannot
            # pass. Instead the connection is accepted only if the server shows this exact certificate.
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            handlers.append(_PinnedHandler(context, fingerprint))
        self._opener = urllib.request.build_opener(*handlers)

    def runs(self, source: str, element: str) -> list[datetime]:
        """The runs PMD holds for a model's element, newest first."""
        body = self._json("/api/modelTimeList", {"data_type": source, "element": element})
        runs = [datetime.strptime(row["data_time"], STAMP) for row in body.get("data") or []]
        return sorted(runs, reverse=True)

    def files(self, source: str, element: str, level: int, run: datetime) -> list[PmdFile]:
        """The forecast files one run has for an element at a level, earliest time first."""
        body = self._json(
            "/api/model",
            {"data_type": source, "element": element, "level": level, "date_time": run.strftime(STAMP), "suffix": "tif"},
        )
        files = [
            PmdFile(run=run, valid=datetime.fromisoformat(row["forecast_time_utc"]), path=row["file_path"])
            for row in body.get("ds") or []
            if str(row.get("file_path", "")).endswith(".tif")
        ]
        return sorted(files, key=lambda file: file.valid)

    def download(self, path: str) -> bytes:
        return self._get(path)

    def _json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        raw = self._get(f"{path}?{urllib.parse.urlencode(params)}")
        try:
            body = json.loads(raw)
        except ValueError as err:
            raise PmdError(f"PMD answered {path} with something that is not JSON") from err
        if not isinstance(body, dict):
            raise PmdError(f"PMD answered {path} with an unexpected shape")
        return body

    def _sign_in(self) -> None:
        request = urllib.request.Request(
            f"{self._base}/user/login",
            data=json.dumps({"username": self._username, "password": self._password}).encode(),
            headers={"Content-Type": "application/json"},
        )
        # A dropped connection here raises OSError, which the caller treats like any other and tries again.
        with self._opener.open(request, timeout=self._timeout) as response:
            raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError as err:
            raise PmdError("PMD answered the sign-in with something that is not JSON") from err
        if str(body.get("success")).lower() != "true":
            raise PmdError("PMD refused the sign-in")
        self._signed_in = True

    def _get(self, path: str) -> bytes:
        """Fetch a path, signing in first if needed and again if the session has ended."""
        last: Exception | None = None
        for _ in range(self._attempts):
            try:
                with self._lock:
                    if not self._signed_in:
                        self._sign_in()
                with self._opener.open(f"{self._base}{path}", timeout=self._timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as err:
                if err.code == 401:
                    self._signed_in = False
                    last = err
                    continue
                raise PmdError(f"PMD answered {err.code} for {path}") from err
            except OSError as err:  # resets and timeouts are common on this server; try again
                last = err
        raise PmdError(f"PMD could not be reached for {path}: {last}")
