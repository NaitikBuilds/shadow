import pytest

from shadow.hal import (
    TASK_CAPTION,
    TASK_DETAILED_CAPTION,
    TASK_OCR,
    TASK_QUERY,
    VALID_TASKS,
    InferenceBackend,
)


class MinimalBackend(InferenceBackend):
    """Smallest valid backend that doesn't implement vision."""

    def generate(self, prompt, **kwargs):
        return ""

    def generate_stream(self, prompt, **kwargs):
        yield ""

    def embed(self, text):
        return [0.0] * 384

    @property
    def info(self):
        return {"backend": "minimal"}


# ---------- task constants ----------


def test_task_constants_are_strings():
    assert isinstance(TASK_CAPTION, str)
    assert isinstance(TASK_DETAILED_CAPTION, str)
    assert isinstance(TASK_OCR, str)
    assert isinstance(TASK_QUERY, str)


def test_valid_tasks_is_frozenset():
    assert isinstance(VALID_TASKS, frozenset)
    assert TASK_CAPTION in VALID_TASKS
    assert TASK_DETAILED_CAPTION in VALID_TASKS
    assert TASK_OCR in VALID_TASKS
    assert TASK_QUERY in VALID_TASKS
    assert len(VALID_TASKS) == 4


# ---------- default understand_image behavior ----------


def test_understand_image_default_raises_not_implemented():
    backend = MinimalBackend()
    with pytest.raises(NotImplementedError):
        backend.understand_image(b"fake image bytes")


def test_understand_image_invalid_task_raises_value_error():
    backend = MinimalBackend()
    with pytest.raises(ValueError, match="unknown vision task"):
        backend.understand_image(b"fake", task="not_a_real_task")


def test_understand_image_valid_task_still_not_implemented():
    backend = MinimalBackend()
    with pytest.raises(NotImplementedError):
        backend.understand_image(b"fake", task=TASK_OCR)


def test_supports_vision_false_by_default():
    backend = MinimalBackend()
    assert backend.supports_vision() is False


# ---------- delegation through ProviderPool ----------


class FakeVisionBackend(MinimalBackend):
    def understand_image(self, image_bytes, task=TASK_CAPTION, prompt=""):
        return f"vision:{task}:{len(image_bytes)}"

    def supports_vision(self):
        return True


def test_provider_pool_delegates_vision_to_local():
    from shadow.hal.provider_pool import ProviderPool

    local = FakeVisionBackend()
    pool = ProviderPool(providers=[], local_fallback=local)
    result = pool.understand_image(b"12345", task=TASK_CAPTION)
    assert result == "vision:caption:5"


def test_provider_pool_supports_vision_when_local_does():
    from shadow.hal.provider_pool import ProviderPool

    local = FakeVisionBackend()
    pool = ProviderPool(providers=[], local_fallback=local)
    assert pool.supports_vision() is True


def test_provider_pool_no_vision_without_local():
    from shadow.hal.provider_pool import ProviderPool

    pool = ProviderPool(providers=[])
    assert pool.supports_vision() is False
    with pytest.raises(NotImplementedError):
        pool.understand_image(b"fake")


# ---------- delegation through HybridBackend ----------


def test_hybrid_backend_delegates_vision_to_local():
    from shadow.hal.hybrid_backend import HybridBackend

    class FakeHealth:
        def is_online(self):
            return True

    local = FakeVisionBackend()
    cloud = MinimalBackend()
    hybrid = HybridBackend(cloud=cloud, local=local, health=FakeHealth())
    result = hybrid.understand_image(b"hello", task=TASK_DETAILED_CAPTION)
    assert result == "vision:detailed_caption:5"


def test_hybrid_backend_supports_vision_from_local():
    from shadow.hal.hybrid_backend import HybridBackend

    class FakeHealth:
        def is_online(self):
            return True

    hybrid = HybridBackend(
        cloud=MinimalBackend(),
        local=FakeVisionBackend(),
        health=FakeHealth(),
    )
    assert hybrid.supports_vision() is True


def test_hybrid_backend_no_vision_when_local_has_none():
    from shadow.hal.hybrid_backend import HybridBackend

    class FakeHealth:
        def is_online(self):
            return True

    hybrid = HybridBackend(
        cloud=MinimalBackend(),
        local=MinimalBackend(),
        health=FakeHealth(),
    )
    assert hybrid.supports_vision() is False
