
import httpx
import pytest

from shadow.hal.cloud_backend import (
    CloudBackend,
    ProviderConfig,
)
from shadow.hal.provider_pool import (
    AllProvidersFailed,
    ProviderPool,
)


def _make_backend(name: str, handler, api_key: str = "key-1234567890") -> CloudBackend:
    provider = ProviderConfig(
        name=name,
        base_url=f"https://{name}.test/v1",
        model=f"{name}-model",
        api_key=api_key,
    )
    backend = CloudBackend(provider, max_retries=0)
    backend._client = httpx.Client(
        base_url=provider.base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        transport=httpx.MockTransport(handler),
        timeout=30,
    )
    return backend


def _sse_body(chunks: list[str]) -> bytes:
    lines = []
    for c in chunks:
        lines.append(f'data: {{"choices":[{{"delta":{{"content":"{c}"}}}}]}}\n\n')
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


# ---------- basic ----------


def test_pool_uses_first_provider():
    def handler_a(request):
        return httpx.Response(200, content=_sse_body(["A"]))

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )
    assert pool.generate("hi") == "A"


def test_pool_failover_on_rate_limit():
    def handler_a(request):
        return httpx.Response(429, json={"error": "too many"})

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )
    assert pool.generate("hi") == "B"


def test_pool_failover_on_server_error():
    def handler_a(request):
        return httpx.Response(500, json={"error": "oops"})

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )
    assert pool.generate("hi") == "B"


def test_pool_failover_on_auth_error():
    def handler_a(request):
        return httpx.Response(401, json={"error": "bad key"})

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )
    assert pool.generate("hi") == "B"


def test_pool_priority_order_enforced():
    def handler_a(request):
        return httpx.Response(200, content=_sse_body(["A"]))

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (5, _make_backend("beta", handler_b)),
            (1, _make_backend("alpha", handler_a)),
        ]
    )
    # alpha has lower priority number, should be tried first
    assert pool.generate("hi") == "A"


# ---------- cooldown ----------


def test_rate_limit_triggers_cooldown():
    calls = {"a": 0}

    def handler_a(request):
        calls["a"] += 1
        return httpx.Response(429, json={"error": "too many"})

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )

    pool.generate("first")
    # Second call — alpha in cooldown, only beta tried
    pool.generate("second")
    assert calls["a"] == 1


def test_auth_error_triggers_long_cooldown():
    calls = {"a": 0}

    def handler_a(request):
        calls["a"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )

    pool.generate("first")
    pool.generate("second")
    pool.generate("third")
    assert calls["a"] == 1


def test_mark_key_updated_clears_cooldown():
    calls = {"a": 0}

    def handler_a(request):
        calls["a"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    def handler_b(request):
        return httpx.Response(200, content=_sse_body(["B"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler_a)),
            (2, _make_backend("beta", handler_b)),
        ]
    )
    pool.generate("first")
    assert calls["a"] == 1

    pool.mark_key_updated("alpha")

    # Now alpha is tried again
    pool.generate("second")
    assert calls["a"] == 2


# ---------- local fallback ----------


class FakeLocalBackend:
    def __init__(self, reply: str = "local reply"):
        self.reply = reply

    def generate_stream(self, prompt, **kwargs):
        yield self.reply

    def generate(self, prompt, **kwargs):
        return self.reply

    def embed(self, text):
        return [0.0] * 384

    @property
    def info(self):
        return {"backend": "fake_local"}


def test_local_fallback_used_when_all_providers_fail():
    def handler_a(request):
        return httpx.Response(429, json={"error": "too many"})

    pool = ProviderPool(
        [(1, _make_backend("alpha", handler_a))],
        local_fallback=FakeLocalBackend("local"),
    )
    assert pool.generate("hi") == "local"


def test_no_fallback_raises_when_all_fail():
    def handler_a(request):
        return httpx.Response(429, json={"error": "too many"})

    pool = ProviderPool([(1, _make_backend("alpha", handler_a))])
    with pytest.raises(AllProvidersFailed) as exc_info:
        pool.generate("hi")
    assert "alpha" in exc_info.value.tried


def test_fallback_embed_delegates_to_local():
    pool = ProviderPool([], local_fallback=FakeLocalBackend())
    emb = pool.embed("hello")
    assert len(emb) == 384


def test_no_embed_raises_without_local():
    pool = ProviderPool([])
    with pytest.raises(NotImplementedError):
        pool.embed("hello")


# ---------- status ----------


def test_status_lists_all_providers():
    def handler(request):
        return httpx.Response(200, content=_sse_body(["x"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler)),
            (2, _make_backend("beta", handler)),
        ]
    )
    status = pool.status()
    assert len(status) == 2
    assert {s["name"] for s in status} == {"alpha", "beta"}
    for s in status:
        assert s["state"] == "ready"


def test_status_reports_no_key():
    def handler(request):
        return httpx.Response(200, content=_sse_body(["x"]))

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler, api_key="")),
        ]
    )
    status = pool.status()
    assert status[0]["state"] == "no_key"


def test_status_reports_cooldown():
    def handler(request):
        return httpx.Response(429, json={"error": "too many"})

    pool = ProviderPool(
        [
            (1, _make_backend("alpha", handler)),
            (
                2,
                _make_backend(
                    "beta", lambda r: httpx.Response(200, content=_sse_body(["x"]))
                ),
            ),
        ]
    )
    pool.generate("hi")
    status = {s["name"]: s for s in pool.status()}
    assert status["alpha"]["state"] == "cooldown"
    assert status["alpha"]["cooldown_remaining"] > 0


# ---------- info ----------


def test_info_reports_pool_shape():
    def handler(request):
        return httpx.Response(200, content=_sse_body(["x"]))

    pool = ProviderPool(
        [(1, _make_backend("alpha", handler))],
        local_fallback=FakeLocalBackend(),
    )
    info = pool.info
    assert info["backend"] == "cloud_pool"
    assert info["provider_count"] == 1
    assert info["has_local_fallback"] is True
    assert "alpha" in info["providers"]
