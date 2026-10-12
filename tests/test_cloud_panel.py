import sys

import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    pytest.skip("Qt not available", allow_module_level=True)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication(sys.argv[:1])
        except Exception as exc:
            pytest.skip(f"QApplication unavailable: {exc}")
    yield app


@pytest.fixture
def config():
    return {
        "cloud": {
            "enabled": False,
            "fallback_to_local": True,
            "providers": [
                {
                    "name": "groq",
                    "enabled": True,
                    "model": "openai/gpt-oss-120b",
                    "env_key": "SHADOW_GROQ_KEY",
                    "base_url": "https://api.groq.com/openai/v1",
                    "priority": 1,
                },
                {
                    "name": "gemini",
                    "enabled": True,
                    "model": "gemini-2.5-flash",
                    "env_key": "SHADOW_GEMINI_KEY",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                    "priority": 2,
                },
            ],
        }
    }


def test_cloud_panel_constructs(qapp, config):
    from shadow.ui.cloud_panel import CloudPanel

    panel = CloudPanel(config)
    assert panel is not None


def test_enable_checkbox_reflects_config(qapp, config):
    config["cloud"]["enabled"] = True
    from shadow.ui.cloud_panel import CloudPanel

    panel = CloudPanel(config)
    assert panel.enable_cb.isChecked() is True


def test_fallback_checkbox_reflects_config(qapp, config):
    config["cloud"]["fallback_to_local"] = False
    from shadow.ui.cloud_panel import CloudPanel

    panel = CloudPanel(config)
    assert panel.fallback_cb.isChecked() is False


def test_provider_cards_match_config(qapp, config):
    from shadow.ui.cloud_panel import CloudPanel, ProviderCard

    panel = CloudPanel(config)
    cards = panel.findChildren(ProviderCard)
    names = {c.provider_name for c in cards}
    assert names == {"groq", "gemini"}


def test_provider_card_reads_env_var(qapp, config, monkeypatch):
    monkeypatch.setenv("SHADOW_GROQ_KEY", "sk-test-1234567890")
    from shadow.ui.cloud_panel import CloudPanel, ProviderCard

    panel = CloudPanel(config)
    cards = panel.findChildren(ProviderCard)
    groq = next(c for c in cards if c.provider_name == "groq")
    # Key should be pre-populated
    assert groq.key_input.text() == "sk-test-1234567890"


def test_save_key_shows_ready(qapp, config, monkeypatch):
    monkeypatch.delenv("SHADOW_TEST_KEY", raising=False)
    from shadow.ui.cloud_panel import ProviderCard

    entry = {
        "name": "test",
        "enabled": True,
        "model": "m",
        "env_key": "SHADOW_TEST_KEY",
        "base_url": "https://x.com/v1",
        "priority": 1,
    }
    card = ProviderCard(entry, {})
    card.key_input.setText("sk-new-key")
    card._on_save()
    # Status text should now indicate saved
    assert "saved" in card.status_text.text().lower()


def test_remove_key_clears_input(qapp, config, monkeypatch):
    monkeypatch.setenv("SHADOW_TEST_KEY2", "sk-something")
    from shadow.ui.cloud_panel import ProviderCard

    entry = {
        "name": "test2",
        "enabled": True,
        "model": "m",
        "env_key": "SHADOW_TEST_KEY2",
        "base_url": "https://x.com/v1",
        "priority": 1,
    }
    card = ProviderCard(entry, {})
    card._on_remove()
    assert card.key_input.text() == ""
