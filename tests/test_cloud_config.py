import os

import pytest

from shadow.config import (
    build_provider_pool,
    cloud_config,
    cloud_enabled,
    resolve_key,
)


@pytest.fixture
def clean_env(monkeypatch):
    """Ensure no SHADOW_* env vars leak between tests."""
    for key in list(os.environ.keys()):
        if key.startswith("SHADOW_"):
            monkeypatch.delenv(key, raising=False)
    yield


# ---------- cloud_config ----------


def test_cloud_config_defaults():
    cfg = cloud_config({})
    assert cfg["enabled"] is False
    assert cfg["fallback_to_local"] is True
    assert cfg["timeout_sec"] == 30
    assert cfg["max_retries"] == 2
    assert cfg["log_prompts"] is False
    assert cfg["providers"] == []


def test_cloud_config_preserves_providers():
    user = {
        "cloud": {
            "enabled": True,
            "providers": [
                {"name": "groq", "enabled": True, "priority": 1},
            ],
        }
    }
    cfg = cloud_config(user)
    assert cfg["enabled"] is True
    assert len(cfg["providers"]) == 1
    assert cfg["providers"][0]["name"] == "groq"


def test_cloud_config_missing_providers_yields_empty():
    cfg = cloud_config({"cloud": {"enabled": True}})
    assert cfg["providers"] == []


# ---------- cloud_enabled ----------


def test_cloud_enabled_false_by_default():
    assert cloud_enabled({}) is False


def test_cloud_enabled_true_when_set():
    assert cloud_enabled({"cloud": {"enabled": True}}) is True


# ---------- resolve_key ----------


def test_resolve_key_from_env(monkeypatch):
    monkeypatch.setenv("SHADOW_TEST_KEY", "sk-test-1234567890")
    assert resolve_key("SHADOW_TEST_KEY") == "sk-test-1234567890"


def test_resolve_key_strips_whitespace(monkeypatch):
    monkeypatch.setenv("SHADOW_TEST_KEY", "  sk-test  ")
    assert resolve_key("SHADOW_TEST_KEY") == "sk-test"


def test_resolve_key_empty_env_name():
    assert resolve_key("") == ""


def test_resolve_key_missing_env_name(clean_env):
    # No env var, keyring likely returns None → empty string
    assert resolve_key("SHADOW_DEFINITELY_NOT_SET_XYZ") == ""


# ---------- build_provider_pool ----------


def test_build_pool_returns_none_when_disabled(clean_env):
    cfg = {"cloud": {"enabled": False}}
    assert build_provider_pool(cfg) is None


def test_build_pool_returns_none_when_no_keys(clean_env):
    cfg = {
        "cloud": {
            "enabled": True,
            "providers": [
                {
                    "name": "groq",
                    "enabled": True,
                    "env_key": "SHADOW_GROQ_KEY",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "priority": 1,
                },
            ],
        }
    }
    assert build_provider_pool(cfg) is None


def test_build_pool_with_env_key(clean_env, monkeypatch):
    monkeypatch.setenv("SHADOW_GROQ_KEY", "sk-test-1234567890")
    cfg = {
        "cloud": {
            "enabled": True,
            "providers": [
                {
                    "name": "groq",
                    "enabled": True,
                    "env_key": "SHADOW_GROQ_KEY",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "priority": 1,
                },
            ],
        }
    }
    pool = build_provider_pool(cfg)
    assert pool is not None
    assert pool.info["provider_count"] == 1
    assert "groq" in pool.info["providers"]


def test_build_pool_skips_disabled_providers(clean_env, monkeypatch):
    monkeypatch.setenv("SHADOW_GROQ_KEY", "sk-test")
    monkeypatch.setenv("SHADOW_GEMINI_KEY", "sk-test-2")
    cfg = {
        "cloud": {
            "enabled": True,
            "providers": [
                {
                    "name": "groq",
                    "enabled": True,
                    "env_key": "SHADOW_GROQ_KEY",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "priority": 1,
                },
                {
                    "name": "gemini",
                    "enabled": False,  # disabled
                    "env_key": "SHADOW_GEMINI_KEY",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                    "model": "gemini-2.5-flash",
                    "priority": 2,
                },
            ],
        }
    }
    pool = build_provider_pool(cfg)
    assert pool is not None
    assert pool.info["provider_count"] == 1
    assert pool.info["providers"] == ["groq"]


def test_build_pool_with_local_fallback(clean_env, monkeypatch):
    monkeypatch.setenv("SHADOW_GROQ_KEY", "sk-test")

    class FakeLocal:
        def generate_stream(self, prompt, **kwargs):
            yield "local"

        def generate(self, prompt, **kwargs):
            return "local"

        def embed(self, text):
            return [0.0] * 384

        @property
        def info(self):
            return {"backend": "fake"}

    cfg = {
        "cloud": {
            "enabled": True,
            "fallback_to_local": True,
            "providers": [
                {
                    "name": "groq",
                    "enabled": True,
                    "env_key": "SHADOW_GROQ_KEY",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "priority": 1,
                },
            ],
        }
    }
    pool = build_provider_pool(cfg, local_backend=FakeLocal())
    assert pool is not None
    assert pool.info["has_local_fallback"] is True


def test_build_pool_no_fallback_when_disabled(clean_env, monkeypatch):
    monkeypatch.setenv("SHADOW_GROQ_KEY", "sk-test")

    class FakeLocal:
        def generate_stream(self, prompt, **kwargs):
            yield "x"

        @property
        def info(self):
            return {}

    cfg = {
        "cloud": {
            "enabled": True,
            "fallback_to_local": False,
            "providers": [
                {
                    "name": "groq",
                    "enabled": True,
                    "env_key": "SHADOW_GROQ_KEY",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "priority": 1,
                },
            ],
        }
    }
    pool = build_provider_pool(cfg, local_backend=FakeLocal())
    assert pool is not None
    assert pool.info["has_local_fallback"] is False


def test_build_pool_priority_order(clean_env, monkeypatch):
    monkeypatch.setenv("SHADOW_A_KEY", "sk-a")
    monkeypatch.setenv("SHADOW_B_KEY", "sk-b")
    cfg = {
        "cloud": {
            "enabled": True,
            "providers": [
                {
                    "name": "b_high_priority_number",
                    "enabled": True,
                    "env_key": "SHADOW_B_KEY",
                    "base_url": "https://b.com/v1",
                    "model": "b",
                    "priority": 5,
                },
                {
                    "name": "a_low_priority_number",
                    "enabled": True,
                    "env_key": "SHADOW_A_KEY",
                    "base_url": "https://a.com/v1",
                    "model": "a",
                    "priority": 1,
                },
            ],
        }
    }
    pool = build_provider_pool(cfg)
    assert pool is not None
    status = pool.status()
    # Lower priority number = first
    assert status[0]["name"] == "a_low_priority_number"
    assert status[1]["name"] == "b_high_priority_number"
