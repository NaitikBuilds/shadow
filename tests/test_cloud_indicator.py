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


def test_cloud_backend_tracks_last_prompt():
    from shadow.hal.cloud_backend import CloudBackend, ProviderConfig

    cfg = ProviderConfig(
        name="test",
        base_url="https://x.com/v1",
        model="m",
        api_key="key-1234567890",
    )
    backend = CloudBackend(cfg)
    assert backend.last_prompt == ""
    assert backend.last_prompt_at == 0.0
    backend.close()


def test_hybrid_backend_info_has_last_prompt():
    from shadow.hal.hybrid_backend import HybridBackend

    class Fake:
        def generate_stream(self, prompt, **kwargs):
            yield "x"

        def embed(self, text):
            return [0.0] * 384

        @property
        def info(self):
            return {"backend": "fake"}

    class FakeHealth:
        def is_online(self):
            return False

    hybrid = HybridBackend(Fake(), Fake(), health=FakeHealth())
    info = hybrid.info
    assert "last_prompt" in info
    assert "last_prompt_at" in info


def test_hybrid_backend_returns_empty_prompt_when_offline():
    from shadow.hal.hybrid_backend import HybridBackend

    class Fake:
        def generate_stream(self, prompt, **kwargs):
            yield "x"

        def embed(self, text):
            return [0.0] * 384

        @property
        def info(self):
            return {"backend": "fake"}

    class FakeHealth:
        def is_online(self):
            return False

    hybrid = HybridBackend(Fake(), Fake(), health=FakeHealth())
    assert hybrid.last_prompt == ""
