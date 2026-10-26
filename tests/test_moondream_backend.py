import sys
import threading
import time
import types

import pytest

from shadow.hal import (
    TASK_CAPTION,
    TASK_DETAILED_CAPTION,
    TASK_OCR,
    TASK_QUERY,
)
from shadow.hal.moondream_backend import (
    UNLOAD_AFTER_SEC,
    Moondream2Backend,
)


def make_backend(tmp_path, with_files: bool = True) -> Moondream2Backend:
    text = tmp_path / "text.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    if with_files:
        text.write_bytes(b"fake")
        mmproj.write_bytes(b"fake")
    return Moondream2Backend(str(text), str(mmproj))


# ---------- fake llama-cpp-python ----------
#
# The real package loads native libraries and 3+ GB of weights, so unit tests
# substitute module-level fakes for Llama and MoondreamChatHandler. The fake
# handler mirrors 0.3.x: no close()/__del__, native state held in an ExitStack.


class FakeExitStack:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class FakeChatHandler:
    def __init__(self, clip_model_path, verbose=True):
        self.clip_model_path = clip_model_path
        self.verbose = verbose
        self._exit_stack = FakeExitStack()


class FakeLlama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.requests = []
        self.reply = "fake caption"
        self.chat_error = None
        self.close_calls = 0

    def create_chat_completion(self, **kwargs):
        self.requests.append(kwargs)
        if self.chat_error is not None:
            raise self.chat_error
        if kwargs.get("stream"):
            return iter(
                [
                    {"choices": [{"delta": {"content": "hi "}}]},
                    {"choices": [{"delta": {"content": "there"}}]},
                    {"choices": [{"delta": {}}]},
                ]
            )
        return {
            "choices": [
                {"message": {"role": "assistant", "content": self.reply}}
            ]
        }

    def close(self):
        self.close_calls += 1


class FakeLlamaCPP:
    def __init__(self):
        self.handlers: list[FakeChatHandler] = []
        self.llamas: list[FakeLlama] = []
        self.llama_error: Exception | None = None
        self.module = None


@pytest.fixture
def fake_llama_cpp(monkeypatch):
    fake = FakeLlamaCPP()

    def make_handler(clip_model_path, verbose=True):
        handler = FakeChatHandler(clip_model_path, verbose=verbose)
        fake.handlers.append(handler)
        return handler

    def make_llama(**kwargs):
        if fake.llama_error is not None:
            raise fake.llama_error
        llm = FakeLlama(**kwargs)
        fake.llamas.append(llm)
        return llm

    llama_mod = types.ModuleType("llama_cpp")
    llama_mod.Llama = make_llama
    chat_mod = types.ModuleType("llama_cpp.llama_chat_format")
    chat_mod.MoondreamChatHandler = make_handler
    llama_mod.llama_chat_format = chat_mod
    fake.module = llama_mod
    monkeypatch.setitem(sys.modules, "llama_cpp", llama_mod)
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_chat_format", chat_mod)
    return fake


# ---------- pure helpers ----------


def test_supports_vision():
    backend = Moondream2Backend("a", "b")
    assert backend.supports_vision() is True


def test_info_reports_not_loaded():
    backend = Moondream2Backend("a", "b")
    info = backend.info
    assert info["backend"] == "moondream2"
    assert info["loaded"] is False


def test_empty_image_returns_empty(tmp_path):
    backend = make_backend(tmp_path)
    assert backend.understand_image(b"") == ""


def test_resolve_prompt_caption():
    backend = Moondream2Backend("a", "b")
    assert "briefly" in backend._resolve_prompt(TASK_CAPTION, "")


def test_resolve_prompt_detailed():
    backend = Moondream2Backend("a", "b")
    assert "detail" in backend._resolve_prompt(TASK_DETAILED_CAPTION, "")


def test_resolve_prompt_ocr():
    backend = Moondream2Backend("a", "b")
    assert "text" in backend._resolve_prompt(TASK_OCR, "").lower()


def test_resolve_prompt_query_uses_user_prompt():
    backend = Moondream2Backend("a", "b")
    assert backend._resolve_prompt(TASK_QUERY, "What is red?") == "What is red?"


def test_resolve_prompt_query_empty_returns_empty():
    backend = Moondream2Backend("a", "b")
    assert backend._resolve_prompt(TASK_QUERY, "") == ""


def test_data_uri_png():
    backend = Moondream2Backend("a", "b")
    uri = backend._to_data_uri(b"\x89PNG\r\n\x1a\n" + b"junk")
    assert uri.startswith("data:image/png;base64,")


def test_data_uri_jpeg():
    backend = Moondream2Backend("a", "b")
    uri = backend._to_data_uri(b"\xff\xd8\xff\xe0" + b"junk")
    assert uri.startswith("data:image/jpeg;base64,")


def test_data_uri_unknown_defaults_to_png():
    backend = Moondream2Backend("a", "b")
    uri = backend._to_data_uri(b"random")
    assert uri.startswith("data:image/png;base64,")


def test_ensure_loaded_raises_when_files_missing(tmp_path):
    backend = make_backend(tmp_path, with_files=False)
    with pytest.raises(FileNotFoundError):
        backend._ensure_loaded()


def test_embed_raises():
    backend = Moondream2Backend("a", "b")
    with pytest.raises(NotImplementedError):
        backend.embed("hello")


def test_close_is_safe_when_never_loaded(tmp_path):
    backend = make_backend(tmp_path)
    backend.close()  # should not raise


def test_unload_constant_value():
    assert UNLOAD_AFTER_SEC == 300


def test_understand_image_returns_empty_on_load_failure(tmp_path):
    backend = make_backend(tmp_path, with_files=False)
    # Should return empty string, not raise
    assert backend.understand_image(b"\x89PNG\r\n\x1a\nx") == ""


# ---------- chat handler wiring ----------


def test_ensure_loaded_passes_moondream_chat_handler(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    llm = backend._ensure_loaded()

    try:
        assert len(fake_llama_cpp.handlers) == 1
        handler = fake_llama_cpp.handlers[0]
        assert handler.clip_model_path == str(tmp_path / "mmproj.gguf")
        assert handler.verbose is False

        assert llm is fake_llama_cpp.llamas[0]
        kwargs = llm.kwargs
        assert kwargs["chat_handler"] is handler
        assert "chat_format" not in kwargs
        assert kwargs["model_path"] == str(tmp_path / "text.gguf")
        assert kwargs["n_ctx"] == 2048
        assert kwargs["n_gpu_layers"] == 0
        assert kwargs["verbose"] is False
    finally:
        backend.close()


def test_ensure_loaded_reuses_single_handler(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    try:
        assert backend._ensure_loaded() is backend._ensure_loaded()
        assert len(fake_llama_cpp.handlers) == 1
        assert len(fake_llama_cpp.llamas) == 1
    finally:
        backend.close()


def test_understand_image_keeps_image_url_payload(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    try:
        llm = backend._ensure_loaded()
        llm.reply = " a cat on a desk\n"
        assert backend.understand_image(b"\x89PNG\r\n\x1a\nx") == "a cat on a desk"

        request = llm.requests[-1]
        content = request["messages"][0]["content"]
        assert content[0]["type"] == "image_url"
        assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
        assert content[1] == {
            "type": "text",
            "text": backend._resolve_prompt(TASK_CAPTION, ""),
        }
        assert request["max_tokens"] == 256
        assert request["temperature"] == 0.2
    finally:
        backend.close()


def test_generate_stream_releases_session_when_exhausted(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    try:
        assert "".join(backend.generate_stream("hello")) == "hi there"
        assert backend._in_flight == 0
        assert backend.info["loaded"] is True
        assert backend.generate("hello") == "hi there"
    finally:
        backend.close()


def test_understand_image_returns_empty_when_inference_fails(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    try:
        llm = backend._ensure_loaded()
        llm.chat_error = RuntimeError("native failure")
        assert backend.understand_image(b"\x89PNG\r\n\x1a\nx") == ""
        assert backend.info["loaded"] is True
    finally:
        backend.close()


# ---------- native resource lifecycle ----------


def test_close_releases_model_and_handler_exactly_once(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    llm = backend._ensure_loaded()
    handler = fake_llama_cpp.handlers[0]

    backend.close()
    assert llm.close_calls == 1
    assert handler._exit_stack.close_calls == 1
    assert backend.info["loaded"] is False

    backend.close()
    assert llm.close_calls == 1
    assert handler._exit_stack.close_calls == 1


def test_idle_unload_releases_handler_and_reload_gets_fresh_one(
    tmp_path, fake_llama_cpp
):
    backend = make_backend(tmp_path)
    first = backend._ensure_loaded()
    backend._last_used_at -= UNLOAD_AFTER_SEC + 1

    assert backend._unload_if_idle() is True
    assert first.close_calls == 1
    assert fake_llama_cpp.handlers[0]._exit_stack.close_calls == 1
    assert backend.info["loaded"] is False

    second = backend._ensure_loaded()
    try:
        assert second is not first
        assert len(fake_llama_cpp.handlers) == 2
        # The replacement handler is still open...
        assert fake_llama_cpp.handlers[1]._exit_stack.close_calls == 0
    finally:
        backend.close()

    # ...and is released once on close, without touching the old handler.
    assert second.close_calls == 1
    assert fake_llama_cpp.handlers[1]._exit_stack.close_calls == 1
    assert fake_llama_cpp.handlers[0]._exit_stack.close_calls == 1


def test_unload_if_idle_keeps_recent_model(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    llm = backend._ensure_loaded()
    try:
        assert backend._unload_if_idle() is False
        assert llm.close_calls == 0
        assert backend.info["loaded"] is True
    finally:
        backend.close()


def test_unload_if_idle_defers_while_inference_in_flight(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    llm = backend._ensure_loaded()
    try:
        with backend._model_session():
            backend._last_used_at -= UNLOAD_AFTER_SEC + 1
            assert backend._unload_if_idle() is False
            assert llm.close_calls == 0
            assert backend.info["loaded"] is True
    finally:
        backend.close()
    assert llm.close_calls == 1


def test_release_model_waits_for_in_flight_session(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    llm = backend._ensure_loaded()
    handler = fake_llama_cpp.handlers[0]

    in_session = threading.Event()
    finish = threading.Event()

    def worker():
        with backend._model_session():
            in_session.set()
            finish.wait(5)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    assert in_session.wait(5)

    closer_thread = threading.Thread(target=backend.close, daemon=True)
    closer_thread.start()
    time.sleep(0.1)
    # close() must not free native state while a generation is running.
    assert llm.close_calls == 0
    assert handler._exit_stack.close_calls == 0

    finish.set()
    worker_thread.join(5)
    closer_thread.join(5)
    assert not worker_thread.is_alive()
    assert not closer_thread.is_alive()
    assert llm.close_calls == 1
    assert handler._exit_stack.close_calls == 1


def test_handler_released_when_llama_init_fails(tmp_path, fake_llama_cpp):
    fake_llama_cpp.llama_error = RuntimeError("failed to load model")
    backend = make_backend(tmp_path)

    with pytest.raises(RuntimeError, match="failed to load model"):
        backend._ensure_loaded()

    assert len(fake_llama_cpp.handlers) == 1
    assert fake_llama_cpp.handlers[0]._exit_stack.close_calls == 1
    assert backend.info["loaded"] is False
    backend.close()


def test_close_prevents_reload(tmp_path, fake_llama_cpp):
    backend = make_backend(tmp_path)
    backend._ensure_loaded()
    backend.close()

    with pytest.raises(RuntimeError, match="closed"):
        backend._ensure_loaded()
    assert backend.understand_image(b"\x89PNG\r\n\x1a\nx") == ""
    assert len(fake_llama_cpp.llamas) == 1


def test_release_accepts_mtmd_owned_handler(caplog):
    # mtmd-based handlers hand their native context to Llama's teardown
    # stack; after llm.close() there is nothing left to free here.
    handler = types.SimpleNamespace(mtmd_ctx=None)

    with caplog.at_level("WARNING", logger="shadow.hal.moondream_backend"):
        Moondream2Backend._release_chat_handler(handler)

    assert not caplog.records


def test_release_warns_when_mtmd_context_still_live(caplog):
    # A surviving native context means cleanup was skipped; surface it
    # rather than freeing memory that Llama may still own.
    handler = types.SimpleNamespace(mtmd_ctx=object())

    with caplog.at_level("WARNING", logger="shadow.hal.moondream_backend"):
        Moondream2Backend._release_chat_handler(handler)

    assert len(caplog.records) == 1
