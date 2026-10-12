import httpx
import pytest

from shadow.hal.cloud_backend import (
    AuthError,
    CloudBackend,
    CloudError,
    ProviderConfig,
    RateLimitError,
    ServerError,
)


def make_backend(handler, **kwargs) -> CloudBackend:
    """Build a CloudBackend with a mocked transport."""
    provider = ProviderConfig(
        name="test",
        base_url="https://api.test.com/v1",
        model="test-model",
        api_key="test-key-1234567890",
    )
    backend = CloudBackend(provider, **kwargs)
    # Replace the client with a mock-transport version
    backend._client = httpx.Client(
        base_url=provider.base_url,
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
        timeout=30,
    )
    return backend


# ---------- info ----------


def test_info_reports_cloud():
    def handler(request):
        return httpx.Response(200, json={})

    backend = make_backend(handler)
    info = backend.info
    assert info["backend"] == "cloud"
    assert info["provider"] == "test"
    assert info["model"] == "test-model"


def test_masked_key():
    provider = ProviderConfig(
        name="x",
        base_url="https://x.com",
        model="m",
        api_key="sk-abcdef1234567890",
    )
    assert provider.masked_key == "sk-a…7890"


def test_masked_key_short():
    provider = ProviderConfig(
        name="x", base_url="https://x.com", model="m", api_key="short"
    )
    assert provider.masked_key == "*****"


# ---------- embed ----------


def test_embed_raises_not_implemented():
    def handler(request):
        return httpx.Response(200, json={})

    backend = make_backend(handler)
    with pytest.raises(NotImplementedError):
        backend.embed("hello")


# ---------- streaming ----------


def _sse_body(chunks: list[str]) -> bytes:
    lines = []
    for c in chunks:
        lines.append(f'data: {{"choices":[{{"delta":{{"content":"{c}"}}}}]}}\n\n')
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def test_generate_stream_yields_chunks():
    def handler(request):
        return httpx.Response(
            200,
            content=_sse_body(["Hello", " ", "world", "!"]),
            headers={"content-type": "text/event-stream"},
        )

    backend = make_backend(handler)
    chunks = list(backend.generate_stream("hi"))
    assert chunks == ["Hello", " ", "world", "!"]


def test_generate_joins_chunks():
    def handler(request):
        return httpx.Response(200, content=_sse_body(["A", "B", "C"]))

    backend = make_backend(handler)
    assert backend.generate("hi") == "ABC"


def test_empty_stream_yields_nothing():
    def handler(request):
        return httpx.Response(200, content=b"data: [DONE]\n\n")

    backend = make_backend(handler)
    assert list(backend.generate_stream("hi")) == []


def test_malformed_json_lines_skipped():
    def handler(request):
        body = (
            'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            "data: not-json\n\n"
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body.encode())

    backend = make_backend(handler)
    assert list(backend.generate_stream("hi")) == ["ok"]


def test_non_data_lines_ignored():
    def handler(request):
        body = (
            ": keep-alive\n\n"
            'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body.encode())

    backend = make_backend(handler)
    assert list(backend.generate_stream("hi")) == ["x"]


# ---------- error taxonomy ----------


def test_rate_limit_raises_rate_limit_error():
    def handler(request):
        return httpx.Response(429, json={"error": "too many"})

    backend = make_backend(handler, max_retries=0)
    with pytest.raises(RateLimitError):
        backend.generate("hi")


def test_auth_error_raises_auth_error():
    def handler(request):
        return httpx.Response(401, json={"error": "bad key"})

    backend = make_backend(handler, max_retries=0)
    with pytest.raises(AuthError):
        backend.generate("hi")


def test_forbidden_raises_auth_error():
    def handler(request):
        return httpx.Response(403, json={"error": "forbidden"})

    backend = make_backend(handler, max_retries=0)
    with pytest.raises(AuthError):
        backend.generate("hi")


def test_server_error_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(500, json={"error": "oops"})
        return httpx.Response(200, content=_sse_body(["ok"]))

    backend = make_backend(handler, max_retries=2)
    assert backend.generate("hi") == "ok"
    assert calls["n"] == 2


def test_server_error_retries_exhausted():
    def handler(request):
        return httpx.Response(500, json={"error": "oops"})

    backend = make_backend(handler, max_retries=1)
    with pytest.raises(ServerError):
        backend.generate("hi")


def test_other_4xx_raises_cloud_error():
    def handler(request):
        return httpx.Response(400, json={"error": "bad request"})

    backend = make_backend(handler, max_retries=0)
    with pytest.raises(CloudError):
        backend.generate("hi")


# ---------- test_connection ----------


def test_test_connection_ok():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})

    backend = make_backend(handler)
    ok, msg = backend.test_connection()
    assert ok is True
    assert msg == "ok"


def test_test_connection_auth_fails():
    def handler(request):
        return httpx.Response(401, json={"error": "bad key"})

    backend = make_backend(handler)
    ok, msg = backend.test_connection()
    assert ok is False
    assert "401" in msg or "invalid" in msg.lower()


def test_test_connection_rate_limit():
    def handler(request):
        return httpx.Response(429, json={"error": "too many"})

    backend = make_backend(handler)
    ok, msg = backend.test_connection()
    assert ok is False
    assert "429" in msg or "rate" in msg.lower()
