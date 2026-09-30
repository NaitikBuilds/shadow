import hashlib
from pathlib import Path

import pytest

from shadow.models import MODELS, ModelManager
from shadow.models.manager import ModelManager as MM

from shadow.memory import MemoryStore


@pytest.fixture
def manager(tmp_path):
    return ModelManager(cache_dir=tmp_path / "models")


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(str(tmp_path / "test.db"))
    yield store
    store.close()


def _write_fake(path: Path, content: bytes = b"hello world") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_registry_has_expected_models():
    assert "chat" in MODELS
    assert "embedder_model" in MODELS
    assert "embedder_tokenizer" in MODELS
    assert "vision" in MODELS
    assert "planner" in MODELS
    assert "asr" in MODELS


def test_registry_chat_is_required():
    assert MODELS["chat"].optional is False


def test_registry_vision_is_optional():
    assert MODELS["vision"].optional is True
    assert MODELS["planner"].optional is True
    assert MODELS["asr"].optional is True


def test_path_for(manager):
    p = manager.path_for("chat")
    assert p.name == "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    assert str(p).startswith(str(manager.cache_dir))


def test_is_present_false_when_missing(manager):
    assert manager.is_present("chat") is False


def test_is_present_true_after_write(manager):
    _write_fake(manager.path_for("chat"))
    assert manager.is_present("chat") is True


def test_verify_without_sidecar_returns_true(manager):
    """If no expected hash, present file is treated as valid."""
    _write_fake(manager.path_for("chat"))
    assert manager.verify("chat") is True


def test_verify_with_sidecar_detects_corruption(manager):
    path = manager.path_for("chat")
    _write_fake(path, b"correct content")
    sidecar = MM._sidecar_path(path)
    sidecar.write_text("0" * 64, encoding="utf-8")  # wrong hash
    assert manager.verify("chat") is False


def test_verify_with_sidecar_accepts_match(manager):
    path = manager.path_for("chat")
    real_hash = _write_fake(path, b"correct content")
    MM._sidecar_path(path).write_text(real_hash, encoding="utf-8")
    assert manager.verify("chat") is True


def test_status_reports_missing(manager):
    status = manager.status()
    assert status["chat"]["present"] is False
    assert status["chat"]["role"] == "chat"


def test_status_reports_present_and_verified(manager):
    path = manager.path_for("chat")
    real_hash = _write_fake(path)
    MM._sidecar_path(path).write_text(real_hash, encoding="utf-8")
    status = manager.status()
    assert status["chat"]["present"] is True
    assert status["chat"]["verified"] is True


def test_recorded_version_missing_without_memory(manager):
    assert manager.get_recorded_version("chat") is None


def test_recorded_version_stored_via_memory(tmp_path, memory):
    mgr = ModelManager(cache_dir=tmp_path / "models", memory=memory)
    mgr._record_version("chat", "abc123")
    assert mgr.get_recorded_version("chat") == "abc123"


def test_recorded_version_updates_on_change(tmp_path, memory):
    mgr = ModelManager(cache_dir=tmp_path / "models", memory=memory)
    mgr._record_version("chat", "old")
    mgr._record_version("chat", "new")
    assert mgr.get_recorded_version("chat") == "new"


def test_ensure_uses_cached_file(manager):
    """A present, verified file should be returned from cache."""
    path = manager.path_for("chat")
    real_hash = _write_fake(path)
    MM._sidecar_path(path).write_text(real_hash, encoding="utf-8")
    result = manager.ensure("chat")
    assert result.from_cache is True
    assert result.path == path
