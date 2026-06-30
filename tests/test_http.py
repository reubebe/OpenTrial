import io
from urllib.error import HTTPError

import pytest

from opentrial.integrations import _http


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


def _http_error(code: int) -> HTTPError:
    return HTTPError("http://x", code, "err", hdrs=None, fp=io.BytesIO(b""))


def test_read_url_returns_body_on_first_success():
    calls = []

    def opener(target, timeout):
        calls.append(target)
        return _FakeResponse(b"ok")

    assert _http.read_url(opener, "http://x", timeout=1.0) == b"ok"
    assert len(calls) == 1


def test_read_url_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda _s: None)  # no real waiting
    attempts = {"n": 0}

    def opener(target, timeout):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429)  # rate limited on the first try
        return _FakeResponse(b"recovered")

    assert _http.read_url(opener, "http://x", timeout=1.0, retries=2) == b"recovered"
    assert attempts["n"] == 2


def test_read_url_does_not_retry_non_retryable():
    attempts = {"n": 0}

    def opener(target, timeout):
        attempts["n"] += 1
        raise _http_error(404)  # not found is not retryable

    with pytest.raises(HTTPError):
        _http.read_url(opener, "http://x", timeout=1.0, retries=3)
    assert attempts["n"] == 1


def test_read_url_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda _s: None)
    attempts = {"n": 0}

    def opener(target, timeout):
        attempts["n"] += 1
        raise _http_error(503)  # always failing

    with pytest.raises(HTTPError):
        _http.read_url(opener, "http://x", timeout=1.0, retries=2)
    assert attempts["n"] == 3  # initial + 2 retries
