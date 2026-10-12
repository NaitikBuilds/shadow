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
