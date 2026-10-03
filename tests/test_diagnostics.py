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
def store(tmp_path):
    from shadow.memory import MemoryStore

    s = MemoryStore(str(tmp_path / "diag.db"))
    yield s
    s.close()


class FakeBackend:
    @property
    def info(self):
        return {
            "backend": "cpu",
            "model": "fake-model",
            "threads": 4,
            "embedder": "none",
        }


def test_diagnostics_constructs(qapp, store):
    from shadow.ui.diagnostics_panel import DiagnosticsPanel

    panel = DiagnosticsPanel(FakeBackend(), store, {})
    assert panel is not None


def test_report_contains_backend(qapp, store):
    from shadow.ui.diagnostics_panel import DiagnosticsPanel

    panel = DiagnosticsPanel(FakeBackend(), store, {})
    report = panel._build_report()
    assert "=== Backend ===" in report
    assert "cpu" in report
    assert "fake-model" in report


def test_report_contains_database_section(qapp, store):
    from shadow.ui.diagnostics_panel import DiagnosticsPanel

    panel = DiagnosticsPanel(FakeBackend(), store, {})
    report = panel._build_report()
    assert "=== Database ===" in report
    assert "observations" in report
    assert "schema version" in report


def test_report_contains_network_section(qapp, store):
    from shadow.ui.diagnostics_panel import DiagnosticsPanel

    panel = DiagnosticsPanel(FakeBackend(), store, {})
    report = panel._build_report()
    assert "isolated" in report


def test_report_contains_retention_section(qapp, store):
    from shadow.ui.diagnostics_panel import DiagnosticsPanel

    panel = DiagnosticsPanel(FakeBackend(), store, {})
    report = panel._build_report()
    assert "=== Retention ===" in report


def test_report_contains_errors_section(qapp, store):
    from shadow.ui.diagnostics_panel import DiagnosticsPanel

    panel = DiagnosticsPanel(FakeBackend(), store, {})
    report = panel._build_report()
    assert "Recent Errors" in report
